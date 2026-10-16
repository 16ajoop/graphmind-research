# Evaluation

What is scored: the extracted graph vs `ground_truth/gold_graph.json`, by `python -m app.eval_extraction --workspace <name>`
(run from `backend/`).

## Extraction scorecard (Stage 2: deterministic ingestion, no LLM)

"Plain ingest" is workspace `demo` (`python -m app.graph.ingest --workspace demo ../corpus/pdf`); "with keyword
intents" is workspace `baseline` (same command plus `--keyword-intents`).

| Relationship | Plain ingest: precision / recall (got/want) | With keyword intents: precision / recall (got/want) |
|---|---|---|
| CITES | 1.0 / 1.0 (49/49) | 1.0 / 1.0 (49/49) |
| Result | 1.0 / 1.0 (70/70) | 1.0 / 1.0 (70/70) |
| CORRECTS | 1.0 / 1.0 (1/1) | 1.0 / 1.0 (1/1) |
| EVALUATES_ON | 1.0 / 0.941 (16/17) | 1.0 / 0.941 (16/17) |
| USES | 1.0 / 0.92 (23/25) | 1.0 / 0.92 (23/25) |
| PROPOSES | 1.0 / 0.75 (6/8) | 1.0 / 0.75 (6/8) |
| INTRODUCES | 1.0 / 0.75 (3/4) | 1.0 / 0.75 (3/4) |
| EXTENDS | 0.0 / 0.0 (0/4) | 1.0 / 0.75 (3/4) |
| SIMILAR_TO | 0.0 / 0.0 (0/1) | 0.0 / 0.0 (0/1) |
| SUPPORTS | 0.0 / 0.0 (0/5) | 0.0 / 0.0 (0/5) |
| CONTRADICTS | 0.0 / 0.0 (0/1) | 0.0 / 0.0 (0/1) |
| QUALIFIES | 0.0 / 0.0 (0/3) | 0.0 / 0.0 (0/3) |
| Claim | 0.0 / 0.0 (0/13) | 0.0 / 0.0 (0/13) |

Unmapped extracted papers, methods or datasets: none in either workspace.

## Why each recall is below 1.0

- **EVALUATES_ON (16/17):** P11 discusses VaigaiQA only in its prose; its results table has no VaigaiQA row ingest can read.
- **USES (23/25):** P08 mentions LinkLite and P11 mentions GraphWalker-QA only in prose, not in a results table.
- **PROPOSES (6/8):** ChainTFIDF and LinkLite are proposed by papers that are only stubs (cited, no PDF in the library).
- **INTRODUCES (3/4):** NarmadaQA is introduced by a stub paper, so there is no title or table to derive it from.
- **EXTENDS (0/4 → 3/4):** lineage is derived from `extends` citation intents. Plain ingest leaves every intent
  `unclassified`; the keyword rules label LiteGraphFuse → GraphFuse as `reproduces` ("…extends GraphFuse [1] … learns to
  reproduce…", and `reproduces` is checked first).
- **SIMILAR_TO (0/1):** needs method-section embeddings (`DocStore.section_vector`), compared in Stage 4.
- **SUPPORTS / CONTRADICTS / QUALIFIES / Claim (0):** claims and claim relations are extracted by the LLM in Stages 3–4.

## Citation intent

Citation intent: keyword baseline 0.551. The LLM (Stage 3) must beat this.

Most frequent keyword-baseline confusions (gold → predicted): compares_against → uses_method (5),
uses_dataset → background (3), compares_against → uses_dataset (3), background → uses_method (2), supports → reproduces (2).

## Upload order

Upload order: three random orders give the same graph (tests/test_ingest.py).
