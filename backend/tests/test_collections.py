import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
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
ADMIN = Identity("root", is_admin=True)
PDF = b"%PDF-1.7\n%fake pdf body\n"


class FakeStore:
    async def put(self, key: str, data: bytes) -> None:
        pass


class FakeQueue:
    async def enqueue_ingestion(self, version_id: uuid.UUID) -> None:
        pass


class Api:
    def __init__(self, client: AsyncClient, current: list[Identity]) -> None:
        self.client = client
        self._current = current

    def as_user(self, identity: Identity) -> "Api":
        self._current[0] = identity
        return self

    async def make(self, name: str, parent: str | None = None, as_admin: bool = True) -> Any:
        previous = self._current[0]
        self._current[0] = ADMIN if as_admin else previous
        response = await self.client.post("/collections", json={"name": name, "parent_id": parent})
        self._current[0] = previous
        return response

    async def tree(self) -> list[dict[str, Any]]:
        tree: list[dict[str, Any]] = (await self.client.get("/collections")).json()
        return tree


@pytest.fixture
async def api(app_engine: AsyncEngine) -> AsyncIterator[Api]:
    app = create_app()
    current = [ALICE]
    app.dependency_overrides[get_identity] = lambda: current[0]
    app.dependency_overrides[get_engine] = lambda: app_engine
    app.dependency_overrides[get_object_store] = lambda: FakeStore()
    app.dependency_overrides[get_job_queue] = lambda: FakeQueue()
    app.dependency_overrides[get_embedding_provider] = lambda: FakeEmbedder()
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLM()
    app.dependency_overrides[get_settings] = lambda: Settings(query_rate_limit_per_minute=1000)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield Api(client, current)


# ---- the tree ----


async def test_everyone_reads_the_tree_but_only_admins_change_it(api: Api) -> None:
    legal = (await api.make("Legal")).json()

    assert [c["name"] for c in await api.as_user(BOB).tree()] == ["Legal"]
    denied = await api.make("Secret", as_admin=False)
    assert denied.status_code == 403
    renamed = await api.client.patch(f"/collections/{legal['id']}", json={"name": "Hacked"})
    assert renamed.status_code == 403
    assert (await api.client.delete(f"/collections/{legal['id']}")).status_code == 403


async def test_children_follow_their_parents_and_depth_is_limited(api: Api) -> None:
    parent = None
    for level in range(1, 5):
        created = await api.make(f"Level {level}", parent)
        assert created.status_code == 201
        assert created.json()["depth"] == level
        parent = created.json()["id"]

    too_deep = await api.make("Level 5", parent)

    assert too_deep.status_code == 422
    assert [c["depth"] for c in await api.tree()] == [1, 2, 3, 4]


async def test_sibling_names_are_unique_ignoring_case(api: Api) -> None:
    root = (await api.make("Contracts")).json()
    await api.make("Suppliers", root["id"])

    assert (await api.make("suppliers", root["id"])).status_code == 409
    assert (await api.make("CONTRACTS")).status_code == 409
    assert (await api.make("Suppliers")).status_code == 201  # same name under another parent


async def test_rename_and_delete_rules(api: Api) -> None:
    root = (await api.make("Legal")).json()
    child = (await api.make("Contracts", root["id"])).json()
    api.as_user(ADMIN)

    renamed = await api.client.patch(f"/collections/{child['id']}", json={"name": "Deals"})
    assert renamed.json()["name"] == "Deals"
    assert (await api.client.delete(f"/collections/{root['id']}")).status_code == 409  # has a child
    assert (await api.client.delete(f"/collections/{child['id']}")).status_code == 204
    assert (await api.client.delete(f"/collections/{root['id']}")).status_code == 204
    assert await api.tree() == []


async def test_a_collection_with_documents_cannot_be_deleted(api: Api) -> None:
    folder = (await api.make("Legal")).json()
    await api.client.post(
        "/documents", files={"file": ("a.pdf", PDF)}, data={"collection_id": folder["id"]}
    )

    response = await api.as_user(ADMIN).client.delete(f"/collections/{folder['id']}")

    assert response.status_code == 409


async def test_document_counts_only_include_documents_the_caller_can_read(api: Api) -> None:
    folder = (await api.make("Legal")).json()
    await api.as_user(ALICE).client.post(
        "/documents", files={"file": ("a.pdf", PDF)}, data={"collection_id": folder["id"]}
    )

    assert [c["document_count"] for c in await api.as_user(ALICE).tree()] == [1]
    assert [c["document_count"] for c in await api.as_user(BOB).tree()] == [0]


# ---- placing and tagging documents ----


async def test_upload_into_a_collection_with_normalized_tags(api: Api) -> None:
    folder = (await api.make("Legal")).json()

    response = await api.as_user(ALICE).client.post(
        "/documents",
        files={"file": ("a.pdf", PDF)},
        data={
            "collection_id": folder["id"],
            "tags": ["  Contract ", "2026", "contract", "Very Old"],
        },
    )

    document = response.json()["document"]
    assert document["collection_id"] == folder["id"]
    assert document["tags"] == ["contract", "2026", "very-old"]


async def test_upload_rejects_an_unknown_collection_and_bad_tags(api: Api) -> None:
    unknown = await api.client.post(
        "/documents", files={"file": ("a.pdf", PDF)}, data={"collection_id": str(uuid.uuid4())}
    )
    too_long = await api.client.post(
        "/documents", files={"file": ("a.pdf", PDF)}, data={"tags": ["x" * 41]}
    )

    assert unknown.status_code == 422
    assert too_long.status_code == 422


