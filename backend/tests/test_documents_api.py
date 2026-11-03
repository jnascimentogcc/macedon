import io
import uuid
import zipfile
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from macedon.auth import get_identity
from macedon.config import Settings, get_settings
from macedon.db.identity import Identity
from macedon.db.session import get_engine
from macedon.documents.queue import get_job_queue
from macedon.documents.storage import get_object_store
from macedon.main import create_app

ALICE = Identity("alice", groups=("engineering",))
BOB = Identity("bob", groups=("legal",))
ADMIN = Identity("root", is_admin=True)

PDF = b"%PDF-1.7\n%fake pdf body\n"
PDF_2 = b"%PDF-1.7\n%another body\n"


def make_docx() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
    return buffer.getvalue()


class FakeStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes) -> None:
        self.objects[key] = data

    async def get(self, key: str) -> bytes:
        return self.objects[key]


class FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[uuid.UUID] = []

    async def enqueue_ingestion(self, version_id: uuid.UUID) -> None:
        self.enqueued.append(version_id)


class Api:
    """A test client whose caller can be switched between requests."""

    def __init__(self, client: AsyncClient, current: list[Identity]) -> None:
        self._client = client
        self._current = current
        self.store = FakeStore()
        self.queue = FakeQueue()

    def as_user(self, identity: Identity) -> "Api":
        self._current[0] = identity
        return self

    async def upload(self, data: bytes = PDF, *, filename: str = "a.pdf", **form: Any) -> Any:
        return await self._client.post("/documents", files={"file": (filename, data)}, data=form)

    async def upload_version(self, document_id: str, data: bytes) -> Any:
        return await self._client.post(
            f"/documents/{document_id}/versions", files={"file": ("v.pdf", data)}
        )

    async def get(self, url: str) -> Any:
        return await self._client.get(url)

    async def post(self, url: str) -> Any:
        return await self._client.post(url)

    async def delete(self, url: str) -> Any:
        return await self._client.delete(url)


@pytest.fixture
async def api(app_engine: AsyncEngine) -> AsyncIterator[Api]:
    app = create_app()
    current = [ALICE]
    fake_store, fake_queue = FakeStore(), FakeQueue()
    app.dependency_overrides[get_identity] = lambda: current[0]
    app.dependency_overrides[get_engine] = lambda: app_engine
    app.dependency_overrides[get_object_store] = lambda: fake_store
    app.dependency_overrides[get_job_queue] = lambda: fake_queue
    app.dependency_overrides[get_settings] = lambda: Settings(
        max_upload_bytes=1024, known_groups=["engineering", "legal"]
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        instance = Api(client, current)
        instance.store, instance.queue = fake_store, fake_queue
        yield instance


async def set_status(engine: AsyncEngine, document_id: str, number: int, status: str) -> None:
    """Stand in for the ingestion worker, which owns these transitions."""
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE document_versions SET status = :s "
                "WHERE document_id = CAST(:d AS uuid) AND number = :n"
            ),
            {"s": status, "d": document_id, "n": number},
        )


async def audit_actions(owner_engine: AsyncEngine) -> list[str]:
    async with owner_engine.connect() as conn:
        result = await conn.execute(text("SELECT action FROM audit_log ORDER BY id"))
        return [row[0] for row in result]


# ---- upload ----


async def test_upload_creates_version_one_and_enqueues_ingestion(
    api: Api, owner_engine: AsyncEngine
) -> None:
    response = await api.upload(name="Contract", tags=["legal"])

    assert response.status_code == 202
    body = response.json()
    assert body["document"]["name"] == "Contract"
    assert body["document"]["doc_type"] == "pdf"
    assert body["document"]["owner_id"] == "alice"
    assert body["document"]["acl_users"] == ["alice"]
    assert body["version"]["number"] == 1
    assert body["version"]["status"] == "processing"
    assert body["document"]["active_version"] is None  # nothing answers until it is indexed
    assert api.queue.enqueued == [uuid.UUID(body["version"]["id"])]
    assert list(api.store.objects.values()) == [PDF]
    assert await audit_actions(owner_engine) == ["upload"]


