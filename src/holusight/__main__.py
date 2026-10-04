"""Public command-line entry point: check an existing Graphify graph offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .api import Holusight


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="holus",
        description="Check Graphify graph mismatches against repository source (read-only)",
    )
    parser.add_argument("command", choices=("check", "status", "align"))
    parser.add_argument(
        "path", nargs="?", default=".", help="Repository directory (default: current directory)"
    )
    parser.add_argument("--scope", help="Focus a repository-relative file or directory")
    parser.add_argument(
        "--docs",
        action="store_true",
        help="Focus supported Markdown anywhere in safe enumeration; intersects --scope",
    )
    parser.add_argument("--against", help="Compare align with a saved repository-relative report")
    args = parser.parse_args(argv)
    if args.command == "status" and (args.scope is not None or args.docs):
        parser.error("status is whole-graph provenance; use check or align with --scope/--docs")
    if args.command != "align" and args.against:
        parser.error("--against applies only to align")
    try:
        engine = Holusight(Path(args.path))
        if args.command == "align":
            result = engine.align(scope=args.scope, docs=args.docs, against=args.against)
        else:
            result = (
                engine.check(scope=args.scope, docs=args.docs)
                if args.command == "check"
                else engine.status()
            )
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return (
        1
        if result["status"] in ("error", "stale", "unknown", "unavailable", "mismatch", "partial")
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
