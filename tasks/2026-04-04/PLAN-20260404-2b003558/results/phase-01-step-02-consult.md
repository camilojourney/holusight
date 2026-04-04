# Phase 1 Step 2 — Consult Engineering Output

**Skill:** /consult-engineering  
**CID:** CONSULT-ENG-20260404-3e0dc4f6  
**Date:** 2026-04-04  
**Specialists:** Systems Architect (Claude), ML Engineer (Gemini), Developer Experience (Claude)  
**Rounds:** 2 (Round 1 split 2-1 on #3 slot; Round 2 unanimous)

---

## Decision: Top Experiments to Implement

### UNANIMOUS (3/3) — Implement

**#1 — CNFB (Query-Aware Multiplicative Filename Boost)**
- What: Replace binary filename boost with multiplicative BM25 token overlap between query tokens and filename tokens
- Where: `search.py` — post-RRF, pre-reranker
- Why first: Zero schema migration, zero API dependency, purely additive signal, rollback = one flag
- Expected MRR lift: +0.01–0.03 (1-2 queries rank-1)
- Effort: S (< 1 day)
- Risk: LOW

**#2 — Contextual Retrieval (Index-time LLM Context Headers)**  
- What: At index time, use Claude Haiku to generate a 1-2 sentence context summary per chunk ("This function is the main search entry point, called by the API layer..."), prepend to chunk before embedding
- Where: `indexer.py` + `chunker.py` — write path
- Why: Addresses root cause of rank-2 failures — bare function bodies lack surrounding context that human queries assume
- Empirical backing: Anthropic tested on 9 codebases, -35–67% retrieval failure rate
- One-time cost: ~$0.05 for holusight codebase
- Env var gate: `CODESIGHT_CONTEXTUAL_RETRIEVAL=true` (graceful fallback if no key)
- Expected MRR lift: +0.03–0.06 (2-4 queries rank-1)
- Effort: M (2-3 days including index rebuild + test)
- Risk: MEDIUM (external LLM dependency at index time; silent degradation without key)

### PREREQUISITE GATE (2/3 required, 3/3 acknowledged)

**Eval corpus expansion to 80–100 queries**
- Why: 20-query eval means +0.057 MRR = only 1-2 queries changing rank. This is noise, not signal.
- Must expand before treating any MRR result as a production decision
- This is NOT an experiment — it's the measurement infrastructure that makes experiments valid
- ML Engineer: HIGH confidence this is required
- DX: "recommending experiments without it is recommending theater"
- Systems Architect: acknowledged the statistical concern explicitly

---

## Deferred (for Phase 3 or later)

| Technique | Status | Reason |
|-----------|--------|--------|
| voyage-context-3 | Deferred (3rd experiment) | Resets MRR baseline; cannot run concurrently. Schema-compatible. |
| TASDI | Deferred | Less empirical backing; narrower than Contextual Retrieval |
| SHCD | Rejected | Doubles reindex time on every incremental build |
| HyDE | Rejected | 2025 paper: gains from LLM knowledge leakage, not retrieval |
| RAPTOR/BGE-M3/GFRC | Rejected | Architecture incompatibility or eval overfitting risk |

---

## Recommended Implementation Sequence for Phase 2

```
Step 1: Expand eval corpus to 80-100 queries (prerequisite gate)
Step 2: Implement CNFB — measure delta on expanded eval
Step 3: If MRR < 0.85: implement Contextual Retrieval — measure delta
Step 4: Gate (hard) — user approves before commit
Step 5: If still < 0.85: implement voyage-context-3 as isolated experiment
```

---

## Decision Record

Full ADR: `docs/decisions/0009-2026-04-04-retrieval-experiments.md`

---

## Key Risks Flagged by Specialists

1. **Statistical validity** (ML Engineer, HIGH): 20-query eval insufficient. Any result could be noise.
2. **Silent degradation** (DX): Contextual Retrieval without ANTHROPIC_API_KEY → silently degraded index, invisible quality split between users
3. **Attribution collapse** (Systems Architect): If voyage-context-3 runs concurrently, cannot attribute MRR changes
