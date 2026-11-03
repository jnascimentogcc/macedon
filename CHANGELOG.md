# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/). Before 1.0.0, minor versions may include breaking changes.

## [Unreleased]

### Added

- The evaluation covers collection and tag scopes: 3 regional documents that compete with the
  group-wide ones, 16 scoped questions (ambiguous, subtree, tags, out of scope, access control)
  and scoped metrics in `baseline.json`. The 34 unscoped questions are unchanged.

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
