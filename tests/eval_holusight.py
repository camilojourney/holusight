#!/usr/bin/env python3
"""Holusight retrieval eval — task-plan compatible CLI.

Indexes the repo and runs the shared eval harness (tests/eval_harness.py)
against one or more retrieval baselines (tests/eval_baselines.py).

Default behavior is unchanged from the original 20-query harness: one
`hybrid` run over `holusight_eval_20q.json` — `just eval` and any existing
automation that shells out to this script keep working identically.

To run the expanded ~85-query taxonomy across baselines:

    uv run python tests/eval_holusight.py \\
        --queries tests/fixtures/holusight_eval_taxonomy.json \\
        --baselines hybrid,bm25,exact,graphify --top-k 10

Opt-in embedding-model variants (never invoked here) live in
tests/eval_variants.py — see specs/014-retrieval-evaluation-harness-expansion.md.

Usage:
    uv run python tests/eval_holusight.py --top-k 10 --output /tmp/eval.json
    just eval
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUERIES = Path(__file__).resolve().parent / "fixtures" / "holusight_eval_20q.json"
KNOWN_BASELINES = ("hybrid", "bm25", "exact", "graphify")


def _load_queries(path: Path):
    from tests.eval_harness import EvalQuery

    raw = json.loads(path.read_text())
    return [
        EvalQuery(
            query=item["query"],
            expected_file=item["expected_file"],
            expected_start_line=item.get("expected_start_line"),
            family=item.get("family", "unspecified"),
            split=item.get("split", "dev"),
            expected_evidence=item.get("expected_evidence"),
        )
        for item in raw
    ]


def _family_breakdown(per_query: list[dict]) -> dict:
    """Deterministic hit-rate rollup per query family, for comparability
    across baseline/variant runs sharing the same query taxonomy."""
    by_family: dict[str, list[dict]] = defaultdict(list)
    for entry in per_query:
        if entry.get("diagnostic_only"):
            continue
        by_family[entry.get("family", "unspecified")].append(entry)
    breakdown = {}
    for family, entries in sorted(by_family.items()):
        hits = sum(1 for e in entries if e.get("hit"))
        breakdown[family] = {
            "num_queries": len(entries),
            "hits": hits,
            "hit_rate": round(hits / len(entries), 4) if entries else 0.0,
        }
    return breakdown


def _search_fn_for(baseline: str, repo_path: Path):
    """Resolve a baseline name to a SearchFn (or None for the default hybrid_search)."""
    if baseline == "hybrid":
        return None
    if baseline == "bm25":
        from tests.eval_baselines import bm25_search_fn

        return bm25_search_fn
    if baseline == "exact":
        from tests.eval_baselines import exact_search_fn_factory

        return exact_search_fn_factory(repo_path)
    if baseline == "graphify":
        from tests.eval_baselines import graphify_structural_search_fn_factory

        return graphify_structural_search_fn_factory(repo_path)
    raise ValueError(f"Unknown baseline: {baseline!r} (known: {KNOWN_BASELINES})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run holusight retrieval eval")
    parser.add_argument(
        "--repo-path",
        type=Path,
        default=REPO_ROOT,
        help="Repo root to index and search (default: holusight root)",
    )
    parser.add_argument(
        "--queries",
        type=Path,
        default=DEFAULT_QUERIES,
        help="JSON file with query list",
    )
    parser.add_argument("--top-k", type=int, default=10, help="Results per query")
    parser.add_argument(
        "--baselines",
        type=str,
        default="hybrid",
        help=f"Comma-separated baselines to run: {','.join(KNOWN_BASELINES)} (default: hybrid)",
    )
    parser.add_argument("--output", type=Path, default=None, help="Write JSON results here")
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Force full reindex before eval",
    )
    parser.add_argument(
        "--no-index",
        action="store_true",
        help="Skip indexing (use existing LanceDB data)",
    )
    args = parser.parse_args(argv)

    repo_path = args.repo_path.resolve()
    if not repo_path.is_dir():
        print(f"error: not a directory: {repo_path}", file=sys.stderr)
        return 1

    sys.path.insert(0, str(repo_path / "src"))
    sys.path.insert(0, str(repo_path))

    from codesight import CodeSight
    from codesight.config import ServerConfig
    from tests.eval_baselines import graphify_availability
    from tests.eval_harness import run_eval

    baselines = [b.strip() for b in args.baselines.split(",") if b.strip()]
    unknown = [b for b in baselines if b not in KNOWN_BASELINES]
    if unknown:
        print(f"error: unknown baseline(s) {unknown}; known: {KNOWN_BASELINES}", file=sys.stderr)
        return 1

    queries = _load_queries(args.queries)
    config = ServerConfig()
    engine = CodeSight(repo_path, config=config)

    if not args.no_index:
        engine.index(force_rebuild=args.reindex)

    graphify_status = None
    if "graphify" in baselines:
        avail = graphify_availability(repo_path)
        graphify_status = {
            "available": avail.available,
            "stale": avail.stale,
            "built_at_commit": avail.built_at_commit,
            "current_commit": avail.current_commit,
        }
        if not avail.available:
            print(
                "warning: graphify-out/graph.json not found or unparsable — "
                "the graphify baseline will return empty results for every query",
                file=sys.stderr,
            )
        elif avail.stale:
            print(
                f"warning: graphify-out/graph.json is stale "
                f"(built_at={avail.built_at_commit}, HEAD={avail.current_commit}) — "
                "run `graphify update .` for a current graph",
                file=sys.stderr,
            )

    baseline_reports = {}
    for baseline in baselines:
        search_fn = _search_fn_for(baseline, repo_path)
        result = run_eval(
            queries,
            engine.store,
            engine.embedder,
            top_k=args.top_k,
            config=config,
            search_fn=search_fn,
        )
        tokens_per_query = result.total_tokens / result.num_queries if result.num_queries else 0.0
        baseline_reports[baseline] = {
            "hit_rate": round(result.hit_rate, 4),
            "recall_at_k": {str(k): round(v, 4) for k, v in result.recall_at_k.items()},
            "mrr_at_10": round(result.mrr_at_10, 4),
            "ndcg_at_10": round(result.ndcg_at_10, 4),
            "evidence_completeness": round(result.evidence_completeness, 4),
            "avg_latency_ms": round(result.avg_latency_ms, 2),
            "tokens_per_query": round(tokens_per_query, 1),
            "tokens_per_correct_answer": round(result.tokens_per_correct_answer, 1),
            "total_tokens": result.total_tokens,
            "num_queries": result.num_queries,
            "num_graded": result.num_graded,
            "num_hits": result.num_hits,
            "num_diagnostic_probes": result.num_diagnostic_probes,
            "family_breakdown": _family_breakdown(result.per_query),
            "per_query": result.per_query,
        }

    payload = {
        "schema_version": "holus-eval-report/v2",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "repo_path": str(repo_path),
        "queries_file": str(args.queries.resolve()),
        "top_k": args.top_k,
        "baselines_run": baselines,
        "graphify_status": graphify_status,
        "num_queries": len(queries),
        "results": baseline_reports,
    }

    text = json.dumps(payload, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n")
        print(f"Wrote {args.output}")
    else:
        print(text)

    summary = "  ".join(
        f"{b}: hit_rate={r['hit_rate']:.1%} "
        f"mrr@10={r['mrr_at_10']:.3f} ndcg@10={r['ndcg_at_10']:.3f}"
        for b, r in baseline_reports.items()
    )
    print(summary, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
