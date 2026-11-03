import json

import httpx
import pytest

from macedon.ingestion.embeddings import (
    BATCH_SIZE,
    EmbeddingError,
    OpenAIEmbeddingProvider,
    TransientEmbeddingError,
)

DIMS = 4


def provider(transport: httpx.MockTransport) -> OpenAIEmbeddingProvider:
    client = httpx.AsyncClient(transport=transport, base_url="https://api.test/v1")
    return OpenAIEmbeddingProvider("sk-test", "m", DIMS, client=client, retry_delay=0)


def ok(request: httpx.Request) -> httpx.Response:
    inputs = json.loads(request.content)["input"]
    # Answer out of order to prove the provider restores the original order.
    data = [{"index": i, "embedding": [float(len(t))] * DIMS} for i, t in enumerate(inputs)]
    return httpx.Response(200, json={"data": list(reversed(data))})


async def test_embeddings_keep_the_input_order_and_send_the_key() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return ok(request)

    vectors = await provider(httpx.MockTransport(handler)).embed(["a", "bbb", "cc"])

    assert [v[0] for v in vectors] == [1.0, 3.0, 2.0]
    assert seen[0].headers["Authorization"] == "Bearer sk-test"
    assert json.loads(seen[0].content)["model"] == "m"


async def test_large_inputs_are_sent_in_batches() -> None:
    sizes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sizes.append(len(json.loads(request.content)["input"]))
        return ok(request)

    vectors = await provider(httpx.MockTransport(handler)).embed(["x"] * (BATCH_SIZE * 2 + 5))

    assert sizes == [BATCH_SIZE, BATCH_SIZE, 5]
    assert len(vectors) == BATCH_SIZE * 2 + 5


async def test_no_texts_means_no_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    assert await provider(httpx.MockTransport(handler)).embed([]) == []


async def test_temporary_errors_are_retried() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(429) if attempts < 3 else ok(request)

    vectors = await provider(httpx.MockTransport(handler)).embed(["a"])

    assert attempts == 3
    assert len(vectors) == 1


async def test_persistent_server_errors_become_transient_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with pytest.raises(TransientEmbeddingError):
        await provider(httpx.MockTransport(handler)).embed(["a"])


async def test_network_failures_become_transient_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    with pytest.raises(TransientEmbeddingError):
        await provider(httpx.MockTransport(handler)).embed(["a"])


async def test_a_rejected_request_is_permanent_and_not_retried() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(401)

    with pytest.raises(EmbeddingError) as error:
        await provider(httpx.MockTransport(handler)).embed(["a"])

    assert attempts == 1
    assert not isinstance(error.value, TransientEmbeddingError)
    assert "sk-test" not in str(error.value)


async def test_wrong_dimensions_are_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})

    with pytest.raises(EmbeddingError, match="dimensions"):
        await provider(httpx.MockTransport(handler)).embed(["a"])
