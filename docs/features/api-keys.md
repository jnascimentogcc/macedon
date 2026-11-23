# Feature spec: API keys for other applications

This spec has two readers: the **administrator** who issues a key, and the **developer of the
application** that uses it. The rules are enforced by the API; the web interface only mirrors them.

## What a key is

- A long-lived credential for a program (a service, a script, a scheduled job), not for a person.
  People sign in through the identity provider.
- It looks like `mcd_` followed by 43 URL-safe characters. Only a SHA-256 hash is stored, so the
  platform cannot show a key again: a lost key is revoked and replaced.
- It acts as its **own identity**, `key:<id>`, with the **groups** and **scopes** chosen at
  creation. It is never an administrator and cannot manage keys.
- It always **expires**: 90 days by default, 365 at most (`MACEDON_API_KEY_DEFAULT_DAYS`,
  `MACEDON_API_KEY_MAX_DAYS`). It can be revoked at any time, with immediate effect.

## Access model

A key is subject to the same document rules as a user, nothing more:

| The key can read a document when... |
| --- |
| one of the key's groups is among the document's groups, or |
| the document was uploaded by this same key (its owner), or |
| the document lists `key:<id>` in its users. |

- A document uploaded by a key belongs to that key. Other keys and users see it only if it was
  shared with a group they have. Share it with groups at upload (`acl_groups`); a key can share only
  with groups in `MACEDON_KNOWN_GROUPS` or its own.
- Answers (`POST /query`) cite only documents the key can read. A document outside its groups does
  not exist for it.
- Give a key the **fewest groups and the narrowest scope** its job needs. A reporting job that only
  asks questions needs `read` and the groups of the documents it should answer from, nothing else.

### Scopes

| Scope | Allows |
| --- | --- |
| `read` | `GET` requests (list and read documents and versions, `/groups`, `/collections`, `/me`) and `POST /query` |
| `write` | everything else on documents: upload, new versions, edit (`PATCH`), activate or roll back a version, archive (`DELETE`) |

The scopes are independent: a key with only `write` cannot read. Collections can be read with `read`;
changing them needs an administrator, so no key can.

## Getting a key (administrators)

1. Sign in to the web interface and open **API keys** (administrators only).
2. **Create key**: a name that says what uses it, the groups, the scopes and the days it stays valid.
3. Copy the key from the dialog. It is shown once.
4. Hand it to the application's owner through a secret manager, never by chat or email.

The same is available through the API with an administrator's token: `POST /api-keys` with
`{"name": "reporting", "groups": ["engineering"], "scopes": ["read"], "expires_in_days": 90}`;
`GET /api-keys` lists keys; `DELETE /api-keys/{id}` revokes one.

## Calling the API (applications)

Send the key as a bearer token on every request. The base URL is wherever the API runs (here
`https://macedon.example.com`).

```bash
curl https://macedon.example.com/me \
  -H "Authorization: Bearer $MACEDON_API_KEY"
```

```json
{ "user_id": "key:9f3c…", "groups": ["engineering"], "is_admin": false, "scopes": ["read"] }
```

`GET /me` is the quickest check that a key works and has the groups and scopes you expect.

### Ask a question (`read`)

```bash
curl https://macedon.example.com/query \
  -H "Authorization: Bearer $MACEDON_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the notice period in the supply contract?"}'
```

The body also accepts `document_id`, `collection_id` (includes subcollections), `tags` (all must
match), `top_k` (1 to 10, default 5), `version` (a historical version, needs `document_id`) and
`inline_citations` (see below). The answer comes with its sources:

```json
{
  "answer": "The notice period is 30 days.",
  "sources": [
    { "id": 1, "document_id": "…", "document_name": "Supply contract", "version": 2,
      "page": 7, "section": "Clause 12", "text": "…", "cited": true }
  ],
  "model": "…"
}
```

