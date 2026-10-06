"""Public command-line entry point: scan repository source offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .api import Holusight


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="holus",
        description="Scan repository source for duplication candidates and fact drift (read-only)",
    )
    parser.add_argument("command", choices=("align",))
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
    try:
        result = Holusight(Path(args.path)).align(
            scope=args.scope, docs=args.docs, against=args.against
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
