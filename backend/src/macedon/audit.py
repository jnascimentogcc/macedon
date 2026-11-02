import uuid
from typing import Any

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
    session.add(
        AuditLog(
            actor_id=identity.user_id,
            action=action,
            document_id=document_id,
            version_id=version_id,
            chunk_ids=chunk_ids,
            details=details,
        )
    )
