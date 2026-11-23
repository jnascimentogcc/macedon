"""API keys: long-lived credentials for other applications, managed by administrators.

A key is its own identity (`key:<id>`) with the groups chosen at creation, never an administrator.
Those groups can only be ones the platform knows (`MACEDON_KNOWN_GROUPS`) or the creator's own,
so a key cannot be given access its creator could not grant. Document ACL and Row-Level Security
apply to it like to any user.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from macedon.apikeys.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from macedon.apikeys.tokens import hash_token, new_token, token_prefix
from macedon.audit import record_audit
from macedon.auth import get_identity
from macedon.config import Settings, get_settings
from macedon.db.identity import Identity
from macedon.db.models import ApiKey
from macedon.db.session import get_session
from macedon.groups import available_groups

router = APIRouter(prefix="/api-keys", tags=["api-keys"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
IdentityDep = Annotated[Identity, Depends(get_identity)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _require_admin(identity: Identity) -> None:
    # An API key is never an administrator, so a key cannot manage keys.
    if not identity.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only administrators manage API keys")


def _out(key: ApiKey) -> ApiKeyOut:
    return ApiKeyOut(
        id=key.id,
        name=key.name,
        prefix=key.prefix,
        groups=list(key.groups),
        scopes=list(key.scopes),
        created_by=key.created_by,
        created_at=key.created_at,
        expires_at=key.expires_at,
        revoked_at=key.revoked_at,
        last_used_at=key.last_used_at,
    )


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: ApiKeyCreate, session: SessionDep, identity: IdentityDep, settings: SettingsDep
) -> ApiKeyCreated:
    _require_admin(identity)
    days = body.expires_in_days or settings.api_key_default_days
    if days > settings.api_key_max_days:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"a key can last at most {settings.api_key_max_days} days",
        )
    groups = sorted(set(body.groups))
    unknown = sorted(set(groups) - set(available_groups(settings, identity)))
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"unknown groups: {', '.join(unknown)}"
        )

    token = new_token()
    now = datetime.now(UTC)
    key = ApiKey(
        id=uuid.uuid4(),
        name=body.name,
        prefix=token_prefix(token),
        token_hash=hash_token(token),
        groups=groups,
        scopes=sorted(set(body.scopes)),
        created_by=identity.user_id,
        created_at=now,
        expires_at=now + timedelta(days=days),
    )
    session.add(key)
    await session.flush()
    await record_audit(
        session,
        identity,
        "api_key_create",
        details={
            "key_id": str(key.id),
            "name": key.name,
            "groups": groups,
            "scopes": key.scopes,
            "expires_at": key.expires_at.isoformat(),
        },
    )
    return ApiKeyCreated(**_out(key).model_dump(), token=token)


@router.get("", response_model=list[ApiKeyOut])
async def list_api_keys(session: SessionDep, identity: IdentityDep) -> list[ApiKeyOut]:
    _require_admin(identity)
    rows = await session.scalars(select(ApiKey).order_by(ApiKey.created_at.desc()))
    return [_out(key) for key in rows]


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(key_id: uuid.UUID, session: SessionDep, identity: IdentityDep) -> None:
    """Revoke a key. It stays listed (and audited) but stops working at once."""
    _require_admin(identity)
    key = await session.get(ApiKey, key_id)
    if key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found")
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        await record_audit(
            session, identity, "api_key_revoke", details={"key_id": str(key.id), "name": key.name}
        )
