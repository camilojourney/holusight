"""CLI entry point for CodeSight.

Usage:
    python -m codesight index /path/to/docs     Index a folder
    python -m codesight search "query" [path]    Search indexed documents
    python -m codesight ask "question" [path]    Ask a question (uses Claude)
    python -m codesight status [path]            Check index status
    python -m codesight demo                     Launch Streamlit web chat
"""

from __future__ import annotations

import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="codesight",
        description="AI-powered document search engine",
    )
    sub = parser.add_subparsers(dest="command")

    # index
    p_index = sub.add_parser("index", help="Index a document folder")
    p_index.add_argument("path", help="Path to folder")
    p_index.add_argument("--force", action="store_true", help="Rebuild from scratch")

    # search
    p_search = sub.add_parser("search", help="Search indexed documents")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("path", nargs="?", default=".", help="Folder path (default: .)")
    p_search.add_argument("-k", "--top-k", type=int, default=8, help="Number of results")

    # ask
    p_ask = sub.add_parser("ask", help="Ask a question (LLM synthesizes answer)")
    p_ask.add_argument("question", help="Question to ask")
    p_ask.add_argument("path", nargs="?", default=".", help="Folder path (default: .)")
    p_ask.add_argument("-k", "--top-k", type=int, default=5, help="Chunks to use as context")

    # status
    p_status = sub.add_parser("status", help="Check index status")
    p_status.add_argument("path", nargs="?", default=".", help="Folder path (default: .)")

    # demo
    sub.add_parser("demo", help="Launch Streamlit web chat UI")

    # SPEC-009-007: Benchmark harness CLI subcommands.
    # benchmark
    p_benchmark = sub.add_parser("benchmark", help="Run benchmark harness")
    benchmark_sub = p_benchmark.add_subparsers(dest="benchmark_command")

    p_benchmark_run = benchmark_sub.add_parser("run", help="Run benchmark query bank")
    p_benchmark_run.add_argument("--config", default="B", help="Benchmark config profile (A-H)")
    p_benchmark_run.add_argument("--corpus", required=True, help="Corpus folder path")
    p_benchmark_run.add_argument(
        "--question-bank",
        default="tests/benchmarks/questions.json",
        help="Question bank JSON path",
    )
    p_benchmark_run.add_argument(
        "--results-db",
        default="tests/benchmarks/results.db",
        help="SQLite results database path",
    )
    p_benchmark_run.add_argument(
        "--include-llm",
        action="store_true",
        help="Enable ask() + answer quality metrics",
    )
    p_benchmark_run.add_argument(
        "--config-file",
        default=None,
        help="Optional custom benchmark config JSON file",
    )

    p_benchmark_compare = benchmark_sub.add_parser("compare", help="Compare two benchmark runs")
    p_benchmark_compare.add_argument("--run-a", required=True, help="Run ID A")
    p_benchmark_compare.add_argument("--run-b", required=True, help="Run ID B")
    p_benchmark_compare.add_argument(
        "--results-db",
        default="tests/benchmarks/results.db",
        help="SQLite results database path",
    )

    p_benchmark_report = benchmark_sub.add_parser("report", help="Report a benchmark run")
    p_benchmark_report.add_argument("--run", required=True, help="Run ID")
    p_benchmark_report.add_argument(
        "--results-db",
        default="tests/benchmarks/results.db",
        help="SQLite results database path",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "demo":
        _launch_demo()
        return

    if args.command == "benchmark":
        if not args.benchmark_command:
            p_benchmark.print_help()
            sys.exit(1)
        _run_benchmark_cli(args)
        return

    # Lazy import to avoid loading heavy deps for --help
    from .api import CodeSight

    if args.command == "index":
        engine = CodeSight(args.path)
        stats = engine.index(force_rebuild=args.force)
        print(json.dumps(stats.model_dump(), indent=2))

    elif args.command == "search":
        engine = CodeSight(args.path)
        results = engine.search(args.query, top_k=args.top_k)
        for r in results:
            print(f"\n--- {r.file_path} (page {r.start_line}-{r.end_line}, score: {r.score}) ---")
            print(f"[{r.scope}]")
            print(r.snippet[:500])

    elif args.command == "ask":
        engine = CodeSight(args.path)
        answer = engine.ask(args.question, top_k=args.top_k)
        print(f"\n{answer.text}")
        print(f"\n--- Sources ({len(answer.sources)}) ---")
        for s in answer.sources:
            print(f"  - {s.file_path} (page {s.start_line}-{s.end_line}): {s.scope}")

    elif args.command == "status":
        engine = CodeSight(args.path)
        status = engine.status()
        print(json.dumps(status.model_dump(), indent=2))


def _launch_demo():
    """Launch the Streamlit demo app."""
    import subprocess
    from pathlib import Path

    app_path = Path(__file__).parent.parent.parent / "demo" / "app.py"
    if not app_path.exists():
        print(f"Demo app not found at {app_path}")
        sys.exit(1)
    subprocess.run(["streamlit", "run", str(app_path)], check=True)


def _run_benchmark_cli(args):
    from .benchmark import BenchmarkStore, build_report, compare_runs, run_benchmark

    if args.benchmark_command == "run":
        result = run_benchmark(
            config_name=args.config,
            corpus_path=args.corpus,
            include_llm=args.include_llm,
            question_bank_path=args.question_bank,
            results_db_path=args.results_db,
            config_file=args.config_file,
        )
        print(json.dumps(result, indent=2))
        return

    store = BenchmarkStore(args.results_db)
    if args.benchmark_command == "compare":
        result = compare_runs(store, args.run_a, args.run_b)
        for warning in result["warnings"]:
            print(warning)
        print("metric\trun_a_mean\trun_b_mean\tdiff\tp_value\tsignificant\tn")
        for row in result["rows"]:
            print(
                f"{row['metric']}\t{row['run_a_mean']}\t{row['run_b_mean']}\t"
                f"{row['difference']}\t{row['p_value']}\t{row['significant']}\t{row['n']}"
            )
        return

    if args.benchmark_command == "report":
        rows = build_report(store, args.run)
        print("metric\tmean\tmedian\tp5\tp95")
        for row in rows:
            print(f"{row['metric']}\t{row['mean']}\t{row['median']}\t{row['p5']}\t{row['p95']}")
        return


if __name__ == "__main__":
    main()
