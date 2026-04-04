---
last_updated: 2026-04-03
review_cadence: 30d
next_review: 2026-05-03
research_cid: holusight-RESEARCH-20260403-c89f3a9d
---

# Adversary Research: Chunking Strategy for Code Search (2026)

**Mode:** ADVERSARY — challenge 5 assumptions against 2026 SOTA  
**Context:** System at MRR@10=0.599, hit_rate=100%. Gap is ranking (rank 3–10 instead of rank 1), not recall.

## Verdict: PROCEED_WITH_MODIFICATIONS

All five assumptions survive but with important caveats. The highest-leverage fix is the **cross-encoder reranker** (always-on), not chunking. AST chunking is the right chunking approach but requires voyage-code-3 to realize gains. Late chunking has NO evidence for code.

---

## Assumption Review

### A1: Tree-sitter scope-based chunking is best
**VERDICT: PROCEED_WITH_MODIFICATIONS**

- [VERIFIED] cAST paper (EMNLP 2025, arXiv:2506.15655): AST-based chunking beats fixed-size by +4.3pp Recall@5 and +2.67pp Pass@1 on SWE-bench. This validates scope-based chunking.
- **CRITICAL CAVEAT:** The gain is **embedding-model-dependent**. With BGE-base, fixed-size actually beats AST on nDCG@5 (71.3 vs 71.1). With GIST-base: AST wins (+4.3pp recall). With CodeSage-small-v2: AST wins.
- [VERIFIED] Supermemory production blog (Dec 2025): AST chunking (code-chunk) achieved 70.1% Recall@5 vs 49.0% for sliding window (+21.1pp) and 42.4% for fixed-size (+27.7pp) on corrected RepoEval with IoU@5 metric.
- **Action:** Keep tree-sitter scope-based chunking. To get the gains, must upgrade to voyage-code-3 embedding — the lift collapses with generic embeddings.

### A2: Fixed overlap (50 lines) is optimal
**VERDICT: PROCEED WITH CAUTION — UNVERIFIED**

- No 2025-2026 paper benchmarks chunk overlap for code specifically.
- [UNVERIFIED] General guidance suggests 10–20% overlap is sufficient; 50 lines may be excessive (creates redundant chunks that dilute reranker signal).
- Vectara/UW-Madison NAACL 2025 (arXiv:2410.13070): "chunking configuration has equal or greater influence on retrieval quality than embedding model choice" — but does not test overlap specifically.
- **Action:** Do NOT change overlap in Phase 2. Collect evidence first. This is a Phase 4 ablation experiment.

### A3: Late chunking is better for code
**VERDICT: NO-GO — NO EVIDENCE**

- [UNVERIFIED] arXiv:2409.04701 (late chunking paper, v3 July 2025): All benchmarks are biomedical/financial/news. ZERO code-specific datasets.
- General text gain: +1.8pp nDCG@10 average across BeIR. Marginal.
- ConTEB preprint (2505.24782): +23.6 nDCG@10 with late chunking + InSeNT, but on cross-boundary QA tasks, not code.
- Late chunking requires a model that supports mean-pooling over full-document context — incompatible with sentence-transformers/all-MiniLM used locally.
- **Action:** Do NOT implement late chunking. No evidence it helps code. Revisit if voyage-context-3 API model is adopted.

### A4: Contextual retrieval (context headers) gives meaningful lift
**VERDICT: PROCEED_WITH_MODIFICATIONS**

- [VERIFIED] Anthropic contextual retrieval (Sep 2024): 35–67% failure reduction tested explicitly including codebases. With reranking: failure rate 5.7% → 1.9%.
- [VERIFIED] voyage-context-3 (Jul 2025, 93 datasets): +14.24% NDCG@10 vs OpenAI-v3-large at chunk level. Includes code datasets.
- **WARNING:** ContextBench (arXiv:2602.05892, Feb 2026, PRIMARY): specifically tests code context retrieval in coding agents and finds "sophisticated scaffolding does NOT consistently outperform simple baselines." LLMs introduce noise that can harm precision.
- **Distinction:** ContextBench tests agent-level scaffolding, not chunk-level static context prepending. These are different interventions. Static headers (file path + scope + line range) are low-risk; LLM-generated context summaries are higher-risk.
- **Action:** Keep existing static context headers (`# File: X\n# Scope: Y\n# Lines: Z-Z`). Do NOT add LLM-generated context summaries. The static headers already provide contextual retrieval benefit.

