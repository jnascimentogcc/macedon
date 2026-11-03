"""Retrieval and answer baseline over the synthetic corpus, using the real providers.

    uv run python eval/run.py [--top-k 5] [--out eval/results/baseline.json]

It ingests the corpus into the dev database (it TRUNCATES it first and again at the end), asks every
question through the real API stack, and writes one JSON file with the per-question outcome and
the aggregate metrics. It calls paid APIs and needs MACEDON_OPENAI_API_KEY, so it is a manual job
and never part of the pull-request CI.
"""

import argparse
import asyncio
import io
import json
import statistics
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from corpus import DOCS, QUESTIONS, Doc, Question
from docx import Document
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from macedon.auth import get_identity
from macedon.config import Settings, get_settings
from macedon.db.identity import Identity
from macedon.db.session import get_engine
from macedon.documents.queue import get_job_queue
from macedon.documents.storage import get_object_store
from macedon.ingestion.embeddings import OpenAIEmbeddingProvider
from macedon.ingestion.pipeline import IngestionDeps, ingest_version
from macedon.main import create_app

ADMIN = Identity("eval-admin", is_admin=True)
OUTSIDER = Identity("eval-outsider", groups=("nobody",))
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def build_docx(doc: Doc) -> bytes:
    document = Document()
    for heading, paragraphs in doc.sections:
        document.add_heading(heading, level=1)
        for paragraph in paragraphs:
            document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def evidence_rank(sources: list[dict[str, Any]], question: Question) -> int | None:
    """1-based rank of the first source containing the evidence, or None."""
    for rank, source in enumerate(sources, start=1):
        if (
            question.evidence
            and question.evidence.lower() in " ".join(source["text"].split()).lower()
        ):
            return rank
    return None


def aggregate(rows: list[dict[str, Any]], top_k: int) -> dict[str, Any]:
    answerable = [r for r in rows if r["document"] is not None]
    no_answer = [r for r in rows if r["document"] is None]
    ranks = [r["evidence_rank"] for r in answerable]
    return {
        "questions": len(rows),
        "answerable": len(answerable),
        "top_k": top_k,
        f"evidence_hit@{top_k}": sum(rank is not None for rank in ranks) / len(answerable),
        "evidence_hit@1": sum(rank == 1 for rank in ranks) / len(answerable),
        "mrr": statistics.fmean(1 / rank if rank else 0.0 for rank in ranks),
        "document_hit": sum(r["document_hit"] for r in answerable) / len(answerable),
        "answered_with_citation": sum(r["cited"] > 0 for r in answerable) / len(answerable),
        "no_answer_abstained": (
            sum(r["cited"] == 0 for r in no_answer) / len(no_answer) if no_answer else None
        ),
        "acl_leaks": sum(r.get("acl_leak", False) for r in rows),
        "latency_p50_s": statistics.median(r["latency_s"] for r in rows),
    }


def write_report(out: Path, report: dict[str, Any]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


async def main(top_k: int, out: Path) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    owner = create_async_engine(settings.migration_database_url)
    store = get_object_store()
    embedder = OpenAIEmbeddingProvider.from_settings(settings)
    current = [ADMIN]
    pending: list[uuid.UUID] = []

    class InlineQueue:
        async def enqueue_ingestion(self, version_id: uuid.UUID) -> None:
            pending.append(version_id)

    app = create_app()
    app.dependency_overrides[get_identity] = lambda: current[0]
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_job_queue] = lambda: InlineQueue()
    app.dependency_overrides[get_settings] = lambda: Settings(
        query_rate_limit_per_minute=10_000, known_groups=["engineering", "legal"]
    )
    truncate = text(
        "TRUNCATE chunks, document_versions, documents, audit_log RESTART IDENTITY CASCADE"
    )

    async with owner.begin() as conn:
        await conn.execute(truncate)
    rows: list[dict[str, Any]] = []
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://eval", timeout=180
        ) as c:
            for doc in DOCS:
                response = await c.post(
                    "/documents",
                    files={"file": (f"{doc.name}.docx", build_docx(doc), DOCX_MIME)},
                    data={"name": doc.name, **({"acl_groups": [doc.group]} if doc.group else {})},
                )
                response.raise_for_status()
            for version_id in pending:
                await ingest_version(version_id, IngestionDeps(engine, store, embedder))
            async with owner.connect() as conn:
                counts = (await conn.execute(text("SELECT count(*) FROM chunks"))).scalar_one()
            print(f"ingested {len(DOCS)} documents, {counts} chunks")

            for index, question in enumerate(QUESTIONS, start=1):
                started = time.monotonic()
                response = await c.post(
                    "/query", json={"question": question.question, "top_k": top_k}
                )
                response.raise_for_status()
                body = response.json()
                sources = body["sources"]
                rank = evidence_rank(sources, question)
                row: dict[str, Any] = {
                    "question": question.question,
                    "document": question.document,
                    "evidence": question.evidence,
                    "reference": question.reference,
                    "tags": question.tags,
                    "answer": body["answer"],
                    "contexts": [s["text"] for s in sources],
                    "source_documents": [s["document_name"] for s in sources],
                    "evidence_rank": rank,
                    "document_hit": question.document in {s["document_name"] for s in sources},
                    "cited": sum(s["cited"] for s in sources),
                    "latency_s": round(time.monotonic() - started, 2),
                }
                for tag in question.tags:
                    if tag.startswith("acl:"):
                        current[0] = OUTSIDER
                        leak = await c.post(
                            "/query", json={"question": question.question, "top_k": top_k}
                        )
                        current[0] = ADMIN
                        row["acl_leak"] = any(
                            s["document_name"] == question.document for s in leak.json()["sources"]
                        )
                rows.append(row)
                print(
                    f"[{index:02d}/{len(QUESTIONS)}] rank={rank} cited={row['cited']} "
                    f"{question.question}"
                )
    finally:
        async with owner.begin() as conn:
            await conn.execute(truncate)
        await engine.dispose()
        await owner.dispose()

    metrics = aggregate(rows, top_k)
    report = {
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "models": {"llm": settings.llm_model, "embedding": settings.embedding_model},
        "metrics": metrics,
        "rows": rows,
    }
    await asyncio.to_thread(write_report, out, report)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--out", type=Path, default=Path("eval/results/baseline.json"))
    args = parser.parse_args()
    asyncio.run(main(args.top_k, args.out))
