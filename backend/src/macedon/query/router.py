from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from macedon.auth import get_identity
from macedon.config import Settings, get_settings
from macedon.db.identity import Identity
from macedon.db.session import get_session
from macedon.ingestion.embeddings import EmbeddingError, EmbeddingProvider, OpenAIEmbeddingProvider
from macedon.llm import LLMError, LLMProvider, LLMUnavailableError, OpenAILLMProvider
from macedon.query.ratelimit import SlidingWindowLimiter
from macedon.query.schemas import QueryRequest, QueryResponse
from macedon.query.service import QueryDeps, answer_question

router = APIRouter(tags=["query"])

IdentityDep = Annotated[Identity, Depends(get_identity)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    try:
        return OpenAIEmbeddingProvider.from_settings(get_settings())
    except EmbeddingError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "embeddings are not configured"
        ) from exc


@lru_cache
def get_llm_provider() -> LLMProvider:
    try:
        return OpenAILLMProvider.from_settings(get_settings())
    except LLMError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "the model is not configured"
        ) from exc


def enforce_rate_limit(
    request: Request,
    identity: IdentityDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    limiter: SlidingWindowLimiter | None = getattr(request.app.state, "query_limiter", None)
    if limiter is None:
        limiter = SlidingWindowLimiter(settings.query_rate_limit_per_minute)
        request.app.state.query_limiter = limiter
    wait = limiter.check(identity.user_id)
    if wait is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too many questions, try again shortly",
            headers={"Retry-After": str(int(wait) + 1)},
        )


@router.post("/query", response_model=QueryResponse, dependencies=[Depends(enforce_rate_limit)])
async def query(
    body: QueryRequest,
    session: SessionDep,
    identity: IdentityDep,
    embedder: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> QueryResponse:
    """Answer a question from the documents the caller can read, citing document and version."""
    try:
        return await answer_question(session, identity, body, QueryDeps(embedder, llm))
    except (EmbeddingError, LLMError) as exc:
        unavailable = isinstance(exc, LLMUnavailableError) or "reach" in str(exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE if unavailable else status.HTTP_502_BAD_GATEWAY,
            "the answer could not be generated, try again later",
        ) from exc
