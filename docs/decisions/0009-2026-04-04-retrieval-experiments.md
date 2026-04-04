---
id: "0009"
title: "Retrieval Experiments: CNFB + Contextual Retrieval to push MRR 0.793 → 0.85+"
date: 2026-04-04
status: accepted
consult_cid: CONSULT-ENG-20260404-3e0dc4f6
---

# ADR 0009: Retrieval Experiments — CNFB + Contextual Retrieval

## Context

CodeSight currently achieves MRR@10 = 0.793 with 100% hit rate on the 20-query holusight eval harness. The target is MRR ≥ 0.85. Hit rate is already at ceiling — the gap is entirely in rank ordering (rank-2 results need to become rank-1). 

Current stack: AST chunking (tree-sitter), BM25+vector RRF (k=60), voyage-code-3 (1024d), voyage rerank-2, metadata filename boost (binary), VPRF.

## Decision

**Implement two experiments in sequence:**

1. **CNFB (Query-Aware Multiplicative Filename Boost)** — first
2. **Contextual Retrieval (Anthropic index-time context injection)** — second

**Defer:** voyage-context-3 upgrade, HyDE, SHCD, TASDI, BGE-M3, RAPTOR.

**Prerequisite gate:** Expand eval corpus to 80–100 queries before treating any MRR result as production signal.

## Rationale

### 3-Specialist Deliberation (2 rounds)

**Round 1 split:** 
- Systems Architect: voyage-context-3 + HyDE + CNFB 
- ML Engineer (Gemini): CNFB + Contextual Retrieval + TASDI
- Developer Experience: CNFB + voyage-context-3 + SHCD

**Round 2 unanimous convergence on CNFB + Contextual Retrieval:**

All three specialists moved to the same position after cross-reading:

- **HyDE rejected** (unanimous): 2025 paper shows gains come from LLM knowledge leakage into the query expansion vector, not genuine retrieval improvement. For private codebases with proprietary symbols the LLM has no prior knowledge of, hallucinated code completions actively hurt precision.
- **SHCD rejected** (unanimous): Doubles index-build time on every incremental reindex. For a dev tool where fast reindex on file-save is table stakes, the permanent latency tax outweighs the gain.
- **voyage-context-3 deferred** (unanimous): Schema is compatible (same 1024d), but running it concurrently with CNFB and Contextual Retrieval makes causal attribution impossible. Upgrading the embedding model resets the MRR baseline. Defer until after CNFB + Contextual Retrieval have clean numbers.
- **TASDI deferred**: Less empirical backing than Contextual Retrieval; similar LLM-at-index-time cost with narrower coverage (only typed but undocumented functions).

### Why CNFB First

- Zero schema migration, zero new API dependency
- Pure query-time additive signal: BM25 token overlap between query and filename → multiplicative boost (replaces the existing binary boost)
- If the query contains tokens that appear in a filename, the matching file's chunks should rank higher — this is a heuristic that is always correct in direction, never wrong
- Rollback is one flag; no index rebuild needed
- ML Engineer, Systems Architect, and DX all ranked this first (3/3 Round 1)

### Why Contextual Retrieval Second

- Anthropic's technique: at index time, use Claude Haiku to generate a context header per chunk ("This function is the main search entry point, called by the API layer, responsible for...") — prepended before embedding
- Addresses the root cause of rank-2 failures: chunks that are semantically correct but lack surrounding context (a bare `def embed()` chunk doesn't indicate it's the main embedding dispatch function)
- Empirical backing: Anthropic tested on 9 codebases, -35–67% retrieval failure rate
- Write-path change → entire existing retrieval stack (including voyage rerank-2) benefits automatically
- One-time cost ~$0.05 for the holusight codebase; one boolean env var (`CODESIGHT_CONTEXTUAL_RETRIEVAL=true`)
- Graceful degradation: if `ANTHROPIC_API_KEY` is absent, skip context generation and log warning

### Statistical Concern (ML Engineer)

With 20 queries and 100% hit rate, MRR improvement from 0.793 to 0.85 requires only 1–2 queries to move from rank 2 to rank 1. This is within noise margin. The eval corpus must be expanded to 80–100 queries before any result is treated as a production decision. Eval expansion is a prerequisite gate in Phase 2, not an afterthought.

## Consequences

### Positive
- CNFB: zero cost, zero risk, demonstrable improvement on filename-query alignment
- Contextual Retrieval: addresses the semantic gap for short/ambiguous chunk bodies
- Orthogonal axes: CNFB improves lexical/structural signal, Contextual Retrieval improves semantic signal — neither cannibalizes the other
- No schema migration required for either experiment
- Eval expansion makes future results trustworthy

### Negative / Risks
- Contextual Retrieval adds external LLM dependency at index time — air-gapped or cost-conscious users get a silently degraded index (mitigation: clear warning log, documented fallback behavior)
- 20-query eval is insufficient for statistical significance — results may not be real (mitigation: eval expansion as prerequisite gate)
- voyage-context-3 deferred — if it turns out to be the highest-leverage lever, we will have spent time on suboptimal experiments (mitigation: it's the third experiment in the sequence)

## What Was Rejected and Why

| Technique | Rejected | Reason |
|-----------|----------|--------|
| HyDE | Yes | 2025 paper: gains from LLM knowledge leakage, not retrieval. Hallucinated code hurts private-repo precision. |
| SHCD | Yes | Doubles reindex time on every incremental build. Permanent latency tax. |
| voyage-context-3 | Deferred | Schema-compatible but resets MRR baseline — cannot run concurrently with other experiments. Third experiment. |
| TASDI | Deferred | Less empirical backing; narrower coverage than Contextual Retrieval. |
| RAPTOR | Rejected | Designed for narrative documents, not code. |
| BGE-M3 multi-vector | Rejected | Large infra change; not tested on code; incompatible with current LanceDB schema. |
| Late chunking | Rejected | Requires token-level access to jina-embeddings, incompatible with voyage-code-3. |
| GFRC | Rejected | Isotonic regression on 20-query eval would severely overfit — eval-specific hack, not a real improvement. |
