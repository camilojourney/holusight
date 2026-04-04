---
last_updated: 2026-04-04
review_cadence: 30d
next_review: 2026-05-04
---

# Research: Pushing CodeSight MRR from 0.793 to 0.85+

**Baseline:** MRR@10 = 0.793, Hit Rate = 100% (20-query holusight eval)
**Current stack:** AST chunking (tree-sitter), BM25+vector RRF, voyage-code-3 1024d, voyage rerank-2, metadata filename boost, VPRF
**Root problem:** Correct results are retrieved but land at rank 2–3 instead of rank 1. Need to improve rank ordering.

---

## Known Techniques from 2024–2026 Literature

### 1. HyDE — Hypothetical Document Embeddings

- **Mechanism:** Generate a hypothetical document/code snippet answering the query. Embed that synthetic document (not the query) for vector search.
- **Code retrieval numbers:** No primary benchmark found for code. General text: +8.6 pp NDCG@5 on SciFact, +10.5 pp Recall@5 on FEVER. [VERIFIED] — https://arxiv.org/html/2504.14175v1
- **⚠️ Critical finding:** A 2025 paper argues HyDE gains on open-domain QA benchmarks come from LLM knowledge leakage (memorized content), not genuine retrieval improvement. [VERIFIED] — https://arxiv.org/html/2504.14175v1. When the LLM lacks domain knowledge (e.g., private codebases), hallucinated code in the hypothetical document can hurt precision.
- **Verdict for CodeSight:** HIGH RISK. Code is diverse; LLM-generated hypothetical code for "how does embedding work" may contain hallucinated API calls that retrieve the wrong module. Not recommended as first experiment.

### 2. Late Chunking (Jina AI, 2024)

