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
    parser.add_argument("command", choices=("check", "status"))
    parser.add_argument(
        "path", nargs="?", default=".", help="Repository directory (default: current directory)"
    )
    parser.add_argument("--scope", help="Only check this repository-relative graph source path")
    args = parser.parse_args(argv)
    if args.command == "status" and args.scope:
        parser.error("--scope applies only to check")
    try:
        engine = Holusight(Path(args.path))
        result = engine.check(scope=args.scope) if args.command == "check" else engine.status()
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 1 if result["status"] in ("error", "stale", "unknown", "unavailable") else 0


if __name__ == "__main__":
    raise SystemExit(main())
