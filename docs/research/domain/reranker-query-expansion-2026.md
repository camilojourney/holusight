---
last_updated: 2026-04-03
review_cadence: 30d
next_review: 2026-05-03
---

# Adversary Research Report — Phase 1 Assumption Check
# Plan: PLAN-20260403-df2d49dc / Phase 1 / Step 0
# Mode: ADVERSARY
# Question: Challenge voyage rerank-2.5 and LLM query expansion assumptions for 2026

---

## Verdict: PROCEED_WITH_MODIFICATIONS

Both changes are directionally correct but require targeted modifications based on 2026 evidence.

---

## CLAIM 1: "Swap to voyage rerank-2.5"

### GO — with one clarification

**voyage rerank-2.5 is the correct choice.** [VERIFIED]

- rerank-2.5 was released Aug 2025 and is the current recommended Voyage model (rerank-2 is now Legacy). Source: https://blog.voyageai.com/2025/08/11/rerank-2-5/
- It outperforms Cohere Rerank v3.5 by +7.94% on 93-dataset suite [VERIFIED]
- It has a 32K token context window (vs 16K on rerank-2) — critical for large code files [VERIFIED]
- No rerank-3 exists as of April 2026. The product line ends at rerank-2.5. [VERIFIED]

**What challenges this:**

zerank-2 (ZeroEntropy, open-weight) tops the Agentset ELO leaderboard at 1638 ELO vs Voyage 2.5's implied placement. However: [UNVERIFIED for code specifically]
- zerank-2 has no published CoIR (Code Information Retrieval) or MTEB-Code benchmark scores
- The Agentset leaderboard measures general RAG, not code retrieval
- zerank-2 latency is 265ms vs Voyage's <100ms for batch API use
- zerank-2 requires self-hosting (no managed API)

Cohere Rerank 4 Pro (Dec 2025, ELO 1629) shows strong improvements only on business/finance tasks — no code-specific benchmark numbers found. [VERIFIED that code numbers are absent]

**Qwen3-Reranker-8B MTEB-Code score of 81.22 is the highest found for any reranker on a code benchmark** [VERIFIED] — but latency is 4687ms which makes it unusable in a coding assistant context.

**Decision: Use voyage rerank-2.5 (not rerank-2 as originally planned — use 2.5, the current model).** Self-hosted alternatives score higher on code benchmarks but have prohibitive latency (4.7s) or no managed API.

---

## CLAIM 2: "Add LLM query expansion (3 variants via claude-haiku)"

### NO-GO as designed — MODIFY to VPRF instead

**LLM query expansion has serious documented problems in 2026:** [VERIFIED]

1. **Degrades retrieval when LLM knowledge is insufficient.** NDCG@10 dropped -8.63 in knowledge-limited conditions (Abe et al. 2025, arXiv). For code search this matters: asking about obscure internal function names the LLM has never seen.
   Source: https://arxiv.org/html/2505.12694v1

2. **Multi-query fusion HURTS accuracy in production deployments.** March 2026 industry study showed Hit@10 dropped from 51.3% → 44.4-47.8% with fusion. "Gains largely neutralized after re-ranking and truncation." [VERIFIED]
   Source: https://arxiv.org/html/2603.02153

3. **Latency cost is prohibitive.** Multi-query fusion adds ~11.4 seconds overhead per query. Target for a coding assistant is <300ms total. [VERIFIED from same source]

4. **Better alternative exists: LLM-VPRF** — Vector Pseudo Relevance Feedback. [VERIFIED]
   - Adds ~5ms overhead (vs 500-1000ms for LLM expansion)
   - No hallucination risk (modifies embedding vectors, not query text)
   - Shows +1.0-2.1% nDCG@10 gains with zero latency penalty
   - Source: https://arxiv.org/html/2504.01448v1

**HyDE (Hypothetical Document Embeddings):**
- Shows 19-26% improvement on Stack Overflow developer support [VERIFIED]
- But: fails in ~25% of concept-focused queries, strong LLMs gain little benefit (Qwen3-8B showed negligible gains), and generates 5 LLM calls per query
- Source: https://arxiv.org/html/2507.16754v1
- Verdict: promising but not production-ready as default; better as an opt-in mode

---

## Adversary Analysis

