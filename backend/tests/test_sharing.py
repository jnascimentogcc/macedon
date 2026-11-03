"""Changing the groups a document is shared with, on the document and on every chunk copy."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from test_query import FakeEmbedder, FakeLLM, seed

from macedon.auth import get_identity
from macedon.config import Settings, get_settings
from macedon.db.identity import Identity
from macedon.db.session import get_engine
from macedon.documents.queue import get_job_queue
from macedon.documents.storage import get_object_store
from macedon.main import create_app
from macedon.query.router import get_embedding_provider, get_llm_provider

ALICE = Identity("alice", groups=("engineering",))
BOB = Identity("bob", groups=("legal",))
CAROL = Identity("carol", groups=("sales",))
ADMIN = Identity("root", is_admin=True)


class Api:
    def __init__(self, client: AsyncClient, current: list[Identity]) -> None:
        self.client = client
        self._current = current

    def as_user(self, identity: Identity) -> "Api":
        self._current[0] = identity
        return self

    async def share(self, document_id: uuid.UUID, groups: list[str]) -> Any:
        return await self.client.patch(f"/documents/{document_id}", json={"acl_groups": groups})

    async def sources(self) -> list[str]:
        response = await self.client.post("/query", json={"question": "refund?"})
        return [s["document_name"] for s in response.json()["sources"]]

    async def listed(self) -> list[str]:
        body = (await self.client.get("/documents")).json()
        return [d["name"] for d in body["items"]]


@pytest.fixture
async def api(app_engine: AsyncEngine) -> AsyncIterator[Api]:
    app = create_app()
    current = [ALICE]
    app.dependency_overrides[get_identity] = lambda: current[0]
    app.dependency_overrides[get_engine] = lambda: app_engine
    app.dependency_overrides[get_object_store] = lambda: None
    app.dependency_overrides[get_job_queue] = lambda: None
    app.dependency_overrides[get_embedding_provider] = lambda: FakeEmbedder()
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLM()
    app.dependency_overrides[get_settings] = lambda: Settings(
        query_rate_limit_per_minute=1000, known_groups=["engineering", "legal", "sales"]
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield Api(client, current)


async def chunk_groups(engine: AsyncEngine, document_id: uuid.UUID) -> set[tuple[str, ...]]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT acl_groups FROM chunks WHERE document_id = :d"), {"d": document_id}
        )
        return {tuple(row[0]) for row in rows}


async def audit_entries(engine: AsyncEngine) -> list[tuple[str, dict[str, Any] | None]]:
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT action, details FROM audit_log ORDER BY id"))
        return [(row[0], row[1]) for row in rows]


async def test_sharing_with_a_group_makes_the_document_and_its_answers_visible(
    api: Api, owner_engine: AsyncEngine
) -> None:
    document_id = await seed(owner_engine, [["Refunds are paid within five days."]])
    assert await api.as_user(BOB).listed() == []
    assert await api.sources() == []

    response = await api.as_user(ALICE).share(document_id, ["legal"])

    assert response.status_code == 200
    assert response.json()["acl_groups"] == ["legal"]
    assert await api.as_user(BOB).listed() == ["Handbook"]
    assert await api.sources() == ["Handbook"]
    assert await chunk_groups(owner_engine, document_id) == {("legal",)}


async def test_unsharing_hides_the_document_from_search_at_once(
    api: Api, owner_engine: AsyncEngine
) -> None:
    document_id = await seed(
        owner_engine, [["Refunds are paid within five days."]], acl_groups=("legal",)
    )
    assert await api.as_user(BOB).sources() == ["Handbook"]

    await api.as_user(ALICE).share(document_id, [])

    assert await api.as_user(BOB).sources() == []
    assert await api.as_user(BOB).listed() == []
    assert await api.as_user(ALICE).sources() == ["Handbook"]  # the owner keeps access
    assert await chunk_groups(owner_engine, document_id) == {()}


async def test_every_version_chunk_follows_the_new_groups(
    api: Api, owner_engine: AsyncEngine
) -> None:
    document_id = await seed(owner_engine, [["Old rule."]], status="archived")
    await seed(owner_engine, [["New rule."]], document_id=document_id, version=2)

    await api.as_user(ALICE).share(document_id, ["legal", "sales"])

    assert await chunk_groups(owner_engine, document_id) == {("legal", "sales")}


async def test_only_the_owner_or_an_admin_can_change_the_groups(
    api: Api, owner_engine: AsyncEngine
) -> None:
    document_id = await seed(owner_engine, [["Refunds."]], acl_groups=("legal",))

    by_reader = await api.as_user(BOB).share(document_id, ["legal", "sales"])
    by_stranger = await api.as_user(CAROL).share(document_id, ["sales"])
    by_admin = await api.as_user(ADMIN).share(document_id, ["sales"])

    assert by_reader.status_code == 403
    assert by_stranger.status_code == 404  # cannot even see it
    assert by_admin.status_code == 200
    assert await chunk_groups(owner_engine, document_id) == {("sales",)}


async def test_unknown_groups_are_refused_but_current_ones_can_be_kept(
    api: Api, owner_engine: AsyncEngine
) -> None:
    document_id = await seed(owner_engine, [["Refunds."]], acl_groups=("retired",))
    api.as_user(ALICE)

    refused = await api.share(document_id, ["retired", "legl"])
    kept = await api.share(document_id, ["retired", "legal"])

    assert refused.status_code == 422
    assert "legl" in refused.json()["detail"]
    assert kept.status_code == 200
    assert kept.json()["acl_groups"] == ["legal", "retired"]


async def test_the_change_is_audited_and_an_unchanged_list_is_not(
    api: Api, owner_engine: AsyncEngine
) -> None:
    document_id = await seed(owner_engine, [["Refunds."]])
    api.as_user(ALICE)

    await api.share(document_id, ["legal"])
    await api.share(document_id, ["legal"])

    entries = [e for e in await audit_entries(owner_engine) if e[0] == "acl_update"]
    assert entries == [("acl_update", {"groups_before": [], "groups_after": ["legal"]})]
