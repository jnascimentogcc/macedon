# Evaluation

Manual jobs: they call paid APIs, so they never run in pull-request CI. Both need
`MACEDON_OPENAI_API_KEY` and the dev stack (`docker compose up -d`).

```bash
uv run python eval/run.py                      # retrieval baseline (TRUNCATES the dev database)
uv run --group eval python eval/ragas_score.py # answer quality, scored with RAGAS
uv run python eval/run.py --scoped-only        # only the scoped questions, keeps the rest
uv run --group eval python eval/ragas_score.py --scoped
```

`corpus.py` holds a synthetic corpus (8 DOCX documents, two of them restricted to a group) and
34 questions: direct lookups, identifiers, multi-hop, paraphrases and three with no answer.
`run.py` ingests it, asks every question through the real API stack and writes
`results/baseline.json`; `ragas_score.py` adds faithfulness, response relevancy and a binary
answer-correctness judge to that file.

The scoped part adds 3 regional documents (two travel addenda and a handbook addendum) that
answer the same questions as the group-wide ones with other facts, and a collection tree
(`Group/...`, `Subsidiaries/...`) with tags for every document. They are ingested after the
unscoped questions run, so the 34-question baseline stays comparable. 16 scoped questions cover:
`ambiguous` (the scope picks one of several similar documents; also asked unscoped), `subtree`
(a parent collection includes its children and excludes its siblings), `in-scope`,
`out-of-scope` (nothing in scope answers, so the system must abstain) and `acl` (a user outside
the group gets nothing, scope or not). `ragas_score.py --scoped` scores only the `ambiguous` ones.

Scoped metrics (under `scoped` in the results): `scoped_evidence_hit@k`, `scoped_mrr`,
`out_of_scope_sources` (a passage from outside the collection or tag scope; must stay 0),
`out_of_scope_abstained`, `acl_leaks`, and on the compared questions `unscoped_evidence_hit@1`
against `scoped_evidence_hit@1_on_compared`: the lift the scope gives.

Retrieval metrics: `evidence_hit@k` (a retrieved passage contains the evidence phrase), `mrr`,
`document_hit`, `no_answer_abstained` (no citation when nothing answers the question) and
`acl_leaks` (a user outside the group got a passage of the restricted document; must stay 0).

Any change to chunking, the embedding model or the reranker must be measured against this
baseline. The corpus is small and easy, so grow it before drawing conclusions from small
differences. `ragas` is pinned because newer releases break against current `langchain-community`.
