"""Generate the installable ``/holus`` Agent Skill from :mod:`codesight.axi_schema`.

Single source of truth: this module reads ``AXI_COMMANDS`` /
``AXI_SCHEMA_VERSION`` from :mod:`codesight.axi_schema` - the same schema
:mod:`codesight.cli_axi` parses against - and renders
``.claude/skills/holus/SKILL.md``. It never hand-writes command names,
flags, or examples a second time, so the skill cannot silently diverge
from either the schema or the executable.

Run directly to regenerate the committed skill file:

    python -m codesight.axi_skill_gen

``tests/test_axi_skill_drift.py`` calls :func:`render_skill` and asserts
its output matches the committed file byte-for-byte - the CI drift check
for acceptance criterion 7. If you change ``axi_schema.py`` and forget to
regenerate, that test fails.

Per the AXI skill's own guidance on shipping a secondary/static skill
path: this file omits live/dynamic repository state (that's what
``holus`` itself, run at agent-invocation time, is for) and rewrites
command examples so they work without a global ``holus`` install
(``python -m codesight.cli_axi`` as the fallback invocation).
"""

from __future__ import annotations

from pathlib import Path

from .axi_schema import AXI_COMMANDS, AXI_SCHEMA_VERSION

SKILL_PATH = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "holus" / "SKILL.md"

_FRONTMATTER = """---
name: holus
description: >
  Ask this Holusight-tracked repository for evidence before trusting or
  editing a spec, ADR, or the code it governs. Use when a question needs
  repository evidence with provenance/freshness/egress attached, not a
  fluent guess - "where is X enforced", "has this spec drifted from its
  implementation", "is the structural graph stale".
---"""


def _flag_line(f) -> str:
    choice_str = f" ({'/'.join(f.choices)})" if f.choices else ""
    default_str = f" [default: {f.default}]" if f.default else ""
    return f"- `{f.name}`{choice_str}{default_str} - {f.help}"


def _command_section(cmd) -> str:
    lines = [f"### `{cmd.usage}`", "", cmd.description, ""]
    if cmd.flags:
        # --help is universal and covered once in the "Getting help" section
        # below; omit it from every per-command flag list to avoid repeating
        # the same line five times.
        visible_flags = [f for f in cmd.flags if f.name != "--help"]
        if visible_flags:
            lines.append("Flags:")
            lines.extend(_flag_line(f) for f in visible_flags)
            lines.append("")
    if cmd.examples:
        lines.append("Examples:")
        lines.append("```")
        for ex in cmd.examples:
            lines.append(ex)
            # Fallback form usable without a global `holus` install, per the
            # AXI skill's "non-interactive commands" guidance for skills.
            fallback = ex.replace("holus", "python -m codesight.cli_axi", 1)
            if fallback != ex:
                lines.append(fallback)
        lines.append("```")
    return "\n".join(lines)


def render_skill() -> str:
    """Each list entry is one Markdown *block* (no embedded blank-line
    spacers) - blocks are joined with a single blank line between them, so
    the output never accumulates the double/triple blank lines a naive
    ``"\\n\\n".join([..., "", ...])`` produces."""
    when_to_use = "\n".join(
        [
            "1. Use native/exact search for exact identifiers and known file "
            "questions - `holus` is for uncertain, conceptual, or "
            "cross-file/mixed code-and-docs questions.",
            '2. Call `holus evidence "<question>"` when the relevant '
            "location is uncertain.",
            "3. Call `holus check [scope]` when the question concerns "
            "whether a spec/ADR has drifted from what it governs.",
            "4. Never treat a `stale`, `partial`, or `unavailable` provider "
            "state as if it were current, authoritative evidence - surface "
            "the state to the user instead of a confident answer.",
        ]
    )
    command_sections = [_command_section(cmd) for cmd in AXI_COMMANDS]

    blocks = [
        _FRONTMATTER,
        "# holus - Holusight-AXI repository evidence CLI",
        f"Schema version: `{AXI_SCHEMA_VERSION}` "
        "(generated from `src/codesight/axi_schema.py` - do not hand-edit "
        "the command reference below; run "
        "`python -m codesight.axi_skill_gen` after changing the schema).",
        "## When to use this",
        when_to_use,
        "## Commands",
        *command_sections,
        "## Output formats",
        "`--format toon` (default, compact agent-facing) · "
        "`--format json` (lossless canonical interchange) · "
        "`--format text` (human-readable). "
        "`--fields a,b.c` projects a payload down to just those dotted "
        "paths before rendering.",
        "## Getting help",
        "`--help` works on every command, including with no command "
        "(`holus --help`) for the full command list. Unknown flags and "
        "commands are rejected with exit code 2 and the valid set listed "
        "inline - never silently ignored.",
        "## Exit codes",
        '`0` success, including a definitive "no evidence" or '
        '"already up to date" answer · `1` runtime error · '
        "`2` usage error (unknown command/flag, missing required argument).",
    ]
    return "\n\n".join(blocks).rstrip() + "\n"


def write_skill(path: Path = SKILL_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_skill(), encoding="utf-8")


if __name__ == "__main__":
    write_skill()
    print(f"wrote {SKILL_PATH}")
