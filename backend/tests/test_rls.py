"""Row-Level Security: the second barrier behind the ACL filter in the query itself."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from macedon.db.identity import Identity, apply_identity

ALICE = Identity("alice", groups=("engineering",))
BOB = Identity("bob", groups=("legal",))
CAROL = Identity("carol", groups=("engineering",))
ADMIN = Identity("root", is_admin=True)
ANONYMOUS = Identity("")

ZERO_EMBEDDING = "[" + ",".join(["0"] * 3072) + "]"


async def make_document(
    engine: AsyncEngine,
    *,
    owner: str = "alice",
    acl_users: list[str] | None = None,
    acl_groups: list[str] | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a document with one active version and one chunk, as the trusted worker would."""
    document_id, version_id = uuid.uuid4(), uuid.uuid4()
    acl_users = acl_users if acl_users is not None else [owner]
    acl_groups = acl_groups or []
    async with engine.begin() as conn:
        await apply_identity(conn, ADMIN)
        await conn.execute(
            text(
                "INSERT INTO documents (id, name, doc_type, owner_id, acl_users, acl_groups) "
                "VALUES (:id, 'doc', 'pdf', :owner, :users, :groups)"
            ),
            {"id": document_id, "owner": owner, "users": acl_users, "groups": acl_groups},
        )
        await conn.execute(
            text(
                "INSERT INTO document_versions "
                "(id, document_id, number, file_hash, storage_key, status, author_id) "
                "VALUES (:id, :doc, 1, 'h', 'k', 'active', :owner)"
            ),
            {"id": version_id, "doc": document_id, "owner": owner},
        )
        await conn.execute(
            text(
                "INSERT INTO chunks (version_id, document_id, section_id, position, path, "
                "content, content_hash, embedding, embedding_model, acl_users, acl_groups) "
                "VALUES (:version, :doc, 's1', 0, 'p', 'c', 'h', "
                "CAST(CAST(:emb AS text) AS halfvec), 'm', :users, :groups)"
            ),
            {
                "version": version_id,
                "doc": document_id,
                "emb": ZERO_EMBEDDING,
                "users": acl_users,
                "groups": acl_groups,
            },
        )
    return document_id, version_id


async def visible(engine: AsyncEngine, identity: Identity, table: str) -> int:
    async with engine.begin() as conn:
        await apply_identity(conn, identity)
        result = await conn.execute(text(f"SELECT count(*) FROM {table}"))  # noqa: S608
        return int(result.scalar_one())


@pytest.mark.parametrize("table", ["documents", "document_versions", "chunks"])
async def test_only_users_in_the_acl_can_read(app_engine: AsyncEngine, table: str) -> None:
    await make_document(app_engine, owner="alice")

    assert await visible(app_engine, ALICE, table) == 1
    assert await visible(app_engine, BOB, table) == 0


async def test_group_in_the_acl_grants_read(app_engine: AsyncEngine) -> None:
    await make_document(app_engine, owner="alice", acl_groups=["engineering"])

    assert await visible(app_engine, CAROL, "chunks") == 1  # via group, not named in acl_users
    assert await visible(app_engine, BOB, "chunks") == 0


async def test_admin_reads_everything(app_engine: AsyncEngine) -> None:
    await make_document(app_engine, owner="alice")

    assert await visible(app_engine, ADMIN, "chunks") == 1


async def test_missing_identity_reads_nothing(app_engine: AsyncEngine) -> None:
    await make_document(app_engine, owner="alice")

    assert await visible(app_engine, ANONYMOUS, "documents") == 0
    assert await visible(app_engine, ANONYMOUS, "chunks") == 0
    async with app_engine.begin() as conn:  # no identity set at all
        result = await conn.execute(text("SELECT count(*) FROM chunks"))
        assert result.scalar_one() == 0


