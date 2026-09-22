"""Install (or update) the general, install-anywhere `/holusight` skill.

Writes the distribution SKILL.md (see :mod:`holusight.axi_skill_gen`'s
``render_distribution_skill`` -- single source of truth stays
``src/holusight/axi_schema.py``) to one canonical real directory, then
symlinks every other supported harness's skills directory to it, exactly
mirroring how ``~/.claude/skills/graphify/`` is the one real copy and
``~/.codex``, ``~/.cursor``, ``~/.gemini``, ``~/.agents`` each hold a symlink
to a single canonical source.

Shipped as the ``holusight-install-skill`` console script (``[project.scripts]``
in ``pyproject.toml``), so ``uv tool install`` (or ``pip install``) of this
package puts it on PATH alongside ``holus`` -- see README.md's "Install
anywhere" section for the two-command install.

Usage:
    holusight-install-skill                     # all harnesses, global
    holusight-install-skill --harness claude,codex
    holusight-install-skill --print              # print, don't write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .axi_skill_gen import render_distribution_skill, write_distribution_skill

SKILL_NAME = "holusight"
CANONICAL_HARNESS = "claude"
ALL_HARNESSES = ("claude", "codex", "cursor", "gemini", "agents")


def canonical_dir() -> Path:
    return Path.home() / f".{CANONICAL_HARNESS}" / "skills" / SKILL_NAME


def harness_dir(harness: str) -> Path:
    return Path.home() / f".{harness}" / "skills" / SKILL_NAME


def install(harnesses: tuple[str, ...]) -> list[str]:
    changes: list[str] = []
    canonical = canonical_dir()
    write_distribution_skill(canonical / "SKILL.md")
    changes.append(f"wrote {canonical / 'SKILL.md'}")

    for harness in harnesses:
        if harness == CANONICAL_HARNESS:
            continue
        link = harness_dir(harness)
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.is_symlink():
            if link.resolve() == canonical.resolve():
                continue  # already correct, idempotent no-op
            link.unlink()
        elif link.exists():
            changes.append(f"skipped {link}: exists and is not a symlink -- remove by hand first")
            continue
        link.symlink_to(canonical, target_is_directory=True)
        changes.append(f"linked {link} -> {canonical}")
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--harness",
        default=",".join(ALL_HARNESSES),
        help=f"comma-separated harnesses to link (default: all of {ALL_HARNESSES})",
    )
    parser.add_argument("--print", action="store_true", help="print the rendered skill and exit")
    args = parser.parse_args()

    if args.print:
        print(render_distribution_skill())
        return 0

    harnesses = tuple(h.strip() for h in args.harness.split(",") if h.strip())
    unknown = set(harnesses) - set(ALL_HARNESSES)
    if unknown:
        print(f"error: unknown harness(es): {sorted(unknown)}", file=sys.stderr)
        return 2

    for line in install(harnesses):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
