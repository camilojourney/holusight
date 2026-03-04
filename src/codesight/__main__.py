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

WORKSPACE_SOURCE_KEYS = {
    "drive": "path",
    "mail": "mailbox",
    "notes": "notebook",
    "sharepoint": "site_url",
    "local": "path",
}
WORKSPACE_SUBCOMMANDS = (
    "create",
    "list",
    "show",
    "update",
    "delete",
    "sync",
    "add-source",
    "remove-source",
    "allow",
    "deny",
    "repair",
)


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

    # sync
    p_sync = sub.add_parser("sync", help="Sync external content sources and index them")
    p_sync.add_argument(
        "--source",
        required=True,
        choices=["m365"],
        help="External source to sync",
    )
    p_sync.add_argument(
        "--reset-auth",
        action="store_true",
        help="Clear cached M365 tokens before syncing (use when switching accounts)",
    )

    # bot
    p_bot = sub.add_parser("bot", help="Start Teams bot server")
    p_bot.add_argument(
        "--data-path",
        default=None,
        help="Optional path to indexed content (defaults to CODESIGHT_BOT_DATA_PATH or cwd)",
    )

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

    # workspace
    p_workspace = sub.add_parser("workspace", help="Manage workspaces")
    workspace_sub = p_workspace.add_subparsers(dest="workspace_command")

    p_workspace_create = workspace_sub.add_parser("create", help="Create a workspace")
    p_workspace_create.add_argument("name", help="Workspace name")
    p_workspace_create.add_argument("--description", default=None, help="Workspace description")
    p_workspace_create.add_argument(
        "--source",
        action="append",
        nargs="+",
        default=[],
        metavar="TYPE:VALUE",
        help="Bind one or more data sources (TYPE:VALUE)",
    )
    p_workspace_create.add_argument(
        "--allow",
        action="append",
        nargs="+",
        default=[],
        metavar="EMAIL",
        help="Allow one or more email addresses",
    )

    workspace_sub.add_parser("list", help="List workspaces")

    p_workspace_show = workspace_sub.add_parser("show", help="Show workspace details")
    p_workspace_show.add_argument("name_or_id", help="Workspace name or ID")

    p_workspace_update = workspace_sub.add_parser("update", help="Update workspace metadata")
    p_workspace_update.add_argument("name_or_id", help="Workspace name or ID")
    p_workspace_update.add_argument("--name", default=None, help="New workspace name")
    p_workspace_update.add_argument("--description", default=None, help="New workspace description")

    p_workspace_delete = workspace_sub.add_parser("delete", help="Delete a workspace")
    p_workspace_delete.add_argument("name_or_id", help="Workspace name or ID")
    p_workspace_delete.add_argument("--yes", action="store_true", help="Skip confirmation prompt")

    p_workspace_sync = workspace_sub.add_parser("sync", help="Sync one workspace")
    p_workspace_sync.add_argument("name_or_id", help="Workspace name or ID")

    p_workspace_add_source = workspace_sub.add_parser("add-source", help="Add one data source")
    p_workspace_add_source.add_argument("name_or_id", help="Workspace name or ID")
    p_workspace_add_source.add_argument(
        "--source",
        required=True,
        metavar="TYPE:VALUE",
        help="Data source to bind",
    )

    p_workspace_remove_source = workspace_sub.add_parser(
        "remove-source", help="Remove a data source"
    )
    p_workspace_remove_source.add_argument("name_or_id", help="Workspace name or ID")
    p_workspace_remove_source.add_argument("--source-id", required=True, help="Source ID")

    p_workspace_allow = workspace_sub.add_parser("allow", help="Allow an email in workspace ACL")
    p_workspace_allow.add_argument("name_or_id", help="Workspace name or ID")
    p_workspace_allow.add_argument("email", help="Email to allow")

    p_workspace_deny = workspace_sub.add_parser("deny", help="Deny an email in workspace ACL")
    p_workspace_deny.add_argument("name_or_id", help="Workspace name or ID")
    p_workspace_deny.add_argument("email", help="Email to deny")

    workspace_sub.add_parser("repair", help="Run workspaces.db integrity check")

    if _has_unknown_workspace_subcommand(sys.argv):
        sys.exit(1)

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
    if args.command == "sync":
        _run_sync(args)
        return
    if args.command == "bot":
        _run_bot(args)
        return
    if args.command == "workspace":
        _run_workspace_cli(args, p_workspace)
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


def _run_sync(args):
    from .connectors import GraphConnector

    connector = GraphConnector.from_source(args.source)
    if getattr(args, "reset_auth", False):
        connector.auth.reset()
        print("Token cache cleared. You will need to re-authenticate.")
    result = connector.sync()
    print(json.dumps(result, indent=2))


def _run_bot(args):
    from .bot.app import run_bot_server

    run_bot_server(data_path=args.data_path)


