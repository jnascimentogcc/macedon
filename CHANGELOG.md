# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/). Before 1.0.0, minor versions may include breaking changes.

## [Unreleased]

## [0.3.0] - 2026-11-17

Better retrieval on Portuguese documents and on PDFs with real structure, and the whole stack runs in Docker.

### Upgrading

- Run `uv run alembic upgrade head` (migration 0004) and restart the API and the worker. The
  migration rebuilds the keyword index, which can take a while on a large database.
- With Docker, `docker compose up -d --build` does both: the new `migrate` service applies the
  migrations before the API and the worker start.
- An existing Keycloak realm is not re-imported. To sign in at `http://127.0.0.1:4200`, add
  `http://127.0.0.1:4200/*` as a redirect URI and `http://127.0.0.1:4200` as a web origin on the
  `macedon-web` client (or run `docker compose down -v` to start from scratch).
- PDFs ingested before this release keep their old structure (section paths, repeated page headers)
  until a new version is uploaded.

### Added

- **The API, the worker and the web interface run in Docker:** a backend image (API, Arq worker and
  Alembic migrations) and a frontend image (Angular build served by nginx), both as non-root users,
  and `migrate`, `api`, `worker` and `web` services in `docker-compose.yml`. `docker compose up -d
  --build` starts everything; `docker compose up -d postgres redis s3 keycloak` starts only the
  infrastructure, to run the rest on the host.
- The evaluation covers collection and tag scopes: 3 regional documents that compete with the
  group-wide ones, 16 scoped questions (ambiguous, subtree, tags, out of scope, access control)
  and scoped metrics in `baseline.json`. The 34 unscoped questions are unchanged.
- A Portuguese evaluation set (`eval/run_pt.py`: 3 documents, 13 questions on inflections, missing
  accents, identifiers and paraphrases) and a real-document set (`eval/run_real.py`: 27 questions
  over two public tender PDFs of 83 and 116 pages, kept outside the repository).
- A one-page overview of the design in the README.

### Changed

- **Keyword search folds accents and stems Portuguese** (`macedon_text` text search configuration,
  migration 0004) instead of matching identical words only. On the Portuguese set evidence@1 went
  from 0.82 to 1.00 and MRR from 0.91 to 1.00; the English baseline is unchanged (MRR 0.93).
- **PDF extraction:** page headers and footers repeated on the pages are dropped, and headings are
  also found by structural label ("Cláusula 5.ª", "Artigo 10.º", "Chapter IV"), with the title line
  merged in whatever its size and the label setting the depth. On the real PDFs the specifications
  went from 2 headings and 3 section paths to 27 and 28, chunks carrying header or footer text from
  75 and 96 to 0, so citations now name the clause instead of the cover title. Spans that sit apart
  without a space are no longer glued together ("b)Encargos"). Retrieval metrics on the real set did
  not move beyond noise (evidence@5 0.96, MRR 0.88).
- Token estimates count letters, digits and punctuation separately instead of a flat 4 characters
  per token. The flat rule undercounted tables, codes and dates by about half, so a section or the
  context budget could hold twice the intended tokens; oversized text without punctuation is cut by
  the same estimate.
- The API's CORS setting and the Keycloak client accept `http://127.0.0.1:4200` as well as
  `http://localhost:4200`.
- Dependency updates (Dependabot): `pymupdf` 2.1, `sqlalchemy` 2.1.8, `boto3`, `ruff`, `uv-build`,
  and in the frontend `jsdom` 31 (major), `vitest` 5.1, `@angular/cli` and `@angular/build` 22.2.x,
  `@tailwindcss/postcss` 4.3.4. Extraction results with `pymupdf` 2.1 are identical to 2.0 on the
  real PDFs.

### Fixed

- Signing in at `http://127.0.0.1:4200` failed with "Invalid parameter: redirect_uri", because only
  `localhost:4200` was accepted.

### Evaluated, not adopted

- A cosine-distance relevance floor to send no sources for unanswerable questions: evidence found
  only by vector search sits as far as 0.69 while the nearest chunk of an unanswerable question is
  at 0.50 to 0.64, so no threshold separates them (see `backend/eval/README.md`).

## [0.2.0] - 2026-11-03

The groups a document is shared with can now be changed after the upload.

### Upgrading

Run `uv run alembic upgrade head` (migration 0003) and restart the API and the worker.

### Added

