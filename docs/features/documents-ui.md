# Feature spec: documents and querying UI

Applies `docs/ui-spec.md`. The frontend is only an API client: every access decision is made by
the API (ACL + RLS), so the UI shows what the API returns and explains its refusals.

## Access

- Sign-in with Keycloak (Authorization Code + PKCE, public client `macedon-web`). Tokens stay in
  `sessionStorage`, so a session lasts for the browser tab. Any `401` from the API restarts sign-in.
- Routes other than `/auth/callback` require a session and remember where the user was headed.

## Screens

| Route | Purpose |
| --- | --- |
| `/documents` | Collection tree on the left (counts include subcollections; administrators create, rename and delete), tag filter, paginated table (name and tags, collection, type, latest version status, active version, created), "show archived" filter, upload dialog. Refreshes by itself while a version is processing. |
| `/documents/:id` | Metadata (collection, tags), edit details (name, collection, tags; owner only), version table, upload a new version, make an archived version active (rollback), archive the document (with confirmation). |
| `/ask` | Question form, "search in" a collection (and its subcollections) or one document, optional tag filter, answer with sources (document, version, page, section, cited or not, passage on demand). |

## Organization

- Collections are a tree (one parent, four levels at most) that anyone signed in can read and only
  administrators change. A document lives in at most one collection and carries free tags.
- Organization never grants access: the ACL stays on each document, and a scoped query returns
  only what the caller could already read. The tree and its names are visible to everyone.
- Tags are stored lowercase, joined with `-`, at most 20 per document and 40 characters each.
- Queries and the document list filter by collection (with descendants) and by tags (all must
  match); the filter is part of the SQL, like the ACL.

## States and messages

- Each asynchronous region has loading, empty, error (with retry) and success feedback; status is
  always text plus color.
- Writes are limited to the document owner by the API; a `403` is explained as such.
- The answer is rendered as plain text (never as HTML) and carries the model name and a reminder
  to check the sources.

## Approved deviations from the UI spec

- Modals use the native `<dialog>` element (focus trap, Escape, focus return) instead of a Spartan
  dialog, to keep a single accessible implementation.
- Interface strings go through a small typed dictionary (`src/app/core/i18n.ts`) with a `t` pipe
  rather than Angular's compile-time i18n, so a locale can be added as one more object.

## Not covered yet

Editing a document's ACL, moving a collection under another parent, bulk moves, text diff between versions (phase 3), and a visual review at all
breakpoints and in dark mode.
