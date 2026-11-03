import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from macedon.db.identity import Identity, apply_identity
from macedon.ingestion.embeddings import EmbeddingError, TransientEmbeddingError
from macedon.ingestion.extract import Block, extract_blocks
from macedon.ingestion.pipeline import IngestionDeps, TransientIngestionError, ingest_version

MODEL = "test-embedding-model"
DIMENSIONS = 3072

TEXT_V1 = b"The notice period is thirty days.\n\nRefunds take five days."
TEXT_V2 = b"The notice period is sixty days.\n\nRefunds take five days."


class FakeStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes) -> None:
        self.objects[key] = data

    async def get(self, key: str) -> bytes:
        return self.objects[key]


class FakeEmbedder:
    model = MODEL
    dimensions = DIMENSIONS

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.error: Exception | None = None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self.error is not None:
            raise self.error
        self.calls.append(list(texts))
        return [[float(len(t) % 9 + 1)] + [0.0] * (DIMENSIONS - 1) for t in texts]


async def in_process_extractor(data: bytes, doc_type: str) -> list[Block]:
    return extract_blocks(data, doc_type)


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def deps(app_engine: AsyncEngine, store: FakeStore, embedder: FakeEmbedder) -> IngestionDeps:
    return IngestionDeps(app_engine, store, embedder, extractor=in_process_extractor)