**Citations are structured, not inline.** The web interface shows `[1]`-style markers in the answer
because it lists the sources beside it. A program has no such list to point at, so for an API key
the `answer` is clean text, and the citations are in `sources`: each entry has the document, version,
page, section and passage, and `cited: true` marks the ones the answer relies on (the others were
retrieved but not used). Pass `"inline_citations": true` to get the markers in the text as well, for
example to display the answer next to your own rendering of the sources.

Show or store the sources with the answer: they are what lets a reader verify it. Treat `answer` as
text, never as HTML or as instructions to follow. When no source supports an answer, the API says so
instead of inventing one.

### Upload a document (`write`)

```bash
curl https://macedon.example.com/documents \
  -H "Authorization: Bearer $MACEDON_API_KEY" \
  -F "file=@contract.pdf" \
  -F "name=Supply contract" \
  -F "acl_groups=legal" \
  -F "tags=contracts"
```

PDF, DOCX and TXT, up to 50 MB by default; the type is checked from the file's bytes, not its name.
The reply is `202 Accepted`: the document is processed in the background and **does not answer
questions yet**. Poll `GET /documents/{id}` (needs `read`) until `active_version` is not `null`; if
the latest version's `status` becomes `failed`, its `error` says why. Sending the same file again as
the latest version changes nothing (`duplicate: true`).

To publish a new version, `POST /documents/{id}/versions` with the file. The previous version keeps
answering until the new one is fully indexed. Only the key that owns a document (or an
administrator) can change it.

### Python example

```python
import os, time
import httpx

client = httpx.Client(
    base_url="https://macedon.example.com",
    headers={"Authorization": f"Bearer {os.environ['MACEDON_API_KEY']}"},
    timeout=60,
)

def ask(question: str) -> dict:
    for attempt in range(5):
        response = client.post("/query", json={"question": question})
        if response.status_code == 429:  # too many questions: wait and try again
            time.sleep(2**attempt)
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError("rate limited")
```

## Errors

| Status | Meaning | What to do |
| --- | --- | --- |
| `401` | The key is missing, unknown, expired or revoked. The response never says which. | Check the key; ask an administrator for a new one if it expired or was revoked. Do not retry in a loop. |
| `403` | The key lacks the scope for this call, or the action is for administrators (`/api-keys`) or the owner. | Ask for the right scope, or use another route. |
| `404` | The document does not exist **or the key cannot read it**. The two look the same on purpose. | Check the groups of the key. |
| `413` / `415` | File too large / type not supported. | Use PDF, DOCX or TXT within the limit. |
| `422` | Invalid input, for example an unknown group or a bad question. | Fix the request. |
| `429` | Too many questions. The limit is per key, 30 a minute by default, and it does not share a quota with people or other keys. | Wait and retry with a growing delay. |
| `502` / `503` | The answering service failed or is not configured. | Retry later; the problem is not in the key. |

## Handling the key (applications)

- Keep it in a **secret manager or an environment variable**, never in source control, a container
  image, a log, an error message or a URL.
- Use it only from **server-side code**. Do not put it in a web page, a mobile app or anything a user
  can inspect; the API is not meant to be called from a browser with a key (CORS allows only the web
  interface).
- **One key per application**, so each can be revoked and audited on its own.
- **Rotate before expiry**: ask for a new key, deploy it, check with `GET /me`, then have the old one
  revoked. Both work during the overlap. Keys expire at most a year after creation; set a reminder.
- If a key may have leaked, tell an administrator at once: revoking is immediate, and the audit
  trail shows what the key did.

## Audit and operation (administrators)

- Creating and revoking a key are audited, and so is every action a key performs, under the actor
  `key:<id>` (uploads, edits, queries, archives). The list in the web interface shows each key's last
  use, to spot keys nobody uses and revoke them.
- Revoked and expired keys stay in the list so the history is kept; they stop working immediately.
- Keys are not tied to a person: when someone who created or used a key leaves, review the keys
  they handled.
- Document content in answers is sent to the external model provider, as for any query. Do not give
  a key access to groups whose documents must not leave the organization.

## Not covered yet

Per-key rate limits that differ from the default, restricting a key to certain collections, keys
that never expire, and automatic notice before a key expires.
