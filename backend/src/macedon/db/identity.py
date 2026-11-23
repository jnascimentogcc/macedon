from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession


@dataclass(frozen=True)
class Identity:
    """Who is acting. Row-Level Security policies read this from transaction-local settings."""

    user_id: str
    groups: tuple[str, ...] = ()
    is_admin: bool = False
    # Set only for an API key: what it may do ("read", "write"). None means no limit, as for a
    # user who signed in. Keys are never administrators.
    scopes: tuple[str, ...] | None = None
    key_id: str | None = None


async def apply_identity(target: AsyncConnection | AsyncSession, identity: Identity) -> None:
    """Set the identity for the current transaction (cleared automatically at its end)."""
    await target.execute(
        text(
            "SELECT set_config('app.user_id', :user_id, true), "
            "set_config('app.groups', :groups, true), "
            "set_config('app.is_admin', :is_admin, true)"
        ),
        {
            "user_id": identity.user_id,
            "groups": ",".join(identity.groups),
            "is_admin": "true" if identity.is_admin else "false",
        },
    )
