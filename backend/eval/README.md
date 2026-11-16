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

Portuguese check (`corpus_pt.py`, `run_pt.py`): 3 Portuguese documents and 13 questions that stress
the keyword half of hybrid search, which uses the Postgres `simple` configuration (no stemming, no
accent folding). Tags: `morphology` (another inflection than the document), `accent` (accents
dropped), `identifier`, `paraphrase`, `no-answer`. It truncates the dev database. Run it before and
after any change to the text search configuration and compare the two files:

```bash
uv run python eval/run_pt.py --label simple       # writes eval/results/pt_simple.json
uv run python eval/run_pt.py --label portuguese   # after the change
```

Real documents (`corpus_real.py`, `run_real.py`): 27 questions over two public Portuguese tender
documents (83 and 116 pages, 341 chunks), kept outside the repository and passed with `--dir`.
Tags: `lot-price` (31 near-identical lot sentences), `page-break`, `confusable` (same rule, two
values), `both-documents`, `formula`, `identifier`, `lookup`, `number`, `paraphrase`, `no-answer`.
Every evidence phrase is checked against the raw PDF text before any paid call.

```bash
uv run python eval/run_real.py --dir <folder with the two PDFs> --label base
```

First run (`results/real_base.json`): evidence@5 0.96, evidence@1 0.88, MRR 0.90, no-answer
abstention 3/3, every lot-price and confusable question at rank 1. The retrieval holds up; the
extraction does not, and that is where this set paid off:

* Section structure is wrong. Headings are found by font size only, but the specifications mark
  clauses ("Cláusula 5.ª") in bold at body size, so the 83-page document has 2 headings and 3
  distinct section paths for 167 chunks: every citation says "section: cover title". In the
  programme, article numbers and titles use different sizes (12 pt and 13 pt), so they become two
  headings and articles nest under each other.
* Running page headers and footers (agency name, address, URL, "PÁGINA n de 83") are kept as text:
  75 of 167 and 96 of 174 chunks carry them, which dilutes embeddings and keyword matches.
* The identifier question counts as a miss only because the evidence is in the section path, not in
  the passage text; the answer was right.

Extraction fixes (`results/real_extraction.json`): page headers and footers are dropped (lines in
the top or bottom 15% of the page whose text, digits aside, repeats on half of the pages), and
headings are also found by structural label ("Cláusula 5.ª", "Artigo 10.º", "CAPÍTULO IV"), whose
title line is merged in whatever its size, and whose depth comes from the label. The
specifications went from 2 headings and 3 section paths to 27 and 28; chunks carrying header or
footer text from 75 and 96 to 0; chunks from 341 to 322. Citations now name the clause
("Cláusula 4.ª Preço contratual e preços base unitários") instead of the cover title. The retrieval
metrics did not move beyond noise (MRR 0.90 to 0.88, one question out of 27 went from rank 1 to 2),
which is expected: the fix is to what the user is shown and to the embedded text, not to what is
found. Still open: the cover title (set in a larger size) stays in every section path of the
specifications.

Relevance floor (tried, not adopted): the idea was to drop vector-only hits above a cosine
distance so unanswerable questions reach the model with no sources. Measured on both corpora, the
evidence chunk of paraphrased questions sits as far as 0.69, while the nearest chunk of an
unanswerable question is at 0.50 to 0.64, and the keyword search (an OR query) also matches
unanswerable questions. No threshold separates them without dropping correct answers, so abstention
stays with the model. Revisit it only with a reranker, whose scores are calibrated.

Any change to chunking, the embedding model or the reranker must be measured against this
baseline. The corpus is small and easy, so grow it before drawing conclusions from small
differences. `ragas` is pinned because newer releases break against current `langchain-community`.
