# Plan: CodeSight → 95% Hit Rate

**CID:** PLAN-20260403-df2d49dc | **Repo:** holusight | **Created:** 2026-04-03
**Status:** PENDING

## Goal

Push CodeSight retrieval from **52.5% hit rate / MRR 0.352** to **95% hit rate**
with minimum tokens-per-correct-answer as a co-metric. Support both local models
(sentence-transformers) and API models (voyage, openai) so users can choose cost vs
quality trade-off.

## Baseline

| Metric | Current |
|--------|---------|
| Hit rate | 52.5% |
| MRR@10 | 0.352 |
| Reranker | ms-marco-MiniLM (web search, generic) |
| Chunking | Fixed 200-line windows |
| Query strategy | Single query, no expansion |
| Token efficiency | Not measured |

## Target

| Metric | Target |
|--------|--------|
| Hit rate | ≥ 95% |
| MRR@10 | ≥ 0.80 |
| Tokens per correct answer | ≤ current baseline (measure in Phase 1) |

---

## Phases

### Phase 1: Challenge assumptions + quick wins
**Goal:** First, adversarially research whether voyage reranker + query expansion are actually the right moves in 2026 — or if there's something better we're missing. Then implement what the research validates.
**Skills:** `/research` (adversary mode), `/code`, `/consult-experiments`
**Done when:** assumptions validated by research, eval hit rate ≥ 65%, token baseline measured

**Steps:**
0. **assumption-check** — /research adversary: "We plan to swap to voyage rerank-2.5 and add LLM query expansion. Challenge this. Are there better 2026 approaches we're ignoring? Is voyage rerank-2 still SOTA or has it been superseded? Is query expansion with an LLM the right move or does it add latency and noise?" → Output: go/no-go + alternatives
1. **swap-reranker** — Replace `ms-marco-MiniLM` with voyage `rerank-2.5` (or research-validated alternative) → Output: eval score post-reranker swap
2. **add-query-expansion** — Add LLM query rewriter: expand 1 query → 3 variants, deduplicate via RRF → Output: eval score post-expansion
3. **measure-token-baseline** — Add token count to eval harness (tokens returned per query, tokens per correct hit) → Output: token efficiency baseline
4. **eval-phase1** — Run full eval, record hit_rate + MRR@10 + token metrics → Output: results/phase-01-eval.json
5. **consult-checkpoint** — If hit rate < 60% after both changes, /consult-experiments to diagnose

**Internal loop:** Steps 1-2 can be done in either order. Step 4 must come after both.

---

### Phase 2: SOTA research + semantic chunking
**Goal:** Research current best practices in 2026 for code retrieval. Challenge the assumption that tree-sitter semantic chunking is the right move. Then implement whatever the research validates.
**Skills:** `/research`, `/consult-experiments`, `/code`
**Done when:** eval hit rate ≥ 78%, best chunking strategy implemented, fleet re-indexed

**Steps:**
0. **assumption-check** — /research adversary: "We plan to implement tree-sitter semantic chunking. Challenge this. In 2026, is scope-based chunking still the best approach? Is late-chunking (embed full file, slice post-hoc) better? Has contextual retrieval from Anthropic made chunk boundaries less important? What does the latest research say specifically about code chunking?" → Output: validated approach or pivot recommendation
1. **consult-chunking-design** — /consult-experiments: given research findings, design the optimal chunking strategy → Output: architecture decision
2. **implement-chunking** — /code: implement the research-validated chunking strategy → Output: updated chunker.py
3. **re-index-fleet** — Re-index all 6 codesight_indexed repos → Output: index rebuild log
4. **eval-phase2** — Run full eval, compare to Phase 1 → Output: results/phase-02-eval.json

---

### Phase 3: Parent-child chunks + metadata boosting
**Goal:** Challenge whether parent-child and metadata boosting are the right structural improvements in 2026. Then implement what's validated.
**Skills:** `/research` (adversary), `/code`, `/consult-experiments`
**Done when:** eval hit rate ≥ 88%, token-per-correct-answer reduced vs Phase 1 baseline

**Steps:**
0. **assumption-check** — /research adversary: "We plan to implement parent-child chunk architecture (small for recall, large for context) and filename/path BM25 boosting. Challenge this. In 2026, do re-ranking models (voyage rerank-2) make parent-child unnecessary because they already surface relevant context? Is metadata boosting still needed or does voyage-code-3 already encode file structure semantically?" → Output: go/no-go for each improvement
1. **implement-parent-child** — /code: add parent-child chunk architecture (if validated by research) → Output: updated indexer + store
2. **implement-metadata-boost** — /code: add filename/path BM25 boosting (if validated) → Output: updated search.py
3. **re-index-fleet** → Output: index rebuild log
4. **eval-phase3** — Full eval + token efficiency → Output: results/phase-03-eval.json
5. **gap-analysis** — If hit rate < 85%: /consult-experiments on remaining failures

---

### Phase 4: Advanced techniques + final gate
**Goal:** Challenge ALL remaining assumptions. Research the 2026 frontier (HyDE, contextual retrieval, ColBERT, sparse+dense fusion). Implement top technique. Final architecture decision.
**Skills:** `/research` (adversary), `/code`, `/consult-experiments`, `/consult-engineering`
**Done when:** hit rate ≥ 95% OR documented decision that 95% requires architecture change beyond current scope
**Gate:** hard — review final eval before committing fleet architecture

**Steps:**
0. **assumption-check** — /research adversary: "We're at ~88% hit rate. We've done voyage reranker, query expansion, semantic chunking, parent-child, metadata boosting. What are we missing? In 2026, what separates 88% from 95%? Challenge everything: is our eval set representative? Is voyage-code-3 still the best code embedding in 2026 or has it been superseded? Should we consider sparse+dense fusion (BM25 + dense + SPLADE)? Is our RRF k=60 optimal?" → Output: diagnosis + highest-ROI remaining technique
1. **implement-top-technique** — /code: implement what research says is the highest-ROI remaining change → Output: updated pipeline
2. **fix-failing-queries** — /code: targeted fixes for specific failing eval query categories → Output: improvements
3. **eval-final** — Full eval: baseline → P1 → P2 → P3 → P4 → Output: results/phase-04-final-eval.json
4. **architecture-decision** — /consult-engineering: recommended config for (a) local users, (b) API users → Output: two config profiles
5. **update-docs** — /specs --sync: ARCHITECTURE.md, README, .env.example with final numbers
   **Gate:** hard — present final numbers, get approval

---

## Risks

1. **Tree-sitter coverage gaps** — not all languages have tree-sitter parsers. Fallback to fixed chunking needed.
2. **Re-indexing cost** — voyage-code-3 costs $0.00018/1K tokens. Full fleet re-index ~$0.50-2.00.
3. **95% may require ColBERT** — token-level matching is architecturally different (multi-vector). If needed, that's a Phase 5.
4. **Query expansion latency** — adding LLM rewriting adds 500-1000ms per query. Acceptable for coding assistant, bad for interactive search.
5. **Eval set size** — 40 queries may not be enough to detect 5% improvements. May need to expand to 100 queries.
