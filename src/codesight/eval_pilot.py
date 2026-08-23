"""Holusight safe continuous-evaluation pilot (spec 017).

The smallest useful local, no-spend continuous-evaluation loop over
already-landed Holusight-AXI work (`consistency.py`, spec 013;
`cli_axi.py`/`axi_providers.py`, spec 015; `fleet_scorecard.py`, spec 016).
This module adds no new retrieval mechanism, no new provider, and no
production-default change. It is a thin evaluator over already-shipped
behavior:

1. A frozen, human-admitted case corpus
   (``tests/fixtures/holusight_eval_pilot_cases.jsonl``) — each case
   carries explicit provenance back to a reproduced real usage gap (a
   fixed bug, see ``cli-axi-provider-starvation-display-quota`` below) or
   a spec-documented deterministic contract. See
   ``docs/playbooks/eval-pilot-case-admission.md`` for how a case is
   admitted.
2. A bounded, deterministic runner (:func:`run_pilot`) that grades every
   case against the current repository state and records who/what
   produced the run (:class:`CandidateLineage`) — never raw prompts, file
   content, or absolute host paths.
3. For cases where a meaningful prior implementation exists
   (``kind: "comparative"``), the runner also grades a frozen **status-quo
   control** — a pinned, pre-fix reference implementation kept here *only*
   as a comparator, never wired into production — so a candidate's win is
   demonstrated, not assumed. See :func:`_naive_concatenate_then_slice`.
4. Two Fleet v1.2-shaped, content-free exports:
   :func:`build_pilot_aggregate_scorecard` (counts/rates only, no raw
   evidence) and :func:`pilot_domain_result_summary` (the minimal dict
   shape ``run_repo_eval.py``'s ``parse_domain_result()`` expects — see
   ``fleet_scorecard.py`` for the landed precedent this mirrors). Neither
   is wired as ``agentic/manifest.yaml``'s declared ``eval_entrypoint``
   (still ``just fleet-smoke``, unchanged) — this pilot is additive, not a
   replacement.

Non-goals (see specs/017-holusight-safe-continuous-evaluation-pilot.md and
the delegated policy it implements): no deployment, no private/production
content, no telemetry, no paid APIs, no external providers, no online
self-modification, no autonomous promotion. Results are advisory only —
nothing in this repository reads a verdict from this module and takes an
automatic action.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

from . import axi_providers, cli_axi, consistency
from .fleet_scorecard import FLEET_CONTRACT_COMMIT, FLEET_CONTRACT_PR, FLEET_CONTRACT_REPO

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES_PATH = REPO_ROOT / "tests" / "fixtures" / "holusight_eval_pilot_cases.jsonl"

SCHEMA_CASE = "holus-eval-pilot-case/v1"
SCHEMA_RESULT = "holus-eval-pilot-result/v1"
SCHEMA_PILOT_SCORECARD = "fleet.eval_scorecard.v1.2"
SCHEMA_INTAKE_PROPOSAL = "holus-improve-intake/v1"

_KNOWN_KINDS = frozenset({"regression", "comparative"})
_REQUIRED_PROVENANCE_FIELDS = frozenset(
    {"origin", "description", "admitted_by", "admitted_at"}
)
_KNOWN_ORIGINS = frozenset(
    {"reproduced_usage_gap", "spec_documented_finding", "spec_documented_contract"}
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_hex(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CandidateLineage(BaseModel):
    """Who/what produced this run. Deliberately excludes any raw-prompt or
    free-text-content field — only identity/workflow metadata."""

    candidate_id: str
    repo_commit: str | None
    workflow: str
    tool: str
    model: str | None = None
    recorded_at: str = Field(default_factory=_now)


class CaseGrade(BaseModel):
    case_id: str
    family: str
    kind: str
    verdict: str  # "pass" | "fail" | "error"
    status_quo_verdict: str | None = None
    detail: str
    provenance_origin: str


class PilotRunResult(BaseModel):
    schema_version: str = SCHEMA_RESULT
    run_id: str
    cases_file: str
    cases_file_hash: str
    lineage: CandidateLineage
    egress_allowed: bool
    semantic_allowed: bool
    grades: list[CaseGrade]
    counts: dict[str, int]
    status_quo_control: str  # "included" | "not_applicable"


class RunContext(BaseModel):
    repo_root: str
    allow_egress: bool = False
    allow_semantic: bool = False


# ---------------------------------------------------------------------------
# Frozen case loading (read-only w.r.t. the case file — never written here)
# ---------------------------------------------------------------------------


def cases_file_hash(cases_path: Path) -> str:
    return _sha256_hex(cases_path.read_bytes())


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def load_cases(cases_path: Path) -> list[dict]:
    """Load and structurally validate the frozen case corpus. Every case
    must declare a supported schema_version, kind, and provenance block —
    a case admitted without full provenance is rejected rather than
    silently run, per the case-admission contract
    (docs/playbooks/eval-pilot-case-admission.md)."""
    cases: list[dict] = []
    for lineno, raw_line in enumerate(cases_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        case = json.loads(line)
        if case.get("schema_version") != SCHEMA_CASE:
            raise ValueError(
                f"{cases_path}:{lineno}: unsupported schema_version "
                f"{case.get('schema_version')!r} (expected {SCHEMA_CASE!r})"
            )
        if case.get("kind") not in _KNOWN_KINDS:
            raise ValueError(f"{cases_path}:{lineno}: unknown kind {case.get('kind')!r}")
        provenance_origin = case.get("provenance", {}).get("origin")
        if provenance_origin not in _KNOWN_ORIGINS:
            raise ValueError(
                f"{cases_path}:{lineno}: case {case.get('case_id')!r} has "
                f"unsupported provenance.origin {provenance_origin!r}"
            )
        provenance = case.get("provenance") or {}
        missing = _REQUIRED_PROVENANCE_FIELDS - provenance.keys()
        if missing:
            raise ValueError(
                f"{cases_path}:{lineno}: case {case.get('case_id')!r} missing "
                f"required provenance field(s): {sorted(missing)}"
            )
        if case.get("grader") not in GRADERS:
            raise ValueError(
                f"{cases_path}:{lineno}: case {case.get('case_id')!r} names unknown "
                f"grader {case.get('grader')!r}"
            )
        cases.append(case)
    return cases


def build_intake_proposal(
    summary: str,
    *,
    origin: str = "reproduced_usage_gap",
    kind: str = "regression",
    diagnosis_ref: str | None = None,
    fix_ref: str | None = None,
    cases_path: Path | None = None,
    admitted_by: str | None = None,
    admitted_at: str | None = None,
    case_id: str | None = None,
    grader: str = "<unassigned>",
) -> dict:
    """Build an explicit content-minimized case intake payload for human review.

    This helper performs no writes and captures only an admission record plus
    optional provenance references.
    """
    if kind not in _KNOWN_KINDS:
        raise ValueError(f"unsupported kind {kind!r}")
    if origin not in _KNOWN_ORIGINS:
        raise ValueError(f"unsupported origin {origin!r}")

    trimmed = " ".join(summary.split())
    if not trimmed:
        raise ValueError("summary must contain at least one non-empty word")

    proposed_case_id = case_id or f"proposed-{_short_hash(trimmed)}"
    is_duplicate_case_id = False
    if cases_path and cases_path.exists():
        try:
            existing_case_ids = {c["case_id"] for c in load_cases(cases_path)}
            is_duplicate_case_id = proposed_case_id in existing_case_ids
        except Exception:
            # Intake can still proceed; the caller can decide whether to proceed
            # once they fix the case file schema.
            is_duplicate_case_id = False

    proposal = {
        "schema_version": SCHEMA_INTAKE_PROPOSAL,
        "case_id": proposed_case_id,
        "family": "regression",
        "kind": kind,
        "provenance": {
            "origin": origin,
            "description": trimmed[:240],
            "diagnosis_ref": diagnosis_ref,
            "fix_ref": fix_ref,
            "admitted_by": admitted_by or "unassigned",
            "admitted_at": admitted_at or _now().split("T", 1)[0],
        },
        "proposed_grader": grader,
        "fixture": {},
        "expected": {},
        "requires_semantic": False,
        "requires_index": False,
        "notes": "human-reviewed repository-local proposal; no raw prompts or private content",
    }
    return {
        "schema_version": SCHEMA_INTAKE_PROPOSAL,
        "intake": proposal,
        "intake_policy": {
            "status": "duplicate_case_id" if is_duplicate_case_id else "proposed",
            "content_minimized": True,
            "captures_prompt_or_private_content": False,
            "auto_placement": False,
        },
    }


def load_prior_run(path: Path) -> PilotRunResult | None:
    """Load a prior PilotRunResult from a JSON artifact path.

    A malformed path is a caller bug and must raise, because compare signals are
    advisory and explicit in this loop.
    """
    if not path.exists():
        raise ValueError(f"{path} does not exist")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    required_keys = {
        "run_id", "counts", "lineage", "cases_file_hash", "cases_file", "schema_version",
    }
    if not required_keys <= set(payload):
        # Some callers may feed a summary-like artifact; fail fast to avoid false
        # confidence.
        raise ValueError(f"{path} does not look like a PilotRunResult")
    return PilotRunResult.model_validate(payload)


def evaluate_progress(
    current: PilotRunResult, previous: PilotRunResult | None
) -> dict[str, object]:
    """Detect stagnation or uncertainty between two frozen runs.

    `current` and `previous` are compared using counts only. `research_needed`
    and `stagnated` are distinct and machine-readable outcomes; neither
    triggers automatic action.
    """
    if previous is None:
        return {
            "outcome": "research_needed",
            "research_needed": True,
            "stagnated": False,
            "reason": "no prior run to compare against",
            "recommended_research": "normal_review",
            "next_step": "run_compare_after_repair",
        }

    current_rate = current.counts["passed"] / max(current.counts["total"], 1)
    previous_rate = previous.counts["passed"] / max(previous.counts["total"], 1)

    if current.counts["errored"] > previous.counts["errored"]:
        return {
            "outcome": "research_needed",
            "research_needed": True,
            "stagnated": False,
            "reason": "errored cases increased",
            "recommended_research": "normal_review",
            "next_step": "isolate_instability",
        }

    if current_rate > previous_rate:
        return {
            "outcome": "improved",
            "research_needed": False,
            "stagnated": False,
            "reason": "pass rate improved",
            "recommended_research": None,
            "next_step": "candidate_readiness_for_review",
        }

    if current_rate < previous_rate:
        return {
            "outcome": "stagnated",
            "research_needed": False,
            "stagnated": True,
            "reason": "pass rate decreased",
            "recommended_research": "gpt_deep_research",
            "next_step": "pause_promotion",
        }

    return {
        "outcome": "stagnated",
        "research_needed": False,
        "stagnated": True,
        "reason": "no measurable change from prior run",
        "recommended_research": "gpt_deep_research",
        "next_step": "add_new_cases",
    }


# ---------------------------------------------------------------------------
# Status-quo control comparator (frozen; never imported by production code)
# ---------------------------------------------------------------------------


def _naive_concatenate_then_slice(item_lists: list[list[dict]], cap: int) -> list[dict]:
    """Pure re-implementation of the PRE-FIX merge strategy
    (`all_items[:_MAX_DISPLAY_ITEMS]` before PR #20), kept here *only* as a
    frozen status-quo-control comparator for this eval pilot.

    This function must never be edited to track a future candidate's
    behavior — doing so would erase the control condition the
    ``cli-axi-provider-starvation-display-quota`` case exists to preserve.
    Production code never imports this function; it always uses
    ``cli_axi._select_display_items``.
    """
    flat = [item for items in item_lists for item in items]
    return flat[:cap]


def _build_synthetic_provider_results(
    provider_item_counts: dict[str, int],
) -> list[axi_providers.ProviderResult]:
    """Synthetic ProviderResult fixtures matching the reproduced starvation
    shape (one alphabetically/scan-early provider with many items,
    others with few) — built in the fixed auto-mode provider order so
    both the candidate and the status-quo comparator see the exact same
    input. Deliberately synthetic rather than derived from live repo
    content, so this case never drifts as prose files are edited."""
    order = axi_providers.MODE_PROVIDERS["auto"]
    results = []
    for name in order:
        count = provider_item_counts.get(name, 0)
        items = [
            axi_providers.EvidenceItem(
                provider=name,
                source=f"synthetic/{name}.txt",
                location=f"L{i + 1}",
                excerpt="synthetic fixture item — not real repository content",
            )
            for i in range(count)
        ]
        results.append(
            axi_providers.ProviderResult(
                provider=name,
                state=axi_providers.ProviderState.OK,
                detail="synthetic fixture",
                route_reason="synthetic fixture",
                items=items,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Graders — one per registered case "grader" name. Each returns a CaseGrade
# and never raises for an ordinary fail (only for a fixture/programming
# error, which run_pilot catches and records as verdict="error").
# ---------------------------------------------------------------------------


def grade_display_quota_case(case: dict, repo_root: Path, ctx: RunContext) -> CaseGrade:
    fixture = case["fixture"]
    expected = case["expected"]
    cap = int(fixture["cap"])

    results = _build_synthetic_provider_results(fixture["provider_item_counts"])

    candidate_displayed = cli_axi._select_display_items(results, cap)
    candidate_providers = {item.provider for item in candidate_displayed}

    status_quo_displayed = _naive_concatenate_then_slice(
        [[item.model_dump() for item in r.items] for r in results], cap
    )
    status_quo_providers = {item["provider"] for item in status_quo_displayed}

    candidate_ok = len(candidate_providers) >= int(expected["candidate_min_distinct_providers"])
    status_quo_ok = len(status_quo_providers) <= int(expected["status_quo_max_distinct_providers"])

    verdict = "pass" if candidate_ok else "fail"
    # The status-quo comparator's own verdict is "pass" when it reproduces
    # the historically-confirmed starvation (<= the expected max distinct
    # providers) — i.e. when it is still genuinely worse than the
    # candidate. If this ever flips, the frozen comparator itself has
    # drifted and no longer serves as a meaningful control.
    status_quo_verdict = "pass" if status_quo_ok else "fail"

    detail = (
        f"candidate displayed {len(candidate_displayed)} items from "
        f"{len(candidate_providers)} distinct provider(s) {sorted(candidate_providers)}; "
        f"status-quo comparator displayed {len(status_quo_displayed)} items from "
        f"{len(status_quo_providers)} distinct provider(s) {sorted(status_quo_providers)}"
    )
    return CaseGrade(
        case_id=case["case_id"],
        family=case["family"],
        kind=case["kind"],
        verdict=verdict,
        status_quo_verdict=status_quo_verdict,
        detail=detail,
        provenance_origin=case["provenance"]["origin"],
    )


def grade_known_dangling_reference_case(case: dict, repo_root: Path, ctx: RunContext) -> CaseGrade:
    fixture = case["fixture"]
    doc_path = fixture["doc_path"]
    expected_token = fixture["expected_dangling_token"]

    full = repo_root / doc_path
    if not full.exists():
        return CaseGrade(
            case_id=case["case_id"],
            family=case["family"],
            kind=case["kind"],
            verdict="error",
            detail=f"fixture document does not exist: {doc_path}",
            provenance_origin=case["provenance"]["origin"],
        )

    _edges, dangling = consistency.extract_exact_references(doc_path, repo_root)
    is_dangling = expected_token in dangling
    verdict = "pass" if is_dangling == bool(case["expected"]["must_be_dangling"]) else "fail"
    return CaseGrade(
        case_id=case["case_id"],
        family=case["family"],
        kind=case["kind"],
        verdict=verdict,
        detail=f"dangling={dangling!r}",
        provenance_origin=case["provenance"]["origin"],
    )


def grade_refresh_then_check_up_to_date(case: dict, repo_root: Path, ctx: RunContext) -> CaseGrade:
    import tempfile

    fixture = case["fixture"]
    expected_status = case["expected"]["status"]

    with tempfile.TemporaryDirectory(prefix="holus-eval-pilot-") as tmp:
        tmp_root = Path(tmp)
        spec_path = tmp_root / "specs" / "001-alpha.md"
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(fixture["spec_body"], encoding="utf-8")
        impl_path = tmp_root / "src" / "pkg" / "mod.py"
        impl_path.parent.mkdir(parents=True, exist_ok=True)
        impl_path.write_text(fixture["impl_body"], encoding="utf-8")

        consistency.refresh(tmp_root)
        report = consistency.check_consistency(tmp_root, "specs/001-alpha.md")

    verdict = "pass" if report.status.value == expected_status else "fail"
    return CaseGrade(
        case_id=case["case_id"],
        family=case["family"],
        kind=case["kind"],
        verdict=verdict,
        detail=f"status={report.status.value!r} notes={report.notes!r}",
        provenance_origin=case["provenance"]["origin"],
    )


def grade_no_egress_default(case: dict, repo_root: Path, ctx: RunContext) -> CaseGrade:
    import os

    expected = case["expected"]
    sentinel = "sk-eval-pilot-sentinel-value"
    saved = os.environ.get("VOYAGE_API_KEY")
    os.environ["VOYAGE_API_KEY"] = sentinel
    try:
        with axi_providers._no_egress_env():
            stripped = "VOYAGE_API_KEY" not in os.environ
        restored = os.environ.get("VOYAGE_API_KEY") == sentinel
    finally:
        if saved is not None:
            os.environ["VOYAGE_API_KEY"] = saved
        else:
            os.environ.pop("VOYAGE_API_KEY", None)

    ok = (
        stripped == bool(expected["key_stripped_without_allow_egress"])
        and restored == bool(expected["key_restored_after_context_exit"])
    )
    verdict = "pass" if ok else "fail"
    return CaseGrade(
        case_id=case["case_id"],
        family=case["family"],
        kind=case["kind"],
        verdict=verdict,
        detail=f"stripped={stripped} restored={restored}",
        provenance_origin=case["provenance"]["origin"],
    )


GRADERS: dict[str, Callable[[dict, Path, RunContext], CaseGrade]] = {
    "grade_display_quota_case": grade_display_quota_case,
    "grade_known_dangling_reference_case": grade_known_dangling_reference_case,
    "grade_refresh_then_check_up_to_date": grade_refresh_then_check_up_to_date,
    "grade_no_egress_default": grade_no_egress_default,
}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_pilot(
    repo_root: Path,
    *,
    cases_path: Path | None = None,
    lineage: CandidateLineage,
    allow_egress: bool = False,
    allow_semantic: bool = False,
) -> PilotRunResult:
    """Grade every frozen case against the current repository state.

    Read-only w.r.t. the case file (never opened for writing) and w.r.t.
    this repository's tracked source — the ``consistency``-backed graders
    operate on synthetic ``tempfile.TemporaryDirectory`` repos, never this
    worktree's own ``.holusight/`` cache.
    """
    cases_path = cases_path or DEFAULT_CASES_PATH
    file_hash = cases_file_hash(cases_path)
    cases = load_cases(cases_path)

    ctx = RunContext(
        repo_root=str(repo_root), allow_egress=allow_egress, allow_semantic=allow_semantic
    )

    grades: list[CaseGrade] = []
    for case in cases:
        if case.get("requires_semantic") and not allow_semantic:
            grades.append(
                CaseGrade(
                    case_id=case["case_id"],
                    family=case["family"],
                    kind=case["kind"],
                    verdict="error",
                    detail="case requires semantic provider; --allow-semantic not set",
                    provenance_origin=case["provenance"]["origin"],
                )
            )
            continue
        grader = GRADERS[case["grader"]]
        try:
            grades.append(grader(case, repo_root, ctx))
        except Exception as exc:  # defensive: a broken fixture is "error", not a crash
            grades.append(
                CaseGrade(
                    case_id=case["case_id"],
                    family=case["family"],
                    kind=case["kind"],
                    verdict="error",
                    detail=f"{type(exc).__name__}: {exc}",
                    provenance_origin=case["provenance"]["origin"],
                )
            )

    counts = {
        "total": len(grades),
        "passed": sum(1 for g in grades if g.verdict == "pass"),
        "failed": sum(1 for g in grades if g.verdict == "fail"),
        "errored": sum(1 for g in grades if g.verdict == "error"),
        "comparative_total": sum(1 for g in grades if g.kind == "comparative"),
        "comparative_with_status_quo_verdict": sum(
            1 for g in grades if g.kind == "comparative" and g.status_quo_verdict is not None
        ),
    }
    status_quo_control = (
        "included" if counts["comparative_total"] > 0 else "not_applicable"
    )

    return PilotRunResult(
        run_id=f"eval-pilot-{lineage.candidate_id}-{_now()}",
        cases_file=str(cases_path),
        cases_file_hash=file_hash,
        lineage=lineage,
        egress_allowed=allow_egress,
        semantic_allowed=allow_semantic,
        grades=grades,
        counts=counts,
        status_quo_control=status_quo_control,
    )


# ---------------------------------------------------------------------------
# Fleet v1.2 aggregate export (content-free — counts/rates only)
# ---------------------------------------------------------------------------


def build_pilot_aggregate_scorecard(
    result: PilotRunResult,
    *,
    repo: str,
    repo_commit: str,
) -> dict:
    """Shape one :class:`PilotRunResult` into a content-free
    ``fleet.eval_scorecard.v1.2``-shaped aggregate: counts and rates only —
    no case questions, no excerpts, no file paths beyond this repo's own
    identity. Mirrors ``fleet_scorecard.build_eval_scorecard``'s honesty
    conventions (see that module's docstring) for a second, independent
    domain evaluator."""
    total = result.counts["total"] or 1  # guard divide-by-zero; total is always >=1 in practice
    pass_rate = result.counts["passed"] / total
    no_regressions = result.counts["failed"] == 0 and result.counts["errored"] == 0
    gate_decision = "pass" if no_regressions else "fail"
    hidden_status = "pass" if gate_decision == "pass" else "fail"

    result_payload = result.model_dump(mode="json")
    result_hash = _sha256_hex(json.dumps(result_payload, sort_keys=True).encode("utf-8"))
    input_hash = _sha256_hex(f"{result.cases_file_hash}:{repo_commit}".encode("utf-8"))

    return {
        "schema": SCHEMA_PILOT_SCORECARD,
        "repo": repo,
        "scorecard_id": f"sc-{result.run_id}",
        "trace_id": f"trace-{result.run_id}",
        "rubric_id": "holusight-eval-pilot-v1",
        "scores": {
            "cases_total": result.counts["total"],
            "cases_passed": result.counts["passed"],
            "cases_failed": result.counts["failed"],
            "cases_errored": result.counts["errored"],
            "pass_rate": round(pass_rate, 4),
            "comparative_cases_total": result.counts["comparative_total"],
            "status_quo_control": result.status_quo_control,
        },
        "gate_decision": gate_decision,
        "input_hash": input_hash,
        "fixture_set_hash": result.cases_file_hash,
        "result_hash": result_hash,
        "evaluator_version": "codesight-eval-pilot/1",
        "repo_commit": repo_commit,
        "environment": {
            "egress_allowed": result.egress_allowed,
            "semantic_allowed": result.semantic_allowed,
        },
        "cross_project_metrics": {
            "hidden_correctness": {
                "status": hidden_status,
                "source": "domain_evaluator",
                "detail": (
                    f"{result.counts['passed']}/{result.counts['total']} frozen eval-pilot "
                    "cases passed; advisory only, no autonomous promotion"
                ),
            },
            "time_to_correct_result_seconds": None,
            "human_correction_burden": {"note": "not tracked by this pilot"},
            "regressions": result.counts["failed"],
            "total_cost_usd": 0.0,
            "handoff_loss": {"occurred": False},
            "fallbacks": 0,
            "operational_failures": result.counts["errored"],
        },
        "diagnostics": {"completion": True},
        "artifacts": {},
        "provenance": {
            "fleet_contract_repo": FLEET_CONTRACT_REPO,
            "fleet_contract_commit": FLEET_CONTRACT_COMMIT,
            "fleet_contract_pr": FLEET_CONTRACT_PR,
        },
    }


def pilot_domain_result_summary(result: PilotRunResult) -> dict:
    """The minimal dict ``run_repo_eval.py``'s ``parse_domain_result()``
    expects as an entrypoint command's last stdout line — see
    ``fleet_scorecard.domain_result_summary`` for the landed precedent this
    mirrors. Not currently wired as ``agentic/manifest.yaml``'s
    ``eval_entrypoint`` (still ``just fleet-smoke``, unchanged)."""
    status = "pass" if result.counts["failed"] == 0 and result.counts["errored"] == 0 else "fail"
    return {
        "hidden_correctness": {
            "status": status,
            "source": "domain_evaluator",
            "detail": (
                f"eval-pilot: {result.counts['passed']}/{result.counts['total']} "
                "frozen cases passed (advisory only)"
            ),
        },
        "scores": {
            "cases_total": result.counts["total"],
            "cases_passed": result.counts["passed"],
            "cases_failed": result.counts["failed"],
            "cases_errored": result.counts["errored"],
        },
        "human_correction_burden": {},
        "regressions": result.counts["failed"],
        "total_cost_usd": 0.0,
        "handoff_loss": {"occurred": False},
    }


# ---------------------------------------------------------------------------
# CLI: `python -m codesight.eval_pilot run`
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(prog="python -m codesight.eval_pilot")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run the frozen eval-pilot case corpus")
    run_p.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    run_p.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    run_p.add_argument("--output", type=Path, default=None)
    run_p.add_argument("--candidate-id", default="current-worktree")
    run_p.add_argument("--workflow", default="manual")
    run_p.add_argument("--tool", default="eval_pilot-cli")
    run_p.add_argument("--model", default=None)
    run_p.add_argument("--allow-egress", action="store_true")
    run_p.add_argument("--allow-semantic", action="store_true")
    run_p.add_argument(
        "--scorecard",
        action="store_true",
        help="Also print the Fleet aggregate scorecard preview",
    )

    args = parser.parse_args(argv)
    if args.command != "run":
        parser.print_help(sys.stderr)
        return 2

    from .git_utils import current_commit, is_git_repo

    repo_root = args.repo_root.resolve()
    commit = current_commit(repo_root) if is_git_repo(repo_root) else None

    lineage = CandidateLineage(
        candidate_id=args.candidate_id,
        repo_commit=commit,
        workflow=args.workflow,
        tool=args.tool,
        model=args.model,
    )

    result = run_pilot(
        repo_root,
        cases_path=args.cases,
        lineage=lineage,
        allow_egress=args.allow_egress,
        allow_semantic=args.allow_semantic,
    )

    payload = result.model_dump(mode="json")
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n")
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(text)

    if args.scorecard:
        scorecard = build_pilot_aggregate_scorecard(
            result, repo="holusight", repo_commit=commit or "unknown"
        )
        print(json.dumps(scorecard, indent=2, sort_keys=True))

    summary = pilot_domain_result_summary(result)
    print(json.dumps(summary, sort_keys=True))

    return 0 if summary["hidden_correctness"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
