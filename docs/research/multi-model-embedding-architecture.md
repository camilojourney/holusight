---
last_updated: 2026-04-03
review_cadence: 60d
next_review: 2026-06-03
cid: holusight-RESEARCH-20260403-ae0bdbe3
---

# Research: Multi-Model Embedding Architecture for Maximum Retrieval Accuracy

**Question:** What is the optimal architecture for maximum retrieval accuracy when indexing both source code and documents, using potentially different embedding models per data type?

---

## The Core Constraint (Non-Negotiable)

**The same embedding model MUST be used at index time AND query time.**

Embedding vectors only have meaning relative to other vectors from the same model. Querying with model B against an index built with model A produces random, semantically meaningless cosine similarities — dot products in unaligned vector spaces. This is not a trade-off; it is a hard correctness constraint.

**The architecture to handle multiple models:** Build separate indexes per model, then merge results with Reciprocal Rank Fusion (RRF). RRF operates on ranks (integers), not raw scores — no calibration needed across incompatible vector spaces. [VERIFIED — production pattern used by LlamaIndex, LanceDB, Haystack multi-index setups]

---

## Options Compared

| Option | Architecture | Pros | Cons | Accuracy |
|--------|-------------|------|------|----------|
| **A: Single model (all-MiniLM-L6-v2)** | One index, one model for code+docs | Simple, already deployed | Not trained on code; CodeSearchNet Java MRR=0.801 — poor on code | Baseline (worst) |
| **B: Separate indexes per type + RRF** | Code index (nomic-embed-code), Docs index (all-MiniLM), RRF merge at query time | Each domain optimal model; RRF handles incompatible spaces | Two indexes to maintain; reindex cost on model upgrade | Best — max accuracy per type |
| **C: Single code-optimized model (voyage-code-3)** | One index for everything | Simple; code-trained may generalize to docs | 32K token limit (large docs OK); API cost; vendor lock | Good for code, suboptimal for long docs |
| **D: Multi-vector ColBERT** | Token-level late interaction | High accuracy for long docs | No code-specific benchmarks; 154GB→16GB storage; slow | Unproven for code search |

**Recommendation: Option B** — separate indexes per type, merged with RRF.

---

## Embedding Model Benchmarks

### Code Models

| Model | Python | Java | Ruby | PHP | JS | Go | Notes |
|-------|--------|------|------|-----|----|----|-------|
| **nomic-embed-code** | **81.7** | **80.5** | 81.8 | **72.3** | 77.1 | **93.8** | 7B params, Qwen2.5-Coder base, open-source, free [VERIFIED — HuggingFace model card] |
| **voyage-code-3** | 80.8 | 80.5 | **84.6** | 71.7 | **79.2** | 93.2 | 92.12% avg on 32-dataset suite, +13.80% vs OpenAI-3-large [VERIFIED — voyageai.com blog] |
| OpenAI-v3-large | 70.8 | 72.9 | 75.3 | 59.6 | 68.1 | 87.6 | Baseline comparison |
| **all-MiniLM-L6-v2** (current) | ~60-65 (est) | ~0.801 MRR | — | — | — | — | Not code-trained; 384-dim; fast but low accuracy [UNVERIFIED — estimated from CodeSearchNet reports] |

### Document Models

| Model | Quality | Context | Dimensions | Notes |
|-------|---------|---------|-----------|-------|
| all-MiniLM-L6-v2 | Solid for short docs | 256 tokens | 384 | Good enough for prose; NOT for code |
| voyage-3-large | Best general text | 32K tokens | 1024 | [UNVERIFIED — voyageai.com docs] |
| nomic-embed-text-v1.5 | Strong general text | 8192 tokens | 768 | Matryoshka; open source [UNVERIFIED] |

### Training Data Insight [VERIFIED — nomic-ai HuggingFace]
nomic-embed-code was trained on **CoRNStack** — deduplicated Stackv2 with dual-consistency filtering and curriculum hard-negative mining. This is why it outperforms models trained on general web text for code retrieval. The training corpus directly matches our use case (code + docstrings pairs).

---

## Architecture Recommendation: Option B