async def test_upload_adds_extra_acl_entries_but_keeps_the_owner(api: Api) -> None:
    response = await api.upload(acl_users=["bob"], acl_groups=["legal"])

    document = response.json()["document"]
    assert document["acl_users"] == ["alice", "bob"]
    assert document["acl_groups"] == ["legal"]


async def test_upload_rejects_groups_nobody_knows(api: Api) -> None:
    response = await api.upload(acl_groups=["legl"])

    assert response.status_code == 422
    assert "legl" in response.json()["detail"]
    assert api.queue.enqueued == []


async def test_groups_lists_the_configured_ones_and_the_callers_own(api: Api) -> None:
    api.as_user(Identity(user_id="carol", groups=("sales",)))

    response = await api.get("/groups")

    assert response.json() == ["engineering", "legal", "sales"]


@pytest.mark.parametrize(
    ("data", "expected_type"), [(PDF, "pdf"), (make_docx(), "docx"), (b"plain text\n", "txt")]
)
async def test_upload_detects_the_type_from_the_bytes(
    api: Api, data: bytes, expected_type: str
) -> None:
    response = await api.upload(data, filename="misleading.bin")

    assert response.status_code == 202
    assert response.json()["document"]["doc_type"] == expected_type


@pytest.mark.parametrize(
    "data",
    [b"", b"\x00\x01\x02binary", b"\xff\xfe invalid utf8", b"PK\x03\x04 not a real zip"],
    ids=["empty", "binary", "invalid-utf8", "fake-zip"],
)
async def test_upload_rejects_unsupported_content(api: Api, data: bytes) -> None:
    response = await api.upload(data)

    assert response.status_code == 415
    assert api.queue.enqueued == []
    assert api.store.objects == {}


async def test_upload_rejects_a_file_over_the_size_limit(api: Api) -> None:
    response = await api.upload(b"%PDF-" + b"x" * 2048)

    assert response.status_code == 413
    assert api.store.objects == {}


async def test_upload_requires_authentication(app_engine: AsyncEngine) -> None:
    app = create_app()
    app.dependency_overrides[get_engine] = lambda: app_engine
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/documents", files={"file": ("a.pdf", PDF)})

    assert response.status_code == 401


# ---- reading ----


async def test_a_user_outside_the_acl_gets_404(api: Api) -> None:
    document_id = (await api.upload()).json()["document"]["id"]

    assert (await api.as_user(BOB).get(f"/documents/{document_id}")).status_code == 404
    assert (await api.get(f"/documents/{document_id}/versions")).status_code == 404
    assert (await api.get(f"/documents/{uuid.uuid4()}")).status_code == 404


async def test_a_user_in_the_acl_can_read(api: Api) -> None:
    document_id = (await api.upload(acl_groups=["legal"])).json()["document"]["id"]

    response = await api.as_user(BOB).get(f"/documents/{document_id}")

    assert response.status_code == 200
    assert response.json()["latest_version"]["number"] == 1


# ---- versions ----


async def test_new_version_gets_the_next_number(api: Api) -> None:
    document_id = (await api.upload()).json()["document"]["id"]

    response = await api.upload_version(document_id, PDF_2)

    assert response.status_code == 202
    assert response.json()["version"]["number"] == 2
    listing = (await api.get(f"/documents/{document_id}/versions")).json()
    assert [v["number"] for v in listing] == [2, 1]
    assert len(api.queue.enqueued) == 2


async def test_resending_the_same_file_is_not_reprocessed(api: Api) -> None:
    document_id = (await api.upload()).json()["document"]["id"]

    response = await api.upload_version(document_id, PDF)

    assert response.status_code == 202
    assert response.json()["duplicate"] is True
    assert response.json()["version"]["number"] == 1
    assert len(api.queue.enqueued) == 1
    assert len((await api.get(f"/documents/{document_id}/versions")).json()) == 1


