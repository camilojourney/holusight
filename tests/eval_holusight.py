#!/usr/bin/env python3
"""Holusight 20-query retrieval eval — task-plan compatible CLI.

Indexes the repo (src/ + docs/ + specs/, excluding tasks/) and runs the
shared eval harness. Replaces the ephemeral script referenced in task plans.

Usage:
    uv run python tests/eval_holusight.py --top-k 10 --output /tmp/eval.json
    just eval
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUERIES = Path(__file__).resolve().parent / "fixtures" / "holusight_eval_20q.json"


def _load_queries(path: Path):
    from tests.eval_harness import EvalQuery

    raw = json.loads(path.read_text())
    return [
        EvalQuery(
            query=item["query"],
            expected_file=item["expected_file"],
            expected_start_line=item.get("expected_start_line"),
        )
        for item in raw
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run holusight 20-query retrieval eval")
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
    from tests.eval_harness import run_eval

    queries = _load_queries(args.queries)
    config = ServerConfig()
    engine = CodeSight(repo_path, config=config)

    if not args.no_index:
        engine.index(force_rebuild=args.reindex)

    result = run_eval(
        queries,
        engine.store,
        engine.embedder,
        top_k=args.top_k,
        config=config,
    )

    tokens_per_query = result.total_tokens / result.num_queries if result.num_queries else 0.0
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "eval_type": "holusight_specific_20q",
        "repo_path": str(repo_path),
        "queries_file": str(args.queries.resolve()),
        "top_k": args.top_k,
        "hit_rate": round(result.hit_rate, 4),
        "mrr_at_10": round(result.mrr_at_10, 4),
        "tokens_per_query": round(tokens_per_query, 1),
        "tokens_per_correct_answer": round(result.tokens_per_correct_answer, 1),
        "total_tokens": result.total_tokens,
        "num_queries": result.num_queries,
        "num_hits": result.num_hits,
        "per_query": result.per_query,
    }

    text = json.dumps(payload, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n")
        print(f"Wrote {args.output}")
    else:
        print(text)

    print(
        f"hit_rate={payload['hit_rate']:.1%}  mrr@10={payload['mrr_at_10']:.3f}  "
        f"hits={result.num_hits}/{result.num_queries}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
