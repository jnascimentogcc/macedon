"""Retrieval check over real PDFs (see `corpus_real.py` for what they are and why).

    uv run python eval/run_real.py --dir <folder with the two PDFs> [--top-k 5] [--label base]

Checks every evidence phrase against the raw PDF text first (free), then ingests the PDFs into the
dev database (it TRUNCATES it first and again at the end), asks every question through the real API
stack and writes `eval/results/real_<label>.json` with the metrics, overall and per tag, and the
ranks of the evidence per question. Document content is sent to the embedding and generation APIs,
so use only documents you are allowed to send. Paid APIs: a manual job, like `run.py`.
"""

import argparse
import asyncio
import re
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pymupdf
from corpus_real import DOCUMENT_FILES, REAL_QUESTIONS
from httpx import ASGITransport, AsyncClient
from run import ADMIN, evidence_rank, write_report
from run_pt import metrics
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


def _normalize(value: str) -> str:
    return " ".join(value.split()).lower()


def check_evidence(folder: Path) -> list[str]:
    """Evidence phrases that are not in the raw text of the PDF they are said to come from."""
    raw: dict[str, str] = {}
    for name, filename in DOCUMENT_FILES.items():
        with pymupdf.open(folder / filename) as pdf:  # type: ignore[no-untyped-call]
            raw[name] = _normalize(" ".join(page.get_text() for page in pdf))
    return [
        f"{q.document}: {q.evidence}"
        for q in REAL_QUESTIONS
        if q.document and q.evidence and _normalize(q.evidence) not in raw[q.document]
    ]


async def main(folder: Path, top_k: int, label: str) -> None:
    missing = check_evidence(folder)
    if missing:
        print("evidence phrases not found in the PDFs, fix corpus_real.py:")
        print("\n".join(f"  {line}" for line in missing))
        sys.exit(1)

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
    chunk_count = 0
    ingest_seconds = 0.0
    async with owner.begin() as conn:
        await conn.execute(truncate)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://eval", timeout=300
        ) as c:
            for name, filename in DOCUMENT_FILES.items():
                data = await asyncio.to_thread((folder / filename).read_bytes)
                response = await c.post(
                    "/documents",
                    files={"file": (filename, data, "application/pdf")},
                    data={"name": name},
                )
                response.raise_for_status()
            started = time.monotonic()
            for version_id in pending:
                await ingest_version(version_id, IngestionDeps(engine, store, embedder))
            ingest_seconds = round(time.monotonic() - started, 1)
            async with owner.connect() as conn:
                chunk_count = (await conn.execute(text("SELECT count(*) FROM chunks"))).scalar_one()
            print(f"ingested {len(DOCUMENT_FILES)} PDFs, {chunk_count} chunks, {ingest_seconds}s")

            for index, question in enumerate(REAL_QUESTIONS, start=1):
                began = time.monotonic()
                response = await c.post(
                    "/query", json={"question": question.question, "top_k": top_k}
                )
                response.raise_for_status()
                body = response.json()
                sources = body["sources"]
                rank = evidence_rank(sources, question.evidence)
                names = [s["document_name"] for s in sources]
                rows.append(
                    {
                        "question": question.question,
                        "tags": question.tags,
                        "document": question.document,
                        "evidence": question.evidence,
                        "reference": question.reference,
                        "evidence_rank": rank,
                        "document_hit": question.document in names if question.document else None,
                        "sources": [
                            {
                                "document": s["document_name"],
                                "page": s["page"],
                                "section": s["section"],
                            }
                            for s in sources
                        ],
                        "cited": sum(s["cited"] for s in sources),
                        "answer": body["answer"],
                        "latency_s": round(time.monotonic() - began, 2),
                    }
                )
                print(f"[{index:02d}/{len(REAL_QUESTIONS)}] rank={rank} {question.question}")
    finally:
        async with owner.begin() as conn:
            await conn.execute(truncate)
        await engine.dispose()
        await owner.dispose()

    per_tag = {
        tag: metrics([r for r in rows if tag in r["tags"]], top_k)
        for tag in sorted({t for q in REAL_QUESTIONS for t in q.tags if t != "no-answer"})
    }
    report = {
        "label": label,
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "models": {"llm": settings.llm_model, "embedding": settings.embedding_model},
        "chunks": chunk_count,
        "ingest_seconds": ingest_seconds,
        "metrics": {
            **metrics(rows, top_k),
            "document_hit": sum(bool(r["document_hit"]) for r in rows if r["document"])
            / sum(1 for r in rows if r["document"]),
        },
        "per_tag": per_tag,
        "rows": rows,
    }
    out = Path(f"eval/results/real_{label}.json")
    await asyncio.to_thread(write_report, out, report)
    print(re.sub(r"\n\s+", " ", str(report["metrics"])))
    for tag, values in per_tag.items():
        print(
            f"{tag:15} n={values['questions']:2} hit@{top_k}={values[f'evidence_hit@{top_k}']:.2f} "
            f"hit@1={values['evidence_hit@1']:.2f} mrr={values['mrr']:.2f}"
        )
    print(f"no_answer_abstained={report['metrics']['no_answer_abstained']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, required=True, help="folder with the two PDFs")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--label", default="base")
    args = parser.parse_args()
    asyncio.run(main(args.dir, args.top_k, args.label))
