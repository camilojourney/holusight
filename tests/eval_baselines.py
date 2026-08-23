"""Retrieval baselines for the eval harness (see eval_harness.py).

Each baseline is a `SearchFn` factory: it returns a callable with the exact
same `(store, embedder, query, top_k, config) -> list[SearchResult]` signature
as `codesight.search.hybrid_search`, so `run_eval()` can score any of them
identically and results are directly comparable across arms.

Baselines:
  exact_search_fn(repo_root)        — literal substring "grep" control (no index).
  bm25_search_fn                    — sparse-only control (FTS5 BM25, bypasses
                                       vector search / RRF / reranker).
  graphify_structural_search_fn(repo_root) — Graphify AST/symbol-graph baseline
                                       (structural provider). Falls back to no
                                       results with an explicit availability
                                       flag when graphify-out/graph.json is
                                       absent or unparsable; always reports
                                       staleness against current HEAD.

The Graphify baseline deliberately reuses `codesight.consistency`'s already-
landed structural-index loader (`_load_structural_index`,
`structural_graph_freshness`) instead of re-parsing graphify-out/graph.json a
second way, so the two subsystems agree on what "stale" and "available" mean.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from codesight.config import ServerConfig
    from codesight.embeddings import Embedder
    from codesight.store import ChunkStore

from codesight.types import SearchResult

BASELINE_EXACT = "baseline:exact"
BASELINE_BM25 = "baseline:bm25"
BASELINE_GRAPHIFY = "baseline:graphify_structural"

_STOPWORDS: frozenset[str] = frozenset({
    "how", "does", "what", "the", "is", "in", "for", "of", "a", "an", "to",
    "do", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "it", "its", "this", "that", "and", "or", "not", "with", "from", "by",
    "on", "at", "as", "and", "used", "use", "uses", "where",
})


def _query_tokens(query: str, min_len: int = 3) -> list[str]:
    return [
        t for t in re.split(r"[^a-z0-9_]+", query.lower())
        if len(t) >= min_len and t not in _STOPWORDS
    ]


def _snippet_for(path: Path, start_line: int, context: int = 3) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return ""
    lo = max(0, start_line - 1 - context)
    hi = min(len(lines), start_line - 1 + context + 1)
    return "\n".join(lines[lo:hi])


# ---------------------------------------------------------------------------
# Exact baseline — literal substring match over the indexed corpus (no index
# structure at all; the ripgrep/grep-style control from spec 012's variant
# matrix). Deterministic, local, zero external calls.
# ---------------------------------------------------------------------------


def exact_search_fn_factory(repo_root: str | Path, max_matches_per_file: int = 3):
    """Return a SearchFn that literally substring-matches the raw query
    (case-insensitive) against every file `walk_repo_files` would index.

    Ranking: files with more matches rank higher; within a file, matches are
    reported in line order. Ignores `store`/`embedder`/`config` — this
    baseline has no index and no embedding dependency.
    """
    from codesight.indexer import walk_repo_files

    root = Path(repo_root).resolve()

    def _search(store, embedder, query: str, top_k: int, config: "ServerConfig | None" = None):
        needle = query.strip().lower()
        if not needle:
            return []

        scored: list[tuple[int, str, int, str]] = []  # (match_count, file_path, line_no, snippet)
        for path in walk_repo_files(root):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            lower = text.lower()
            if needle not in lower:
                continue
            lines = text.splitlines()
            match_count = lower.count(needle)
            found = 0
            for i, line in enumerate(lines, start=1):
                if needle in line.lower():
                    rel = str(path.relative_to(root))
                    scored.append((match_count, rel, i, line.strip()[:200]))
                    found += 1
                    if found >= max_matches_per_file:
                        break

        # Rank by (match_count desc, file/line asc) for determinism.
        scored.sort(key=lambda t: (-t[0], t[1], t[2]))

        results: list[SearchResult] = []
        seen_files: set[str] = set()
        for match_count, rel, line_no, snippet in scored:
            if len(results) >= top_k:
                break
            chunk_id = f"exact:{rel}:{line_no}"
            results.append(SearchResult(
                file_path=rel,
                start_line=line_no,
                end_line=line_no,
                snippet=snippet,
                score=round(float(match_count), 6),
                scope="exact_match",
                chunk_id=chunk_id,
                tokens_used=max(1, len(snippet) // 4),
                source=BASELINE_EXACT,
                source_label="Exact substring match",
            ))
            seen_files.add(rel)
        return results

    return _search


# ---------------------------------------------------------------------------
# BM25-only baseline — sparse retrieval control. Calls the same FTS5 sidecar
# hybrid_search uses, but skips vector search, RRF, CNFB, and reranking so
# the sparse arm can be measured in isolation.
# ---------------------------------------------------------------------------


def bm25_search_fn(
    store: "ChunkStore",
    embedder: "Embedder",
    query: str,
    top_k: int,
    config: "ServerConfig | None" = None,
) -> list[SearchResult]:
    """Sparse-only baseline: BM25 via the FTS5 sidecar, no vector/RRF/rerank."""
    chunk_ids = store.bm25_search(query, top_k=top_k)
    if not chunk_ids:
        return []
    metadatas = store.get_chunk_metadata(chunk_ids)

    results: list[SearchResult] = []
    for rank, cid in enumerate(chunk_ids, start=1):
        meta = metadatas.get(cid)
        if meta is None:
            continue
        snippet = meta["content"]
        if len(snippet) > 1500:
            snippet = snippet[:1500] + "\n... (truncated)"
        # SQLite FTS5 doesn't expose a normalized bm25() score via this
        # query path — rank position is the deterministic, reproducible
        # signal reported here (lower rank = better), converted to a
        # descending score so downstream consumers sort identically to
        # every other SearchFn (higher score = better).
        results.append(SearchResult(
            file_path=meta["file_path"],
            start_line=meta["start_line"],
            end_line=meta["end_line"],
            snippet=snippet,
            score=round(1.0 / rank, 6),
            scope=meta["scope"],
            chunk_id=cid,
            tokens_used=len(snippet) // 4,
            source=BASELINE_BM25,
            source_label="BM25 only (FTS5, no vector/RRF/rerank)",
        ))
    return results


# ---------------------------------------------------------------------------
# Graphify structural baseline — matches query tokens against the tracked
# Graphify symbol graph (graphify-out/graph.json), then ranks files by how
# many distinct matched symbols they contain. This is a structural signal
# (AST-derived node identity + graph structure), distinct from BM25's
# full-text index over chunk content.
# ---------------------------------------------------------------------------


class GraphifyAvailability(NamedTuple):
    available: bool
    stale: bool
    built_at_commit: str | None
    current_commit: str | None


def graphify_availability(repo_root: str | Path) -> GraphifyAvailability:
    """Report whether graphify-out/graph.json exists and whether it matches
    current HEAD, without running a query. Used by the CLI to surface clear
    availability/staleness at the top of a run's output, not just buried in
    per-result text."""
    from codesight.consistency import _load_structural_index, structural_graph_freshness
    from codesight.git_utils import current_commit

    root = Path(repo_root).resolve()
    index = _load_structural_index(root)
    stale, built_at = structural_graph_freshness(index, root)
    return GraphifyAvailability(
        available=index.available,
        stale=stale,
        built_at_commit=built_at,
        current_commit=current_commit(root),
    )


def graphify_structural_search_fn_factory(repo_root: str | Path):
    """Return a SearchFn backed by the tracked Graphify graph.

    Availability/staleness is loaded once at factory time (not per-query) and
    stamped into every result's `source_label`. If the graph is unavailable
    (no `graphify-out/graph.json`, or unparsable), the returned SearchFn
    always returns `[]` — callers should check `graphify_availability()`
    first to distinguish "not available" from "ran, found nothing."
    """
    from codesight.consistency import _load_structural_index, structural_graph_freshness

    root = Path(repo_root).resolve()
    index = _load_structural_index(root)
    stale, built_at = structural_graph_freshness(index, root)
    label = (
        f"Graphify structural (available={index.available}, stale={stale}, "
        f"built_at_commit={built_at})"
    )

    def _search(store, embedder, query: str, top_k: int, config: "ServerConfig | None" = None):
        if not index.available:
            return []

        tokens = _query_tokens(query)
        if not tokens:
            return []

        # Score each source_file by the number of distinct query tokens that
        # appear as a substring of any node's norm_label/community_name in
        # that file — the structural analogue of a lexical match, but scoped
        # to symbol identity rather than full chunk text.
        # _StructuralIndex (consistency.py) exposes only node_file/file_nodes/
        # links, not full node records — match against each node_id itself,
        # which Graphify derives from the symbol's normalized label (e.g.
        # "src_codesight_search_rrf_merge" for `rrf_merge()` in search.py).
        file_scores: dict[str, float] = {}
        file_best_node: dict[str, str] = {}
        for file_path, node_ids in index.file_nodes.items():
            matched = 0
            best_label = ""
            for node_id in node_ids:
                haystack = node_id.lower()
                hit = sum(1 for t in tokens if t in haystack)
                if hit > matched:
                    matched = hit
                    best_label = node_id
            if matched > 0:
                file_scores[file_path] = float(matched)
                file_best_node[file_path] = best_label

        ranked = sorted(file_scores.items(), key=lambda kv: (-kv[1], kv[0]))[:top_k]

        results: list[SearchResult] = []
        for file_path, score in ranked:
            node_label = file_best_node.get(file_path, "")
            abs_path = root / file_path
            snippet = _snippet_for(abs_path, 1) or f"[matched symbol: {node_label}]"
            results.append(SearchResult(
                file_path=file_path,
                start_line=1,
                end_line=1,
                snippet=snippet or f"[matched symbol: {node_label}]",
                score=round(score, 6),
                scope="graphify_structural_match",
                chunk_id=f"graphify:{file_path}",
                tokens_used=max(1, len(snippet) // 4),
                source=BASELINE_GRAPHIFY,
                source_label=label,
            ))
        return results

    return _search