async def test_a_new_version_must_keep_the_document_type(api: Api) -> None:
    document_id = (await api.upload()).json()["document"]["id"]

    response = await api.upload_version(document_id, b"now it is text")

    assert response.status_code == 422


async def test_only_the_owner_can_add_versions(api: Api) -> None:
    document_id = (await api.upload(acl_users=["bob"])).json()["document"]["id"]

    response = await api.as_user(BOB).upload_version(document_id, PDF_2)

    assert response.status_code == 403
    assert len(api.queue.enqueued) == 1


async def test_an_admin_can_add_versions_to_any_document(api: Api) -> None:
    document_id = (await api.upload()).json()["document"]["id"]

    response = await api.as_user(ADMIN).upload_version(document_id, PDF_2)

    assert response.status_code == 202


# ---- activation and rollback ----


async def test_activating_an_older_version_is_a_rollback(
    api: Api, owner_engine: AsyncEngine
) -> None:
    document_id = (await api.upload()).json()["document"]["id"]
    await api.upload_version(document_id, PDF_2)
    await set_status(owner_engine, document_id, 1, "archived")
    await set_status(owner_engine, document_id, 2, "active")

    response = await api.post(f"/documents/{document_id}/versions/1/activate")

    assert response.status_code == 200
    assert response.json()["status"] == "active"
    versions = {
        v["number"]: v["status"]
        for v in (await api.get(f"/documents/{document_id}/versions")).json()
    }
    assert versions == {1: "active", 2: "archived"}


async def test_activating_the_active_version_changes_nothing(
    api: Api, owner_engine: AsyncEngine
) -> None:
    document_id = (await api.upload()).json()["document"]["id"]
    await set_status(owner_engine, document_id, 1, "active")

    response = await api.post(f"/documents/{document_id}/versions/1/activate")

    assert response.status_code == 200
    assert response.json()["status"] == "active"


@pytest.mark.parametrize("status_value", ["processing", "failed"])
async def test_a_version_that_is_not_indexed_cannot_be_activated(
    api: Api, owner_engine: AsyncEngine, status_value: str
) -> None:
    document_id = (await api.upload()).json()["document"]["id"]
    await api.upload_version(document_id, PDF_2)
    await set_status(owner_engine, document_id, 1, "active")
    await set_status(owner_engine, document_id, 2, status_value)

    response = await api.post(f"/documents/{document_id}/versions/2/activate")

    assert response.status_code == 409
    versions = {
        v["number"]: v["status"]
        for v in (await api.get(f"/documents/{document_id}/versions")).json()
    }
    assert versions[1] == "active"  # the previous version keeps answering


async def test_activating_a_missing_version_is_404(api: Api) -> None:
    document_id = (await api.upload()).json()["document"]["id"]

    assert (await api.post(f"/documents/{document_id}/versions/9/activate")).status_code == 404


async def test_only_the_owner_can_activate(api: Api, owner_engine: AsyncEngine) -> None:
    document_id = (await api.upload(acl_users=["bob"])).json()["document"]["id"]
    await set_status(owner_engine, document_id, 1, "archived")

    response = await api.as_user(BOB).post(f"/documents/{document_id}/versions/1/activate")

    assert response.status_code == 403


# ---- archiving ----


async def test_delete_archives_without_erasing(api: Api, owner_engine: AsyncEngine) -> None:
    document_id = (await api.upload()).json()["document"]["id"]
    await set_status(owner_engine, document_id, 1, "active")

    response = await api.delete(f"/documents/{document_id}")

    assert response.status_code == 204
    document = (await api.get(f"/documents/{document_id}")).json()
    assert document["archived_at"] is not None
    assert document["active_version"] is None
    assert document["latest_version"]["status"] == "archived"
    assert await audit_actions(owner_engine) == ["upload", "archive"]


