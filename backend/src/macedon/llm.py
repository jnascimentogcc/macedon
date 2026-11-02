from typing import Protocol

import httpx

from macedon.config import Settings


class LLMError(Exception):
    """The provider rejected the request or returned something unusable."""


class LLMUnavailableError(LLMError):
    """The provider could not answer right now."""


class LLMProvider(Protocol):
    model: str

    async def complete(self, system: str, user: str) -> str:
        """Single-turn completion. The provider never gets tools or side effects."""
        ...


class OpenAILLMProvider:
    """OpenAI Chat Completions over plain HTTP, so the pipeline is not tied to an SDK."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=120)

    @classmethod
    def from_settings(cls, settings: Settings) -> "OpenAILLMProvider":
        if not settings.openai_api_key:
            raise LLMError("MACEDON_OPENAI_API_KEY is not set")
        return cls(
            settings.openai_api_key.get_secret_value(), settings.llm_model, settings.openai_base_url
        )

    async def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            response = await self._client.post(
                "/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        except httpx.TransportError as exc:
            raise LLMUnavailableError(f"could not reach the provider: {exc}") from exc
        if response.status_code in {408, 429, 500, 502, 503, 504}:
            raise LLMUnavailableError(f"the provider answered {response.status_code}")
        if response.status_code != 200:
            raise LLMError(f"the provider answered {response.status_code}")
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError):
            raise LLMError("the provider returned an unexpected response") from None
        if not isinstance(content, str) or not content.strip():
            raise LLMError("the provider returned an empty answer")
        return content.strip()
