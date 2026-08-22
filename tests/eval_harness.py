"""Eval harness for CodeSight search quality and token efficiency.

Metrics (all deterministic — computed from exact string/rank matches
against hand-verified gold `expected_file`/`expected_evidence` fields,
never from an LLM judge):

  hit_rate                  — fraction of graded queries where the expected file
                               appears anywhere in the returned results
  recall_at_k[K]             — fraction of graded queries whose first matching
                               result ranks at or above K, for each K in k_values
  mrr_at_10                  — mean(1/rank) of the first matching result
  ndcg_at_10                 — mean(1/log2(rank+1)) of the first matching result
                               (single-relevant-item nDCG; 1.0 for a rank-1 hit)
  evidence_completeness       — mean fraction of `expected_evidence` files found
                               anywhere in the returned results (defaults to the
                               single `expected_file` when no multi-file gold is set)
  avg_latency_ms              — mean wall-clock time per query's search_fn call
  tokens_per_correct_answer  — average snippet tokens across result sets that had a hit
  total_tokens               — sum of all snippet tokens across all queries

`contradiction_no_answer` queries (``expected_file == NO_MATCH_SENTINEL``) have
no positive gold file. They are run for diagnostic visibility (top result,
score, latency) but excluded from hit_rate/recall/MRR/nDCG/evidence-completeness
aggregates — this harness does not implement engine-side abstention, so scoring
them as pass/fail would fabricate ground truth. See
specs/014-retrieval-evaluation-harness-expansion.md.

Token counting uses tiktoken when available, falls back to len(text)//4.

`search_fn` makes the retrieval method pluggable (default: production
`hybrid_search`). See eval_baselines.py for exact/BM25-only/Graphify-structural
baselines with the same call signature, and eval_variants.py for opt-in
embedding-model variant runs.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from codesight.config import ServerConfig
    from codesight.embeddings import Embedder
    from codesight.store import ChunkStore
    from codesight.types import SearchResult

# Sentinel expected_file value marking a "should not confidently match a real
# file" diagnostic probe (contradiction/no-answer family). Never a real path.
NO_MATCH_SENTINEL = "__NO_MATCH__"


def _count_tokens(text: str) -> int:
    """Estimate token count. Uses tiktoken if available, else len//4."""
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)


# search_fn signature: (store, embedder, query, top_k, config) -> list[SearchResult]
SearchFn = Callable[..., "list[SearchResult]"]


@dataclass
class EvalQuery:
    """A single eval query with its expected answer location.

    `family` and `split` follow the task taxonomy in
    specs/014-retrieval-evaluation-harness-expansion.md (exact_lookup,
    conceptual_localization, symbol_reference, doc_synthesis, config_lookup,
    test_coverage, contradiction_no_answer). Both default to values that keep
    existing 2-field callers (query, expected_file) working unchanged.
    """

    query: str
    expected_file: str  # substring match; NO_MATCH_SENTINEL marks a diagnostic-only probe
    expected_start_line: int | None = None  # optional line check (within ±10 lines)
    family: str = "unspecified"
    split: str = "dev"
    expected_evidence: list[str] | None = None  # multi-file gold; defaults to [expected_file]

    @property
    def is_diagnostic_probe(self) -> bool:
        return self.expected_file == NO_MATCH_SENTINEL

    def evidence_files(self) -> list[str]:
        if self.expected_evidence:
            return self.expected_evidence
        if self.is_diagnostic_probe:
            return []
        return [self.expected_file]


@dataclass
class EvalResult:
    """Aggregate metrics from running the eval harness."""

    hit_rate: float
    mrr_at_10: float
    tokens_per_correct_answer: float
    total_tokens: int
    num_queries: int
    num_hits: int
    recall_at_k: dict[int, float] = field(default_factory=dict)
    ndcg_at_10: float = 0.0
    evidence_completeness: float = 0.0
    avg_latency_ms: float = 0.0
    num_graded: int = 0  # queries counted in hit_rate/recall/mrr/ndcg (excludes diagnostic probes)
    num_diagnostic_probes: int = 0
    per_query: list[dict] = field(default_factory=list)


def _default_search_fn(store, embedder, query, top_k, config=None):
    """Default retriever: production hybrid_search. Imported lazily so tests
    can patch `codesight.search.hybrid_search` and have it take effect."""
    from codesight.search import hybrid_search

    return hybrid_search(store, embedder, query, top_k=top_k, config=config)


