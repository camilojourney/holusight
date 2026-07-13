"""Eval harness for CodeSight search quality and token efficiency.

Metrics:
  hit_rate                — fraction of queries where expected file appears in top-K
  mrr_at_10               — mean(1/rank) for correct answer within top 10
  tokens_per_correct_answer — average snippet tokens across result sets that had a hit
  total_tokens            — sum of all snippet tokens across all queries

Token counting uses tiktoken when available, falls back to len(text)//4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codesight.config import ServerConfig
    from codesight.embeddings import Embedder
    from codesight.store import ChunkStore


def _count_tokens(text: str) -> int:
    """Estimate token count. Uses tiktoken if available, else len//4."""
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)


@dataclass
class EvalQuery:
    """A single eval query with its expected answer location."""

    query: str
    expected_file: str  # substring match against result file_path
    expected_start_line: int | None = None  # optional line check (within ±10 lines)


@dataclass
class EvalResult:
    """Aggregate metrics from running the eval harness."""

    hit_rate: float
    mrr_at_10: float
    tokens_per_correct_answer: float
    total_tokens: int
    num_queries: int
    num_hits: int
    per_query: list[dict] = field(default_factory=list)


def run_eval(
    queries: list[EvalQuery],
    store: "ChunkStore",
    embedder: "Embedder",
    top_k: int = 10,
    config: "ServerConfig | None" = None,
) -> EvalResult:
    """Run eval harness over a list of queries against an indexed store.

    Args:
        queries: List of EvalQuery with expected answer locations.
        store: Indexed ChunkStore to search against.
        embedder: Embedder used for query vectorisation.
        top_k: Number of results to retrieve per query.
        config: Optional ServerConfig (reranker, VPRF, etc.)

    Returns:
        EvalResult with hit_rate, mrr_at_10, token metrics.
    """
    from codesight.search import hybrid_search

    reciprocal_ranks: list[float] = []
    hits = 0
    total_tokens = 0
    tokens_on_hits: list[int] = []
    per_query: list[dict] = []

    for eq in queries:
        results = hybrid_search(store, embedder, eq.query, top_k=top_k, config=config)

        # Token count for this query's result set
        query_tokens = sum(
            r.tokens_used if r.tokens_used is not None else _count_tokens(r.snippet)
            for r in results
        )
        total_tokens += query_tokens

        # Find rank of correct answer (1-indexed)
        hit_rank: int | None = None
        for rank, result in enumerate(results[:10], start=1):
            file_match = eq.expected_file in result.file_path
            if not file_match:
                continue
            if eq.expected_start_line is not None:
                if abs(result.start_line - eq.expected_start_line) > 10:
                    continue
            hit_rank = rank
            break

        is_hit = hit_rank is not None
        rr = 1.0 / hit_rank if is_hit else 0.0
        reciprocal_ranks.append(rr)
        if is_hit:
            hits += 1
            tokens_on_hits.append(query_tokens)

        per_query.append(
            {
                "query": eq.query,
                "expected_file": eq.expected_file,
                "hit": is_hit,
                "rank": hit_rank,
                "rr": rr,
                "query_tokens": query_tokens,
            }
        )

    num_queries = len(queries)
    hit_rate = hits / num_queries if num_queries > 0 else 0.0
    mrr = sum(reciprocal_ranks) / num_queries if num_queries > 0 else 0.0
    tokens_per_hit = sum(tokens_on_hits) / hits if hits > 0 else 0.0

    return EvalResult(
        hit_rate=hit_rate,
        mrr_at_10=mrr,
        tokens_per_correct_answer=tokens_per_hit,
        total_tokens=total_tokens,
        num_queries=num_queries,
        num_hits=hits,
        per_query=per_query,
    )