async def test_non_admin_cannot_write_chunks(app_engine: AsyncEngine) -> None:
    _, version_id = await make_document(app_engine, owner="alice")

    async with app_engine.begin() as conn:
        await apply_identity(conn, ALICE)
        with pytest.raises(DBAPIError):  # the owner may re-share (ACL columns), never rewrite
            await conn.execute(
                text("UPDATE chunks SET content = 'tampered' WHERE version_id = :v"),
                {"v": version_id},
            )

    async with app_engine.begin() as conn:
        await apply_identity(conn, ALICE)
        with pytest.raises(DBAPIError):
            await conn.execute(
                text(
                    "INSERT INTO chunks (version_id, document_id, section_id, position, path, "
                    "content, content_hash, embedding, embedding_model) "
                    "SELECT version_id, document_id, 's', 9, 'p', 'x', 'h', embedding, 'm' "
                    "FROM chunks"
                )
            )

    async with app_engine.begin() as conn:
        await apply_identity(conn, ALICE)
        result = await conn.execute(text("SELECT content FROM chunks"))
        assert result.scalar_one() == "c"


async def test_only_the_owner_can_change_the_acl_on_chunks(app_engine: AsyncEngine) -> None:
    document_id, _ = await make_document(
        app_engine, owner="alice", acl_users=["alice", "bob"]
    )  # bob can read the chunks, but does not own the document
    update = text("UPDATE chunks SET acl_groups = ARRAY['legal'] WHERE document_id = :d")

    async with app_engine.begin() as conn:
        await apply_identity(conn, BOB)
        assert (await conn.execute(update, {"d": document_id})).rowcount == 0

    async with app_engine.begin() as conn:
        await apply_identity(conn, ALICE)
        assert (await conn.execute(update, {"d": document_id})).rowcount == 1


async def test_non_owner_cannot_add_a_version(app_engine: AsyncEngine) -> None:
    document_id, _ = await make_document(
        app_engine, owner="alice", acl_users=["alice", "bob"]
    )  # bob can read, but does not own it

    async with app_engine.begin() as conn:
        await apply_identity(conn, BOB)
        with pytest.raises(DBAPIError):
            await conn.execute(
                text(
                    "INSERT INTO document_versions "
                    "(document_id, number, file_hash, storage_key, status, author_id) "
                    "VALUES (:doc, 2, 'h2', 'k2', 'processing', 'bob')"
                ),
                {"doc": document_id},
            )


async def test_non_owner_cannot_archive_a_document(app_engine: AsyncEngine) -> None:
    document_id, _ = await make_document(app_engine, owner="alice", acl_users=["alice", "bob"])

    async with app_engine.begin() as conn:
        await apply_identity(conn, BOB)
        result = await conn.execute(
            text("UPDATE documents SET archived_at = now() WHERE id = :id"), {"id": document_id}
        )
        assert result.rowcount == 0  # the UPDATE policy hides the row from bob's writes


async def test_only_one_active_version_per_document(app_engine: AsyncEngine) -> None:
    document_id, _ = await make_document(app_engine, owner="alice")

    async with app_engine.begin() as conn:
        await apply_identity(conn, ALICE)
        with pytest.raises(DBAPIError):
            await conn.execute(
                text(
                    "INSERT INTO document_versions "
                    "(document_id, number, file_hash, storage_key, status, author_id) "
                    "VALUES (:doc, 2, 'h2', 'k2', 'active', 'alice')"
                ),
                {"doc": document_id},
            )


async def test_documents_cannot_be_hard_deleted(app_engine: AsyncEngine) -> None:
    document_id, _ = await make_document(app_engine, owner="alice")

    async with app_engine.begin() as conn:
        await apply_identity(conn, ADMIN)
        with pytest.raises(DBAPIError):
            await conn.execute(text("DELETE FROM documents WHERE id = :id"), {"id": document_id})


async def test_audit_log_is_append_only_and_admin_readable(app_engine: AsyncEngine) -> None:
    async with app_engine.begin() as conn:
        await apply_identity(conn, ALICE)
        await conn.execute(
            text("INSERT INTO audit_log (actor_id, action) VALUES ('alice', 'upload')")
        )

    async with app_engine.begin() as conn:  # cannot forge another actor
        await apply_identity(conn, ALICE)
        with pytest.raises(DBAPIError):
            await conn.execute(
                text("INSERT INTO audit_log (actor_id, action) VALUES ('bob', 'upload')")
            )

    assert await visible(app_engine, ALICE, "audit_log") == 0  # not an admin
    assert await visible(app_engine, ADMIN, "audit_log") == 1

    async with app_engine.begin() as conn:
        await apply_identity(conn, ADMIN)
        with pytest.raises(DBAPIError):  # no UPDATE privilege, even for admins
            await conn.execute(text("UPDATE audit_log SET action = 'x'"))