async def test_only_the_owner_can_archive(api: Api) -> None:
    document_id = (await api.upload(acl_users=["bob"])).json()["document"]["id"]

    assert (await api.as_user(BOB).delete(f"/documents/{document_id}")).status_code == 403


async def test_an_archived_document_accepts_no_new_versions(api: Api) -> None:
    document_id = (await api.upload()).json()["document"]["id"]
    await api.delete(f"/documents/{document_id}")

    assert (await api.upload_version(document_id, PDF_2)).status_code == 409


async def test_a_failed_request_leaves_no_trace(
    api: Api, owner_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing_put(key: str, data: bytes) -> None:
        raise RuntimeError("object store is down")

    monkeypatch.setattr(api.store, "put", failing_put)

    with pytest.raises(RuntimeError):
        await api.upload()

    async with owner_engine.connect() as conn:
        count = (await conn.execute(text("SELECT count(*) FROM documents"))).scalar_one()
    assert count == 0
    assert api.queue.enqueued == []


def test_helper_types() -> None:
    check: Callable[[], bytes] = make_docx
    assert check().startswith(b"PK")


# ---- listing ----


async def test_listing_returns_only_what_the_caller_can_read(api: Api) -> None:
    await api.upload(name="Alice only")
    await api.upload(PDF_2, name="Shared with legal", acl_groups=["legal"])
    await api.as_user(BOB).upload(b"bob text", name="Bob's own")

    alice = (await api.as_user(ALICE).get("/documents")).json()
    bob = (await api.as_user(BOB).get("/documents")).json()

    assert sorted(d["name"] for d in alice["items"]) == ["Alice only", "Shared with legal"]
    assert alice["total"] == 2
    assert sorted(d["name"] for d in bob["items"]) == ["Bob's own", "Shared with legal"]


async def test_listing_shows_latest_and_active_versions(
    api: Api, owner_engine: AsyncEngine
) -> None:
    document_id = (await api.upload(name="Doc")).json()["document"]["id"]
    await api.upload_version(document_id, PDF_2)
    await set_status(owner_engine, document_id, 1, "active")

    [item] = (await api.get("/documents")).json()["items"]

    assert item["latest_version"]["number"] == 2
    assert item["latest_version"]["status"] == "processing"
    assert item["active_version"]["number"] == 1


async def test_listing_hides_archived_documents_unless_asked(api: Api) -> None:
    document_id = (await api.upload(name="Old")).json()["document"]["id"]
    await api.upload(PDF_2, name="Current")
    await api.delete(f"/documents/{document_id}")

    default = (await api.get("/documents")).json()
    everything = (await api.get("/documents?include_archived=true")).json()

    assert [d["name"] for d in default["items"]] == ["Current"]
    assert default["total"] == 1
    assert {d["name"] for d in everything["items"]} == {"Old", "Current"}


async def test_listing_is_paginated_newest_first(api: Api) -> None:
    for number in range(5):
        await api.upload(PDF + bytes([number]), name=f"Doc {number}")

    first = (await api.get("/documents?limit=2")).json()
    second = (await api.get("/documents?limit=2&offset=2")).json()
    last = (await api.get("/documents?limit=2&offset=4")).json()

    assert [d["name"] for d in first["items"]] == ["Doc 4", "Doc 3"]
    assert [d["name"] for d in second["items"]] == ["Doc 2", "Doc 1"]
    assert [d["name"] for d in last["items"]] == ["Doc 0"]
    assert first["total"] == second["total"] == last["total"] == 5


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1"])
async def test_listing_rejects_out_of_range_pagination(api: Api, query: str) -> None:
    assert (await api.get(f"/documents?{query}")).status_code == 422


async def test_listing_an_empty_account(api: Api) -> None:
    page = (await api.as_user(BOB).get("/documents")).json()

    assert page == {"items": [], "total": 0, "limit": 50, "offset": 0}