- **Mechanism:** Feed the ENTIRE document through a long-context encoder; THEN chunk by applying mean-pooling within chunk spans. Each chunk's embedding has full-document context.
- **Numbers (general text, nDCG@10):** +1.8–1.9 pp absolute (+3.5% relative) for 256-token chunks. [VERIFIED] — https://arxiv.org/html/2409.04701v3
- **Code retrieval numbers:** NOT tested in primary literature.
- **Implementation complexity:** Requires a long-context encoder (jina-embeddings-v2 or nomic-embed); incompatible with voyage-code-3 (which doesn't expose token-level embeddings). Schema break: LanceDB dimension change required.
- **Verdict:** MEDIUM potential, HIGH compatibility risk. Would require switching from voyage-code-3.

### 3. Contextual Retrieval (Anthropic, 2024)

- **Mechanism:** For each chunk, LLM generates a ~50–100 token context summary ("This function is called by X and implements Y in the context of Z"). Prepend to chunk before embedding AND BM25 indexing.
- **Numbers (retrieval failure rate at top-20, codebase domain):** −35% failure rate with contextual embeddings alone; −49% with contextual BM25 added; −67% with full pipeline + reranker. [UNVERIFIED — measured as recall@20 failure rate, not MRR] — https://www.anthropic.com/news/contextual-retrieval
- **Code retrieval:** Explicitly tested on 9 codebases with 248 queries. One of four evaluation domains.
- **Verdict:** HIGH potential, MEDIUM effort. One-time LLM cost at index time. Directly addresses the rank ordering problem (richer context → better embedding → better rank). Compatible with voyage-code-3.

### 4. BGE-M3 Multi-Vector (ColBERT-style)

- **Mechanism:** Multi-vector per document (one per token). MaxSim scoring. Can combine dense + sparse + multi-vector heads.
- **Numbers (MIRACL nDCG@10):** All-combined 70.0 vs dense-only 67.8 (+2.2 pp). [VERIFIED] — https://arxiv.org/html/2402.03216v3
- **Code retrieval:** NOT tested in BGE-M3 paper. On CoIR, not in top 3.
- **Verdict:** Large infrastructure change (FAISS PLAID or specialized index). Not compatible with current LanceDB single-vector schema without major refactor. LOW priority.

### 5. RAPTOR (ICLR 2024)

- **Mechanism:** Hierarchical clustering + LLM summarization of clusters → tree structure. Retrieval at multiple abstraction levels.
- **Numbers:** +20 pp accuracy on QuALITY (long doc QA). Good for thematic questions across long documents. [VERIFIED] — ICLR 2024 paper.
- **Code retrieval:** NOT tested. Designed for narrative documents, not codebases.
- **Verdict:** Not applicable to CodeSight's code-retrieval use case. Skip.

### 6. Multi-Query Expansion / Query Decomposition (DMQR-RAG, 2024)

- **Mechanism:** Generate N query variants, retrieve for each, merge with RRF.
- **Numbers:** +15 pp P@5 on AmbigNQ (open-domain QA). [VERIFIED] — https://arxiv.org/html/2411.13154v1
- **Code retrieval:** NOT tested. All results on Wikipedia-based QA.
- **Known risk:** Same knowledge leakage concern as HyDE for LLM-generated expansions.
- **Verdict:** MEDIUM potential for code. Adds N× query latency. Could help "how does embedding work" by generating variants like "embedding function implementation" and "text to vector conversion".

### 7. voyage rerank-2 vs BGE-reranker-v2-m3

- Already using voyage rerank-2. It outperforms BGE v2-m3 by 14.75% on average across 93 datasets. [UNVERIFIED — vendor numbers] — https://blog.voyageai.com/2024/09/30/rerank-2/
- Current implementation is already optimal.

### 8. voyage-context-3 (Voyage AI, July 2025)

- **Mechanism:** Voyage's contextual chunk embeddings — each chunk embedding encodes both chunk content AND full-document context, natively in the model.
- **Numbers vs other models (chunk-level):** +14.24% vs OpenAI-v3-large, +12.56% vs Cohere-v4, +23.66% vs Jina-v3 late chunking, +6.76% vs Anthropic contextual retrieval. [UNVERIFIED — vendor blog, no independent benchmark]
- **Verdict:** Drop-in replacement for voyage-code-3 (same 1024d schema, same API). Could give +6–14% improvement over current embedding. HIGH potential, LOW implementation complexity (one flag change + re-index).

---

## Novel Experiment Ideas (Original — Not in Literature)

### Novel-1: Signature-Header Chunk Duplication (SHCD) ⭐ Recommended

**Mechanism:** For every function/class chunk, create an additional ultra-compact "header chunk" containing ONLY: function signature + first docstring sentence + return type + parameter types. Index this header chunk alongside the full chunk. At retrieval, search both indexes, merge with RRF (full_chunk:0.7, header_chunk:0.3).

**Why it improves MRR:** "how does embedding work" is semantically closest to `def embed(text: str) -> List[float]` + `"Converts text to a dense vector representation"` — the semantic CONTRACT, not the implementation. The header chunk forces the embedding model to concentrate on contract semantics, reducing noise from numpy ops and API calls in the body.

**Implementation:** S (< 50 lines — post-process AST chunks, extract signature + first docstring sentence + type hints, write to separate LanceDB column)

**Risk:** Functions without docstrings or type hints → header chunks are nearly empty. Mitigation: only create header chunks when `len(docstring) > 0 OR len(annotations) > 2`.

### Novel-2: LLM Functional Role Query Expansion (FQRE) ⭐⭐ Top Recommendation

**Mechanism:** For each query, use fast LLM (Haiku) to generate 3 functional role paraphrases:
- (a) "what it does" version: "convert text to vector representation"
- (b) "how it's used" version: "call a function to get embeddings from text"
- (c) "what it returns" version: "function that outputs a float array from a string"

Embed original + 3 variants, run 4 retrievals, merge with RRF (original_weight=1.0, variants=0.6).

**Why it improves MRR:** Role-based paraphrases specifically address the NL→code semantic gap. Variant (a) maps to docstrings; variant (c) maps to return type annotations. At least 2 of 4 query embeddings land in the right neighborhood. Unlike HyDE (generates fake code), this generates NL paraphrases with zero hallucination risk.

**Implementation:** M (~100 lines — async Haiku calls, 4 embedding calls, RRF with configurable weights)

**Risk:** +200–400ms query latency. Only needed when VOYAGE_API_KEY is set (same gate as other API features). Can be opt-in via `CODESIGHT_QUERY_EXPANSION_MODE=functional`.

### Novel-3: Call-Graph-Aware Chunk Stitching (CGACS)

**Mechanism:** Extract function call relationships (tree-sitter queries). For each function chunk, append: `Called by: [retrieve, evaluate_index]. Calls: [tokenize, normalize_vector]`. At retrieval, also expand top-K to include 1-hop callers (at 0.4× score weight).

**Implementation:** L (200+ lines — static analysis pass, call graph construction, graph expansion at query time)

**Risk:** Language-specific; dynamic dispatch breaks static analysis. Worth doing as a later experiment after simpler wins.

### Novel-4: Type-Annotation Synthetic Docstring Injection (TASDI) ⭐⭐ Top Recommendation

**Mechanism:** For functions with type annotations but no/minimal docstring, use Haiku to generate a synthetic 1-sentence docstring from ONLY the signature. Inject into chunk text at index time. Store `doc_source: synthetic` flag.

**Why it improves MRR:** `embed(text: str) -> List[float]` → synthesized: `"Converts text input to a dense float vector for similarity search."` — exactly what "how does embedding work" maps to. Fixes the semantic gap at index time (no query-time latency).

**Implementation:** M (~80 lines — one-time batch LLM pass at index time; regenerate on file change)

**Risk:** One-time cost ~$0.002/1000 functions. Stale after refactors. LLM may be inaccurate for complex functions.

### Novel-5: Query-Aware Multiplicative Filename Boost (CNFB)

**Mechanism:** Current filename boost is stable re-ordering (binary). CNFB makes it query-aware: compute BM25 token overlap between query and filename. Apply multiplicative boost: `score × (1 + α × filename_overlap)` where α=0.3. Higher overlap = stronger boost.

**Implementation:** S (< 30 lines — BM25 tokenize query, compute overlap with filename tokens, apply multiplicative factor to reranker scores)

**Risk:** Over-boosts test files (`test_embeddings.py`) — mitigation: exclude files matching `test_*` pattern from boost.

### Novel-6: HyPE — Hypothetical Prompt Embeddings at Index Time ⭐ Recommended

**Mechanism:** For each function/class chunk, use Haiku to generate 3–5 natural language questions the chunk answers (e.g., for `embed()`: "How do I convert text to a vector?", "What function generates embeddings?"). Store question embeddings in a separate index. At query time, search question index + code index in parallel, merge with RRF (question_index=0.4, code_index=0.6).

**Why it improves MRR:** Inverse of HyDE. Instead of making the query look like a document, make each document look like the queries it answers. No query-time LLM latency. The question index directly retrieves chunks whose pre-generated questions match the user's query.

**Implementation:** M (~150 lines — one-time batch LLM pass, store question embeddings, dual-index search)

**Risk:** Storage doubles (two embedding stores). One-time LLM cost ~$0.01/1000 functions.

### Novel-7: Cross-File Near-Duplicate Rank Diversity Injection (CSDRDI)

**Mechanism:** After retrieval, detect near-duplicate chunks (cosine similarity > 0.92 between top-20 results). Apply diversity penalty to lower-ranked duplicates: `score × (1 - 0.15 × (k-1))` where k is the duplicate rank. This prevents wrapper/implementation near-duplicates from occupying ranks 1 and 2 simultaneously.

**Implementation:** S (< 50 lines — pairwise cosine on top-20 embeddings, apply penalty)

**Risk:** May over-penalize legitimately equivalent answers.

### Novel-8: Gradient-Free Score Calibration via Isotonic Regression (GFRC)

**Mechanism:** Use the 20-query eval set to train an isotonic regression mapping (reranker_score, bm25_score, filename_boost) → final score. Learns codebase-specific correlations invisible to generic RRF.

**Implementation:** S (< 50 lines — sklearn IsotonicRegression, leave-one-out CV to validate)

**Risk:** With only 20 examples, overfitting risk is high. Need to validate with LOO-CV before deploying.

---

## Options Compared (Ranked by Expected MRR Impact × Effort)

| Technique | Type | Est. MRR Lift | Effort | Risk | Recommended? |
|-----------|------|---------------|--------|------|--------------|
| voyage-context-3 upgrade | Drop-in | +5–10% relative | S (re-index only) | LOW | ✅ #1 |
| FQRE (functional role query expansion) | Novel | +3–7% relative | M | LOW-MED | ✅ #2 |
| TASDI (synthetic docstring injection) | Novel | +3–6% relative | M | LOW | ✅ #3 |
| Contextual Retrieval (Anthropic-style) | Known | +5–8% relative | M/L | LOW | ✅ #4 |
| SHCD (signature-header chunk duplication) | Novel | +2–4% relative | S | LOW | ✅ #5 |
| CNFB (query-aware filename boost) | Novel | +1–3% relative | S | LOW | ✅ #6 |
| HyPE (question generation at index) | Novel | +3–5% relative | M | MED | Consider |
| GFRC (isotonic score calibration) | Novel | +1–3% relative | S | MED | Consider |
| CSDRDI (diversity injection) | Novel | +1–2% relative | S | LOW | Later |
| Multi-query expansion (DMQR-style) | Known | +2–5% relative | M | MED | Later |
| Call-graph stitching (CGACS) | Novel | +3–6% relative | L | HIGH | Later |
| HyDE | Known | UNKNOWN, risk negative | M | HIGH | ❌ |
| Late Chunking | Known | +3% on general text | L | HIGH compat | ❌ |
| RAPTOR | Known | Not applicable to code | L | N/A | ❌ |
| BGE-M3 multi-vector | Known | Not tested on code | L | HIGH compat | ❌ |

---

## Recommendation

**Highest confidence path to MRR 0.85+:**

**Option A (easiest — no LLM cost):** voyage-context-3 upgrade + CNFB (query-aware filename boost)
- voyage-context-3 is a drop-in model swap with the same 1024d interface (verify schema compatibility)
- CNFB is 30 lines, directly targets rank-2 problem
- Combined est. MRR lift: 0.793 × 1.08 × 1.02 ≈ 0.873 (if voyage-context-3 numbers hold for code)

**Option B (most novel, medium effort):** FQRE + TASDI
- FQRE: query-time functional role expansion — 3 NL paraphrases, no hallucination risk
- TASDI: index-time synthetic docstrings for type-annotated but undocumented functions
- Combined est. MRR lift: 0.793 × 1.05 × 1.04 ≈ 0.866

**Option C (robust, highest ceiling):** Contextual Retrieval (Anthropic-style) for code
- LLM-generated context headers per chunk at index time
- Directly tested on codebases (248 queries, 9 repos)
- Est. MRR lift: similar to −35–49% failure rate reduction → translates to +0.05–0.08 MRR lift

---

## Adversary Analysis

### Strongest argument AGAINST the top recommendation

**voyage-context-3** is a vendor product released July 2025 with only self-reported benchmarks. The +6.76% over Anthropic contextual retrieval is from a Voyage AI blog post with no independent replication. The specific number (+6.76%) is unverified. voyage-code-3 (which we currently use) already incorporates code-specific training; voyage-context-3 adds contextual chunk encoding but its gain on code specifically (vs general text) is unknown. If it was trained primarily on general text with contextual retrieval, the uplift on code may be smaller than the headline number suggests.

### What makes us regret this in 6 months?

**FQRE dependency risk:** If Anthropic deprecates Haiku or raises prices, the query-time LLM expansion becomes expensive. Mitigation: FQRE should be opt-in via `VOYAGE_API_KEY` gate (already the pattern for other premium features).

**TASDI maintenance:** Synthetic docstrings at index time need regeneration when function signatures change. If this is not automated, the index diverges from the codebase over time and misleading docstrings lower precision.

### Risk Matrix

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| voyage-context-3 schema incompatibility | HIGH | LOW | Verify dimension (1024d) before re-indexing |
| FQRE adds latency beyond user tolerance | MED | MED | Default off, opt-in via env var |
| TASDI docstrings become stale | MED | HIGH | Invalidate on file hash change |
| Eval overfitting (20 queries only) | MED | HIGH | Use held-out queries from other repos |
| voyage-context-3 numbers don't generalize to code | HIGH | MED | Run A/B eval before committing |

### Missing Evidence

- voyage-context-3 vs voyage-code-3 specifically on code retrieval (CoIR) — vendor hasn't published this comparison
- FQRE MRR lift on code benchmarks — this is a novel idea with no empirical validation
- Whether MRR@10 on 20 holusight queries is stable enough to detect +0.05 improvements reliably (sample size concern)

---

## Decision Points

DECISION_POINT: primary_technique
OPTIONS: A) voyage-context-3 upgrade (drop-in, vendor, unverified for code) B) FQRE functional role query expansion (novel, medium effort, no latency at index time) C) TASDI synthetic docstring injection (novel, index-time LLM, low risk) D) Contextual Retrieval Anthropic-style (known technique, tested on codebases, medium effort)
RECOMMENDATION: C (TASDI) then B (FQRE) — both are novel, code-specific, and complement each other. TASDI fixes the index; FQRE fixes the query.
CONFIDENCE: MEDIUM
EVIDENCE: [UNVERIFIED] Both are novel ideas without prior empirical validation. The reasoning is mechanistically sound but needs empirical validation on the eval harness.

