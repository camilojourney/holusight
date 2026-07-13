# Spec 007: Cross-Encoder Reranking

**Status:** implemented
**Phase:** v0.3
**Author:** Juan Martinez
**Created:** 2026-02-28
**Updated:** 2026-02-28

## Problem

After RRF merge, the top K results are ranked by combining BM25 and vector scores independently. Neither method reads the query and chunk together — BM25 counts keyword matches, vector search compares embeddings. This means the ranking can be wrong: a chunk that superficially matches keywords might outrank a chunk that actually answers the question.

A cross-encoder reranker reads the query AND each candidate chunk as a pair, producing a much more accurate relevance score. In benchmarks, adding a reranker to hybrid search typically improves Precision@5 by 15-25%.

For consulting engagements, this means the difference between "the answer is usually in the top 5 results" and "the answer is almost always the #1 result."

## Goals

- Add optional cross-encoder reranking step after RRF merge
- Use a local model (no API, runs on CPU) — maintains the "search is 100% local" promise
- Improve Precision@5 by at least 15% on a benchmark query set
- Search latency increase < 100ms for top 20 candidates on an M1 Mac
- Configurable — can be disabled for speed-sensitive deployments

## Non-Goals

- API-based rerankers (Cohere Rerank, Voyage Rerank) — add later if needed
- Reranking at indexing time — reranking is query-time only
- Replacing RRF — reranking complements it, runs after it

## Solution

```
Current pipeline:
   query → BM25 top 20 → ┐
                          ├→ RRF merge → top K → done
   query → Vector top 20 → ┘

New pipeline:
   query → BM25 top 20 → ┐
                          ├→ RRF merge → top 20 → cross-encoder reranker → top K → done
   query → Vector top 20 → ┘
```

The reranker takes the top 20 RRF results, scores each (query, chunk) pair with a cross-encoder model, re-sorts by reranker score, and returns the top K.

### Why This Works

| Step | What it does | Limitation |
|------|-------------|------------|
| BM25 | Finds exact keyword matches | Misses semantic meaning |
| Vector | Finds semantic meaning | Misses exact keywords |
| RRF | Combines both rankings | Scores are independent, not calibrated |
| **Reranker** | **Reads query + chunk together** | **Slower (but only on top 20)** |

## Implementation Notes

### Key Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Default reranker model | `ms-marco-MiniLM-L-6-v2` | 80MB, ~50ms for 20 chunks, good quality |
| Reranker candidates | 20 | Feed top 20 from RRF to reranker |
| Reranker enabled | `false` (default) | Opt-in to avoid breaking existing behavior |
| Better model option | `bge-reranker-v2-m3` | 560MB, ~200ms, better quality |

### Reranker Model Options

| Model | Size | Speed (20 chunks, M1) | Quality |
|-------|------|----------------------|---------|
| `ms-marco-MiniLM-L-6-v2` | 80MB | ~50ms | Good |
| `bge-reranker-v2-m3` | 560MB | ~200ms | Better |
| `BAAI/bge-reranker-large` | 1.3GB | ~500ms | Best local |

### Dependencies

- `sentence-transformers` (already installed) — provides `CrossEncoder` class
- No new dependencies needed
- Depends on: Spec 001 (search pipeline), Spec 002 (better embeddings improve reranker input)

### Implementation

```python
# In search.py

from sentence_transformers import CrossEncoder

_reranker: CrossEncoder | None = None

def _get_reranker(model_name: str) -> CrossEncoder:
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder(model_name)
    return _reranker

def _rerank(query: str, results: list[SearchResult], top_k: int) -> list[SearchResult]:
    reranker = _get_reranker(config.reranker_model)
    pairs = [(query, r.content) for r in results]
    scores = reranker.predict(pairs)
    for result, score in zip(results, scores):
        result.score = float(score)
    return sorted(results, key=lambda r: r.score, reverse=True)[:top_k]
```

### Configuration

```bash
CODESIGHT_RERANKER=true                          # enable reranking
CODESIGHT_RERANKER_MODEL=ms-marco-MiniLM-L-6-v2  # which model
CODESIGHT_RERANKER_TOP_N=20                      # feed this many to reranker
```

### File Changes

| File | Change |
|------|--------|
| `src/codesight/search.py` | Add `_rerank()` function, call after RRF merge when enabled |
| `src/codesight/config.py` | Add `reranker`, `reranker_model`, `reranker_top_n` settings |

## Alternatives Considered

### Alternative A: API-based reranker (Cohere Rerank)

Trade-off: Better quality, but sends document chunks to Cohere's API, costs money, requires internet.
Rejected because: Breaks "search is 100% local" promise. Add as optional later if clients request it.

### Alternative B: Replace RRF with learned fusion

Trade-off: Train a model to combine BM25 + vector scores optimally. Better than RRF in theory.
Rejected because: Requires training data (query-relevance pairs) specific to each document collection. Not practical for consulting where each engagement has different documents.

### Alternative C: Always-on reranking

Trade-off: Better results for everyone, simpler config.
Rejected because: Adds ~50-200ms to every search. Some deployments prioritize speed. Opt-in is safer.

## Edge Cases & Failure Modes

- Reranker model not downloaded → auto-download on first use, log message with progress
- Very short query (1-2 words) → reranker still runs but may not improve much; harmless
- Chunk with empty content → skip from reranking input, keep original RRF position
- MPS acceleration available → use automatically on Apple Silicon
- Reranker disabled → pipeline is identical to current behavior, zero overhead
- Concurrent searches → reranker model is loaded once, thread-safe for inference

## Open Questions

- [ ] Should the reranker be enabled by default once validated? Or always opt-in? — @juan
- [ ] Is 20 candidates optimal? More = better quality but slower. Benchmark 10 vs 20 vs 50. — @juan
- [ ] Should `SearchResult.score` be the reranker score (replacing RRF score) or a separate field? — @juan

## Acceptance Criteria

- [ ] `CODESIGHT_RERANKER=true` enables cross-encoder reranking after RRF
- [ ] `CODESIGHT_RERANKER=false` (default) skips reranking — zero overhead, no behavior change
- [ ] Reranker model downloaded once, cached in `~/.cache/torch/`
- [ ] Reranker processes top 20 RRF results, returns top K re-sorted by reranker score
- [ ] Search latency increase < 100ms for 20 chunks on M1 Mac
- [ ] Works with both `search()` and `ask()` pipelines
- [ ] Precision@5 improves by at least 15% on a benchmark query set (5+ test queries)
- [ ] `uv run --extra dev pytest tests/ -x -v` passes with reranker both enabled and disabled
