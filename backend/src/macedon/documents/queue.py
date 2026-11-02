import uuid
from typing import Protocol

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from macedon.config import get_settings

INGEST_FUNCTION = "ingest_version"


class JobQueue(Protocol):
    async def enqueue_ingestion(self, version_id: uuid.UUID) -> None: ...


class ArqJobQueue:
    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._pool: ArqRedis | None = None

    async def enqueue_ingestion(self, version_id: uuid.UUID) -> None:
        if self._pool is None:
            self._pool = await create_pool(RedisSettings.from_dsn(self._redis_url))
        await self._pool.enqueue_job(INGEST_FUNCTION, str(version_id))


_queue: JobQueue | None = None


def get_job_queue() -> JobQueue:
    global _queue
    if _queue is None:
        _queue = ArqJobQueue(get_settings().redis_url)
    return _queue