def _run_workspace_cli(args, parser):
    from .workspace import CORRUPTED_DB_MESSAGE, WorkspaceDB, WorkspaceManager

    if not args.workspace_command:
        parser.print_help()
        _print_workspace_subcommands()
        sys.exit(1)

    if args.workspace_command == "repair":
        try:
            db = WorkspaceDB()
            with db.connection() as conn:
                result = conn.execute("PRAGMA integrity_check").fetchone()
            if result is None or result[0] != "ok":
                print(CORRUPTED_DB_MESSAGE)
                sys.exit(1)
            print("workspaces.db integrity check passed.")
            return
        except Exception as exc:
            message = str(exc)
            print(message if message else CORRUPTED_DB_MESSAGE)
            sys.exit(1)

    try:
        manager = WorkspaceManager()

        if args.workspace_command == "create":
            sources = [_parse_source_arg(raw) for raw in _flatten_multi_values(args.source)]
            allowed_emails = _flatten_multi_values(args.allow)
            workspace = manager.create(
                args.name,
                description=args.description,
                sources=sources,
                allowed_emails=allowed_emails,
            )
            print(f"Created workspace '{workspace.name}' ({workspace.id})")
            return

        if args.workspace_command == "list":
            workspaces = manager.list()
            _print_workspace_list(workspaces)
            return

        if args.workspace_command == "show":
            workspace = manager.get(args.name_or_id)
            print(f"id: {workspace.id}")
            print(f"name: {workspace.name}")
            print(f"description: {workspace.description or ''}")
            print(f"sync_status: {workspace.sync_status}")
            print(f"last_synced_at: {workspace.last_synced_at or ''}")
            print(f"created_at: {workspace.created_at}")
            print(f"updated_at: {workspace.updated_at}")
            return

        if args.workspace_command == "update":
            workspace = manager.get(args.name_or_id)
            updated = manager.update(
                workspace.id,
                name=args.name,
                description=args.description,
            )
            print(f"Updated workspace '{updated.name}' ({updated.id})")
            return

        if args.workspace_command == "delete":
            workspace = manager.get(args.name_or_id)
            if not args.yes:
                answer = input("Are you sure? [y/N]: ").strip().lower()
                if answer not in {"y", "yes"}:
                    print("Aborted.")
                    sys.exit(1)
            manager.delete(workspace.id)
            print(f"Deleted workspace '{workspace.name}' ({workspace.id})")
            return

        if args.workspace_command == "sync":
            workspace = manager.get(args.name_or_id)
            result = manager.sync(workspace.id)
            print(f"workspace: {workspace.name}")
            print(f"sync_run_id: {result.id}")
            print(f"status: {result.status}")
            print(f"started_at: {result.started_at}")
            print(f"completed_at: {result.completed_at or ''}")
            print(f"files_added: {result.files_added}")
            print(f"files_updated: {result.files_updated}")
            print(f"files_deleted: {result.files_deleted}")
            if result.error_message:
                print(f"error_message: {result.error_message}")
            return

        if args.workspace_command == "add-source":
            workspace = manager.get(args.name_or_id)
            source = manager.add_source(workspace.id, _parse_source_arg(args.source))
            print(f"Added source '{source.id}' to workspace '{workspace.name}'")
            print(f"type: {source.source_type}")
            print(f"config: {json.dumps(source.source_config, sort_keys=True)}")
            return

        if args.workspace_command == "remove-source":
            workspace = manager.get(args.name_or_id)
            manager.remove_source(workspace.id, args.source_id)
            print(f"Removed source '{args.source_id}' from workspace '{workspace.name}'")
            return

        if args.workspace_command == "allow":
            workspace = manager.get(args.name_or_id)
            manager.allow(workspace.id, args.email)
            print(f"Allowed '{args.email}' for workspace '{workspace.name}'")
            return

        if args.workspace_command == "deny":
            workspace = manager.get(args.name_or_id)
            manager.deny(workspace.id, args.email)
            print(f"Denied '{args.email}' for workspace '{workspace.name}'")
            return
    except Exception as exc:
        print(str(exc))
        sys.exit(1)

    print(f"Unknown workspace subcommand '{args.workspace_command}'.")
    _print_workspace_subcommands()
    sys.exit(1)


def _parse_source_arg(raw_value: str):
    from .types import DataSource

    source_type, separator, value = raw_value.partition(":")
    source_type = source_type.strip().lower()
    value = value.strip()
    if not separator or not source_type or not value:
        raise ValueError(f"Invalid source value '{raw_value}'. Use TYPE:VALUE.")

    required_key = WORKSPACE_SOURCE_KEYS.get(source_type)
    if required_key is None:
        valid = ", ".join(WORKSPACE_SOURCE_KEYS.keys())
        raise ValueError(f"Unsupported source type '{source_type}'. Valid types: {valid}.")

    return DataSource(source_type=source_type, source_config={required_key: value})


def _flatten_multi_values(values: list[list[str]]) -> list[str]:
    flattened: list[str] = []
    for group in values:
        flattened.extend(group)
    return flattened


def _has_unknown_workspace_subcommand(argv: list[str]) -> bool:
    if len(argv) < 3 or argv[1] != "workspace":
        return False
    candidate = argv[2]
    if candidate.startswith("-"):
        return False
    if candidate in WORKSPACE_SUBCOMMANDS:
        return False
    print(f"Unknown workspace subcommand '{candidate}'.")
    _print_workspace_subcommands()
    return True


def _print_workspace_subcommands() -> None:
    print(f"Valid subcommands: {', '.join(WORKSPACE_SUBCOMMANDS)}")


def _print_workspace_list(workspaces) -> None:
    headers = ("id", "name", "sync_status", "last_synced_at")
    rows = [
        (
            workspace.id,
            workspace.name,
            workspace.sync_status,
            workspace.last_synced_at or "",
        )
        for workspace in workspaces
    ]
    widths = [len(header) for header in headers]
    for row in rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(str(value)))

    print("  ".join(header.ljust(widths[idx]) for idx, header in enumerate(headers)))
    for row in rows:
        print("  ".join(str(value).ljust(widths[idx]) for idx, value in enumerate(row)))


if __name__ == "__main__":
    main()
