"""From matched chunks to the passages the model reads.

Search runs over small chunks because they are precise; answering needs more context. So each
hit is expanded to its whole section when that fits the limit, and otherwise to a window of
neighbouring chunks. This is the unified retrieval rule from the design.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from macedon.ingestion.chunking import estimate_tokens
from macedon.query.retrieval import Hit

SECTION_TOKEN_LIMIT = 1500
CONTEXT_TOKEN_BUDGET = 6000
NEIGHBOUR_WINDOW = 1


@dataclass(frozen=True)
class Passage:
    number: int  # the [n] the model cites
    hit: Hit
    text: str
    chunk_ids: tuple[int, ...]


async def build_passages(
    session: AsyncSession,
    hits: list[Hit],
    *,
    section_token_limit: int = SECTION_TOKEN_LIMIT,
    token_budget: int = CONTEXT_TOKEN_BUDGET,
) -> list[Passage]:
    passages: list[Passage] = []
    covered: set[int] = set()
    used_tokens = 0
    for hit in hits:
        if hit.chunk_id in covered:
            continue  # already inside a passage built for a better hit
        rows = await _section(session, hit.version_id, hit.section_id)
        if sum(estimate_tokens(content) for _, content in rows) > section_token_limit:
            rows = await _window(session, hit.version_id, hit.position)
        body = "\n\n".join(content for _, content in rows)
        cost = estimate_tokens(body)
        if passages and used_tokens + cost > token_budget:
            break
        ids = tuple(chunk_id for chunk_id, _ in rows)
        covered.update(ids)
        used_tokens += cost
        passages.append(Passage(len(passages) + 1, hit, body, ids))
    return passages


async def _section(
    session: AsyncSession, version_id: uuid.UUID, section_id: str
) -> list[tuple[int, str]]:
    result = await session.execute(
        text(
            "SELECT id, content FROM chunks "
            "WHERE version_id = :version AND section_id = :section ORDER BY position"
        ),
        {"version": version_id, "section": section_id},
    )
    return [(row[0], row[1]) for row in result]


async def _window(
    session: AsyncSession, version_id: uuid.UUID, position: int
) -> list[tuple[int, str]]:
    result = await session.execute(
        text(
            "SELECT id, content FROM chunks WHERE version_id = :version "
            "AND position BETWEEN :low AND :high ORDER BY position"
        ),
        {
            "version": version_id,
            "low": position - NEIGHBOUR_WINDOW,
            "high": position + NEIGHBOUR_WINDOW,
        },
    )
    return [(row[0], row[1]) for row in result]
