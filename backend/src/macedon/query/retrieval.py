"""Hybrid retrieval: vector search plus keyword search, fused by reciprocal rank.

The ACL filter is written into the SQL of both searches, so it is part of the query itself and
never a post-filter. Postgres Row-Level Security applies on top of it as a second barrier.
"""

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from macedon.db.identity import Identity

CANDIDATES_PER_SEARCH = 30
RRF_K = 60
MAX_KEYWORDS = 12

# Words that would match nearly every chunk. Keyword search is there for codes, acronyms and
# proper names, which vector search handles poorly.
STOPWORDS = frozenset(
    "about after again also been before being between both could does doing during each from "
    "have having here into just more most much only other over same should some such than that "
    "their them then there these they this those through under until very what when where which "
    "while with would your "
    "algum alguma como entre essa esse essas esses esta este estas estes foram isso mais mesmo "
    "muito nada nossa nosso para pela pelas pelo pelos qual quais quando quem seja sobre tambem "
    "todo toda todos todas voce".split()
)

_SELECT = """
SELECT c.id, c.version_id, c.document_id, d.name AS document_name, v.number AS version_number,
       c.section_id, c.position, c.page, c.path, c.content
FROM chunks c
JOIN document_versions v ON v.id = c.version_id
JOIN documents d ON d.id = c.document_id
WHERE d.archived_at IS NULL
  AND {scope}
  AND (
        CAST(:is_admin AS boolean)
        OR CAST(:user_id AS text) = ANY (c.acl_users)
        OR c.acl_groups && CAST(:groups AS text[])
      )
  {extra}
ORDER BY {order}
LIMIT :limit
"""


@dataclass(frozen=True)
class Hit:
    chunk_id: int
    version_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    version_number: int
    section_id: str
    position: int
    page: int | None
    path: str
    content: str


def keyword_query(question: str) -> str | None:
    """An OR query over the distinctive words of the question, or None if there are none.

    Kept: words of four letters or more, anything with a digit (codes, article numbers) and
    short acronyms written in capitals. Dropped: common words that match almost every chunk.
    """
    seen: dict[str, None] = {}
    for token in re.findall(r"\w+", question):
        word = token.lower()
        distinctive = (
            len(word) >= 4
            or any(ch.isdigit() for ch in word)
            or (token.isupper() and len(token) >= 2)
        )
        if distinctive and word not in STOPWORDS:
            seen.setdefault(word, None)
    tokens = list(seen)[:MAX_KEYWORDS]
    return " | ".join(tokens) if tokens else None


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.7g}" for value in vector) + "]"


def _hit(row: object) -> Hit:
    values = row._mapping  # type: ignore[attr-defined]
    return Hit(
        chunk_id=values["id"],
        version_id=values["version_id"],
        document_id=values["document_id"],
        document_name=values["document_name"],
        version_number=values["version_number"],
        section_id=values["section_id"],
        position=values["position"],
        page=values["page"],
        path=values["path"],
        content=values["content"],
    )


async def search(
    session: AsyncSession,
    identity: Identity,
    question: str,
    query_vector: list[float],
    *,
    document_id: uuid.UUID | None = None,
    version: int | None = None,
    limit: int = 5,
) -> list[Hit]:
    """Return the best `limit` chunks the caller may read, best first.

    By default only active versions are searched. With `document_id` the search is limited to
    that document, and with `version` as well it targets that (possibly historical) version.
    """
    params: dict[str, object] = {
        "is_admin": identity.is_admin,
        "user_id": identity.user_id,
        "groups": list(identity.groups),
        "limit": CANDIDATES_PER_SEARCH,
    }
    if document_id is None:
        scope = "v.status = 'active'"
    elif version is None:
        scope = "c.document_id = :document_id AND v.status = 'active'"
        params["document_id"] = document_id
    else:
        scope = "c.document_id = :document_id AND v.number = :version"
        params["document_id"] = document_id
        params["version"] = version

    # Filtered HNSW searches may need to keep scanning to fill the limit (pgvector 0.8+).
    await session.execute(text("SELECT set_config('hnsw.iterative_scan', 'relaxed_order', true)"))
    vector_rows = await session.execute(
        text(
            _SELECT.format(
                scope=scope,
                extra="",
                order="c.embedding <=> CAST(CAST(:query_vector AS text) AS halfvec)",
            )
        ),
        {**params, "query_vector": _vector_literal(query_vector)},
    )
    ranked = [_hit(row) for row in vector_rows]

    keywords = keyword_query(question)
    lexical: list[Hit] = []
    if keywords:
        lexical_rows = await session.execute(
            text(
                _SELECT.format(
                    scope=scope,
                    extra="AND c.tsv @@ to_tsquery('simple', :tsquery)",
                    order="ts_rank_cd(c.tsv, to_tsquery('simple', :tsquery)) DESC, c.id",
                )
            ),
            {**params, "tsquery": keywords},
        )
        lexical = [_hit(row) for row in lexical_rows]

    return _fuse([ranked, lexical])[:limit]


def _fuse(rankings: list[list[Hit]]) -> list[Hit]:
    """Reciprocal rank fusion: a chunk ranked high by either search floats to the top."""
    scores: dict[int, float] = {}
    by_id: dict[int, Hit] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1.0 / (RRF_K + rank)
            by_id[hit.chunk_id] = hit
    ordered = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))
    return [by_id[chunk_id] for chunk_id in ordered]
