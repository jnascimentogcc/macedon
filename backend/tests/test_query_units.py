import httpx
import pytest

from macedon.llm import LLMError, LLMUnavailableError, OpenAILLMProvider
from macedon.query.prompt import cited_numbers
from macedon.query.ratelimit import SlidingWindowLimiter
from macedon.query.retrieval import MAX_KEYWORDS, keyword_query


def test_keywords_keep_distinctive_words_and_drop_common_ones() -> None:
    assert keyword_query("What does the termination clause say about notice?") == (
        "termination | clause | notice"
    )


def test_keywords_keep_codes_numbers_and_capitalised_acronyms() -> None:
    assert keyword_query("Does NDA 4521 apply, or CLT-4521?") == "nda | 4521 | apply | clt"


def test_keywords_are_none_when_nothing_is_distinctive() -> None:
    assert keyword_query("what is the one?") is None


def test_keywords_are_capped_and_deduplicated() -> None:
    words = " ".join(f"word{n:02d}" for n in range(40))

    query = keyword_query(f"{words} {words}")

    assert query is not None
    assert len(query.split(" | ")) == MAX_KEYWORDS


def test_keywords_cannot_inject_tsquery_syntax() -> None:
    query = keyword_query("refund & !(secret) | 'quoted' :* <-> value")

    assert query is not None
    assert all(part.isalnum() or "_" in part for part in query.split(" | "))


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("Claim [1].", {1}),
        ("Claim [1][2] and [3].", {1, 2, 3}),
        ("Claim [1, 2].", {1, 2}),
        ("No citations here.", set()),
        ("An array like arr[0] is not a citation.", {0}),
        ("Words in [brackets] are not citations.", set()),
    ],
)
def test_citations_are_parsed_from_the_answer(answer: str, expected: set[int]) -> None:
    assert cited_numbers(answer) == expected


def test_limiter_allows_up_to_the_limit_then_reports_the_wait() -> None:
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60)

    assert limiter.check("alice") is None
    assert limiter.check("alice") is None
    wait = limiter.check("alice")
    assert wait is not None and 0 < wait <= 60
    assert limiter.check("bob") is None  # separate budget


def test_limiter_frees_a_slot_when_the_window_passes() -> None:
    limiter = SlidingWindowLimiter(limit=1, window_seconds=0.05)
    assert limiter.check("alice") is None
    assert limiter.check("alice") is not None

    import time

    time.sleep(0.06)

    assert limiter.check("alice") is None


def provider(handler: httpx.MockTransport) -> OpenAILLMProvider:
    client = httpx.AsyncClient(transport=handler, base_url="https://api.test/v1")
    return OpenAILLMProvider("sk-test", "model-x", client=client)


async def test_llm_sends_system_and_user_messages_and_returns_the_text() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "  Hello [1]  "}}]})

    answer = await provider(httpx.MockTransport(handler)).complete("be brief", "question")

    assert answer == "Hello [1]"
    request = seen[0]
    assert request.headers["Authorization"] == "Bearer sk-test"
    body = request.read().decode()
    assert '"model":"model-x"' in body.replace(" ", "")
    assert "tools" not in body  # the model never gets tools


@pytest.mark.parametrize("status_code", [429, 500, 503])
async def test_llm_temporary_errors_are_reported_as_unavailable(status_code: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code)

    with pytest.raises(LLMUnavailableError):
        await provider(httpx.MockTransport(handler)).complete("s", "u")


async def test_llm_network_failures_are_reported_as_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    with pytest.raises(LLMUnavailableError):
        await provider(httpx.MockTransport(handler)).complete("s", "u")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": {"content": "  "}}]}),
        httpx.Response(200, text="not json"),
    ],
    ids=["rejected", "no-choices", "blank", "not-json"],
)
async def test_llm_unusable_responses_are_permanent_errors(response: httpx.Response) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response

    with pytest.raises(LLMError) as error:
        await provider(httpx.MockTransport(handler)).complete("s", "u")

    assert not isinstance(error.value, LLMUnavailableError)
    assert "sk-test" not in str(error.value)