def run_eval(
    queries: list[EvalQuery],
    store: "ChunkStore",
    embedder: "Embedder",
    top_k: int = 10,
    config: "ServerConfig | None" = None,
    search_fn: SearchFn | None = None,
    k_values: tuple[int, ...] = (1, 5, 10),
) -> EvalResult:
    """Run eval harness over a list of queries against an indexed store.

    Args:
        queries: List of EvalQuery with expected answer locations.
        store: Indexed ChunkStore to search against.
        embedder: Embedder used for query vectorisation.
        top_k: Number of results to retrieve per query.
        config: Optional ServerConfig (reranker, VPRF, etc.)
        search_fn: Retriever to evaluate. Defaults to production `hybrid_search`.
            Pass one of the baselines in eval_baselines.py to compare arms —
            all baselines share this same (store, embedder, query, top_k, config)
            call signature so results are directly comparable.
        k_values: Recall@K cutoffs to report (must be positive, need not be sorted).

    Returns:
        EvalResult with hit_rate, recall@k, mrr, nDCG, evidence completeness,
        latency, and token metrics.
    """
    fn = search_fn or _default_search_fn

    reciprocal_ranks: list[float] = []
    ndcg_scores: list[float] = []
    recall_hits: dict[int, int] = dict.fromkeys(k_values, 0)
    evidence_scores: list[float] = []
    hits = 0
    total_tokens = 0
    tokens_on_hits: list[int] = []
    latencies_ms: list[float] = []
    per_query: list[dict] = []
    num_graded = 0
    num_diagnostic = 0

    for eq in queries:
        t0 = time.perf_counter()
        results = fn(store, embedder, eq.query, top_k, config)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(latency_ms)

        # Token count for this query's result set
        query_tokens = sum(
            r.tokens_used if r.tokens_used is not None else _count_tokens(r.snippet)
            for r in results
        )
        total_tokens += query_tokens

        if eq.is_diagnostic_probe:
            num_diagnostic += 1
            top = results[0] if results else None
            per_query.append({
                "query": eq.query,
                "family": eq.family,
                "split": eq.split,
                "expected_file": eq.expected_file,
                "diagnostic_only": True,
                "top_result_file": top.file_path if top else None,
                "top_result_score": top.score if top else None,
                "latency_ms": round(latency_ms, 2),
                "query_tokens": query_tokens,
            })
            continue

        num_graded += 1

        # Find rank of correct answer (1-indexed) among the returned results.
        hit_rank: int | None = None
        for rank, result in enumerate(results, start=1):
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
        ndcg = 1.0 / math.log2(hit_rank + 1) if is_hit else 0.0
        ndcg_scores.append(ndcg)
        for k in k_values:
            if is_hit and hit_rank <= k:
                recall_hits[k] += 1
        if is_hit:
            hits += 1
            tokens_on_hits.append(query_tokens)

        evidence_required = eq.evidence_files()
        found_files = {r.file_path for r in results}
        matched_evidence = sum(
            1 for ev in evidence_required if any(ev in f for f in found_files)
        )
        evidence_completeness = (
            matched_evidence / len(evidence_required) if evidence_required else 0.0
        )
        evidence_scores.append(evidence_completeness)

        per_query.append({
            "query": eq.query,
            "family": eq.family,
            "split": eq.split,
            "expected_file": eq.expected_file,
            "hit": is_hit,
            "rank": hit_rank,
            "rr": rr,
            "ndcg": round(ndcg, 4),
            "evidence_completeness": round(evidence_completeness, 4),
            "latency_ms": round(latency_ms, 2),
            "query_tokens": query_tokens,
        })

    hit_rate = hits / num_graded if num_graded > 0 else 0.0
    mrr = sum(reciprocal_ranks) / num_graded if num_graded > 0 else 0.0
    ndcg_at_10 = sum(ndcg_scores) / num_graded if num_graded > 0 else 0.0
    evidence_completeness_avg = (
        sum(evidence_scores) / num_graded if num_graded > 0 else 0.0
    )
    avg_latency_ms = sum(latencies_ms) / len(queries) if queries else 0.0
    tokens_per_hit = sum(tokens_on_hits) / hits if hits > 0 else 0.0
    recall_at_k = {
        k: (recall_hits[k] / num_graded if num_graded > 0 else 0.0) for k in k_values
    }

    return EvalResult(
        hit_rate=hit_rate,
        mrr_at_10=mrr,
        tokens_per_correct_answer=tokens_per_hit,
        total_tokens=total_tokens,
        num_queries=len(queries),
        num_hits=hits,
        recall_at_k=recall_at_k,
        ndcg_at_10=ndcg_at_10,
        evidence_completeness=evidence_completeness_avg,
        avg_latency_ms=avg_latency_ms,
        num_graded=num_graded,
        num_diagnostic_probes=num_diagnostic,
        per_query=per_query,
    )
