import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
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


# ---- JWKS handling ----


def jwk_of(key: rsa.RSAPrivateKey, kid: str, **extra: Any) -> dict[str, Any]:
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    return {**jwk, "kid": kid, "use": "sig", "alg": "RS256", **extra}


def jwks_provider(
    handler: Any,
) -> Any:
    from macedon.auth import JwksKeyProvider

    return JwksKeyProvider("https://idp.test/certs", transport=httpx.MockTransport(handler))


async def test_jwks_ignores_encryption_keys_published_next_to_signing_keys() -> None:
    # Keycloak publishes a use=enc key (RSA-OAEP) that PyJWT cannot load.
    encryption = jwk_of(new_key(), "enc-key", use="enc", alg="RSA-OAEP")
    keys = {"keys": [encryption, jwk_of(SIGNING_KEY, KID)]}
    provider = jwks_provider(lambda request: httpx.Response(200, json=keys))

    key = await provider.get_key(KID)

    assert key.public_numbers() == SIGNING_KEY.public_key().public_numbers()
    with pytest.raises(AuthError):
        await provider.get_key("enc-key")


async def test_jwks_skips_unreadable_keys_without_losing_the_good_ones() -> None:
    broken = {"kid": "weird", "kty": "XX", "use": "sig"}
    keys = {"keys": [broken, jwk_of(SIGNING_KEY, KID)]}
    provider = jwks_provider(lambda request: httpx.Response(200, json=keys))

    assert await provider.get_key(KID) is not None


async def test_jwks_are_cached_between_calls() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"keys": [jwk_of(SIGNING_KEY, KID)]})

    provider = jwks_provider(handler)
    await provider.get_key(KID)
    await provider.get_key(KID)

    assert calls == 1


async def test_a_rotated_key_is_picked_up_after_the_refetch_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import macedon.auth as auth

    new = new_key()
    published = [jwk_of(SIGNING_KEY, KID)]
    provider = jwks_provider(lambda request: httpx.Response(200, json={"keys": published}))
    await provider.get_key(KID)
    published.append(jwk_of(new, "rotated"))

    with pytest.raises(AuthError):  # too soon: an unknown kid must not trigger a refetch storm
        await provider.get_key("rotated")
    monkeypatch.setattr(auth, "JWKS_MIN_REFETCH_SECONDS", -1)

    assert await provider.get_key("rotated") is not None


async def test_an_unreachable_provider_rejects_tokens_instead_of_crashing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    from macedon.auth import verify_token

    with pytest.raises(AuthError):
        await verify_token(make_token(), get_settings(), jwks_provider(handler))
