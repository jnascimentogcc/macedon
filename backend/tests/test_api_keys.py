import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pytest
from fastapi import FastAPI
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

ADMIN = Identity("root", groups=("ops",), is_admin=True)
ALICE = Identity("alice", groups=("engineering",))
PREFIX = "mcd_"
PDF = b"%PDF-1.7\n%fake pdf body\n"


class FakeStore:
    async def put(self, key: str, data: bytes) -> None:
        pass


class FakeQueue:
    async def enqueue_ingestion(self, version_id: uuid.UUID) -> None:
        pass


@dataclass
class Clients:
    admin: AsyncClient  # signed in as an administrator
    key: AsyncClient  # as another application calls: real authentication, no override
    user: AsyncClient  # a signed-in user who is not an administrator
    owner_engine: AsyncEngine

    async def create(self, **body: Any) -> Any:
        body.setdefault("name", "reporting")
        return await self.admin.post("/api-keys", json=body)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _app(app_engine: AsyncEngine, identity: Identity | None) -> FastAPI:
    app = create_app()
    if identity is not None:
        app.dependency_overrides[get_identity] = lambda: identity
    app.dependency_overrides[get_engine] = lambda: app_engine
    app.dependency_overrides[get_object_store] = lambda: FakeStore()
    app.dependency_overrides[get_job_queue] = lambda: FakeQueue()
    app.dependency_overrides[get_settings] = lambda: Settings(
        known_groups=["engineering", "legal"], api_key_default_days=90, api_key_max_days=365
    )
    return app


@pytest.fixture
async def clients(app_engine: AsyncEngine, owner_engine: AsyncEngine) -> AsyncIterator[Clients]:
    def client(identity: Identity | None) -> AsyncClient:
        return AsyncClient(
            transport=ASGITransport(app=_app(app_engine, identity)), base_url="http://test"
        )

    async with client(ADMIN) as admin, client(None) as key, client(ALICE) as user:
        yield Clients(admin, key, user, owner_engine)


async def audit_actions(owner_engine: AsyncEngine) -> list[str]:
    async with owner_engine.connect() as conn:
        result = await conn.execute(text("SELECT action FROM audit_log ORDER BY id"))
        return [row[0] for row in result]


async def test_create_returns_the_secret_once_and_stores_only_its_hash(clients: Clients) -> None:
    response = await clients.create(groups=["engineering"], scopes=["read", "write"])

    assert response.status_code == 201
    body = response.json()
    assert body["token"].startswith(PREFIX)
    assert body["prefix"] == body["token"][:10]
    assert body["scopes"] == ["read", "write"]
    listed = (await clients.admin.get("/api-keys")).json()
    assert [k["id"] for k in listed] == [body["id"]]
    assert "token" not in listed[0]
    async with clients.owner_engine.connect() as conn:
        stored = (await conn.execute(text("SELECT token_hash FROM api_keys"))).scalar_one()
    assert body["token"] not in stored
    assert await audit_actions(clients.owner_engine) == ["api_key_create"]


async def test_default_expiry_is_ninety_days_and_the_maximum_is_enforced(
    clients: Clients,
) -> None:
    await clients.create()
    created = (await clients.admin.get("/api-keys")).json()[0]
    lifetime = datetime.fromisoformat(created["expires_at"]) - datetime.fromisoformat(
        created["created_at"]
    )
    assert lifetime.days == 90

    assert (await clients.create(expires_in_days=365)).status_code == 201
    assert (await clients.create(expires_in_days=366)).status_code == 422
    assert (await clients.create(expires_in_days=0)).status_code == 422


async def test_only_administrators_manage_keys(clients: Clients) -> None:
    assert (await clients.user.post("/api-keys", json={"name": "x"})).status_code == 403
    assert (await clients.user.get("/api-keys")).status_code == 403
    assert (await clients.user.delete(f"/api-keys/{uuid.uuid4()}")).status_code == 403


async def test_a_key_cannot_manage_keys(clients: Clients) -> None:
    token = (await clients.create(scopes=["read", "write"])).json()["token"]

    assert (await clients.key.get("/api-keys", headers=bearer(token))).status_code == 403
    created = await clients.key.post("/api-keys", json={"name": "x"}, headers=bearer(token))
    assert created.status_code == 403


