"""Retrieval and answer baseline over the synthetic corpus, using the real providers.

    uv run python eval/run.py [--top-k 5] [--out eval/results/baseline.json] [--scoped-only]

It ingests the corpus into the dev database (it TRUNCATES it first and again at the end), asks every
question through the real API stack, and writes one JSON file with the per-question outcome and
the aggregate metrics. It calls paid APIs and needs MACEDON_OPENAI_API_KEY, so it is a manual job
and never part of the pull-request CI.

The unscoped questions run first, on the original documents only. Then the regional documents are
ingested and the scoped questions (collection subtree and tags) run under `scoped` in the same
file. With `--scoped-only` the unscoped questions are skipped and the existing file keeps its
unscoped results.
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

from corpus import (
    ALL_DOCS,
    DOCS,
    QUESTIONS,
    SCOPED_DOCS,
    SCOPED_QUESTIONS,
    Doc,
    Question,
    ScopedQuestion,
    in_scope,
)
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


def evidence_rank(sources: list[dict[str, Any]], evidence: str | None) -> int | None:
    """1-based rank of the first source containing the evidence, or None."""
    for rank, source in enumerate(sources, start=1):
        if evidence and evidence.lower() in " ".join(source["text"].split()).lower():
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


def aggregate_scoped(rows: list[dict[str, Any]], top_k: int) -> dict[str, Any]:
    answerable = [r for r in rows if r["document"] is not None]
    no_answer = [r for r in rows if r["document"] is None]
    compared = [r for r in answerable if "unscoped_evidence_rank" in r]

    def hit(rank: int | None, k: int) -> bool:
        return rank is not None and rank <= k

    return {
        "questions": len(rows),
        "answerable": len(answerable),
        "top_k": top_k,
        f"scoped_evidence_hit@{top_k}": sum(hit(r["evidence_rank"], top_k) for r in answerable)
        / len(answerable),
        "scoped_evidence_hit@1": sum(hit(r["evidence_rank"], 1) for r in answerable)
        / len(answerable),
        "scoped_mrr": statistics.fmean(
            1 / r["evidence_rank"] if r["evidence_rank"] else 0.0 for r in answerable
        ),
        "out_of_scope_sources": sum(len(r["out_of_scope_sources"]) for r in rows),
        "out_of_scope_abstained": (
            sum(r["cited"] == 0 for r in no_answer) / len(no_answer) if no_answer else None
        ),
        "compared_questions": len(compared),
        "unscoped_evidence_hit@1": sum(hit(r["unscoped_evidence_rank"], 1) for r in compared)
        / len(compared),
        "scoped_evidence_hit@1_on_compared": sum(hit(r["evidence_rank"], 1) for r in compared)
        / len(compared),
        f"unscoped_evidence_hit@{top_k}": sum(
            hit(r["unscoped_evidence_rank"], top_k) for r in compared
        )
        / len(compared),
        f"scoped_evidence_hit@{top_k}_on_compared": sum(
            hit(r["evidence_rank"], top_k) for r in compared
        )
        / len(compared),
        "acl_leaks": sum(r.get("acl_leak", False) for r in rows),
        "latency_p50_s": statistics.median(r["latency_s"] for r in rows),
    }


def write_report(out: Path, report: dict[str, Any]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


async def main(top_k: int, out: Path, scoped_only: bool) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    owner = create_async_engine(settings.migration_database_url)
    store = get_object_store()
    embedder = OpenAIEmbeddingProvider.from_settings(settings)
    current = [ADMIN]
    pending: list[uuid.UUID] = []
    collection_ids: dict[str, str] = {}
    docs_by_name = {doc.name: doc for doc in ALL_DOCS}

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
        "TRUNCATE chunks, document_versions, documents, collections, audit_log "
        "RESTART IDENTITY CASCADE"
    )

    async def ensure_collection(c: AsyncClient, path: str) -> str:
        """Creates the collection and its ancestors on first use, returns its id."""
        parent = ""
        walked = ""
        for name in path.split("/"):
            walked = f"{walked}/{name}" if walked else name
            if walked not in collection_ids:
                response = await c.post(
                    "/collections", json={"name": name, "parent_id": parent or None}
                )
                response.raise_for_status()
                collection_ids[walked] = response.json()["id"]
            parent = collection_ids[walked]
        return parent

    async def ingest(c: AsyncClient, docs: list[Doc]) -> None:
        for doc in docs:
            data: dict[str, Any] = {"name": doc.name}
            if doc.group:
                data["acl_groups"] = [doc.group]
            if doc.tags:
                data["tags"] = doc.tags
            if doc.collection:
                data["collection_id"] = await ensure_collection(c, doc.collection)
            response = await c.post(
                "/documents",
                files={"file": (f"{doc.name}.docx", build_docx(doc), DOCX_MIME)},
                data=data,
            )
            response.raise_for_status()
        for version_id in pending:
            await ingest_version(version_id, IngestionDeps(engine, store, embedder))
        pending.clear()
        async with owner.connect() as conn:
            counts = (await conn.execute(text("SELECT count(*) FROM chunks"))).scalar_one()
        print(f"ingested {len(docs)} documents, {counts} chunks in total")

    async def ask(
        c: AsyncClient,
        question: str,
        scope: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], float]:
        started = time.monotonic()
        response = await c.post(
            "/query", json={"question": question, "top_k": top_k, **(scope or {})}
        )
        response.raise_for_status()
        return response.json(), round(time.monotonic() - started, 2)

    async def ask_as_outsider(
        c: AsyncClient, question: str, scope: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        current[0] = OUTSIDER
        try:
            body, _ = await ask(c, question, scope)
        finally:
            current[0] = ADMIN
        return list(body["sources"])

    async def run_unscoped(c: AsyncClient) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for index, question in enumerate(QUESTIONS, start=1):
            body, latency = await ask(c, question.question)
            sources = body["sources"]
            rank = evidence_rank(sources, question.evidence)
            row = unscoped_row(question, body, rank, latency)
            if any(tag.startswith("acl:") for tag in question.tags):
                leaked = await ask_as_outsider(c, question.question)
                row["acl_leak"] = any(s["document_name"] == question.document for s in leaked)
            rows.append(row)
            print(
                f"[{index:02d}/{len(QUESTIONS)}] rank={rank} cited={row['cited']} "
                f"{question.question}"
            )
        return rows

    async def run_scoped(c: AsyncClient) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for index, question in enumerate(SCOPED_QUESTIONS, start=1):
            scope: dict[str, Any] = {"tags": question.tags}
            if question.collection:
                scope["collection_id"] = collection_ids[question.collection]
            body, latency = await ask(c, question.question, scope)
            sources = body["sources"]
            rank = evidence_rank(sources, question.evidence)
            row = scoped_row(question, body, rank, latency)
            if question.compare_unscoped:
                unscoped, _ = await ask(c, question.question)
                row["unscoped_evidence_rank"] = evidence_rank(
                    unscoped["sources"], question.evidence
                )
                row["unscoped_source_documents"] = [s["document_name"] for s in unscoped["sources"]]
            if question.acl:
                leaked = await ask_as_outsider(c, question.question, scope)
                row["acl_leak"] = any(s["document_name"] == question.document for s in leaked)
            rows.append(row)
            print(
                f"[{index:02d}/{len(SCOPED_QUESTIONS)}] {question.kind} rank={rank} "
                f"cited={row['cited']} outside={len(row['out_of_scope_sources'])} "
                f"{question.question}"
            )
        return rows

    def unscoped_row(
        question: Question, body: dict[str, Any], rank: int | None, latency: float
    ) -> dict[str, Any]:
        sources = body["sources"]
        return {
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
            "latency_s": latency,
        }

    def scoped_row(
        question: ScopedQuestion, body: dict[str, Any], rank: int | None, latency: float
    ) -> dict[str, Any]:
        sources = body["sources"]
        names = [s["document_name"] for s in sources]
        return {
            "question": question.question,
            "kind": question.kind,
            "collection": question.collection,
            "scope_tags": question.tags,
            "document": question.document,
            "evidence": question.evidence,
            "reference": question.reference,
            "answer": body["answer"],
            "contexts": [s["text"] for s in sources],
            "source_documents": names,
            "evidence_rank": rank,
            "document_hit": question.document in set(names),
            "cited": sum(s["cited"] for s in sources),
            "out_of_scope_sources": [
                name
                for name in names
                if not in_scope(docs_by_name[name], question.collection, question.tags)
            ],
            "latency_s": latency,
        }

    async with owner.begin() as conn:
        await conn.execute(truncate)
    rows: list[dict[str, Any]] = []
    scoped_rows: list[dict[str, Any]] = []
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://eval", timeout=180
        ) as c:
            await ingest(c, DOCS)
            if not scoped_only:
                rows = await run_unscoped(c)
            await ingest(c, SCOPED_DOCS)
            scoped_rows = await run_scoped(c)
    finally:
        async with owner.begin() as conn:
            await conn.execute(truncate)
        await engine.dispose()
        await owner.dispose()

    scoped_metrics = aggregate_scoped(scoped_rows, top_k)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    scoped = {"date": now, "metrics": scoped_metrics, "rows": scoped_rows}
    if scoped_only:
        report = json.loads(await asyncio.to_thread(out.read_text, encoding="utf-8"))
        report["scoped"] = scoped
    else:
        report = {
            "date": now,
            "models": {"llm": settings.llm_model, "embedding": settings.embedding_model},
            "metrics": aggregate(rows, top_k),
            "rows": rows,
            "scoped": scoped,
        }
    await asyncio.to_thread(write_report, out, report)
    print(json.dumps(report["metrics"], indent=2))
    print(json.dumps(scoped_metrics, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--out", type=Path, default=Path("eval/results/baseline.json"))
    parser.add_argument(
        "--scoped-only",
        action="store_true",
        help="skip the unscoped questions and keep their results from the existing file",
    )
    args = parser.parse_args()
    asyncio.run(main(args.top_k, args.out, args.scoped_only))