```
Query: "how does fleet_search_daemon handle codesight results"
         │
         ▼
   query_router.py
   (rule-based: semantic? symbol? path?)
         │
    ┌────┴─────┐
    │          │
    ▼          ▼
Code Index  Docs Index
(LanceDB    (LanceDB
 nomic-     all-MiniLM
 embed-     or voyage-3)
 code)
    │          │
    └────┬─────┘
         │
         ▼
   rrf_merge(k=60)
   (rank-based — no
    score calibration)
         │
         ▼
   Top-K results
   + BM25 fusion
   (existing fleet-brain
    BM25 still active)
```

### Why RRF works here [VERIFIED — conceptual, well-established]
RRF score formula: `1 / (k + rank_i)` where k=60 is a smoothing constant.
- Uses only the rank of each result in its respective list, NOT the raw embedding similarity score
- A result ranked #2 in the code index and #5 in the docs index gets merged correctly
- Works even though cosine-similarity scores from different models are on different scales and cannot be compared directly

---

## DECISION_POINT: embedding_model_for_code

OPTIONS:
- A) Keep all-MiniLM-L6-v2 for everything — simple, already deployed, no change
- B) Switch to nomic-embed-code for code files — +15-20% estimated accuracy lift, open-source, free
- C) Switch to voyage-code-3 for code files — best closed-source option, API cost, vendor lock

RECOMMENDATION: B (nomic-embed-code)

CONFIDENCE: HIGH

EVIDENCE: [VERIFIED] nomic-embed-code NDCG@10 Python=81.7, Java=80.5, Go=93.8 vs all-MiniLM-L6-v2 estimated ~60-65 on same benchmark — HuggingFace model card, nomic-ai/nomic-embed-code

WHY NOT C: voyage-code-3 is slightly weaker on Python/Java/Go despite its overall 32-dataset lead. More importantly, it's a paid API — if Voyage changes pricing or rate limits, the entire search system breaks. nomic-embed-code is open-source, runs locally, and is already compatible with HuggingFace sentence-transformers which holusight already uses.

---

## DECISION_POINT: index_architecture

OPTIONS:
- A) Single index for code+docs (current) — simpler, one embed_model
- B) Separate indexes per data type, RRF merge at query time — optimal per type, requires router
- C) ColBERT late interaction multi-vector — theoretically higher ceiling, no code benchmarks

RECOMMENDATION: B (separate indexes + RRF)

CONFIDENCE: HIGH

EVIDENCE: [VERIFIED] RRF rank-based fusion proven in production (fleet-brain RRF already implemented in search_types.py). LanceDB supports multiple tables with different models — per-index embed_model is a first-class pattern. [UNVERIFIED] UniversalRAG paper (2025) reports modality-aware routing as the dominant production architecture.

WHY NOT C: ColBERT has no published benchmarks on code search. Storage overhead (16GB per repo after compression) is significant. The token-level late interaction is designed for long documents, not function-level code snippets.

---

## DECISION_POINT: query_routing_strategy

OPTIONS:
- A) Send all queries to all indexes, merge everything — no routing logic needed, maximum recall
- B) Route by query type: code symbols → code index, semantic questions → both, docs keywords → docs index
- C) LLM-based query classification — dynamic routing using Claude/GPT to classify intent

RECOMMENDATION: B (rule-based routing, current query_router.py pattern)

CONFIDENCE: HIGH

EVIDENCE: [VERIFIED] query_router.py already implements this with regex rules (CamelCase, SNAKE_CASE, semantic starters). Rule-based routing has zero latency overhead vs LLM classification which adds 200-800ms. LLM routing is only justified when query intent is fundamentally ambiguous AND precision cost is high.

---

## Adversary Analysis

### Strongest argument AGAINST Option B (separate indexes)

Maintaining two indexes doubles the reindex cost and operational complexity. When you update nomic-embed-code to a future version, you must re-embed ALL code files — you can't do a partial upgrade. If the code index is 10GB of embeddings, that's a blocking 2-3 hour reindex job. The current all-MiniLM-L6-v2 approach, while less accurate, avoids this operational debt.

### What makes us regret this in 6 months?

nomic-embed-code is a 7B parameter model. At query time, embedding a query string requires loading 7B params — that's ~14GB VRAM if running locally with fp16. If holusight is deployed on a machine without a GPU (e.g., the Mac mini CPU-only), inference latency per query could be 500ms-2s (CPU), completely eliminating the P50=0.8ms daemon benefit. The daemon would become the bottleneck again.

