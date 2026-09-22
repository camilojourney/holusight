"""CLI entry point for Holusight.

Usage:
    python -m holusight index /path/to/docs     Index a folder
    python -m holusight search "query" [path]    Search indexed documents
    python -m holusight ask "question" [path]    Ask a question (uses Claude)
    python -m holusight status [path]            Check index status
    python -m holusight demo                     Launch Streamlit web chat
    python -m holusight serve                    Launch FastAPI production server
    python -m holusight consistency refresh [path]        Refresh consistency cache
    python -m holusight consistency evidence <concept> [path]  Pre-change evidence packet
    python -m holusight consistency check <concept> [path]     Post-change consistency check
    python -m holusight consistency status [path]         Concepts + open health flags
"""

from __future__ import annotations

import argparse
import json
import logging
import sys


def _configure_logging(verbose: bool = False) -> None:
    """Set up logging for the CLI."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        format="%(levelname)s: %(message)s",
        level=level,
    )


def main():
    parser = argparse.ArgumentParser(
        prog="holusight",
        description="AI-powered document search engine",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable verbose logging",
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
    p_search.add_argument(
        "-g", "--glob", dest="file_glob", default=None,
        help="Filter results by file glob pattern (e.g. '*.pdf', 'src/*.py')",
    )
    p_search.add_argument(
        "--json", dest="output_json", action="store_true",
        help="Output results as JSON",
    )

    # ask
    p_ask = sub.add_parser("ask", help="Ask a question (LLM synthesizes answer)")
    p_ask.add_argument("question", help="Question to ask")
    p_ask.add_argument("path", nargs="?", default=".", help="Folder path (default: .)")
    p_ask.add_argument("-k", "--top-k", type=int, default=5, help="Chunks to use as context")
    p_ask.add_argument(
        "-g", "--glob", dest="file_glob", default=None,
        help="Filter results by file glob pattern (e.g. '*.pdf', 'src/*.py')",
    )
    p_ask.add_argument(
        "--json", dest="output_json", action="store_true",
        help="Output results as JSON",
    )

    # status
    p_status = sub.add_parser("status", help="Check index status")
    p_status.add_argument("path", nargs="?", default=".", help="Folder path (default: .)")

    # consistency (Holusight-AXI documentation-code consistency system, Phase 1)
    p_consistency = sub.add_parser(
        "consistency", help="Documentation-code consistency cache (Phase 1)"
    )
    consistency_sub = p_consistency.add_subparsers(dest="consistency_command")

    p_c_refresh = consistency_sub.add_parser(
        "refresh", help="Refresh the .holusight/consistency.db cache"
    )
    p_c_refresh.add_argument("path", nargs="?", default=".", help="Repo path (default: .)")
    p_c_refresh.add_argument(
        "--semantic", action="store_true",
        help="Also compute local-embedding semantic edges (opt-in, no network)",
    )

    p_c_evidence = consistency_sub.add_parser(
        "evidence", help="Print the pre-change evidence packet for a concept"
    )
    p_c_evidence.add_argument("concept_id", help="Concept ID (canonical spec/ADR path)")
    p_c_evidence.add_argument("path", nargs="?", default=".", help="Repo path (default: .)")

    p_c_check = consistency_sub.add_parser(
        "check", help="Post-change consistency check for a concept"
    )
    p_c_check.add_argument("concept_id", help="Concept ID (canonical spec/ADR path)")
    p_c_check.add_argument("path", nargs="?", default=".", help="Repo path (default: .)")

    p_c_status = consistency_sub.add_parser(
        "status", help="Print cached concepts and open health flags"
    )
    p_c_status.add_argument("path", nargs="?", default=".", help="Repo path (default: .)")

    # demo
    sub.add_parser("demo", help="Launch Streamlit web chat UI")

    # serve
    p_serve = sub.add_parser("serve", help="Launch FastAPI production server")
    p_serve.add_argument("--host", default="0.0.0.0", help="Bind host")
    p_serve.add_argument("--port", type=int, default=8000, help="Bind port")
    p_serve.add_argument(
        "path", nargs="?", default=None,
        help="Document folder (sets HOLUSIGHT_DOCUMENTS_DIR)",
    )

    args = parser.parse_args()
    _configure_logging(getattr(args, "verbose", False))

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "demo":
        _launch_demo()
        return

    if args.command == "serve":
        _launch_serve(args)
        return

    if args.command == "consistency":
        _run_consistency(args)
        return

    # Lazy import to avoid loading heavy deps for --help
    from .api import Holusight

    # Path validation with helpful messages
    if hasattr(args, "path"):
        from pathlib import Path as _Path
        _p = _Path(args.path).expanduser().resolve()
        if not _p.exists():
            print(f"Error: Path does not exist: {args.path}", file=sys.stderr)
            print(f"  Resolved to: {_p}", file=sys.stderr)
            print("\n  Hint: Use an absolute path or a path relative to",
                  "your current directory.", file=sys.stderr)
            print("  Hint: Use tab completion in your shell to",
                  "autocomplete paths.", file=sys.stderr)
            sys.exit(1)
        if not _p.is_dir():
            print(f"Error: Not a directory: {args.path}", file=sys.stderr)
            print("  Holusight indexes directories, not individual files.", file=sys.stderr)
            sys.exit(1)

    try:
        if args.command == "index":
            engine = Holusight(args.path)
            stats = engine.index(force_rebuild=args.force)
            print(json.dumps(stats.model_dump(), indent=2))

        elif args.command == "search":
            engine = Holusight(args.path)
            results = engine.search(
                args.query, top_k=args.top_k, file_glob=args.file_glob,
            )

            if args.output_json:
                print(json.dumps(
                    [r.model_dump() for r in results], indent=2,
                ))
            elif not results:
                print("No results found.")
            else:
                for r in results:
                    loc_label = _location_label(r.start_line, r.end_line, r.scope)
                    print(f"\n--- {r.file_path} ({loc_label}, score: {r.score:.4f}) ---")
                    print(f"[{r.scope}]")
                    print(r.snippet[:500])

        elif args.command == "ask":
            engine = Holusight(args.path)
            answer = engine.ask(
                args.question, top_k=args.top_k, file_glob=args.file_glob,
            )

            if args.output_json:
                print(json.dumps(answer.model_dump(), indent=2))
            else:
                print(f"\n{answer.text}")
                print(f"\n--- Sources ({len(answer.sources)}) ---")
                for s in answer.sources:
                    loc_label = _location_label(s.start_line, s.end_line, s.scope)
                    print(f"  - {s.file_path} ({loc_label}): {s.scope}")

        elif args.command == "status":
            engine = Holusight(args.path)
            status = engine.status()
            print(json.dumps(status.model_dump(), indent=2))

    except ValueError as e:
        error_msg = str(e)
        # Detect missing API key errors and provide onboarding guidance
        if "API_KEY" in error_msg or "environment variable is required" in error_msg:
            print("\n" + "=" * 60, file=sys.stderr)
            print("  Holusight Setup Required", file=sys.stderr)
            print("=" * 60, file=sys.stderr)
            print(f"\n  {error_msg}\n", file=sys.stderr)
            print("  Quick setup:", file=sys.stderr)
            print("    1. Copy the env template:  cp .env.example .env", file=sys.stderr)
            print("    2. Add your API key to .env", file=sys.stderr)
            print("    3. Source it:  source .env  (or export vars in your shell)", file=sys.stderr)
            print("\n  For 100% local mode (no API key needed):", file=sys.stderr)
            print("    export HOLUSIGHT_LLM_BACKEND=ollama", file=sys.stderr)
            print("    ollama pull llama3.1", file=sys.stderr)
            print("\n" + "=" * 60, file=sys.stderr)
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        logging.getLogger(__name__).debug("Unhandled exception", exc_info=True)
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _location_label(start_line: int, end_line: int, scope: str) -> str:
    """Return 'lines X-Y' for code or 'page X-Y' for documents."""
    # Document scopes use "page N" format
    if scope.startswith("page ") or scope.startswith("section "):
        return f"page {start_line}-{end_line}"
    return f"lines {start_line}-{end_line}"


def _launch_demo():
    """Launch the Streamlit demo app."""
    import subprocess
    from pathlib import Path

    app_path = Path(__file__).parent.parent.parent / "demo" / "app.py"
    if not app_path.exists():
        print(f"Demo app not found at {app_path}", file=sys.stderr)
        sys.exit(1)
    subprocess.run(["streamlit", "run", str(app_path)], check=True)


def _launch_serve(args) -> None:
    """Launch the FastAPI production server."""
    import os
    from pathlib import Path

    if args.path:
        docs = Path(args.path).expanduser().resolve()
        if not docs.is_dir():
            print(f"Error: Not a directory: {args.path}", file=sys.stderr)
            sys.exit(1)
        os.environ["HOLUSIGHT_DOCUMENTS_DIR"] = str(docs)

    # Production-shaped unless explicitly opted out
    if not os.environ.get("HOLUSIGHT_ALLOW_UNAUTHENTICATED"):
        os.environ.setdefault("HOLUSIGHT_PRODUCTION", "1")

    # SEC-005: tell validate_startup() which host we're actually binding to,
    # so it can refuse to start HOLUSIGHT_ALLOW_UNAUTHENTICATED on anything
    # but a loopback bind.
    os.environ["HOLUSIGHT_BIND_HOST"] = args.host

    try:
        import uvicorn
    except ImportError:
        print(
            "FastAPI server dependencies missing. Install with: pip install -e \".[server]\"",
            file=sys.stderr,
        )
        sys.exit(1)

    uvicorn.run(
        "holusight.web.server:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


def _run_consistency(args) -> None:
    """Dispatch `python -m holusight consistency <action> ...` (Phase 1)."""
    from pathlib import Path as _Path

    action = getattr(args, "consistency_command", None)
    if not action:
        print(
            "Error: missing consistency subcommand (refresh|evidence|check|status)",
            file=sys.stderr,
        )
        sys.exit(1)

    repo_path = _Path(args.path).expanduser().resolve()
    if not repo_path.is_dir():
        print(f"Error: Not a directory: {args.path}", file=sys.stderr)
        sys.exit(1)

    from . import consistency

    try:
        if action == "refresh":
            result = consistency.refresh(repo_path, run_semantic=args.semantic)
            print(json.dumps(result.model_dump(), indent=2))
        elif action == "evidence":
            packet = consistency.build_evidence_packet(repo_path, args.concept_id)
            print(json.dumps(packet.model_dump(), indent=2))
        elif action == "check":
            report = consistency.check_consistency(repo_path, args.concept_id)
            print(json.dumps(report.model_dump(), indent=2))
        elif action == "status":
            from .consistency_store import ConsistencyStore

            store = ConsistencyStore(consistency.consistency_db_path(repo_path))
            try:
                payload = {
                    "concepts": store.all_concepts(),
                    "health_flags": store.all_health_flags(),
                }
            finally:
                store.close()
            print(json.dumps(payload, indent=2))
    except KeyError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