DECISION_POINT: voyage_context_3_upgrade  
OPTIONS: A) Upgrade to voyage-context-3 now B) Stay on voyage-code-3, test novel ideas first C) A/B test both in parallel
RECOMMENDATION: B
CONFIDENCE: MEDIUM
EVIDENCE: [VERIFIED] voyage-code-3 scores +13.80% over OpenAI-v3-large; voyage-context-3's code-specific gains are [UNVERIFIED]. Novel ideas are lower-risk experiments to run first.

---

## Discarded Claims

> [VERIFIED with caveat] "cAST achieves +5.5 points average on RepoEval" — this is model-specific (StarCoder2-7B), not a general average. Broader result is "+4.3 pp Recall@5 on RepoEval retrieval."

---

## Sources

1. [HyDE / Knowledge Leakage paper](https://arxiv.org/html/2504.14175v1) — PRIMARY [VERIFIED]
2. [Late Chunking (Jina AI)](https://arxiv.org/html/2409.04701v3) — PRIMARY [VERIFIED]
3. [Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) — SECONDARY
4. [BGE-M3 paper](https://arxiv.org/html/2402.03216v3) — PRIMARY [VERIFIED]
5. [CoIR Benchmark (ACL 2025)](https://arxiv.org/html/2407.02883v1) — PRIMARY [VERIFIED]
6. [RAPTOR (ICLR 2024)](https://arxiv.org/abs/2401.18059) — PRIMARY
7. [DMQR-RAG](https://arxiv.org/html/2411.13154v1) — PRIMARY [VERIFIED]
8. [Voyage rerank-2 blog](https://blog.voyageai.com/2024/09/30/rerank-2/) — SECONDARY
9. [Voyage code-3 evaluation](https://blog.voyageai.com/2024/12/04/voyage-code-3/) — SECONDARY [VERIFIED]
10. [voyage-context-3 blog](https://blog.voyageai.com/2025/07/23/voyage-context-3/) — SECONDARY [UNVERIFIED]
11. [CodeXEmbed-7B paper](https://arxiv.org/html/2411.12644) — PRIMARY [VERIFIED]
12. [CodeRAG-Bench](https://arxiv.org/html/2406.14497v1) — PRIMARY
13. [Repository-level neural reranking](https://arxiv.org/html/2502.07067) — PRIMARY
14. [PEFT code embeddings](https://arxiv.org/html/2405.04126v1) — PRIMARY
15. [cAST paper](https://arxiv.org/html/2506.15655v1) — PRIMARY [VERIFIED with caveat]
16. [LLM-VPRF](https://arxiv.org/abs/2504.01448) — PRIMARY
17. [Matryoshka NeurIPS 2022](https://proceedings.neurips.cc/paper_files/paper/2022/file/c32319f4868da7613d78af9993100e42-Paper-Conference.pdf) — PRIMARY
18. [Agentset Reranker Leaderboard](https://agentset.ai/rerankers) — SECONDARY