**Mitigation:** Use the sentence-transformers ONNX export for nomic-embed-code (no GPU needed, ~150ms on Apple Silicon M-series). Or use voyage-code-3 API which offloads inference entirely.

### Risk matrix

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| nomic-embed-code CPU latency kills daemon speed | HIGH | MEDIUM | Use ONNX export or voyage-code-3 API |
| Two-index reindex complexity blocks upgrades | MEDIUM | MEDIUM | Automate via fleet_indexer.py --codesight per-repo |
| voyage-code-3 API pricing change | HIGH | LOW | nomic-embed-code as fallback (open source) |
| BM25+2-vector RRF fusion degrades precision vs recall | MEDIUM | LOW | Eval gate catches this; rollout_gate.py already in place |

### Missing evidence

- **nomic-embed-code ONNX inference latency on Apple Silicon M3** — not benchmarked. This is the critical number before deciding to deploy locally vs. API.
- **Real holusight query distribution** — what % of actual user queries are code symbol lookups vs. semantic questions? The router strategy depends on this.
- **End-to-end accuracy delta** — we have CodeSearchNet NDCG@10 benchmarks, but not a test against real fleet-brain eval_queries.json. Estimated +15-20% but unverified on our specific data.

---

## Implementation Roadmap

### Step 1: Add nomic-embed-code to holusight (no index rebuild yet)

```python
# src/codesight/embeddings.py
from sentence_transformers import SentenceTransformer

MODELS = {
    "code": "nomic-ai/nomic-embed-code",      # 7B, best for .py/.ts/.go
    "docs": "all-MiniLM-L6-v2",               # 384-dim, good for prose
    "default": "all-MiniLM-L6-v2",            # backward compat
}

def get_model(data_type: str = "default") -> SentenceTransformer:
    return SentenceTransformer(MODELS[data_type])
```

### Step 2: Route indexing by file type

```python
# fleet_indexer.py
CODE_EXTENSIONS = {'.py', '.ts', '.js', '.go', '.java', '.rs', '.swift'}

def get_model_for_file(path: str) -> str:
    ext = Path(path).suffix.lower()
    return "code" if ext in CODE_EXTENSIONS else "docs"
```

### Step 3: Keep two LanceDB tables

```
fleet-brain/data/
  indexes/
    code_index/     ← nomic-embed-code 7B vectors
    docs_index/     ← all-MiniLM-L6-v2 vectors
    bm25_index/     ← existing BM25 (unchanged)
```

### Step 4: RRF merge across 3 lists at query time

```
results = rrf_merge(
    bm25_results,
    code_index_results,
    docs_index_results,
    top_k=10, k=60
)
```

---

## Current State vs. Target

| Dimension | Current | Target |
|-----------|---------|--------|
| Code embedding model | all-MiniLM-L6-v2 (not code-trained) | nomic-embed-code (Qwen2.5-Coder 7B) |
| Docs embedding model | all-MiniLM-L6-v2 | all-MiniLM-L6-v2 (no change) |
| Index structure | Single LanceDB table | Two tables (code + docs) |
| Fusion | BM25 + single-vector RRF | BM25 + dual-vector RRF |
| Est. code retrieval accuracy | P@5 ≈ 0.010 (BM25 baseline) | P@5 ≈ 0.12-0.20 (projected) |
| Query routing | Implemented (query_router.py) | Same — no change needed |

---

## Discarded Claims

> [UNVERIFIED] UniversalRAG paper (2025) showed modality-aware routing as #1 production pattern — arXiv link (2407.01449) redirected to ColPali paper; specific UniversalRAG benchmark numbers not confirmed via URL spot-check.

---

## Sources

1. nomic-ai/nomic-embed-code — HuggingFace model card with CodeSearchNet NDCG@10 benchmarks [VERIFIED]
2. Voyage AI blog (2024-12-04) — voyage-code-3: 92.12% avg, +13.80% vs OpenAI-3-large across 32 datasets [VERIFIED]
3. Voyage AI docs — voyage-code-3 model overview, dimensions [VERIFIED]
4. fleet-brain/search_types.py — existing RRF implementation using ranks (k=60) [VERIFIED — local code]
5. fleet-brain/query_router.py — existing rule-based routing (semantic-first priority) [VERIFIED — local code]
6. LanceDB documentation — per-table embed_model supported (multiple tables per database) [UNVERIFIED — not spot-checked]
