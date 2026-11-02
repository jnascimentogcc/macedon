"""Arq worker: `uv run arq macedon.worker.WorkerSettings`."""

import uuid
from datetime import timedelta
from typing import Any

from arq import Retry, cron
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import create_async_engine

from macedon.config import get_settings
from macedon.documents.queue import INGEST_FUNCTION
from macedon.documents.storage import get_object_store
from macedon.ingestion.embeddings import OpenAIEmbeddingProvider
from macedon.ingestion.pipeline import (
    IngestionDeps,
    TransientIngestionError,
    fail_version,
    find_stale_versions,
)
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


STALE_AFTER = timedelta(minutes=15)


async def requeue_stale(ctx: dict[str, Any]) -> int:
    """Re-enqueue versions whose ingestion job was lost (see find_stale_versions)."""
    stale = await find_stale_versions(ctx["engine"], STALE_AFTER)
    for version_id in stale:
        await ctx["redis"].enqueue_job(
            INGEST_FUNCTION, str(version_id), _job_id=f"ingest:{version_id}"
        )
    return len(stale)


class WorkerSettings:
    functions = [ingest_version]
    cron_jobs = [cron(requeue_stale, minute=set(range(0, 60, 5)), run_at_startup=True)]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_tries = MAX_TRIES + 1  # arq counts the final attempt that gives up
    job_timeout = 900