async def test_groups_are_limited_to_known_ones_and_the_creators(clients: Clients) -> None:
    assert (await clients.create(groups=["legal", "ops"])).status_code == 201  # ops: creator
    unknown = await clients.create(groups=["finance"])
    assert unknown.status_code == 422
    assert "finance" in unknown.json()["detail"]


async def test_scopes_must_be_valid(clients: Clients) -> None:
    assert (await clients.create(scopes=[])).status_code == 422
    assert (await clients.create(scopes=["admin"])).status_code == 422


async def test_a_key_authenticates_as_its_own_non_admin_identity(clients: Clients) -> None:
    created = (await clients.create(groups=["engineering"])).json()

    me = await clients.key.get("/me", headers=bearer(created["token"]))

    assert me.status_code == 200
    assert me.json() == {
        "user_id": f"key:{created['id']}",
        "groups": ["engineering"],
        "is_admin": False,
        "scopes": ["read"],
    }


async def test_unknown_and_missing_tokens_are_rejected(clients: Clients) -> None:
    assert (await clients.key.get("/me")).status_code == 401
    assert (await clients.key.get("/me", headers=bearer(PREFIX + "nope"))).status_code == 401


async def test_revoked_keys_stop_working_but_stay_listed(clients: Clients) -> None:
    created = (await clients.create()).json()
    headers = bearer(created["token"])
    assert (await clients.key.get("/me", headers=headers)).status_code == 200

    assert (await clients.admin.delete(f"/api-keys/{created['id']}")).status_code == 204
    assert (await clients.admin.delete(f"/api-keys/{created['id']}")).status_code == 204  # again

    assert (await clients.key.get("/me", headers=headers)).status_code == 401
    assert (await clients.admin.get("/api-keys")).json()[0]["revoked_at"] is not None
    assert await audit_actions(clients.owner_engine) == ["api_key_create", "api_key_revoke"]
    assert (await clients.admin.delete(f"/api-keys/{uuid.uuid4()}")).status_code == 404


async def test_expired_keys_are_rejected(clients: Clients) -> None:
    created = (await clients.create()).json()
    async with clients.owner_engine.begin() as conn:
        await conn.execute(text("UPDATE api_keys SET expires_at = now() - interval '1 second'"))

    response = await clients.key.get("/me", headers=bearer(created["token"]))

    assert response.status_code == 401


async def test_last_use_is_recorded(clients: Clients) -> None:
    created = (await clients.create()).json()
    assert (await clients.admin.get("/api-keys")).json()[0]["last_used_at"] is None

    await clients.key.get("/me", headers=bearer(created["token"]))

    assert (await clients.admin.get("/api-keys")).json()[0]["last_used_at"] is not None


async def test_read_scope_reads_and_asks_but_cannot_write(clients: Clients) -> None:
    headers = bearer((await clients.create(scopes=["read"])).json()["token"])

    assert (await clients.key.get("/documents", headers=headers)).status_code == 200
    ask = await clients.key.post("/query", json={"question": "anything"}, headers=headers)
    assert ask.status_code != 403  # the scope allows it; answering needs an LLM
    upload = await clients.key.post("/documents", files={"file": ("a.pdf", PDF)}, headers=headers)
    assert upload.status_code == 403


async def test_write_scope_alone_cannot_read(clients: Clients) -> None:
    headers = bearer((await clients.create(scopes=["write"])).json()["token"])

    assert (await clients.key.get("/documents", headers=headers)).status_code == 403
    upload = await clients.key.post("/documents", files={"file": ("a.pdf", PDF)}, headers=headers)
    assert upload.status_code != 403


async def test_a_key_sees_only_documents_shared_with_its_groups(clients: Clients) -> None:
    mine = (await clients.create(groups=["engineering"])).json()["token"]
    other = (await clients.create(groups=["legal"])).json()["token"]
    uploaded = await clients.user.post(
        "/documents",
        files={"file": ("a.pdf", PDF)},
        data={"name": "Eng only", "acl_groups": ["engineering"]},
    )
    assert uploaded.status_code == 202

    seen = (await clients.key.get("/documents", headers=bearer(mine))).json()
    hidden = (await clients.key.get("/documents", headers=bearer(other))).json()

    assert [d["name"] for d in seen["items"]] == ["Eng only"]
    assert hidden["items"] == []
