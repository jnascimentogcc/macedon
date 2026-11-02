"""Arq worker: `uv run arq macedon.worker.WorkerSettings`."""

import uuid
from typing import Any

from arq import Retry
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import create_async_engine

from macedon.config import get_settings
from macedon.documents.storage import get_object_store
from macedon.ingestion.embeddings import OpenAIEmbeddingProvider
from macedon.ingestion.pipeline import IngestionDeps, TransientIngestionError, fail_version
from macedon.ingestion.pipeline import ingest_version as run_ingestion

MAX_TRIES = 4
RETRY_BASE_DELAY_SECONDS = 30


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    ctx["engine"] = engine
    ctx["deps"] = IngestionDeps(
        engine=engine,
        store=get_object_store(),
        embedder=OpenAIEmbeddingProvider.from_settings(settings),
    )


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["engine"].dispose()


async def ingest_version(ctx: dict[str, Any], version_id: str) -> None:
    """Retry temporary failures with a growing delay; give up and mark the version failed."""
    try:
        await run_ingestion(uuid.UUID(version_id), ctx["deps"])
    except TransientIngestionError as exc:
        tries: int = ctx["job_try"]
        if tries >= MAX_TRIES:
            await fail_version(
                ctx["engine"], uuid.UUID(version_id), f"gave up after retries: {exc}"
            )
            return
        raise Retry(defer=RETRY_BASE_DELAY_SECONDS * tries) from exc


class WorkerSettings:
    functions = [ingest_version]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_tries = MAX_TRIES + 1  # arq counts the final attempt that gives up
    job_timeout = 900
