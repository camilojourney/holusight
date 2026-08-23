"""Versioned command/output schema for the ``holus`` AXI command surface.

This module is the single source of truth for the ``holus`` CLI's job
surface (:mod:`codesight.cli_axi`) and its generated agent skill
(:mod:`codesight.axi_skill_gen` -> ``.claude/skills/holus/SKILL.md``).
Both read ``AXI_COMMANDS`` from here instead of hard-coding flags or
examples a second time, so the executable, this schema, and the skill
cannot silently diverge - ``tests/test_axi_skill_drift.py`` regenerates the
skill from this module on every test run and fails if the committed file
differs (the project's CI drift check for acceptance criterion 7).

Bump :data:`AXI_SCHEMA_VERSION` (semver) whenever a command, flag, or
output field is added, renamed, or removed. The version is included in
every ``holus`` JSON/TOON payload as ``schema_version`` so a caller can
detect a contract change without parsing prose.
"""

from __future__ import annotations

from dataclasses import dataclass

AXI_SCHEMA_VERSION = "0.1.0"

# The five stable jobs, per specs/011-holusight-product-architecture-research.md
# ("holus-axi: smallest stable command surface") and
# specs/015-holusight-axi-command-surface.md. "" is the no-argument home view.
STABLE_JOBS: tuple[str, ...] = ("", "evidence", "check", "status", "providers")

PROVIDER_NAMES: tuple[str, ...] = ("exact", "structural", "consistency", "semantic")

# spec 011's forceable routing modes. Note "structure" (not "structural") is
# the mode name - it maps to the "structural" provider; kept distinct so the
# CLI's --mode choices match the spec text exactly.
MODE_CHOICES: tuple[str, ...] = ("auto", "exact", "semantic", "structure")

FORMAT_CHOICES: tuple[str, ...] = ("toon", "json", "text")


@dataclass(frozen=True)
class AxiFlag:
    name: str  # e.g. "--mode"
    help: str
    choices: tuple[str, ...] | None = None
    default: str | None = None
    takes_value: bool = True


@dataclass(frozen=True)
class AxiCommand:
    name: str  # "" for the no-arg home view
    usage: str
    description: str
    positional: tuple[str, ...] = ()
    flags: tuple[AxiFlag, ...] = ()
    examples: tuple[str, ...] = ()


# Flags shared by every job that returns an evidence-shaped or listing
# payload. Kept as a named tuple so each command below composes it
# explicitly rather than re-declaring the same four flags four times.
_FORMAT_FLAG = AxiFlag(
    "--format", "Output encoding.", choices=FORMAT_CHOICES, default="toon"
)
_FIELDS_FLAG = AxiFlag(
    "--fields", "Comma-separated dotted-path projection (e.g. snapshot,evidence.source)."
)
_FULL_FLAG = AxiFlag(
    "--full", "Disable excerpt truncation.", takes_value=False,
)
_HELP_FLAG = AxiFlag("--help", "Show this command's reference and exit.", takes_value=False)

AXI_COMMANDS: tuple[AxiCommand, ...] = (
    AxiCommand(
        name="",
        usage="holus",
        description=(
            "Content-first repository home view: identity, snapshot, "
            "provider freshness, egress, contract summary."
        ),
        flags=(_FORMAT_FLAG, _HELP_FLAG),
        examples=("holus",),
    ),
    AxiCommand(
        name="evidence",
        usage='holus evidence "<question>"',
        description=(
            "Return the smallest current evidence packet for a question, "
            "routed across the exact, structural, consistency, and "
            "(if already indexed) semantic providers."
        ),
        positional=("question",),
        flags=(
            AxiFlag(
                "--mode", "Restrict which providers run.",
                choices=MODE_CHOICES, default="auto",
            ),
            AxiFlag(
                "--provider", "Restrict to exactly one named provider.",
                choices=PROVIDER_NAMES,
            ),
            AxiFlag(
                "--explain-route", "Include route_reason per provider.", takes_value=False,
            ),
            AxiFlag(
                "--allow-egress",
                "Permit the semantic provider to query a Voyage-embedded index "
                "(external API call). Off by default.",
                takes_value=False,
            ),
            _FULL_FLAG,
            _FIELDS_FLAG,
            _FORMAT_FLAG,
            _HELP_FLAG,
        ),
        examples=(
            'holus evidence "where is retry policy enforced?"',
            'holus evidence "where is retry policy enforced?" --mode exact',
            'holus evidence "<question>" --fields snapshot,evidence.source,evidence.location',
        ),
    ),
    AxiCommand(
        name="check",
        usage="holus check [scope]",
        description=(
            "Post-change consistency check: has the canonical spec/ADR at "
            "`scope`, or every concept if `scope` is omitted, drifted from "
            "its linked artifacts since the cache was last refreshed?"
        ),
        positional=("scope?",),
        flags=(
            AxiFlag(
                "--refresh",
                "Refresh the consistency cache to current disk state before checking "
                "(resets the drift baseline).",
                takes_value=False,
            ),
            _FIELDS_FLAG,
            _FORMAT_FLAG,
            _HELP_FLAG,
        ),
        examples=(
            "holus check",
            "holus check specs/013-holusight-axi-consistency-architecture.md",
            "holus check --refresh",
        ),
    ),
    AxiCommand(
        name="status",
        usage="holus status",
        description=(
            "Repository snapshot, per-provider freshness/egress, contract "
            "(claim) pass/fail counts, and open health-flag counts by severity."
        ),
        flags=(_FIELDS_FLAG, _FORMAT_FLAG, _HELP_FLAG),
        examples=("holus status",),
    ),
    AxiCommand(
        name="providers",
        usage="holus providers",
        description=(
            "List each provider's availability, version/model, freshness, and egress class."
        ),
        flags=(_FORMAT_FLAG, _HELP_FLAG),
        examples=("holus providers",),
    ),
)


def command_by_name(name: str) -> AxiCommand:
    for cmd in AXI_COMMANDS:
        if cmd.name == name:
            return cmd
    raise KeyError(name)