### A5: Parent-child chunking improves accuracy and token efficiency
**VERDICT: PROCEED — mechanism sound, evidence multi-domain**

- No peer-reviewed paper benchmarks parent-child with MRR/NDCG on code specifically.
- [VERIFIED] FloTorch 2026 explains the mechanism: small semantic chunks achieve 91.9% recall but only 54% end-to-end accuracy because 43-token fragments lack context for generation. Parent-child solves this directly.
- arXiv:2507.09935 (Jul 2025): Hierarchical segment-cluster chunking +5.9% to +11.8% on QA benchmarks vs flat.
- EMNLP 2025 MultiDocFusion: +8–15% retrieval precision with hierarchical chunking.
- Token efficiency: logical — retrieve small (high precision), expand to parent (sufficient context). Fewer tokens per correct answer than retrieving K large chunks.
- **Action:** Implement in Phase 3. Low risk, strong theoretical basis, multi-domain evidence.

---

## What Actually Moves MRR@10 from 0.599 → 0.75+

Root cause: 100% hit rate means the right answer is always in top-10. This is a **pure ranking problem**. The fix is reranking calibration.

| Lever | Expected MRR Lift | Evidence | Status |
|-------|-------------------|----------|--------|
| Cross-encoder reranker (always-on, not opt-in) | +0.05–0.07 absolute | [VERIFIED] TOSS: 0.713→0.763 MRR; prod: 0.640→0.708 MRR | Phase 1 ✓ (but opt-in — consider always-on) |
| AST-based function-level chunks | +4.3pp Recall@5 | [VERIFIED] cAST EMNLP 2025 | Phase 2 target |
| voyage-code-3 embedding for code files | +13.8% NDCG@10 | [VERIFIED] Voyage blog, CoIR ACL 2025 | Already wired, needs VOYAGE_API_KEY |
| Parent-child chunks | +5.9–15% QA accuracy | Multi-domain evidence | Phase 3 target |
| Context headers (static file/scope) | 35–67% failure reduction | [VERIFIED] Anthropic Sep 2024 | Already implemented |

**Key insight from Gatherer 3:** The TOSS architecture (MRR 0.763 on CodeSearchNet) is already our architecture. The gap to 0.75 is closed by ensuring the reranker is always-on and getting better chunk boundaries.

---

## Adversary Analysis

### Strongest argument AGAINST Phase 2 (AST chunking)

The cAST gains (+4.3pp Recall@5) **collapse with some embedding models** (BGE-base: AST loses to fixed-size on nDCG@5). Our current default embedding is all-MiniLM-L6-v2, which is the weakest model tested. We may invest significant re-indexing effort for near-zero gain unless we simultaneously upgrade to voyage-code-3.

### What makes us regret Phase 2 in 6 months?

We upgrade chunking but keep all-MiniLM as the local embedding default. Users without VOYAGE_API_KEY see degraded performance. We ship a Phase 2 that only helps users with the API key.

### Risk matrix

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| AST gains vanish with all-MiniLM | HIGH | MEDIUM | Run ablation before committing re-index |
| Re-index breaks production indexes | HIGH | LOW | Bump schema version, migrate gracefully |
| Late chunking implementation wastes sprint | MEDIUM | LOW | Already NO-GO above |
| Parent-child adds schema complexity | MEDIUM | MEDIUM | Design schema change carefully in Phase 3 |
| ContextBench warning materializes | LOW | LOW | Static headers are low-risk; avoid LLM-generated context |

### Missing evidence

- MRR@10 (not nDCG@10) is almost absent from 2025-2026 code search papers. Our primary metric is MRR, but the literature benchmarks nDCG. The correspondence is strong (rank-1 emphasis) but not exact.
- Anthropic contextual retrieval appendix (code-specific breakdown) was binary-encoded and inaccessible. The domain-averaged 35–67% numbers include code but code-isolated figures unknown.
- No paper tests scope-based chunking (function/class level) with 50-line overlap — the exact configuration CodeSight uses. Closest is cAST which does function-level without overlap.

---

## Decision Points

