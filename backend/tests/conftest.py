from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from macedon.config import get_settings


@pytest.fixture
async def owner_engine() -> AsyncIterator[AsyncEngine]:
    """Schema owner (superuser in dev): bypasses RLS, used for cleanup only."""
    engine = create_async_engine(get_settings().migration_database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1 FROM chunks LIMIT 1"))
    except SQLAlchemyError:
        await engine.dispose()
        pytest.skip("database not available or not migrated (docker compose up -d postgres)")
    yield engine
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE chunks, document_versions, documents, audit_log RESTART IDENTITY CASCADE"
            )
        )
    await engine.dispose()


@pytest.fixture
async def app_engine(owner_engine: AsyncEngine) -> AsyncIterator[AsyncEngine]:
    """The application role: RLS applies to it."""
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    yield engine
    await engine.dispose()
