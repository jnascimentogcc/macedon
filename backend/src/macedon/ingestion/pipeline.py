"""Ingestion of one document version: extract, chunk, embed, index, activate."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from macedon.audit import record_audit
from macedon.db.identity import Identity, apply_identity
from macedon.db.models import Document, DocumentVersion
from macedon.documents.storage import ObjectStore
from macedon.ingestion.chunking import Chunk, chunk_document
from macedon.ingestion.embeddings import EmbeddingError, EmbeddingProvider, TransientEmbeddingError
from macedon.ingestion.extract import Block, ExtractionError
from macedon.ingestion.sandbox import extract_isolated

# The worker is trusted: it writes chunks, which no API request is allowed to do.
WORKER = Identity("ingestion-worker", is_admin=True)

Extractor = Callable[[bytes, str], Awaitable[list[Block]]]


class TransientIngestionError(Exception):
    """A temporary failure (for example the embeddings provider is down); retry later."""


@dataclass(frozen=True)
class IngestionDeps:
    engine: AsyncEngine
    store: ObjectStore
    embedder: EmbeddingProvider
    extractor: Extractor = extract_isolated


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.7g}" for value in vector) + "]"


async def ingest_version(version_id: uuid.UUID, deps: IngestionDeps) -> None:
    """Index a version that is `processing`. Safe to call again: other states are ignored.

    Permanent problems mark the version `failed` and leave the active version untouched;
    temporary ones raise TransientIngestionError and leave it `processing` for a retry.
    """
    sessions = async_sessionmaker(deps.engine, expire_on_commit=False)
    async with sessions() as session:
        await apply_identity(session, WORKER)
        version = await session.get(DocumentVersion, version_id)
        if version is None or version.status != "processing":
            return
        document = await session.get(Document, version.document_id)
        if document is None:
            return
        if document.archived_at is not None:
            await _fail(session, version, "the document was archived before indexing finished")
            await session.commit()
            return
        key, doc_type, name = version.storage_key, document.doc_type, document.name

    try:
        chunks, vectors, reused = await _prepare(deps, key, doc_type, name)
    except TransientEmbeddingError as exc:
        raise TransientIngestionError(str(exc)) from exc
    except (ExtractionError, EmbeddingError) as exc:
        await _mark_failed(sessions, version_id, str(exc))
        return

    async with sessions() as session:
        await apply_identity(session, WORKER)
        version = await session.get(DocumentVersion, version_id)
        document = await session.get(Document, version.document_id) if version else None
        if version is None or document is None or version.status != "processing":
            return
        if document.archived_at is not None:
            await _fail(session, version, "the document was archived before indexing finished")
            await session.commit()
            return
        await _write_chunks(session, version, document, chunks, vectors, deps.embedder.model)
        activated = await _activate_or_shelve(session, version)
        await record_audit(
            session,
            WORKER,
            "ingest",
            document_id=document.id,
            version_id=version.id,
            details={
                "chunks": len(chunks),
                "embeddings_reused": reused,
                "activated": activated,
            },
        )
        await session.commit()


async def _prepare(
    deps: IngestionDeps, key: str, doc_type: str, document_name: str
) -> tuple[list[Chunk], dict[str, list[float]], int]:
    """Everything slow and fallible happens here, before any chunk is written."""
    data = await deps.store.get(key)
    blocks = await deps.extractor(data, doc_type)
    chunks = chunk_document(blocks, document_name)
    if not chunks:
        raise ExtractionError("the document has no indexable text")

    hashes = sorted({chunk.content_hash for chunk in chunks})
    async with async_sessionmaker(deps.engine)() as session:
        await apply_identity(session, WORKER)
        result = await session.execute(
            text(
                "SELECT DISTINCT content_hash FROM chunks "
                "WHERE embedding_model = :model AND content_hash = ANY(:hashes)"
            ),
            {"model": deps.embedder.model, "hashes": hashes},
        )
        existing = {row[0] for row in result}

    missing = {c.content_hash: c.embedding_text for c in chunks if c.content_hash not in existing}
    texts = list(missing.values())
    embedded = await deps.embedder.embed(texts) if texts else []
    if len(embedded) != len(texts):
        raise EmbeddingError("the provider returned the wrong number of embeddings")
    return chunks, dict(zip(missing, embedded, strict=True)), len(existing)


async def _write_chunks(
    session: AsyncSession,
    version: DocumentVersion,
    document: Document,
    chunks: list[Chunk],
    vectors: dict[str, list[float]],
    model: str,
) -> None:
    base = {
        "version": version.id,
        "document": document.id,
        "model": model,
        "users": document.acl_users,
        "groups": document.acl_groups,
    }
    fresh = [c for c in chunks if c.content_hash in vectors]
    reused = [c for c in chunks if c.content_hash not in vectors]
    columns = (
        "version_id, document_id, section_id, position, page, path, content, content_hash, "
        "embedding_model, acl_users, acl_groups, embedding"
    )
    if fresh:
        await session.execute(
            text(
                f"INSERT INTO chunks ({columns}) VALUES (:version, :document, :section, :position, "  # noqa: S608
                ":page, :path, :content, :hash, :model, :users, :groups, "
                "CAST(CAST(:embedding AS text) AS halfvec))"
            ),
            [
                {
                    **base,
                    "section": c.section_id,
                    "position": c.position,
                    "page": c.page,
                    "path": c.path,
                    "content": c.content,
                    "hash": c.content_hash,
                    "embedding": _vector_literal(vectors[c.content_hash]),
                }
                for c in fresh
            ],
        )
    for c in reused:
        # Copy the embedding of a chunk with identical embedded text instead of paying for it again.
        await session.execute(
            text(
                f"INSERT INTO chunks ({columns}) "  # noqa: S608
                "SELECT CAST(:version AS uuid), CAST(:document AS uuid), "
                "CAST(:section AS varchar), CAST(:position AS integer), "
                "CAST(:page AS integer), CAST(:path AS text), "
                "CAST(:content AS text), CAST(:hash AS varchar), CAST(:model AS varchar), "
                "CAST(:users AS text[]), CAST(:groups AS text[]), embedding FROM chunks "
                "WHERE content_hash = CAST(:hash AS varchar) "
                "AND embedding_model = CAST(:model AS varchar) LIMIT 1"
            ),
            {
                **base,
                "section": c.section_id,
                "position": c.position,
                "page": c.page,
                "path": c.path,
                "content": c.content,
                "hash": c.content_hash,
            },
        )


async def _activate_or_shelve(session: AsyncSession, version: DocumentVersion) -> bool:
    """Atomic switch, in the same transaction that wrote the chunks.

    The new version replaces the active one unless a newer version is already active, in which
    case it is kept as `archived`: indexed and available for rollback, but not answering.
    """
    newer_active = (
        await session.execute(
            select(DocumentVersion.id).where(
                DocumentVersion.document_id == version.document_id,
                DocumentVersion.status == "active",
                DocumentVersion.number > version.number,
            )
        )
    ).first()
    if newer_active is not None:
        version.status = "archived"
        await session.flush()
        return False
    await session.execute(
        update(DocumentVersion)
        .where(
            DocumentVersion.document_id == version.document_id,
            DocumentVersion.status == "active",
        )
        .values(status="archived")
    )
    version.status = "active"
    await session.flush()
    return True


async def _fail(session: AsyncSession, version: DocumentVersion, reason: str) -> None:
    version.status = "failed"
    version.error = reason[:500]
    await session.flush()
    await record_audit(
        session,
        WORKER,
        "ingest_failed",
        document_id=version.document_id,
        version_id=version.id,
        details={"error": version.error},
    )


async def _mark_failed(
    sessions: async_sessionmaker[AsyncSession], version_id: uuid.UUID, reason: str
) -> None:
    async with sessions() as session:
        await apply_identity(session, WORKER)
        version = await session.get(DocumentVersion, version_id)
        if version is not None and version.status == "processing":
            await _fail(session, version, reason)
            await session.commit()


async def fail_version(engine: AsyncEngine, version_id: uuid.UUID, reason: str) -> None:
    """Give up on a version after retries are exhausted."""
    await _mark_failed(async_sessionmaker(engine, expire_on_commit=False), version_id, reason)


async def find_stale_versions(engine: AsyncEngine, older_than: timedelta) -> list[uuid.UUID]:
    """Versions still `processing` long after upload, whose job was probably lost.

    The upload commits before it enqueues, so a crash in between leaves a version no job knows
    about. Enqueuing it again is safe: ingestion ignores versions that are no longer processing,
    and the job id (the version id) stops a live job from being duplicated.
    """
    async with async_sessionmaker(engine)() as session:
        await apply_identity(session, WORKER)
        result = await session.execute(
            text(
                "SELECT id FROM document_versions "
                "WHERE status = 'processing' "
                "AND created_at < now() - make_interval(secs => :seconds) ORDER BY created_at"
            ),
            {"seconds": older_than.total_seconds()},
        )
        return [row[0] for row in result]