DECISION_POINT: chunking_strategy_phase2
OPTIONS: A) AST-based function-level (no overlap) B) Current tree-sitter scope-based (50-line overlap) C) Late chunking
RECOMMENDATION: A
CONFIDENCE: HIGH
EVIDENCE: [VERIFIED] cAST EMNLP 2025 +4.3pp Recall@5 on RepoEval. Supermemory prod +21pp Recall@5 over sliding window.

DECISION_POINT: overlap_change
OPTIONS: A) Remove overlap (function-level boundaries are complete units) B) Keep 50-line overlap C) Reduce to 10 lines
RECOMMENDATION: A
CONFIDENCE: MEDIUM
EVIDENCE: [UNVERIFIED] No paper benchmarks overlap specifically for code. Function boundaries are natural complete units — overlap adds redundancy.

DECISION_POINT: late_chunking
OPTIONS: A) Skip B) Implement with voyage-context-3 C) Implement with sentence-transformers
RECOMMENDATION: A
CONFIDENCE: HIGH
EVIDENCE: [UNVERIFIED for code] arXiv:2409.04701 has zero code-specific benchmarks. ContextBench Feb 2026 warns against sophisticated scaffolding for code agents.

DECISION_POINT: context_headers
OPTIONS: A) Keep static headers (current) B) Add LLM-generated context summaries C) Remove headers
RECOMMENDATION: A
CONFIDENCE: HIGH
EVIDENCE: [VERIFIED] Anthropic Sep 2024 — static contextual retrieval works. ContextBench Feb 2026 — LLM scaffolding does NOT consistently improve code precision.

DECISION_POINT: reranker_mode
OPTIONS: A) Always-on (remove opt-in gate for voyage/local) B) Keep opt-in C) Remove reranker
RECOMMENDATION: A (with config override)
CONFIDENCE: HIGH
EVIDENCE: [VERIFIED] TOSS MRR 0.763 with always-on cross-encoder. Production deployment: 0.640→0.708 absolute MRR gain.

---

## Discarded Claims

> [UNVERIFIED] "Late chunking improves code retrieval" — arXiv:2409.04701 explicitly has NO code datasets. Claim does not apply to code search systems.

---

## Sources

1. [cAST: AST-Based Chunking for Code RAG (EMNLP 2025)](https://arxiv.org/abs/2506.15655) — PRIMARY [VERIFIED]
2. [TOSS: Two-Stage Code Search (WSDM 2023 / Microsoft Research)](https://arxiv.org/abs/2208.11274) — PRIMARY [VERIFIED]
3. [Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) — PRIMARY [VERIFIED]
4. [Late Chunking: Contextual Chunk Embeddings (Jina, arXiv:2409.04701)](https://arxiv.org/abs/2409.04701) — PRIMARY
5. [voyage-code-3: Code Retrieval Benchmark (Voyage AI, Dec 2024)](https://blog.voyageai.com/2024/12/04/voyage-code-3/) — PRIMARY
6. [CoIR: Code Information Retrieval Benchmark (ACL 2025)](https://arxiv.org/abs/2407.02883) — PRIMARY
7. [Beyond More Context: Granularity Matters (Oct 2025)](https://arxiv.org/abs/2510.06606) — PRIMARY
8. [OASIS: Order-Augmented Code Search (ACL 2025)](https://arxiv.org/abs/2503.08161) — PRIMARY
9. [Hierarchical Chunking for QA (Jul 2025)](https://arxiv.org/abs/2507.09935) — PRIMARY
10. [ContextBench: Code Context Retrieval in Agents (Feb 2026)](https://arxiv.org/abs/2602.05892) — PRIMARY
11. [Vectara Chunking Study (NAACL 2025)](https://arxiv.org/abs/2410.13070) — PRIMARY
12. [Supermemory: AST-Aware Code Chunking (Dec 2025)](https://supermemory.ai/blog/building-code-chunk-ast-aware-code-chunking/) — SECONDARY
13. [ConTEB: Contextual Embeddings Benchmark (arXiv:2505.24782, 2025)](https://arxiv.org/abs/2505.24782) — PRIMARY
14. [FloTorch 2026 RAG Chunking Benchmark](https://blog.premai.io/rag-chunking-strategies-the-2026-benchmark-guide/) — SECONDARY