async def create_version(
    owner_engine: AsyncEngine,
    store: FakeStore,
    data: bytes,
    *,
    document_id: uuid.UUID | None = None,
    number: int = 1,
    status: str = "processing",
    acl_users: tuple[str, ...] = ("alice",),
    acl_groups: tuple[str, ...] = (),
    archived: bool = False,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Insert a document (the first time) and a version, as the upload endpoint would."""
    new_document = document_id is None
    document_id = document_id or uuid.uuid4()
    version_id = uuid.uuid4()
    key = f"documents/{document_id}/versions/{number}"
    store.objects[key] = data
    async with owner_engine.begin() as conn:
        if new_document:
            await conn.execute(
                text(
                    "INSERT INTO documents "
                    "(id, name, doc_type, owner_id, acl_users, acl_groups, archived_at) "
                    "VALUES (:id, 'Handbook', 'txt', 'alice', :users, :groups, "
                    "CASE WHEN :archived THEN now() END)"
                ),
                {
                    "id": document_id,
                    "users": list(acl_users),
                    "groups": list(acl_groups),
                    "archived": archived,
                },
            )
        await conn.execute(
            text(
                "INSERT INTO document_versions "
                "(id, document_id, number, file_hash, storage_key, status, author_id) "
                "VALUES (:id, :doc, :n, :hash, :key, :status, 'alice')"
            ),
            {
                "id": version_id,
                "doc": document_id,
                "n": number,
                "hash": uuid.uuid4().hex * 2,
                "key": key,
                "status": status,
            },
        )
    return document_id, version_id


async def statuses(engine: AsyncEngine, document_id: uuid.UUID) -> dict[int, str]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT number, status FROM document_versions WHERE document_id = :d"),
            {"d": document_id},
        )
        return {number: status for number, status in rows}


async def chunk_rows(engine: AsyncEngine, version_id: uuid.UUID) -> list[tuple[str, str, int]]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT path, content, position FROM chunks WHERE version_id = :v ORDER BY position"
            ),
            {"v": version_id},
        )
        return [(r[0], r[1], r[2]) for r in rows]


async def test_ingestion_indexes_chunks_and_activates_the_version(
    owner_engine: AsyncEngine, deps: IngestionDeps, store: FakeStore, embedder: FakeEmbedder
) -> None:
    document_id, version_id = await create_version(
        owner_engine, store, TEXT_V1, acl_users=("alice", "bob"), acl_groups=("legal",)
    )

    await ingest_version(version_id, deps)

    assert await statuses(owner_engine, document_id) == {1: "active"}
    body = "The notice period is thirty days.\n\nRefunds take five days."
    assert await chunk_rows(owner_engine, version_id) == [("Handbook", body, 0)]
    async with owner_engine.connect() as conn:
        chunk = (
            await conn.execute(
                text("SELECT acl_users, acl_groups, embedding_model FROM chunks LIMIT 1")
            )
        ).one()
        audit = (await conn.execute(text("SELECT action, details FROM audit_log"))).all()
    assert list(chunk) == [["alice", "bob"], ["legal"], MODEL]  # ACL copied from the document
    assert [entry[0] for entry in audit] == ["ingest"]
    assert audit[0][1] == {"chunks": 1, "embeddings_reused": 0, "activated": True}
    assert embedder.calls == [[f"Handbook\n\n{body}"]]


async def test_chunks_are_visible_only_to_the_acl_through_rls(
    owner_engine: AsyncEngine, app_engine: AsyncEngine, deps: IngestionDeps, store: FakeStore
) -> None:
    _, version_id = await create_version(owner_engine, store, TEXT_V1, acl_users=("alice",))
    await ingest_version(version_id, deps)

    async def count(identity: Identity) -> int:
        async with app_engine.begin() as conn:
            await apply_identity(conn, identity)
            return int((await conn.execute(text("SELECT count(*) FROM chunks"))).scalar_one())

    assert await count(Identity("alice")) == 1
    assert await count(Identity("bob")) == 0


async def test_a_new_version_replaces_the_active_one_atomically(
    owner_engine: AsyncEngine, deps: IngestionDeps, store: FakeStore
) -> None:
    document_id, v1 = await create_version(owner_engine, store, TEXT_V1)
    await ingest_version(v1, deps)
    _, v2 = await create_version(owner_engine, store, TEXT_V2, document_id=document_id, number=2)
    assert await statuses(owner_engine, document_id) == {1: "active", 2: "processing"}

    await ingest_version(v2, deps)

    assert await statuses(owner_engine, document_id) == {1: "archived", 2: "active"}
    assert len(await chunk_rows(owner_engine, v1)) == 1  # the old chunks stay, for rollback


async def test_identical_text_reuses_the_existing_embedding(
    owner_engine: AsyncEngine, deps: IngestionDeps, store: FakeStore, embedder: FakeEmbedder
) -> None:
    document_id, v1 = await create_version(owner_engine, store, TEXT_V1)
    await ingest_version(v1, deps)
    _, v2 = await create_version(owner_engine, store, TEXT_V1, document_id=document_id, number=2)
    embedder.calls.clear()

    await ingest_version(v2, deps)

    assert embedder.calls == []  # nothing new to embed
    assert len(await chunk_rows(owner_engine, v2)) == 1
    async with owner_engine.connect() as conn:
        distinct = (
            await conn.execute(text("SELECT count(DISTINCT embedding::text) FROM chunks"))
        ).scalar_one()
        details = (
            await conn.execute(text("SELECT details FROM audit_log ORDER BY id DESC LIMIT 1"))
        ).scalar_one()
    assert distinct == 1
    assert details["embeddings_reused"] == 1


async def test_a_version_older_than_the_active_one_is_shelved_not_activated(
    owner_engine: AsyncEngine, deps: IngestionDeps, store: FakeStore
) -> None:
    document_id, v1 = await create_version(owner_engine, store, TEXT_V1)
    await create_version(
        owner_engine, store, TEXT_V2, document_id=document_id, number=2, status="active"
    )

    await ingest_version(v1, deps)

    assert await statuses(owner_engine, document_id) == {1: "archived", 2: "active"}
    assert len(await chunk_rows(owner_engine, v1)) == 1  # indexed, so a rollback can use it


async def test_an_unreadable_file_marks_the_version_failed(
    owner_engine: AsyncEngine, deps: IngestionDeps, store: FakeStore
) -> None:
    document_id, v1 = await create_version(owner_engine, store, TEXT_V1)
    await ingest_version(v1, deps)
    _, v2 = await create_version(
        owner_engine, store, b"   \n\n  ", document_id=document_id, number=2
    )

    await ingest_version(v2, deps)

    # The previous version keeps answering.
    assert await statuses(owner_engine, document_id) == {1: "active", 2: "failed"}
    assert await chunk_rows(owner_engine, v2) == []
    async with owner_engine.connect() as conn:
        error = (
            await conn.execute(text("SELECT error FROM document_versions WHERE id = :v"), {"v": v2})
        ).scalar_one()
    assert "no text" in error


async def test_a_permanent_embedding_error_marks_the_version_failed(
    owner_engine: AsyncEngine, deps: IngestionDeps, store: FakeStore, embedder: FakeEmbedder
) -> None:
    document_id, version_id = await create_version(owner_engine, store, TEXT_V1)
    embedder.error = EmbeddingError("the provider answered 401")

    await ingest_version(version_id, deps)

    assert await statuses(owner_engine, document_id) == {1: "failed"}


async def test_a_temporary_embedding_error_leaves_the_version_for_a_retry(
    owner_engine: AsyncEngine, deps: IngestionDeps, store: FakeStore, embedder: FakeEmbedder
) -> None:
    document_id, version_id = await create_version(owner_engine, store, TEXT_V1)
    embedder.error = TransientEmbeddingError("the provider answered 503")

    with pytest.raises(TransientIngestionError):
        await ingest_version(version_id, deps)

    assert await statuses(owner_engine, document_id) == {1: "processing"}
    embedder.error = None
    await ingest_version(version_id, deps)  # the retry succeeds
    assert await statuses(owner_engine, document_id) == {1: "active"}


async def test_an_archived_document_is_not_indexed(
    owner_engine: AsyncEngine, deps: IngestionDeps, store: FakeStore
) -> None:
    document_id, version_id = await create_version(owner_engine, store, TEXT_V1, archived=True)

    await ingest_version(version_id, deps)

    assert await statuses(owner_engine, document_id) == {1: "failed"}
    assert await chunk_rows(owner_engine, version_id) == []


async def test_ingesting_twice_is_harmless(
    owner_engine: AsyncEngine, deps: IngestionDeps, store: FakeStore, embedder: FakeEmbedder
) -> None:
    document_id, version_id = await create_version(owner_engine, store, TEXT_V1)
    await ingest_version(version_id, deps)
    embedder.calls.clear()

    await ingest_version(version_id, deps)

    assert embedder.calls == []
    assert await statuses(owner_engine, document_id) == {1: "active"}
    assert len(await chunk_rows(owner_engine, version_id)) == 1


async def test_unknown_version_is_ignored(deps: IngestionDeps, owner_engine: AsyncEngine) -> None:
    await ingest_version(uuid.uuid4(), deps)


# ---- recovery of lost jobs ----


async def backdate(engine: AsyncEngine, version_id: uuid.UUID, minutes: int) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE document_versions SET created_at = now() - make_interval(mins => :m) "
                "WHERE id = :v"
            ),
            {"m": minutes, "v": version_id},
        )


async def test_only_old_processing_versions_count_as_stale(
    owner_engine: AsyncEngine, app_engine: AsyncEngine, store: FakeStore
) -> None:
    from datetime import timedelta

    from macedon.ingestion.pipeline import find_stale_versions

    _, old = await create_version(owner_engine, store, TEXT_V1)
    _, fresh = await create_version(owner_engine, store, TEXT_V1)
    _, done = await create_version(owner_engine, store, TEXT_V1, status="active")
    _, failed = await create_version(owner_engine, store, TEXT_V1, status="failed")
    for version_id in (old, done, failed):
        await backdate(owner_engine, version_id, 60)

    stale = await find_stale_versions(app_engine, timedelta(minutes=15))

    assert stale == [old]
    assert fresh not in stale


async def test_the_sweep_requeues_stale_versions_with_a_deduplicating_job_id(
    owner_engine: AsyncEngine, app_engine: AsyncEngine, store: FakeStore
) -> None:
    from macedon.worker import requeue_stale

    class FakeRedis:
        def __init__(self) -> None:
            self.jobs: list[tuple[str, str, str]] = []

        async def enqueue_job(self, function: str, version_id: str, _job_id: str) -> None:
            self.jobs.append((function, version_id, _job_id))

    _, lost = await create_version(owner_engine, store, TEXT_V1)
    await backdate(owner_engine, lost, 60)
    redis = FakeRedis()

    count = await requeue_stale({"engine": app_engine, "redis": redis})

    assert count == 1
    assert redis.jobs == [("ingest_version", str(lost), f"ingest:{lost}")]
