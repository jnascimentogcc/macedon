import asyncio
from functools import lru_cache
from typing import Any, Protocol

import boto3
from botocore.exceptions import ClientError

from macedon.config import get_settings


class ObjectStore(Protocol):
    async def put(self, key: str, data: bytes) -> None: ...

    async def get(self, key: str) -> bytes: ...


class S3ObjectStore:
    """S3 or MinIO. boto3 is synchronous, so calls run in a worker thread."""

    def __init__(self, client: Any, bucket: str) -> None:
        self._client = client
        self._bucket = bucket
        self._bucket_ready = False

    async def put(self, key: str, data: bytes) -> None:
        await asyncio.to_thread(self._put, key, data)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._get, key)

    def _put(self, key: str, data: bytes) -> None:
        self._ensure_bucket()
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)

    def _get(self, key: str) -> bytes:
        body: bytes = self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        return body

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self._bucket)
        self._bucket_ready = True


@lru_cache
def get_object_store() -> ObjectStore:
    settings = get_settings()
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
    )
    return S3ObjectStore(client, settings.s3_bucket)
