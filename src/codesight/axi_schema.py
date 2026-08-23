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

AXI_SCHEMA_VERSION = "0.4.0"

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
_FORMAT_FLAG = AxiFlag("--format", "Output encoding.", choices=FORMAT_CHOICES, default="toon")
_FIELDS_FLAG = AxiFlag(
    "--fields", "Comma-separated dotted-path projection (e.g. snapshot,evidence.source)."
)
_FULL_FLAG = AxiFlag(
    "--full",
    "Disable excerpt truncation.",
    takes_value=False,
)
_HELP_FLAG = AxiFlag("--help", "Show this command's reference and exit.", takes_value=False)
_CASES_FLAG = AxiFlag("--cases", "Path to the frozen case corpus JSONL file.")
_ORIGIN_FLAG = AxiFlag("--origin", "Case origin.")
_KIND_FLAG = AxiFlag(
    "--kind", "Case kind.", choices=("regression", "comparative"), default="regression"
)
_DIAGNOSIS_REF_FLAG = AxiFlag("--diagnosis-ref", "Reference path for reproduced findings.")
_FIX_REF_FLAG = AxiFlag("--fix-ref", "Reference to the fix commit/PR for a reproduced gap.")
_CASE_ID_FLAG = AxiFlag("--case-id", "Explicit candidate case id to propose.")
_ADMITTED_BY_FLAG = AxiFlag("--admitted-by", "Approver name or team in plain text.")
_ADMITTED_AT_FLAG = AxiFlag("--admitted-at", "YYYY-MM-DD date for the admission record.")
_ARTIFACT_TYPE_FLAG = AxiFlag(
    "--artifact-type",
    "Logical placement kind for a proposed artifact.",
    choices=(
        "case",
        "fixture",
        "test",
        "spec",
        "adr",
        "decision",
        "playbook",
        "source",
        "skill",
        "agent",
        "docs",
    ),
)
_PROPOSED_PATH_FLAG = AxiFlag("--proposed-path", "Proposed artifact path to validate.")
_COMPARE_FLAG = AxiFlag(
    "--compare-result",
    "Previous pilot result JSON path. Promotion-relevant comparison requires a clean "
    "tracked evaluated manifest that pins its exact bytes; all other comparisons fail closed.",
)
_WORKFLOW_FLAG = AxiFlag("--workflow", "Execution workflow label.")
_TOOL_FLAG = AxiFlag("--tool", "Tool that produced this run.")
_MODEL_FLAG = AxiFlag("--model", "LLM model name used by the run.")
_PHASE_FLAG = AxiFlag(
    "--phase",
    "Deterministic review phase.",
    choices=("before_change", "after_implementation", "after_test", "pre_promotion"),
    default="before_change",
)
_RECORD_FLAG = AxiFlag(
    "--record",
    "Opt in to a content-minimized derived review record under .holusight/.",
    takes_value=False,
)

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
                "--mode",
                "Restrict which providers run.",
                choices=MODE_CHOICES,
                default="auto",
            ),
            AxiFlag(
                "--provider",
                "Restrict to exactly one named provider.",
                choices=PROVIDER_NAMES,
            ),
            AxiFlag(
                "--explain-route",
                "Include route_reason per provider.",
                takes_value=False,
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
    AxiCommand(
        name="improve-status",
        usage="holus improve-status",
        description=(
            "Continuous-improvement lifecycle status: frozen-case corpus summary, "
            "status-quo coverage, and placement-guard capabilities."
        ),
        flags=(
            _CASES_FLAG,
            _FIELDS_FLAG,
            _FORMAT_FLAG,
            _HELP_FLAG,
        ),
        examples=(
            "holus improve-status",
            "holus improve-status --cases tests/fixtures/holusight_eval_pilot_cases.jsonl",
        ),
    ),
    AxiCommand(
        name="improve-intake",
        usage='holus improve-intake "<summary>"',
        description=(
            "Produce an explicit, sanitized, content-minimized proposed regression case "
            "for human-reviewed admission. No files are written."
        ),
        positional=("summary",),
        flags=(
            _ORIGIN_FLAG,
            _KIND_FLAG,
            _DIAGNOSIS_REF_FLAG,
            _FIX_REF_FLAG,
            _CASES_FLAG,
            _ADMITTED_BY_FLAG,
            _ADMITTED_AT_FLAG,
            _CASE_ID_FLAG,
            _FIELDS_FLAG,
            _FORMAT_FLAG,
            _HELP_FLAG,
        ),
        examples=(
            'holus improve-intake "holus evidence can starve structural evidence" '
            "--origin reproduced_usage_gap --kind comparative --admitted-by team-x",
            'python -m codesight.cli_axi improve-intake "structural graph stale case" '
            "--origin spec_documented_finding --admitted-by team-x",
        ),
    ),
    AxiCommand(
        name="improve-run",
        usage="holus improve-run",
        description=(
            "Run the frozen continuous-improvement corpus with explicit lineage and "
            "machine-readable lifecycle outcome."
        ),
        flags=(
            _CASES_FLAG,
            _WORKFLOW_FLAG,
            _TOOL_FLAG,
            _MODEL_FLAG,
            _COMPARE_FLAG,
            AxiFlag("--candidate-id", "Stable candidate identifier for this run."),
            AxiFlag(
                "--output",
                "Write the full PilotRunResult JSON only to gitignored derived state "
                "or a safe external path.",
            ),
            AxiFlag(
                "--allow-egress",
                "Allow egress-only pilot operations when a case explicitly requires it.",
                takes_value=False,
            ),
            AxiFlag(
                "--allow-semantic",
                "Allow semantic providers while running cases that require them.",
                takes_value=False,
            ),
            AxiFlag(
                "--scorecard",
                "Also print the Fleet aggregate scorecard preview.",
                takes_value=False,
            ),
            _FORMAT_FLAG,
            _HELP_FLAG,
        ),
        examples=(
            "holus improve-run",
            "holus improve-run --candidate-id run-42 --workflow crewmate --model claude-sonnet-5",
            "holus improve-run --cases tests/fixtures/holusight_eval_pilot_cases.jsonl "
            "--compare-result /tmp/last-run.json",
        ),
    ),
    AxiCommand(
        name="improve-placement",
        usage="holus improve-placement",
        description=(
            "Validate a proposed artifact path against structure, canonical locations, "
            "and existing duplicates. Never edits files."
        ),
        flags=(
            _ARTIFACT_TYPE_FLAG,
            _PROPOSED_PATH_FLAG,
            _FIELDS_FLAG,
            _FORMAT_FLAG,
            _HELP_FLAG,
        ),
        examples=(
            "holus improve-placement --artifact-type case "
            "--proposed-path tests/fixtures/my_case.jsonl",
            "holus improve-placement --artifact-type spec --proposed-path specs/018-new-idea.md",
        ),
    ),
    AxiCommand(
        name="improve-review",
        usage="holus improve-review <change-manifest.json>",
        description=(
            "Deterministically classify one tracked change, verify its canonical links, "
            "and return stage, missing evidence, next permitted action, and promotion blockers."
        ),
        positional=("change-manifest.json",),
        flags=(_PHASE_FLAG, _RECORD_FLAG, _FIELDS_FLAG, _FORMAT_FLAG, _HELP_FLAG),
        examples=(
            "holus improve-review specs/019-example.change.json --phase before_change",
            "holus improve-review specs/019-example.change.json --phase pre_promotion --record",
        ),
    ),
    AxiCommand(
        name="improve-history",
        usage="holus improve-history <change-id>",
        description=(
            "Inspect content-minimized, opt-in derived stage history for a change. "
            "Deleting derived records never changes canonical truth."
        ),
        positional=("change-id",),
        flags=(_FIELDS_FLAG, _FORMAT_FLAG, _HELP_FLAG),
        examples=("holus improve-history example-change",),
    ),
    AxiCommand(
        name="improve-integration",
        usage="holus improve-integration <change-manifest.json>",
        description=(
            "Emit the stable local advisory review contract for a future No Mistakes or "
            "Fleet consumer. It performs no integration, promotion, or egress."
        ),
        positional=("change-manifest.json",),
        flags=(_PHASE_FLAG, _FIELDS_FLAG, _FORMAT_FLAG, _HELP_FLAG),
        examples=("holus improve-integration specs/019-example.change.json --phase pre_promotion",),
    ),
)


def command_by_name(name: str) -> AxiCommand:
    for cmd in AXI_COMMANDS:
        if cmd.name == name:
            return cmd
    raise KeyError(name)
