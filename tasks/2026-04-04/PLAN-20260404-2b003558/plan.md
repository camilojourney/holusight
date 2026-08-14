# Plan: Push CodeSight Retrieval Quality Above MRR 0.85

**CID:** PLAN-20260404-2b003558 | **Repo:** holusight | **Created:** 2026-04-04
**Status:** PENDING

## Goal

Push CodeSight's retrieval quality from MRR 0.793 (current best) to MRR 0.85+ on the 20-query holusight eval harness, while maintaining 100% hit rate. Research the latest 2026 retrieval techniques online, pick the highest-impact levers, implement them, and measure.

## Current Baseline

| Config | Hit Rate | MRR@10 |
|--------|----------|--------|
| voyage-code-3 + AST chunking + voyage rerank-2 | 100% | 0.793 |

**Gap to close:** +0.057 MRR (≈7%). Any technique that moves the correct result from rank 2 to rank 1 on 1-2 more queries closes the gap.

## Phases

### Phase 1: Research and Decide

**Goal:** Know exactly which 2-3 retrieval techniques are worth implementing. Backed by 2026 literature, not guessing. End with a prioritized list of experiments with expected MRR lift estimates.

**Skills:** `/research` (online research for latest techniques + novel idea generation) + `/consult-engineering` (architecture deliberation on which to implement and in what order)

**Done when:** Research doc written with claim-tagged findings + novel experiment ideas + consult output with prioritized implementation list (top 3 techniques with expected lift, effort, and implementation path)

**Steps:**
1. **research-retrieval-techniques** — Search online for 2025-2026 RAG/retrieval improvements (HyDE, late chunking, RAPTOR, multi-vector, contextual compression, query decomposition, ColBERT, BGE-M3, etc.) AND generate novel experiment ideas specific to code retrieval that are not in any paper → Output: `results/phase-01-step-01-research.md`
2. **consult-architecture** — 3 specialists deliberate: given known techniques AND novel ideas, which 2-3 experiments should CodeSight run to push MRR from 0.793 to 0.85+? Ranked by expected MRR lift vs implementation effort → Output: `results/phase-01-step-02-consult.md`

### Phase 2: Implement, Eval, and Ship

**Goal:** Implement the top techniques from Phase 1, run the eval harness after each, and confirm MRR ≥ 0.85. Gate before commit.

**Skills:** `/specs` (write spec for each technique) + `/code` (implement + tests) + bash eval harness run

**Done when:** MRR ≥ 0.85 on 20-query holusight eval, tests pass, code committed.

**Gate:** hard — user approves before final commit

**Internal loop:** For each technique (max 3): spec → code → run eval → if MRR ≥ 0.85, stop. Otherwise implement next technique.

**Steps:**
1. **write-spec** — Write spec for highest-priority technique from Phase 1 → Output: `specs/NNN-technique.md`
2. **implement** — Implement the technique via `/code` (Codex + Gemini review) → source files changed, tests written
3. **run-eval** — Run eval harness: `uv run python tests/eval_holusight.py` (or `just eval`) → Output: `results/phase-02-step-03-eval.json`
4. **check-gate** — If MRR ≥ 0.85: proceed to commit. Else: loop back to step 1 with next technique (max 3 iterations total)
5. **sync-docs** — `/specs --sync` to update ARCHITECTURE.md + CLAUDE.md with new techniques → Output: updated docs

## Risks

- **HyDE hallucination risk**: Hypothetical Document Embeddings generate fake documents to improve query vectors — can introduce hallucinated terms that hurt precision. Test carefully.
- **Diminishing returns**: We're already at 100% hit rate. The remaining gap (0.057 MRR) may require techniques that cost latency or external API calls.
- **Eval overfitting**: With only 20 queries, techniques may overfit the eval set. Use techniques that have strong theoretical backing, not just eval hacks.
- **voyage-code-3 dimension mismatch**: Any new embedding technique must be compatible with the existing 1024-dim LanceDB schema or require a full re-index.
