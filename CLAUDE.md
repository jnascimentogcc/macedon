# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository state

Phase 1 (secure foundation) is in progress. Layout: `backend/` (Python, uv), `deploy/` (dev Keycloak realm, Postgres init), `docker-compose.yml` (Postgres+pgvector, Redis, SeaweedFS as S3, Keycloak), `docs/` (`docs/vision.md` is the source of truth for the design). `frontend/` does not exist yet. Done so far: backend scaffold with CI, dev stack, initial schema migration with RLS, applied and covered by integration tests in `backend/tests/test_rls.py` (they run against the dev Postgres and skip if it is down). Use `127.0.0.1`, not `localhost`, for Postgres on Windows: `localhost` adds ~2s per connection. JWT auth, the per-request RLS session, audit helper and the document/version endpoints exist (`backend/src/macedon/documents/`). Ingestion queue: Arq; The Arq worker (`uv run arq macedon.worker.WorkerSettings`, needs `MACEDON_OPENAI_API_KEY`) runs `ingestion/pipeline.py`: extraction in an isolated subprocess (`ingestion/sandbox.py`, empty environment, timeout), structural chunking, OpenAI embeddings with reuse by text hash, then chunk writes and the version switch in one transaction. `POST /query` (`backend/src/macedon/query/`) embeds the question, runs vector and keyword search with the ACL written into the SQL (RLS stays on as a second barrier; both were checked to hold on their own), fuses with reciprocal rank, expands each hit to its section or a neighbour window, and asks the LLM with delimited, escaped sources and `[n]` citations. The audit entry is committed before the model call. There is no reranker yet (deferred). Per-user rate limiting is in-process. Config comes from `backend/.env` (see `.env.example`; every variable needs the `MACEDON_` prefix). Validated end to end with the real OpenAI API (upload, ingestion, answers with citations, a no-answer case, and a user outside the ACL getting no sources); a later run used real Keycloak tokens (`user_id` is the token `sub` UUID; dev scripts use the `macedon-dev-cli` password-grant client; Keycloak's `KC_HOSTNAME` is pinned so the issuer matches) and the Arq worker as a separate process over Redis. The JWKS provider keeps only `use=sig` keys because Keycloak also publishes an unreadable encryption key. A cron job in the worker (every 5 minutes) re-enqueues versions stuck in `processing` for over 15 minutes. The CI steps were replicated on Linux in a container; the GitHub-hosted workflow itself has not run yet. `GET /documents` lists documents (limit, offset, include_archived). Never insert into `audit_log` with `RETURNING`: only admins can read it, so use `record_audit`.

## Commands

Run from `backend/` unless noted.

```bash
uv sync                                  # install dependencies
uv run pytest                            # all tests
uv run pytest tests/test_health.py::test_health   # a single test
uv run ruff check . && uv run ruff format --check .
uv run mypy src tests
uv run alembic upgrade head              # needs the dev stack: `docker compose up -d` at the repo root
```

The API connects as the `macedon_app` role (not superuser, no BYPASSRLS) so Row-Level Security applies; migrations run as the schema owner (`MACEDON_MIGRATION_DATABASE_URL`). Each request/transaction must set `app.user_id`, `app.groups` and `app.is_admin` with `set_config(..., true)`; the ingestion worker runs with `app.is_admin = 'true'`.

## Language

All generated content is in English: README, docs, source code, comments, identifiers, commit messages. Only the chat with the user is in Portuguese.

## What the project is

Document RAG platform (repo name: Macedon): receives documents, chunks them preserving context, indexes them in a vector store and answers questions via API citing document, version, page and section. Also manages versioning and access control.

## Planned stack

Python + FastAPI (validates the JWT on every request); Postgres + pgvector (HNSW index) — no dedicated vector database at the start; S3-compatible storage for originals (SeaweedFS in the dev stack: MinIO no longer ships a community image) (one object per version); ingestion queue (Celery, RQ or Arq) with workers; extraction via PyMuPDF (PDF; headings by font size, tables come out as plain text) and python-docx (DOCX), direct read (TXT); Docling was deliberately left out (PyTorch and model downloads) and can replace the extractor later — initial formats: PDF, DOCX and TXT; OpenAI `text-embedding-3-large` embeddings; hybrid search (vector + Postgres full-text) with a reranker via external API, service still to be defined (candidate: Cohere Rerank; top 20–30 → top 5); generation with OpenAI LLMs (mid-tier, e.g. GPT-6.1 Terra; mini tier, e.g. GPT-6 Luna, for Contextual Retrieval); evaluation with RAGAS (30–50 questions). Pipeline written directly, **no LangChain/LlamaIndex**.

Ingestion is asynchronous (upload responds immediately, processing in a worker); querying runs directly in the API.

## Architecture invariants

- **No multi-tenant at the start** (simplification decision): there is no `tenant_id`; the ACL is by users and groups. If multi-tenant becomes a requirement, revisit the ACL, RLS and the vector query filter.
- **Expected volume:** ~5,000 documents per year; pgvector is more than enough. `text-embedding-3-large` has 3072 dimensions and pgvector's HNSW limits `vector` to 2000: decision is an embedding column of `halfvec(3072)` with an HNSW index, without reducing dimensions (plan B: `dimensions=1536`). The dimension is fixed; changing it requires reindexing.
- **Chunks belong to the version, not the document.** Tables: `documents` (identity, ACL), `document_versions` (SHA-256 hash, S3 path, status `processing|active|archived|failed`), `chunks` (text, embedding, `version_id`, `section_id`, `position`, text hash, `embedding_model`, permissions).
- **One active version per document.** Default search filters `status = 'active'`; a historical version only via an explicit parameter on `/query`.
- **Atomic switch:** a new version only becomes active when all its chunks are indexed; until then the previous one answers.
- **Deduplication** by file hash; **embedding reuse** by chunk text hash.
- **Soft delete:** `DELETE` archives versions (preserves audit).
- **The embedding model is recorded per chunk** and fixed from the start; changing it requires reindexing (in parallel, without taking search down).
- **Query security:** ACL copied to the chunks and applied *inside* the vector query (never post-filter), with Postgres Row-Level Security as a second barrier. Auth, ACL/RLS and audit are phase 1 priorities.
- **Prompt injection:** chunks delimited in the prompt and treated as data; no tools with side effects in the query flow.
- **Frontend:** Angular + Tailwind CSS + SpartanNG, for document management, versions and querying with sources. It is only an API client: no business or access rules in the frontend; OIDC login (Keycloak, Authorization Code + PKCE). The normative design system is `docs/ui-spec.md`; pages and flows go in separate feature specs. `docs/tech-stack.md` describes another project (STC) and does not apply to Macedon.
- **Inference is 100% external API, nothing local.** OpenAI is the default provider, but this is an open-source project: generation, embeddings and reranking sit behind own interfaces (`LLMProvider`, `EmbeddingProvider`, `Reranker`) configurable by provider/model/key. Never couple the pipeline to a specific SDK. Model names come from the OpenAI models page and change fast: revalidate before fixing them.
- **Identity:** Keycloak (OIDC/JWT) is the default provider, but it only authenticates and supplies claims (groups, roles). The API only validates the JWT, without depending on Keycloak-specific APIs, so the provider can be swapped. Authorization over documents/chunks (ACL + RLS) lives in the platform, never delegated to Keycloak.
- Upload: validate type from the bytes, size limit, parsing in an isolated worker.

## CI

GitHub Actions CI is part of the first code commit; do not add workflows before there is code to run. Start with lint/format, type checks, backend tests, the frontend build and a check that migrations apply from scratch; also enable Dependabot and secret scanning. Integration tests with Postgres + pgvector in a container come later. Do not run the RAGAS evaluation on every PR (it calls paid APIs and fork PRs have no secrets): keep it as a manual or scheduled job, and use mocked providers (`LLMProvider`, `EmbeddingProvider`) in PR tests.

## Chunking strategy

Adoption order: (1) structural splitting (section > paragraph > sentence; 500–800 tokens, 10–15% overlap; tables/lists whole), (2) document path prefix before embedding, (4) parent-child (index ~200 tokens, deliver the parent block), with (5) N±1 neighbor expansion as fallback for unstructured text. (3) Contextual Retrieval only if evaluation shows ambiguous chunks being missed. Semantic chunking by embeddings is out of scope.

Unified retrieval rule: each chunk stores `doc_id`, `section_id`, `position`; if the section fits in ~1500 tokens the whole section is sent, otherwise the neighbor window.

Any change to chunking, embedding model or reranker must be measured with the RAGAS evaluation set.

## Planned API

`POST /documents`, `GET /documents`, `GET /documents/{id}`, `POST|GET /documents/{id}/versions`, `POST /documents/{id}/versions/{v}/activate` (also rollback), `DELETE /documents/{id}`, `POST /query` (answer with sources: document, version, page, section).

## Open questions

None. Deferred decision: reranker service (see "Deferred decisions" in `docs/vision.md`; do not assume a provider). The README warns that document content is sent to external APIs, with no data masking.
