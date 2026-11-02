import uuid
from typing import Any, cast

from sqlalchemy import Table, insert
from sqlalchemy.ext.asyncio import AsyncSession

from macedon.db.identity import Identity
from macedon.db.models import AuditLog


async def record_audit(
    session: AsyncSession,
    identity: Identity,
    action: str,
    *,
    document_id: uuid.UUID | None = None,
    version_id: uuid.UUID | None = None,
    chunk_ids: list[int] | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Append an entry in the caller's transaction, so it commits or rolls back with the action."""
    # A plain INSERT, without RETURNING: reading the row back would apply the audit log's
    # SELECT policy, which only admins pass. Callers can write entries but never read them.
    await session.execute(
        insert(cast(Table, AuditLog.__table__))
        .inline()  # no RETURNING for the generated id
        .values(
            actor_id=identity.user_id,
            action=action,
            document_id=document_id,
            version_id=version_id,
            chunk_ids=chunk_ids,
            details=details,
        )
    )
