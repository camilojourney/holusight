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


# ---------------------------------------------------------------------------
# Distribution skill -- installable in ANY project, any harness
# ---------------------------------------------------------------------------
#
# render_skill() above renders the repo-local `.claude/skills/holus/SKILL.md`,
# deliberately self-referential to this repository's own dev loop (its
# fallback invocation is `python -m codesight.cli_axi`, which only works
# from inside a checkout of this repo). The distribution variant below is
# for the *general* /holusight skill installed once into
# ~/.claude/skills/holusight/ (and symlinked into every other harness), so
# it can bootstrap `holus` itself, in any project, the first time it runs
# -- mirroring the self-installing Step 1 in ~/.claude/skills/graphify/
# SKILL.md. It reuses render_skill()'s command reference verbatim (single
# source of truth stays axi_schema.py) and only adds the install/index
# preamble around it.

GITHUB_URL = "https://github.com/camilojourney/holusight"

_INSTALL_STEP = f"""## Step 0 -- Ensure `holus` is installed

```bash
PYTHON=""
# 1. Already on PATH from a prior install in this shell
if command -v holus >/dev/null 2>&1; then
    PYTHON="__PATH__"
fi
# 2. uv tool install -- most reliable on modern Mac/Linux, isolated venv
if [ "$PYTHON" != "__PATH__" ] && command -v uv >/dev/null 2>&1; then
    _UV_PY=$(uv tool run --from codesight python -c "import sys; print(sys.executable)" 2>/dev/null)
    if [ -n "$_UV_PY" ] && "$_UV_PY" -c "import codesight" 2>/dev/null; then PYTHON="$_UV_PY"; fi
fi
# 3. Fall back to python3 and check for an existing install
if [ -z "$PYTHON" ]; then PYTHON="python3"; fi
if [ "$PYTHON" != "__PATH__" ] && ! "$PYTHON" -c "import codesight" 2>/dev/null; then
    if command -v uv >/dev/null 2>&1; then
        uv tool install --upgrade "git+{GITHUB_URL}" -q 2>&1 | tail -5
        _UV_PY=$(uv tool run --from codesight python \\
            -c "import sys; print(sys.executable)" 2>/dev/null)
        if [ -n "$_UV_PY" ]; then PYTHON="$_UV_PY"; fi
    else
        "$PYTHON" -m pip install "git+{GITHUB_URL}" -q 2>/dev/null \\
          || "$PYTHON" -m pip install "git+{GITHUB_URL}" -q --break-system-packages 2>&1 | tail -5
    fi
fi
mkdir -p .holusight
if [ "$PYTHON" != "__PATH__" ]; then
    "$PYTHON" -c "
import sys
open('.holusight/.holusight_python', 'w', encoding='utf-8').write(sys.executable)
"
fi
```

If `holus` was already on PATH (case 1), skip straight to Step 1 -- no
install output to print. Otherwise print nothing on success and move to
Step 1.

**In every subsequent bash block below, prefer the bare `holus` command.**
Only fall back to `$(cat .holusight/.holusight_python) -m codesight.cli_axi`
when `holus` is not found on PATH (a fresh `uv tool install` shim may not
be visible until a new shell) -- and to
`$(cat .holusight/.holusight_python) -m codesight index .` for Step 1's
`index` subcommand, which `python -m codesight` (not `holus`) exposes.

## Step 1 -- Build the search index (first run, or after significant changes)

`holus evidence`/`check`/`status` work with no index (exact + structural +
consistency providers only). The `semantic` provider -- needed for
fuzzy/conceptual search across this project -- requires an index built
once, ahead of time; it is never built as a side effect of a read-only
`holus` call:

```bash
holus_python="$(cat .holusight/.holusight_python 2>/dev/null || echo python3)"
"$holus_python" -m codesight index . 2>&1 | tail -10
```

Re-run this after substantial content changes (`--force` to rebuild from
scratch). Skip it entirely for a quick first look -- `holus evidence`
already works without it, just without the semantic provider.
"""


def render_distribution_skill() -> str:
    """SKILL.md for the general, cross-project /holusight install.

    Same command reference as render_skill(), with a self-install preamble
    spliced in front of it and the frontmatter's trigger name changed to
    match the product name (``holusight``) rather than the binary name
    (``holus``) -- see module docstring above.
    """
    body = render_skill()
    # Drop render_skill()'s own frontmatter and title line; replace with
    # distribution-specific ones, then splice the install step in before
    # the rest of the (otherwise identical) command reference.
    _, _, rest = body.partition("---\n")
    _, _, rest = rest.partition("---\n")
    rest = rest.strip("\n")
    _, _, rest = rest.partition("\n\n")  # drop the "# holus - ..." title line

    frontmatter = """---
name: holusight
description: >
  Hybrid BM25 + vector + structural search over any project's code and
  docs, with provenance/freshness/egress attached to every answer -- not
  a fluent guess. Self-installs `holus` on first use, in any project.
  Trigger: /holusight.
---"""

    blocks = [
        frontmatter,
        "# /holusight - install-anywhere Holusight-AXI search",
        "Ask this project for evidence before trusting or editing a spec, "
        "ADR, or the code it governs -- \"where is X enforced\", \"has this "
        "spec drifted from its implementation\", \"is the structural graph "
        "stale\". Works per-project: run it from inside any repository's "
        "checkout, and it indexes and evidences that repository.",
        _INSTALL_STEP.strip("\n"),
        rest,
    ]
    return "\n\n".join(blocks).rstrip() + "\n"


def write_distribution_skill(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_distribution_skill(), encoding="utf-8")


if __name__ == "__main__":
    write_skill()
    print(f"wrote {SKILL_PATH}")
