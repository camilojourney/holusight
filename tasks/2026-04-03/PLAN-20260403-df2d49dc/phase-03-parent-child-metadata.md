# Phase 3: Parent-Child Chunks + Metadata Boosting

**Goal:** Store small chunks (50 lines) for recall precision, return large parent chunks (200 lines) for LLM context. Add filename/path metadata boosting to BM25. These changes directly reduce tokens-per-answer.
**Done when:** eval hit_rate ≥ 88%, token-per-correct-answer reduced vs Phase 1 baseline

## FOCUS ANCHOR — Read this before every step

```
You are executing: PLAN-20260403-df2d49dc / Phase 3
Read status.json to confirm current step.
Phase 2 results are in results/phase-02-eval.json.
Current hit rate going into Phase 3 should be ~78%.

SKILL ENFORCEMENT: ALL source changes → /code skill. No direct edits.
```

---

## Step 1: Implement parent-child chunk architecture

```
INVOKE: Skill(skill="code", args="holusight Implement parent-child chunk architecture in indexer.py, store.py, and search.py. Architecture: (1) At index time, create two chunk sizes per file: child chunks (50 lines, 25-line overlap) used for embedding + retrieval, parent chunks (200 lines, 50-line overlap) stored separately for LLM context. Store parent_id foreign key on each child chunk. (2) In store.py: add parent_chunks table in LanceDB (no embedding needed, just text + metadata), add get_parent_chunks(parent_ids) retrieval function. (3) In search.py: after retrieval + reranking, replace returned child chunk text with parent chunk text (look up parent_id for each result). This means: precision of small-chunk retrieval, but LLM sees the full surrounding context. The trade-off: tokens increase slightly but correctness increases significantly. Add CODESIGHT_PARENT_CHILD=true env var, default true.")
```

**Done when:** indexer creates both chunk sizes, search returns parent context, tests pass

---

## Step 2: Implement filename/path metadata boosting

```
INVOKE: Skill(skill="code", args="holusight Add filename and directory path metadata boosting to search.py BM25 scoring. When a query term exactly matches a filename (without extension) or directory name in the indexed path, apply a score multiplier (1.5x) to BM25 results from that file. Implementation: in hybrid_search(), after BM25 results come back with scores, check each result's file_path against query tokens. If any query token is a substring of the filename (case-insensitive), multiply that result's BM25 score by 1.5 before RRF. Example: query 'embeddings model' → results from 'embeddings.py' get 1.5x boost. This is cheap and high-signal — if someone mentions a filename, the file should rank higher. Store file_path in LanceDB metadata already (verify it's there).")
```

**Done when:** metadata boost is applied, test verifies that querying a filename surfaces that file higher

---

## Step 3: Re-index the fleet

```bash
cd /Users/mini/.openclaw/workspace/github/~Projects/system/skills/fleet-brain/scripts
python3 fleet_indexer.py --codesight --force-reindex
```

This re-index creates both parent and child chunk tables. Expected to be faster than Phase 2 (same embedding model, just additional chunk size).

Write log to results/phase-03-step-03-reindex.md.

**Done when:** all 6 repos indexed with parent+child tables

---

## Step 4: Run eval and record Phase 3 results

```bash
cd /Users/mini/.openclaw/workspace/github/~Projects/system/skills/fleet-brain/scripts
CODESIGHT_RERANKER=true CODESIGHT_QUERY_EXPANSION=true CODESIGHT_PARENT_CHILD=true \
  python3 eval_search.py --backend codesight --output ../data/eval_phase3_results.json
```

Record:
- hit_rate (target ≥ 88%)
- mrr_at_10
- token efficiency delta (parent-child should improve this — better context, fewer wasted tokens)
- Full comparison table: baseline → P1 → P2 → P3

---

## Step 5: Gap analysis consultation (conditional)

**Only invoke if hit_rate < 85%:**

```
INVOKE: Skill(skill="consult-experiments", args="holusight After 3 phases of improvements (voyage reranker, query expansion, semantic chunking, parent-child, metadata boost), hit rate is still below 85% (target was 88%). Read results/phase-03-eval.json. Which query categories are still failing? Options to close the gap: (A) HyDE — generate hypothetical code that would answer the query, embed that, use for retrieval. (B) Expand eval set — are 40 queries statistically sufficient? (C) Improve query expansion prompts — current prompt may generate poor variants. (D) Index more metadata — function signatures, docstrings as separate indexed fields. What should Phase 4 prioritize?")
```

**Done when:** either hit rate ≥ 88% (skip consultation) or gap analysis written to results

---

## Output

- `results/phase-03-eval.json` — eval numbers after parent-child + metadata boost
- comparison table: all phases side by side
- token efficiency trend

## Feeds into Phase 4

Phase 4 needs: list of specific failing query categories from Phase 3 eval.
