import asyncio
from typing import Protocol

import httpx

from macedon.config import Settings

BATCH_SIZE = 64
MAX_ATTEMPTS = 4
RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}


class EmbeddingError(Exception):
    """The provider rejected the request for good (bad key, bad input, wrong dimensions)."""


class TransientEmbeddingError(EmbeddingError):
    """The provider could not answer right now; the job may be retried later."""


class EmbeddingProvider(Protocol):
    model: str
    dimensions: int

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """One vector per text, in the same order."""
        ...


class OpenAIEmbeddingProvider:
    """OpenAI embeddings over plain HTTP; no SDK, so the pipeline is not tied to one."""

    def __init__(
        self,
        api_key: str,
        model: str,
        dimensions: int,
        base_url: str = "https://api.openai.com/v1",
        client: httpx.AsyncClient | None = None,
        retry_delay: float = 1.0,
    ) -> None:
        self.model = model
        self.dimensions = dimensions
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=60)
        self._retry_delay = retry_delay

    @classmethod
    def from_settings(cls, settings: Settings) -> "OpenAIEmbeddingProvider":
        if not settings.openai_api_key:
            raise EmbeddingError("MACEDON_OPENAI_API_KEY is not set")
        return cls(
            settings.openai_api_key.get_secret_value(),
            settings.embedding_model,
            settings.embedding_dimensions,
            settings.openai_base_url,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), BATCH_SIZE):
            vectors.extend(await self._embed_batch(texts[start : start + BATCH_SIZE]))
        return vectors

    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        payload = {"model": self.model, "input": batch}
        headers = {"Authorization": f"Bearer {self._api_key}"}
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await self._client.post("/embeddings", json=payload, headers=headers)
            except httpx.TransportError as exc:
                if attempt == MAX_ATTEMPTS:
                    raise TransientEmbeddingError(f"could not reach the provider: {exc}") from exc
            else:
                if response.status_code == 200:
                    return self._parse(response.json(), len(batch))
                if response.status_code not in RETRYABLE_STATUS:
                    raise EmbeddingError(f"the provider answered {response.status_code}")
                if attempt == MAX_ATTEMPTS:
                    raise TransientEmbeddingError(f"the provider answered {response.status_code}")
            await asyncio.sleep(self._retry_delay * 2 ** (attempt - 1))
        raise AssertionError("unreachable")  # pragma: no cover

    def _parse(self, body: dict[str, list[dict[str, object]]], expected: int) -> list[list[float]]:
        items = sorted(body["data"], key=lambda item: int(item["index"]))  # type: ignore[call-overload]
        if len(items) != expected:
            raise EmbeddingError(f"expected {expected} embeddings, got {len(items)}")
        vectors: list[list[float]] = [item["embedding"] for item in items]  # type: ignore[misc]
        if any(len(vector) != self.dimensions for vector in vectors):
            raise EmbeddingError(f"the provider did not return {self.dimensions} dimensions")
        return vectors
