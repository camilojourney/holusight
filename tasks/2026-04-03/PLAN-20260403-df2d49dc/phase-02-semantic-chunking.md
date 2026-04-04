# Phase 2: Research SOTA + Semantic Chunking

**Goal:** Research current best practices in code retrieval, then implement tree-sitter semantic chunking. Requires full fleet re-index.
**Done when:** eval hit_rate ≥ 78%, semantic chunking live, fleet re-indexed with new chunks

## FOCUS ANCHOR — Read this before every step

```
You are executing: PLAN-20260403-df2d49dc / Phase 2
Read status.json to confirm your current step.
Phase 1 results are in results/phase-01-eval.json — read them before starting.

SKILL ENFORCEMENT:
  - EVERY source code change → /code skill only
  - NEVER edit .py files directly
```

---

## Step 1: Research SOTA code retrieval techniques

```
INVOKE: Skill(skill="research", args="holusight What are the best code retrieval techniques as of 2024-2025? Research: (1) semantic chunking strategies for code — tree-sitter scope boundaries vs sliding window vs late-chunking, (2) HyDE (hypothetical document embeddings) — generate a fake answer, embed it, use that for retrieval, (3) contextual retrieval — Anthropic's technique of prepending chunk-level context before embedding, (4) ColBERT — token-level multi-vector retrieval, (5) parent-child chunk architecture — small chunks for recall, large for context. For each: what's the expected lift in code retrieval, what's the implementation complexity, and is it compatible with our LanceDB + BM25 + voyage-code-3 stack? Focus on practical implementation, not theory.")
```

**What Claude Code does:**
1. Invoke the skill
2. Write synthesis to results/phase-02-step-01-research.md
3. Update status.json

**Done when:** research output covers all 5 techniques with implementation feasibility rating

---

## Step 2: Consult on chunking architecture

```
INVOKE: Skill(skill="consult-experiments", args="holusight Given research findings (read results/phase-02-step-01-research.md), design the optimal chunking strategy for CodeSight. Our current stack: tree-sitter already imported in parsers.py, LanceDB for vectors, SQLite FTS5 for BM25, voyage-code-3 embeddings (1024-dim). Key question: should we do (A) tree-sitter scope chunking — chunk at function/class/block boundaries, (B) contextual retrieval — prepend file path + parent scope to each chunk before embedding, (C) both A+B together, or (D) something else? Evaluate: expected hit rate lift, re-indexing cost, implementation risk. We need to get from ~65% to 78% hit rate in this phase.")
```

**Done when:** architecture decision written to results/phase-02-step-02-design.md

---

## Step 3: Implement semantic chunking

```
INVOKE: Skill(skill="code", args="holusight Implement tree-sitter semantic chunking in src/codesight/chunker.py based on the design decision in tasks/2026-04-03/PLAN-20260403-df2d49dc/results/phase-02-step-02-design.md. The key change: instead of fixed-line sliding windows, chunk at scope boundaries (function definitions, class definitions, method boundaries). Implementation requirements: (1) Use tree-sitter (already in pyproject.toml as tree-sitter-languages) to parse supported languages, identify scope nodes (function_definition, class_definition, method_definition), chunk at those boundaries with up to DEFAULT_CHUNK_MAX_LINES lines. (2) If a scope exceeds max lines, split within the scope with overlap. (3) For unsupported languages (no tree-sitter parser), fall back to existing fixed-line chunker. (4) If the design decision includes contextual retrieval (prepend context), also prepend parent scope path (e.g. 'File: embeddings.py > Class: VoyageEmbedder > Method: embed') to the chunk text before embedding — but store the original text for display. (5) Add CODESIGHT_CHUNKING=semantic|fixed env var, default semantic.")
```

**Done when:** `pytest tests/ -x -v` passes, chunker produces scope-aligned chunks for .py files

---

## Step 4: Re-index the fleet with semantic chunks

```bash
cd /Users/mini/.openclaw/workspace/github/~Projects/system/skills/fleet-brain/scripts
# Clear existing index to force full re-embed
python3 fleet_indexer.py --codesight --force-reindex
```

Monitor output. Expected cost: ~$0.50-2.00 for voyage-code-3 re-embedding.

Write re-index log to results/phase-02-step-04-reindex.md:
- Repos indexed
- Files processed  
- Estimated cost
- Any errors

**Done when:** all 6 codesight_indexed repos show successful index in fleet_indexer output

---

## Step 5: Run eval and record Phase 2 results

```bash
cd /Users/mini/.openclaw/workspace/github/~Projects/system/skills/fleet-brain/scripts
CODESIGHT_RERANKER=true CODESIGHT_QUERY_EXPANSION=true \
  python3 eval_search.py --backend codesight --output ../data/eval_phase2_results.json
```

Write results to `results/phase-02-eval.json`. Record:
- hit_rate (target ≥ 78%)
- mrr_at_10
- delta vs Phase 1 baseline
- token efficiency delta (should improve — better chunks = fewer tokens needed)

**⚠️ RESEARCH CHECKPOINT:** If hit_rate < 70% after re-indexing with semantic chunks:
```
INVOKE: Skill(skill="consult-experiments", args="holusight Semantic chunking re-index did not reach 70% hit rate (target was 78%). Read results/phase-02-eval.json for failing queries. What's wrong? Is the issue chunking strategy, embedding model, query expansion, or eval query quality?")
```

**Done when:** eval results documented, comparison table written

---

## Output

- `results/phase-02-step-01-research.md` — SOTA research synthesis
- `results/phase-02-step-02-design.md` — chunking architecture decision
- `results/phase-02-eval.json` — eval numbers after semantic chunking

## Feeds into Phase 3

Phase 3 needs: confirmed Phase 2 hit rate, list of query types still failing.
