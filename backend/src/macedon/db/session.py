from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from macedon.auth import get_identity
from macedon.config import get_settings
from macedon.db.identity import Identity, apply_identity


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


async def get_session(
    identity: Annotated[Identity, Depends(get_identity)],
    engine: Annotated[AsyncEngine, Depends(get_engine)],
) -> AsyncIterator[AsyncSession]:
    """One transaction per request, with the caller's identity applied so RLS sees it.

    Commits when the request succeeds and rolls back on any error. An endpoint may commit
    early (for example before enqueuing a job); after that the identity is gone, so it must
    not run further queries.
    """
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        await apply_identity(session, identity)
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
