from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from macedon.audit import record_audit
from macedon.db.identity import Identity
from macedon.documents.tags import normalize_tags
from macedon.ingestion.embeddings import EmbeddingProvider
from macedon.llm import LLMProvider
from macedon.query import prompt
from macedon.query.context import build_passages
from macedon.query.retrieval import search
from macedon.query.schemas import QueryRequest, QueryResponse, SourceOut

AUDITED_QUESTION_CHARS = 500


@dataclass(frozen=True)
class QueryDeps:
    embedder: EmbeddingProvider
    llm: LLMProvider


async def answer_question(
    session: AsyncSession, identity: Identity, request: QueryRequest, deps: QueryDeps
) -> QueryResponse:
    """Retrieve what the caller may read, then answer from it with citations.

    The audit entry is committed before the model is called, so it records the chunks that are
    about to leave for the external API even if that call then fails. The session must not be
    used after this function returns: the identity only lives for the committed transaction.
    """
    vector = (await deps.embedder.embed([request.question]))[0]
    hits = await search(
        session,
        identity,
        request.question,
        vector,
        document_id=request.document_id,
        version=request.version,
        collection_id=request.collection_id,
        tags=normalize_tags(request.tags),
        limit=request.top_k,
    )
    passages = await build_passages(session, hits)

    await record_audit(
        session,
        identity,
        "query",
        document_id=request.document_id,
        chunk_ids=[chunk_id for p in passages for chunk_id in p.chunk_ids],
        details={
            "question": request.question[:AUDITED_QUESTION_CHARS],
            "version": request.version,
            "collection_id": str(request.collection_id) if request.collection_id else None,
            "tags": request.tags,
            "passages": len(passages),
        },
    )
    await session.commit()

    if not passages:
        return QueryResponse(answer=prompt.NO_SOURCES_ANSWER, sources=[])

    answer = await deps.llm.complete(
        prompt.SYSTEM_PROMPT, prompt.build_user_message(request.question, passages)
    )
    cited = prompt.cited_numbers(answer)
    return QueryResponse(
        answer=answer,
        model=deps.llm.model,
        sources=[
            SourceOut(
                id=p.number,
                document_id=p.hit.document_id,
                document_name=p.hit.document_name,
                version=p.hit.version_number,
                page=p.hit.page,
                section=p.hit.path,
                text=p.text,
                cited=p.number in cited,
            )
            for p in passages
        ],
    )