- **Editing who a document is shared with:** `PATCH /documents/{id}` accepts `acl_groups`, and the
  edit dialog has a group picker (the upload form uses the same one). The change is applied to the
  document and to every chunk copy in one transaction, takes effect on search at once, and is
  audited as `acl_update`. Groups must be known (`MACEDON_KNOWN_GROUPS` or the caller's own), except
  ones the document already has, which can always be kept or dropped.
- A Screenshots section in the README.

### Fixed

- Answers are asked to be plain text: the interface shows them as written, so Markdown such as
  `**bold**` appeared with literal asterisks. The evaluation was re-run: retrieval is unchanged
  (evidence in the top 5 for every answerable question, MRR 0.93, no ACL leaks), answer
  correctness is 0.94 as before, and no answer contains Markdown any more (7 did).

### Changed

- Migration 0003: the owner of a document can update the ACL columns of its chunks; the
  application role can no longer update any other chunk column.
- Secondary text uses a darker token to reach the 4.5:1 contrast the UI spec requires, and controls
  grow to 44px on narrow screens and touch devices.

## [0.1.1] - 2026-11-03

Maintenance release: dependency updates and a packaging fix. No behaviour changes.

### Changed

- Updated runtime and build dependencies: `uvicorn` 0.54, `sqlalchemy` 2.1.6, `pyjwt` 2.15.1,
  `uv-build` 0.13, `@ng-icons/core` and `@ng-icons/lucide` 36. The full backend test suite and the
  frontend build and tests pass with them.
- Updated GitHub Actions: `actions/checkout` 7, `actions/setup-node` 7 and `astral-sh/setup-uv` 7.
- Dependabot no longer proposes TypeScript major updates (Angular 22 supports only TypeScript 6.0)
  or updates to `ragas`, `langchain-community` and `langchain-openai`, which the evaluation group
  pins on purpose.

### Fixed

- `uv build` of the backend package failed because `pyproject.toml` pointed its `readme` at a file
  outside the package; the field was removed.

## [0.1.0] - 2026-11-03

First release: a working document RAG platform with a secure foundation, a web interface and an
evaluation baseline.

### Added

- **Documents and versions:** upload of PDF, DOCX and TXT (type detected from the bytes, size limit),
  deduplication by file hash, one active version per document, atomic version switch, rollback and
  soft delete. Endpoints: `POST|GET /documents`, `GET|PATCH /documents/{id}`,
  `POST|GET /documents/{id}/versions`, `POST /documents/{id}/versions/{v}/activate`,
  `DELETE /documents/{id}`.
- **Asynchronous ingestion:** Arq worker over Redis with extraction in an isolated subprocess,
  structural chunking, OpenAI embeddings with reuse by text hash, and recovery of versions stuck in
  `processing`.
- **Questions with citations:** `POST /query` with hybrid search (vector and keyword, fused by
  reciprocal rank), expansion to the section or a neighbour window, delimited and escaped sources,
  `[n]` citations and per-user rate limiting. No reranker yet (deferred decision).
- **Access control:** JWT validation against any OIDC provider (Keycloak in the dev stack), ACL by
  owner and groups applied inside the search SQL, Postgres Row-Level Security as a second barrier,
  and an audit log.
- **Organization:** collections tree (up to 4 levels, managed by administrators) and normalized
  tags; `GET /documents` and `POST /query` can be scoped by collection subtree and tags. Collections
  never grant access. Endpoints: `GET|POST /collections`, `PATCH|DELETE /collections/{id}`.
- **Group sharing:** `GET /groups` and the `MACEDON_KNOWN_GROUPS` setting; uploads naming unknown
  groups are rejected.
- **Web interface:** Angular, Tailwind CSS and SpartanNG client with sign-in (Authorization Code +
  PKCE), document list and upload, document detail with versions, collections and tags, and an ask
  screen with sources.
- **Evaluation baseline:** synthetic corpus, 34 questions, retrieval metrics and RAGAS scoring
  (`backend/eval/`).
- **Tooling:** local stack with Docker Compose (Postgres with pgvector, Redis, SeaweedFS, Keycloak),
  GitHub Actions for backend and frontend, Dependabot, and a step-by-step installation guide in the
  README.

### Known limitations

- The groups a document is shared with can only be set at upload.
- Per-user rate limiting is in-process, so it does not span several API instances.
- The embedding model and its dimension (3072) are fixed once documents are indexed.
- The web interface has not been reviewed visually at every breakpoint or in dark mode.
- The dev stack is not hardened and must not be exposed.

[Unreleased]: https://github.com/jnascimentogcc/macedon/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/jnascimentogcc/macedon/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/jnascimentogcc/macedon/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/jnascimentogcc/macedon/releases/tag/v0.1.0
