import time
from collections.abc import AsyncIterator
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient

from macedon.auth import AuthError, get_key_provider
from macedon.config import get_settings
from macedon.main import create_app

KID = "test-key"


def new_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


SIGNING_KEY = new_key()


class StaticKeys:
    def __init__(self, keys: dict[str, Any]) -> None:
        self._keys = keys

    async def get_key(self, kid: str) -> Any:
        try:
            return self._keys[kid]
        except KeyError:
            raise AuthError("unknown signing key") from None


def make_token(key: rsa.RSAPrivateKey = SIGNING_KEY, kid: str = KID, **overrides: Any) -> str:
    settings = get_settings()
    claims: dict[str, Any] = {
        "sub": "alice",
        "iss": settings.oidc_issuer,
        "aud": settings.oidc_audience,
        "exp": int(time.time()) + 300,
        "groups": ["engineering"],
        "realm_access": {"roles": ["user"]},
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_key_provider] = lambda: StaticKeys({KID: SIGNING_KEY.public_key()})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_valid_token_maps_claims_to_identity(client: AsyncClient) -> None:
    response = await client.get("/me", headers=bearer(make_token()))

    assert response.status_code == 200
    assert response.json() == {"user_id": "alice", "groups": ["engineering"], "is_admin": False}


async def test_admin_role_makes_an_admin(client: AsyncClient) -> None:
    token = make_token(realm_access={"roles": ["admin", "user"]})

    response = await client.get("/me", headers=bearer(token))

    assert response.json()["is_admin"] is True


async def test_missing_token_is_rejected(client: AsyncClient) -> None:
    assert (await client.get("/me")).status_code == 401


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": int(time.time()) - 10},
        {"aud": "another-api"},
        {"iss": "http://evil.example/realms/macedon"},
    ],
    ids=["expired", "wrong-audience", "wrong-issuer"],
)
async def test_invalid_claims_are_rejected(client: AsyncClient, overrides: dict[str, Any]) -> None:
    response = await client.get("/me", headers=bearer(make_token(**overrides)))

    assert response.status_code == 401


async def test_token_without_required_claim_is_rejected(client: AsyncClient) -> None:
    token = jwt.encode(
        {"iss": get_settings().oidc_issuer, "aud": get_settings().oidc_audience},
        SIGNING_KEY,
        algorithm="RS256",
        headers={"kid": KID},
    )

    assert (await client.get("/me", headers=bearer(token))).status_code == 401


async def test_token_signed_by_an_unknown_key_is_rejected(client: AsyncClient) -> None:
    response = await client.get("/me", headers=bearer(make_token(key=new_key())))

    assert response.status_code == 401


async def test_unknown_key_id_is_rejected(client: AsyncClient) -> None:
    response = await client.get("/me", headers=bearer(make_token(kid="rotated-away")))

    assert response.status_code == 401


async def test_unsigned_token_is_rejected(client: AsyncClient) -> None:
    claims = {
        "sub": "alice",
        "iss": get_settings().oidc_issuer,
        "aud": get_settings().oidc_audience,
    }
    token = jwt.encode(claims, key="", algorithm="none", headers={"kid": KID})

    assert (await client.get("/me", headers=bearer(token))).status_code == 401
