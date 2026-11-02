"""OIDC/JWT validation. Provider-agnostic: only standard OIDC claims plus Keycloak-style roles."""

import time
from typing import Annotated, Any, Protocol

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from macedon.config import Settings, get_settings
from macedon.db.identity import Identity

JWKS_TTL_SECONDS = 600
JWKS_MIN_REFETCH_SECONDS = 30


class AuthError(Exception):
    """The token is missing, malformed, expired or not meant for this API."""


class KeyProvider(Protocol):
    async def get_key(self, kid: str) -> Any: ...


class JwksKeyProvider:
    """Fetches the provider's signing keys and caches them, refetching on an unknown `kid`."""

    def __init__(self, jwks_url: str) -> None:
        self._jwks_url = jwks_url
        self._keys: dict[str, Any] = {}
        self._fetched_at = 0.0

    async def get_key(self, kid: str) -> Any:
        now = time.monotonic()
        stale = now - self._fetched_at > JWKS_TTL_SECONDS
        unknown = kid not in self._keys
        if stale or (unknown and now - self._fetched_at > JWKS_MIN_REFETCH_SECONDS):
            await self._refresh()
        try:
            return self._keys[kid]
        except KeyError:
            raise AuthError("unknown signing key") from None

    async def _refresh(self) -> None:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(self._jwks_url)
            response.raise_for_status()
        self._keys = {
            jwk["kid"]: jwt.PyJWK(jwk).key for jwk in response.json()["keys"] if "kid" in jwk
        }
        self._fetched_at = time.monotonic()


async def verify_token(token: str, settings: Settings, keys: KeyProvider) -> Identity:
    """Validate signature, expiry, issuer and audience, and map claims to an Identity."""
    try:
        kid = jwt.get_unverified_header(token).get("kid")
        if not kid:
            raise AuthError("token has no key id")
        claims = jwt.decode(
            token,
            await keys.get_key(kid),
            algorithms=["RS256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthError(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise AuthError("could not fetch signing keys") from exc

    roles = claims.get("realm_access", {}).get("roles", [])
    return Identity(
        user_id=claims["sub"],
        groups=tuple(claims.get("groups", [])),
        is_admin=settings.admin_role in roles,
    )


_bearer = HTTPBearer(auto_error=False)


def get_key_provider(request: Request) -> KeyProvider:
    provider: KeyProvider | None = getattr(request.app.state, "key_provider", None)
    if provider is None:
        provider = JwksKeyProvider(get_settings().oidc_jwks_url)
        request.app.state.key_provider = provider
    return provider


async def get_identity(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    keys: Annotated[KeyProvider, Depends(get_key_provider)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Identity:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        return await verify_token(credentials.credentials, settings, keys)
    except AuthError:
        # Never echo why the token failed back to the caller.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "invalid token", headers={"WWW-Authenticate": "Bearer"}
        ) from None
