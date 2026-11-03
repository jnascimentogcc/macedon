# Evaluation

Manual jobs: they call paid APIs, so they never run in pull-request CI. Both need
`MACEDON_OPENAI_API_KEY` and the dev stack (`docker compose up -d`).

```bash
uv run python eval/run.py                      # retrieval baseline (TRUNCATES the dev database)
uv run --group eval python eval/ragas_score.py # answer quality, scored with RAGAS
```

`corpus.py` holds a synthetic corpus (8 DOCX documents, two of them restricted to a group) and
34 questions: direct lookups, identifiers, multi-hop, paraphrases and three with no answer.
`run.py` ingests it, asks every question through the real API stack and writes
`results/baseline.json`; `ragas_score.py` adds faithfulness, response relevancy and a binary
answer-correctness judge to that file.

Retrieval metrics: `evidence_hit@k` (a retrieved passage contains the evidence phrase), `mrr`,
`document_hit`, `no_answer_abstained` (no citation when nothing answers the question) and
`acl_leaks` (a user outside the group got a passage of the restricted document; must stay 0).

Any change to chunking, the embedding model or the reranker must be measured against this
baseline. The corpus is small and easy, so grow it before drawing conclusions from small
differences. `ragas` is pinned because newer releases break against current `langchain-community`.