### Strongest argument AGAINST our reranker plan
The absence of code-specific benchmarks for voyage rerank-2.5 means we're extrapolating from general RAG performance to code retrieval. Qwen3-Reranker-8B scored 81.22 on MTEB-Code — the only code-specific benchmark found — and it's open-weight. If we ran it at index time (batch reranking, not real-time), the latency problem disappears. We are potentially leaving accuracy on the table by defaulting to API convenience.

### What makes us regret this in 6 months?
If Voyage releases rerank-3 with code-specific training (they have voyage-code-3 embedding, a rerank-3-code is plausible). Also: zerank-2 publishing CoIR benchmarks showing 10%+ gains over voyage rerank-2.5 would invalidate our choice.

### Risk matrix
| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| LLM query expansion adds noise for internal APIs | HIGH | HIGH | Use VPRF instead |
| voyage rerank-2.5 not optimal for code | MED | MED | Run ablation after Phase 1 eval |
| Multi-query fusion degrades accuracy | HIGH | HIGH (verified) | Do NOT implement multi-query fusion |
| zerank-2 outperforms voyage on code | MED | LOW (no code benchmarks) | Re-evaluate if CoIR scores published |

### Missing evidence
- voyage rerank-2.5 CoIR or MTEB-Code benchmark score (not published)
- Head-to-head: voyage rerank-2.5 vs Qwen3-Reranker-8B on CodeSearchNet

---

## Decision Points

DECISION_POINT: reranker_model
OPTIONS: A) voyage rerank-2.5 (API, no code benchmark, strong general) B) Cohere Rerank 4 Pro (no code benchmark, business-focused) C) Qwen3-Reranker-8B (best MTEB-Code score, 4.7s latency)
RECOMMENDATION: A
CONFIDENCE: HIGH
EVIDENCE: [VERIFIED] voyage rerank-2.5 is current model, +7.94% over Cohere v3.5 on 93 datasets — https://blog.voyageai.com/2025/08/11/rerank-2-5/

DECISION_POINT: query_expansion_strategy
OPTIONS: A) LLM 3-variant expansion via haiku (original plan) B) No expansion C) LLM-VPRF (vector PRF, modify query embedding post-retrieval)
RECOMMENDATION: C (VPRF) for default; A as opt-in only
CONFIDENCE: HIGH
EVIDENCE: [VERIFIED] Multi-query fusion decreases Hit@10 in production (44-48% vs 51% baseline), +11.4s latency — https://arxiv.org/html/2603.02153. VPRF adds 5ms overhead, +1-2% nDCG@10 — https://arxiv.org/html/2504.01448v1

DECISION_POINT: hyde_usage
OPTIONS: A) HyDE as default B) HyDE as opt-in C) Skip HyDE
RECOMMENDATION: B (opt-in via CODESIGHT_HYDE=true)
CONFIDENCE: MEDIUM
EVIDENCE: [VERIFIED] 19-26% lift on developer Q&A, fails 25% of concept queries — https://arxiv.org/html/2507.16754v1

---

## Impact on Phase 1 Steps

**Step 1 (reranker swap): PROCEED** — swap to voyage rerank-2.5 as planned (the upgrade from rerank-2 is a 1.85% boost for free).

**Step 2 (query expansion): MODIFY** — Instead of LLM 3-variant expansion, implement LLM-VPRF: after initial retrieval, take top-3 results, average their embeddings with the original query embedding (weighted 0.8 original + 0.2 feedback), re-search. 5ms overhead, no hallucination risk.

**Step 3 (HyDE): ADD as Phase 4 opt-in** — not a default behavior.

---

## Discarded Claims
> [UNVERIFIED] "zerank-2 claims code domain leadership" — No independent CoIR/MTEB-Code scores found. Marketing claim only.

## Sources
1. https://blog.voyageai.com/2025/08/11/rerank-2-5/ — Voyage rerank-2.5 release
2. https://docs.voyageai.com/docs/reranker — Official reranker docs
3. https://agentset.ai/rerankers — ELO leaderboard
4. https://cohere.com/blog/rerank-4 — Cohere Rerank 4 announcement
5. https://arxiv.org/html/2603.02153 — RAG-Fusion industry deployment (March 2026)
6. https://arxiv.org/html/2504.01448v1 — LLM-VPRF paper
7. https://arxiv.org/html/2505.12694v1 — LLM expansion degradation study
8. https://arxiv.org/html/2507.16754v1 — Adaptive HyDE on developer support
9. https://arxiv.org/abs/2212.10692 — GACR code retrieval paper
10. https://arxiv.org/html/2509.07794v1 — Query expansion survey