async def test_only_the_owner_moves_or_retags_a_document(api: Api) -> None:
    folder = (await api.make("Legal")).json()
    other = (await api.make("Finance")).json()
    document = (
        await api.as_user(ALICE).client.post(
            "/documents",
            files={"file": ("a.pdf", PDF)},
            data={"collection_id": folder["id"], "acl_users": ["bob"]},
        )
    ).json()["document"]
    url = f"/documents/{document['id']}"

    forbidden = await api.as_user(BOB).client.patch(url, json={"collection_id": other["id"]})
    assert forbidden.status_code == 403

    moved = await api.as_user(ALICE).client.patch(
        url, json={"collection_id": other["id"], "tags": ["Urgent"], "name": "Renamed"}
    )
    assert moved.json()["collection_id"] == other["id"]
    assert moved.json()["tags"] == ["urgent"]
    assert moved.json()["name"] == "Renamed"

    retagged = await api.client.patch(url, json={"tags": ["urgent", "late"]})
    assert retagged.json()["collection_id"] == other["id"]  # not mentioned, so unchanged

    cleared = await api.client.patch(url, json={"collection_id": None})
    assert cleared.json()["collection_id"] is None

    missing = await api.client.patch(url, json={"collection_id": str(uuid.uuid4())})
    assert missing.status_code == 422


async def test_listing_filters_by_collection_subtree_and_tags(api: Api) -> None:
    root = (await api.make("Legal")).json()
    child = (await api.make("Contracts", root["id"])).json()
    elsewhere = (await api.make("Finance")).json()
    api.as_user(ALICE)

    async def add(name: str, collection: dict[str, Any] | None, tags: list[str]) -> None:
        data: dict[str, Any] = {"name": name, "tags": tags}
        if collection:
            data["collection_id"] = collection["id"]
        files = {"file": (f"{name}.pdf", PDF + name.encode())}
        await api.client.post("/documents", files=files, data=data)

    await add("in-root", root, ["a"])
    await add("in-child", child, ["a", "b"])
    await add("in-finance", elsewhere, ["b"])
    await add("loose", None, [])

    async def names(**params: Any) -> list[str]:
        body = (await api.client.get("/documents", params=params)).json()
        return sorted(d["name"] for d in body["items"])

    assert await names(collection_id=root["id"]) == ["in-child", "in-root"]  # root plus below
    assert await names(collection_id=child["id"]) == ["in-child"]
    assert await names(tag="b") == ["in-child", "in-finance"]
    assert await names(tag=["a", "b"]) == ["in-child"]  # all tags must match
    assert await names(collection_id=root["id"], tag="b") == ["in-child"]


# ---- scoped queries ----


async def test_a_query_can_be_scoped_to_a_collection_and_its_children(
    api: Api, owner_engine: AsyncEngine
) -> None:
    root = (await api.make("Legal")).json()
    child = (await api.make("Contracts", root["id"])).json()
    other = (await api.make("Finance")).json()
    where = {"Root doc": root, "Child doc": child, "Finance doc": other}
    for name, collection in where.items():
        await seed(
            owner_engine,
            [[f"refund in {name}"]],
            name=name,
            collection_id=uuid.UUID(collection["id"]),
        )
    await seed(owner_engine, [["refund unfiled"]], name="Loose doc")

    async def sources(**scope: Any) -> list[str]:
        response = await api.client.post("/query", json={"question": "refund?", **scope})
        return sorted(s["document_name"] for s in response.json()["sources"])

    assert await sources() == ["Child doc", "Finance doc", "Loose doc", "Root doc"]
    assert await sources(collection_id=root["id"]) == ["Child doc", "Root doc"]
    assert await sources(collection_id=child["id"]) == ["Child doc"]
    assert await sources(collection_id=str(uuid.uuid4())) == []


async def test_a_query_can_be_scoped_by_tags(api: Api, owner_engine: AsyncEngine) -> None:
    await seed(owner_engine, [["refund one"]], name="Tagged", tags=("policy", "2026"))
    await seed(owner_engine, [["refund two"]], name="Half", tags=("policy",))
    await seed(owner_engine, [["refund three"]], name="Plain")

    async def sources(tags: list[str]) -> list[str]:
        response = await api.client.post("/query", json={"question": "refund?", "tags": tags})
        return sorted(s["document_name"] for s in response.json()["sources"])

    assert await sources(["Policy"]) == ["Half", "Tagged"]  # normalized like stored tags
    assert await sources(["policy", "2026"]) == ["Tagged"]


async def test_scoping_by_collection_never_widens_access(
    api: Api, owner_engine: AsyncEngine
) -> None:
    folder = (await api.make("Legal")).json()
    await seed(
        owner_engine,
        [["refund secret"]],
        name="Private",
        acl_users=("alice",),
        collection_id=uuid.UUID(folder["id"]),
    )

    response = await api.as_user(BOB).client.post(
        "/query", json={"question": "refund?", "collection_id": folder["id"]}
    )

    assert response.json()["sources"] == []


async def test_the_application_role_cannot_write_collections_without_being_admin(
    app_engine: AsyncEngine,
) -> None:
    async with app_engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.user_id', 'alice', true)"))
        with pytest.raises(DBAPIError, match="row-level security"):
            await conn.execute(
                text("INSERT INTO collections (name, path, depth) VALUES ('x', '/x/', 1)")
            )
