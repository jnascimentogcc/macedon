"""Portuguese retrieval check, to compare text search configurations.

    uv run python eval/run_pt.py [--top-k 5] [--out eval/results/pt_<label>.json] [--label simple]

Ingests `corpus_pt.PT_DOCS` into the dev database (it TRUNCATES it first and again at the end), asks
every question through the real API stack and writes the retrieval metrics, overall and per tag.
Run it before and after a change to the text search configuration and compare the two files. It
calls paid APIs (embeddings and generation) and needs MACEDON_OPENAI_API_KEY, so it is a manual
job, like `run.py`.
"""

import argparse
import asyncio
import json
import statistics
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from corpus_pt import PT_DOCS, PT_QUESTIONS
from httpx import ASGITransport, AsyncClient
from run import ADMIN, DOCX_MIME, build_docx, evidence_rank, write_report
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from macedon.auth import get_identity
from macedon.config import Settings, get_settings
from macedon.db.session import get_engine
from macedon.documents.queue import get_job_queue
from macedon.documents.storage import get_object_store
from macedon.ingestion.embeddings import OpenAIEmbeddingProvider
from macedon.ingestion.pipeline import IngestionDeps, ingest_version
from macedon.main import create_app


def metrics(rows: list[dict[str, Any]], top_k: int) -> dict[str, Any]:
    answerable = [r for r in rows if r["document"] is not None]
    no_answer = [r for r in rows if r["document"] is None]
    ranks = [r["evidence_rank"] for r in answerable]
    result: dict[str, Any] = {
        "questions": len(rows),
        f"evidence_hit@{top_k}": sum(rank is not None for rank in ranks) / len(answerable),
        "evidence_hit@1": sum(rank == 1 for rank in ranks) / len(answerable),
        "mrr": statistics.fmean(1 / rank if rank else 0.0 for rank in ranks),
        "no_answer_abstained": (
            sum(r["cited"] == 0 for r in no_answer) / len(no_answer) if no_answer else None
        ),
    }
    return result


async def main(top_k: int, out: Path, label: str) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    owner = create_async_engine(settings.migration_database_url)
    store = get_object_store()
    embedder = OpenAIEmbeddingProvider.from_settings(settings)
    pending: list[uuid.UUID] = []

    class InlineQueue:
        async def enqueue_ingestion(self, version_id: uuid.UUID) -> None:
            pending.append(version_id)

    app = create_app()
    app.dependency_overrides[get_identity] = lambda: ADMIN
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_job_queue] = lambda: InlineQueue()
    app.dependency_overrides[get_settings] = lambda: Settings(query_rate_limit_per_minute=10_000)
    truncate = text(
        "TRUNCATE chunks, document_versions, documents, collections, audit_log "
        "RESTART IDENTITY CASCADE"
    )

    rows: list[dict[str, Any]] = []
    async with owner.begin() as conn:
        await conn.execute(truncate)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://eval", timeout=180
        ) as c:
            for doc in PT_DOCS:
                response = await c.post(
                    "/documents",
                    files={"file": (f"{doc.name}.docx", build_docx(doc), DOCX_MIME)},
                    data={"name": doc.name},
                )
                response.raise_for_status()
            for version_id in pending:
                await ingest_version(version_id, IngestionDeps(engine, store, embedder))
            for index, question in enumerate(PT_QUESTIONS, start=1):
                response = await c.post(
                    "/query", json={"question": question.question, "top_k": top_k}
                )
                response.raise_for_status()
                body = response.json()
                rank = evidence_rank(body["sources"], question.evidence)
                rows.append(
                    {
                        "question": question.question,
                        "tags": question.tags,
                        "document": question.document,
                        "evidence": question.evidence,
                        "evidence_rank": rank,
                        "source_documents": [s["document_name"] for s in body["sources"]],
                        "cited": sum(s["cited"] for s in body["sources"]),
                        "answer": body["answer"],
                    }
                )
                print(f"[{index:02d}/{len(PT_QUESTIONS)}] rank={rank} {question.question}")
    finally:
        async with owner.begin() as conn:
            await conn.execute(truncate)
        await engine.dispose()
        await owner.dispose()

    per_tag: dict[str, Any] = {}
    for tag in sorted({t for q in PT_QUESTIONS for t in q.tags if t != "no-answer"}):
        subset = [r for r in rows if tag in r["tags"]]
        per_tag[tag] = metrics(subset, top_k)
    report = {
        "label": label,
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "models": {"llm": settings.llm_model, "embedding": settings.embedding_model},
        "metrics": metrics(rows, top_k),
        "per_tag": per_tag,
        "rows": rows,
    }
    await asyncio.to_thread(write_report, out, report)
    print(json.dumps({"metrics": report["metrics"], "per_tag": per_tag}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--label", default="simple", help="names this run, e.g. the text config")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    asyncio.run(
        main(args.top_k, args.out or Path(f"eval/results/pt_{args.label}.json"), args.label)
    )
