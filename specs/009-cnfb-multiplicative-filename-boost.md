---
id: SPEC-009
name: CNFB — Query-Aware Multiplicative Filename Boost
status: Approved
phase: v0.5
decision_record: docs/decisions/0009-2026-04-04-retrieval-experiments.md
---

# SPEC-009: CNFB — Query-Aware Multiplicative Filename Boost

## Summary

Replace the existing binary filename boost (`_reorder_by_filename_match`) with a multiplicative score adjustment based on BM25 token overlap between query tokens and filename tokens. Applied pre-reranker so the reranker can further refine the order.

**Why:** The current boost is binary (file matches or doesn't) and applied post-reranker, meaning it overwrites expensive reranker scores. CNFB is graded (partial matches score less), applied pre-reranker (reranker can correct it), and uses set overlap rather than substring containment.

---

## Trigger

`hybrid_search()` is called with a non-empty query string and `cnfb_alpha > 0.0`.

## Input

- `query: str` — user search query
- `results: list[SearchResult]` — top-K results after RRF merge, before reranker
- `cnfb_alpha: float` — boost strength, range [0.0, 2.0], default 0.0

## Output

`list[SearchResult]` — same results with modified `score` field, re-sorted descending.

## Algorithm

```
query_tokens = {t.lower() for t in re.split(r'[^a-z0-9]', query.lower()) 
                if len(t) >= 3 and t not in STOPWORDS}

for each result in results:
    filename_stem = Path(result.file_path).stem.lower()
    filename_tokens = {t for t in re.split(r'[^a-z0-9]', filename_stem) if len(t) >= 2}
    
    if filename_tokens:
        overlap = len(query_tokens & filename_tokens) / len(filename_tokens)
    else:
        overlap = 0.0
    
    result.score *= (1.0 + cnfb_alpha * overlap)

return sorted(results, key=lambda r: r.score, reverse=True)
```

Query tokens are computed **once** before the loop (not per-chunk).

---

## Placement in Pipeline

```
RRF merge
    ↓
[CNFB score adjustment]  ← NEW (pre-reranker)
    ↓
Reranker (voyage rerank-2 or cross-encoder)
    ↓
[REMOVE: _reorder_by_filename_match]  ← DELETE existing post-reranker boost
    ↓
top K results
```

CNFB **replaces** `_reorder_by_filename_match` entirely. The old binary post-reranker boost is removed. Setting `cnfb_alpha=0.0` produces equivalent behavior to the old `metadata_boost=False`.

---

## Configuration

| Env var | Type | Default | Range | Notes |
|---------|------|---------|-------|-------|
| `CODESIGHT_CNFB_ALPHA` | float | `0.0` | [0.0, 2.0] | 0.0 = disabled (old metadata_boost=False behavior). Values clamped at load time. |

**Migration:** The existing `metadata_boost` env var is deprecated. When `CODESIGHT_CNFB_ALPHA > 0.0`, `metadata_boost` is ignored. When `CODESIGHT_CNFB_ALPHA = 0.0` and `metadata_boost = true`, the old binary boost still applies (backwards compatibility during rollout, remove in v0.6).

**Rollback:** Set `CODESIGHT_CNFB_ALPHA=0.0` — no index rebuild, no schema change.

---

## Files to Change

| File | Change |
|------|--------|
| `src/codesight/search.py` | Add `_cnfb_boost()` function. Insert call after RRF merge, before `_rerank()`. Mark `_reorder_by_filename_match` as deprecated. |
| `src/codesight/config.py` | Add `cnfb_alpha: float = Field(default=0.0)` with validator clamping to [0.0, 2.0]. |
| `tests/test_search.py` | Add unit tests for `_cnfb_boost()` (see Acceptance Criteria). |

No LanceDB schema changes. No new API dependencies. No index rebuild required.

---

## Acceptance Criteria

**AC-001 — Alpha-zero identity**
Given `cnfb_alpha=0.0`, when `hybrid_search()` is called, then scores are identical to the pre-CNFB baseline and result order is unchanged (within floating-point tolerance).

**AC-002 — Full-match boost**
Given a query "chunker" and a result from `src/codesight/chunker.py`, when `cnfb_alpha=0.5`, then that result's score is multiplied by 1.5 (overlap=1.0, boost=1 + 0.5*1.0).

**AC-003 — No-match zero boost**
Given a query "chunker" and a result from `src/codesight/store.py`, when `cnfb_alpha=0.5`, then that result's score is unchanged (overlap=0.0, boost=1.0).

**AC-004 — Partial match**
Given a query "vector search store" and a result from `src/codesight/vector_store_impl.py`, when `cnfb_alpha=0.5`, then overlap = |{vector, store} ∩ {vector, store, impl}| / 3 = 2/3, boost = 1 + 0.5*(2/3) ≈ 1.333.

**AC-005 — Alpha clamped**
Given `CODESIGHT_CNFB_ALPHA=5.0`, when the config is loaded, then `cnfb_alpha` is stored as 2.0 (clamped).

**AC-006 — Query tokens precomputed**
Given a call to `_cnfb_boost()` with 20 results, the query tokenization is performed exactly once (verifiable via unit test with mock).

**AC-007 — Existing tests pass**
`pytest tests/ -x -q` passes with zero failures after implementation.

---

## Edge Cases

**EDGE-001 — Empty filename stem**
Scenario: file_path is `/foo/.hidden` — `Path.stem` returns `.hidden` → after split, tokens = `{'hidden'}`. No special handling needed; the regex split handles it correctly.
Expected: Normal overlap computation, no crash.

**EDGE-002 — Single-token filename collision (e.g., "test")**
Scenario: Query is "test" → matches test_foo.py, test_bar.py, test_baz.py — all get full boost.
Expected: This is correct behavior (query token "test" should prefer test files). However, stopword list should include common single-char tokens (filtered by `len >= 3`). The 3-char minimum already excludes "a", "is", etc.
Recovery: If over-boosting observed, increase alpha minimum length to 4 chars — configurable as follow-on.

**EDGE-003 — Alpha clamping boundary**
Scenario: `CODESIGHT_CNFB_ALPHA=-0.5` (negative value).
Expected: Clamped to 0.0 at config load time. Warning logged: "CNFB alpha must be in [0.0, 2.0], got -0.5, clamping to 0.0."
Recovery: User corrects env var.

---

## Decisions

| Decision | Vote | Rationale |
|----------|------|-----------|
| Replace or extend existing binary boost? | **Replace** (arch) | Two separate boost passes with different semantics create maintenance debt and unpredictable interactions |
| Alpha default: 0.0 or 0.5? | **0.0** (arch) | Every other tunable defaults to false/off; silent score-changing default breaks established contract |
| Precompute query tokens? | **Yes, once** (perf) | Query string is constant for all K chunks; recomputing K times is pure waste |
| Alpha bounds? | **[0.0, 2.0]** (sec) | Prevents alpha from becoming a dominance override; 2.0 = maximum score doubling on full match |

---

## Out of Scope

- Boosting based on directory name (current binary boost uses parent dir — CNFB does not, to reduce false positive matches)
- Index-time filename indexing into BM25 (that is a separate spec)
- Multi-field filename expansion (module path tokens, e.g., `src.codesight.search` → `{src, codesight, search}`)
- Deprecation and removal of `metadata_boost` env var (v0.6 cleanup, not this spec)
