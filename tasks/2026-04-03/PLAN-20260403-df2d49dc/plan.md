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

### Phase 1: Quick wins — swap reranker + add query expansion
**Goal:** Fast 15-20% lift with minimal re-indexing. Voyage rerank-2.5 + LLM query expansion.
**Skills:** `/code`, `/consult-experiments`
**Done when:** eval run shows hit rate ≥ 65%, MRR improvement confirmed, token baseline measured

**Steps:**
1. **swap-reranker** — Replace `ms-marco-MiniLM` with voyage `rerank-2.5` in search.py + config.py → Output: eval score post-reranker swap
2. **add-query-expansion** — Add LLM query rewriter: expand 1 query → 3 variants, deduplicate RRF results → Output: eval score post-expansion
3. **measure-token-baseline** — Add token count to eval harness (tokens returned per query, tokens per correct hit) → Output: token efficiency baseline
4. **eval-phase1** — Run full eval, record hit_rate + MRR@10 + token metrics → Output: results/phase-01-eval.json
5. **consult-checkpoint** — If hit rate < 60% after both changes, /consult-experiments to diagnose before proceeding

**Internal loop:** Steps 1-2 can be done in either order. Step 4 must come after both.

---

### Phase 2: Research SOTA + semantic chunking
**Goal:** Understand current SOTA for code retrieval, then implement semantic chunking (tree-sitter scope boundaries). This requires re-indexing the fleet.
**Skills:** `/research`, `/consult-experiments`, `/code`
**Done when:** eval hit rate ≥ 78%, tree-sitter chunking live, fleet re-indexed

**Steps:**
1. **research-sota** — /research: what are the best code retrieval techniques in 2024-2025? ColBERT, HyDE, late-chunking, contextual retrieval (Anthropic's), semantic chunking alternatives → Output: results/phase-02-research.md
2. **consult-chunking-design** — /consult-experiments: given research findings, what chunking strategy maximizes recall for code? → Output: architecture decision
3. **implement-semantic-chunking** — /code: replace fixed-line chunker with tree-sitter scope-aware chunking (functions, classes as natural boundaries). Keep fallback for non-tree-sitter languages → Output: updated chunker.py
4. **re-index-fleet** — Re-index all 6 codesight_indexed repos with new chunking → Output: index rebuild log
5. **eval-phase2** — Run full eval, compare to Phase 1 baseline → Output: results/phase-02-eval.json

**⚠️ RESEARCH CHECKPOINT:** After step 1, if research reveals a technique that would make steps 3-4 obsolete (e.g., late-chunking with voyage), STOP and invoke `/consult-experiments` before implementing.

---

### Phase 3: Parent-child chunks + metadata boosting + token efficiency
**Goal:** Implement the two remaining structural improvements. Parent-child: store small chunks (50 lines) for retrieval, return parent (200 lines) for context. Metadata boost: filename/path signals. This directly reduces tokens-per-answer.
**Skills:** `/code`, `/consult-experiments`
**Done when:** eval hit rate ≥ 88%, token-per-correct-answer reduced vs Phase 1 baseline

**Steps:**
1. **implement-parent-child** — /code: add parent-child chunk architecture to indexer.py + store.py. Small chunks for recall, parent returned for LLM context → Output: updated indexer + store
2. **implement-metadata-boost** — /code: add filename/path token matching as BM25 signal boost in search.py → Output: updated search.py
3. **re-index-fleet** — Re-index with new structure (faster than Phase 2, same chunker) → Output: index rebuild log
4. **eval-phase3** — Run full eval + token efficiency metrics → Output: results/phase-03-eval.json
5. **consult-gap-analysis** — If hit rate < 85%: /consult-experiments to identify remaining gap. What queries are still failing? → Output: gap analysis + next actions

---

### Phase 4: Research advanced techniques + targeted fixes + gate
**Goal:** Close the remaining gap to 95%. Research HyDE, contextual retrieval, ColBERT if needed. Targeted fixes for query types still failing. Final eval + architecture decision on local vs API model recommendations.
**Skills:** `/research`, `/code`, `/consult-experiments`, `/consult-engineering`
**Done when:** hit rate ≥ 95% OR decision made that 95% is not achievable with current architecture (with documented reason + next steps)
**Gate:** hard — review final eval before committing fleet architecture

**Steps:**
1. **research-advanced** — /research: HyDE (hypothetical document embeddings), contextual retrieval (prepend chunk context), ColBERT token-level matching, late-chunking — which apply to our stack? → Output: results/phase-04-research.md
2. **implement-top-technique** — /code: implement the 1-2 highest-ROI findings from research → Output: updated search pipeline
3. **fix-failing-queries** — /code: analyze which eval queries still fail, targeted fixes (e.g., add docstring extraction, improve code comment indexing) → Output: eval improvement
4. **eval-final** — Full eval run, compare all phases: baseline → P1 → P2 → P3 → P4 → Output: results/phase-04-final-eval.json
5. **architecture-decision** — /consult-engineering: given results, what is the recommended config for (a) local-only users, (b) API users with voyage? Document in ARCHITECTURE.md → Output: final architecture recommendation
6. **update-docs** — /specs --sync: update ARCHITECTURE.md, config docs, README with final model recommendations and performance numbers
   **Gate:** hard — present final numbers, get approval before committing architecture

---

## Risks

1. **Tree-sitter coverage gaps** — not all languages have tree-sitter parsers. Fallback to fixed chunking needed.
2. **Re-indexing cost** — voyage-code-3 costs $0.00018/1K tokens. Full fleet re-index ~$0.50-2.00.
3. **95% may require ColBERT** — token-level matching is architecturally different (multi-vector). If needed, that's a Phase 5.
4. **Query expansion latency** — adding LLM rewriting adds 500-1000ms per query. Acceptable for coding assistant, bad for interactive search.
5. **Eval set size** — 40 queries may not be enough to detect 5% improvements. May need to expand to 100 queries.
