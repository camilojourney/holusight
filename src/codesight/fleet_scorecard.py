"""Fleet v1.2 agentic-contract scorecard bridge for the Holusight-AXI
documentation-code consistency evaluator (see ``consistency.py``, Phase 1).

This module is a *document producer*, not the contracts themselves. The
canonical JSON Schemas any document built here must validate against, the
responsibility-boundary ADR that governs them, and the runner that consumes
a repo's ``agentic/manifest.yaml`` all live outside this repository:

    github.com/camilojourney/fleet-system @ 7d396b30f0250a414f9115964c945e29b7afb267
    system/shared/contracts/agentic/{eval-scorecard,agent-trace,repo-agent-manifest}.schema.json
    system/shared/contracts/agentic/ADR-001-fleet-responsibility-boundary.md
    system/shared/scripts/run_repo_eval.py
    PR: https://github.com/camilojourney/fleet-system/pull/58

Holusight does not vendor a copy of those schemas. See
``specs/016-fleet-v1.2-protocol-pilot.md`` and
``docs/decisions/0012-fleet-v1.2-protocol-wiring.md`` for the full
provenance chain and scope.

Two distinct outputs, matching two distinct consumers
------------------------------------------------------

1. :func:`build_eval_scorecard` — a full ``fleet.eval_scorecard.v1.2``-shaped
   document for one :class:`~codesight.consistency.ConsistencyReport`. This
   is Holusight's own, locally computed preview of what that report would
   look like normalized into Fleet's envelope. It is **not** what Fleet's
   ``run_repo_eval.py`` currently emits: as of the commit pinned above,
   ``run_repo_eval.py`` accepts a ``fleet.repo_agent_manifest.v1.2``
   manifest as input but still hardcodes ``"schema":
   "fleet.eval_scorecard.v1.1"`` on its own output (v1.2 output emission is
   documented there as deferred Fleet-side work). This function is honest
   about that gap: it is a demonstration of correct v1.2 shaping, not a
   claim that Fleet's runner already produces this.

2. :func:`domain_result_summary` — the minimal dict
   ``run_repo_eval.py``'s own ``parse_domain_result()`` actually looks for
   today: the *last non-blank line* of ``eval_entrypoint.command``'s stdout,
   parsed as one JSON object with an optional ``hidden_correctness``, an
   optional ``scores``, and any of ``human_correction_burden``,
   ``regressions``, ``total_cost_usd``, ``handoff_loss``. This is what
   ``agentic/manifest.yaml``'s declared entrypoint (``just fleet-smoke``)
   actually prints, via :func:`main`.

Only ``exact`` and ``structural`` consistency providers are exercised by
anything in this module or by ``tests/test_fleet_smoke.py``. The
``semantic`` provider stays opt-in-only, unchanged, and is never invoked
here — this module makes no network calls and costs nothing to run.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import subprocess
import sys
import uuid
from pathlib import Path

from .consistency import ConsistencyReport, ConsistencyStatus

# ---------------------------------------------------------------------------
# Provenance constants (pointers only -- never a copy of the schema itself)
# ---------------------------------------------------------------------------

FLEET_CONTRACT_REPO = "github.com/camilojourney/fleet-system"
FLEET_CONTRACT_COMMIT = "7d396b30f0250a414f9115964c945e29b7afb267"
FLEET_CONTRACT_PR = "https://github.com/camilojourney/fleet-system/pull/58"

SCHEMA_EVAL_SCORECARD = "fleet.eval_scorecard.v1.2"

# ---------------------------------------------------------------------------
# Honest outcome -> (gate_decision, hidden_correctness.status) mapping
# ---------------------------------------------------------------------------
#
# check_consistency() is explicit that it performs "deterministic
# hash-diffing, not semantic value comparison": it reports THAT something
# changed since the cache's last refresh, not WHETHER the content is still
# semantically consistent. Only UP_TO_DATE is a claim this evaluator can
# actually stand behind ("nothing changed; the cache still matches disk"),
# so only that outcome maps to "pass". POSSIBLE_UNDOCUMENTED_DRIFT is the
# one outcome this evaluator is specifically designed to catch, so it maps
# to "fail". The other two outcomes mean a change happened but this
# evaluator has no semantic power to confirm the result still agrees --
# "hold", not "pass", is the honest verdict.

_GATE_BY_STATUS: dict[ConsistencyStatus, str] = {
    ConsistencyStatus.UP_TO_DATE: "pass",
    ConsistencyStatus.SPEC_CHANGED_AWAITING_IMPLEMENTATION: "hold",
    ConsistencyStatus.POSSIBLE_UNDOCUMENTED_DRIFT: "fail",
    ConsistencyStatus.COORDINATED_CHANGE: "hold",
}

_HIDDEN_CORRECTNESS_BY_STATUS: dict[ConsistencyStatus, str] = {
    ConsistencyStatus.UP_TO_DATE: "pass",
    ConsistencyStatus.SPEC_CHANGED_AWAITING_IMPLEMENTATION: "unknown",
    ConsistencyStatus.POSSIBLE_UNDOCUMENTED_DRIFT: "fail",
    ConsistencyStatus.COORDINATED_CHANGE: "unknown",
}

# The four outcomes this bridge covers. ConsistencyStatus.UNKNOWN_CONCEPT is
# a fifth, guard-only value returned when a concept_id isn't cached at all
# -- there is nothing to evaluate, so it deliberately has no scorecard.
SCORECARD_ELIGIBLE_STATUSES = frozenset(_GATE_BY_STATUS)


def _sha256_hex(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _package_version() -> str:
    try:
        from importlib.metadata import version

        return version("codesight")
    except Exception:  # pragma: no cover - defensive; package always installed in dev/test
        return "0.0.0-unknown"


def build_eval_scorecard(
    report: ConsistencyReport,
    *,
    repo: str,
    repo_commit: str,
    evaluator_version: str | None = None,
    environment: dict[str, str] | None = None,
    scorecard_id: str | None = None,
    trace_id: str | None = None,
    rubric_id: str = "holusight-axi-consistency-v1",
) -> dict:
    """Shape one :class:`ConsistencyReport` into a
    ``fleet.eval_scorecard.v1.2``-shaped document.

    Raises ``ValueError`` for ``ConsistencyStatus.UNKNOWN_CONCEPT`` -- that
    status means the concept was never cached, so there is no consistency
    verdict to report and building a scorecard for it would be fabricating
    one.

    ``scores`` carries only what this repo's own evaluator actually
    computed (the consistency status and which artifacts changed) --
    nothing here invents a numeric quality score this evaluator did not
    measure. ``artifacts`` is left empty: this evaluator produces no
    OpenTelemetry trace, SARIF findings, in-toto/SLSA attestation, or SPDX
    SBOM, and this function does not pretend otherwise.
    """
    if report.status not in SCORECARD_ELIGIBLE_STATUSES:
        raise ValueError(
            f"{report.status.value!r} is not one of the four scorecard-eligible "
            "consistency outcomes (up_to_date, spec_changed_awaiting_implementation, "
            "possible_undocumented_drift, coordinated_change); UNKNOWN_CONCEPT means "
            "the concept was never cached, so there is nothing to build a scorecard for."
        )

    gate_decision = _GATE_BY_STATUS[report.status]
    hidden_status = _HIDDEN_CORRECTNESS_BY_STATUS[report.status]

    result_payload = report.model_dump(mode="json")
    result_hash = _sha256_hex(
        json.dumps(result_payload, sort_keys=True).encode("utf-8")
    )
    input_hash = _sha256_hex(f"{report.concept_id}:{repo_commit}".encode("utf-8"))
    fixture_set_hash = _sha256_hex(
        json.dumps(
            sorted({report.concept_id, *report.linked_changed, *report.linked_unchanged}),
            sort_keys=True,
        ).encode("utf-8")
    )

    env = dict(environment) if environment else {"python": platform.python_version()}

    hidden_correctness = {
        "status": hidden_status,
        "source": "domain_evaluator",
        "detail": report.notes,
    }

    return {
        "schema": SCHEMA_EVAL_SCORECARD,
        "repo": repo,
        "scorecard_id": scorecard_id or f"sc-{uuid.uuid4().hex}",
        "trace_id": trace_id or f"trace-{uuid.uuid4().hex}",
        "rubric_id": rubric_id,
        "scores": {
            "consistency_status": report.status.value,
            "canonical_changed": report.canonical_changed,
            "linked_changed_count": len(report.linked_changed),
            "linked_unchanged_count": len(report.linked_unchanged),
        },
        "gate_decision": gate_decision,
        "input_hash": input_hash,
        "fixture_set_hash": fixture_set_hash,
        "result_hash": result_hash,
        "evaluator_version": evaluator_version or f"codesight-consistency/{_package_version()}",
        "repo_commit": repo_commit,
        "environment": env,
        "cross_project_metrics": {
            "hidden_correctness": hidden_correctness,
            # Not applicable: this is a single deterministic detection pass,
            # not a fix-and-measure loop. Null, not a fabricated number.
            "time_to_correct_result_seconds": None,
            "human_correction_burden": {
                "note": "not tracked by the exact/structural consistency evaluator",
            },
            # This evaluator holds no persistent cross-run regression
            # ledger (single-shot exact/structural checks); 0 is a
            # structural default, not a verified claim that nothing
            # regressed since a prior run.
            "regressions": 0,
            # Genuinely zero: exact/structural providers make no API calls.
            "total_cost_usd": 0.0,
            "handoff_loss": {"occurred": False},
            "fallbacks": 0,
            "operational_failures": 0,
        },
        "diagnostics": {"completion": True},
        # No OTel trace, SARIF findings, in-toto/SLSA attestation, or SPDX
        # SBOM is produced by this evaluator. An empty object is honest;
        # inventing a reference to a file that doesn't exist would not be.
        "artifacts": {},
    }


def domain_result_summary(
    *, hidden_correctness_status: str, detail: str, scores: dict
) -> dict:
    """The minimal dict ``run_repo_eval.py``'s ``parse_domain_result()``
    expects as the entrypoint command's last stdout line.

    Deliberately excludes ``pr_created``/``self_reported_success``/
    ``completion``/``output_bytes`` — those are diagnostics-only fields on
    Fleet's side (``run_repo_eval.py`` computes them itself from the
    subprocess outcome) and this repo's own non-negotiable clause forbids
    using them as a correctness input.
    """
    return {
        "hidden_correctness": {
            "status": hidden_correctness_status,
            "source": "domain_evaluator",
            "detail": detail,
        },
        "scores": scores,
        "human_correction_burden": {},
        "regressions": 0,
        "total_cost_usd": 0.0,
        "handoff_loss": {"occurred": False},
    }


# ---------------------------------------------------------------------------
# `just fleet-smoke` entrypoint: runs the no-spend smoke suite, then prints
# the domain-result JSON summary as the last stdout line.
# ---------------------------------------------------------------------------

_SUMMARY_RE = re.compile(r"(\d+) passed|(\d+) failed|(\d+) error")


def _run_smoke_suite() -> tuple[int, dict[str, int]]:
    """Run tests/test_fleet_smoke.py in a subprocess and return
    (returncode, {"passed": n, "failed": n, "errors": n})."""
    repo_root = Path(__file__).resolve().parents[2]
    smoke_path = repo_root / "tests" / "test_fleet_smoke.py"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(smoke_path), "-q", "--no-header"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=280,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)

    counts = {"passed": 0, "failed": 0, "errors": 0}
    for line in result.stdout.splitlines():
        for match in _SUMMARY_RE.finditer(line):
            passed, failed, errors = match.groups()
            if passed:
                counts["passed"] += int(passed)
            elif failed:
                counts["failed"] += int(failed)
            elif errors:
                counts["errors"] += int(errors)
    return result.returncode, counts


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] != "smoke":
        print(
            "usage: python -m codesight.fleet_scorecard smoke",
            file=sys.stderr,
        )
        return 2

    returncode, counts = _run_smoke_suite()
    status = "pass" if returncode == 0 else "fail"
    summary = domain_result_summary(
        hidden_correctness_status=status,
        detail=(
            "tests/test_fleet_smoke.py (exact+structural providers only, no network) "
            f"exit_code={returncode}"
        ),
        scores={
            "smoke_suite": "tests/test_fleet_smoke.py",
            "smoke_tasks_passed": counts["passed"],
            "smoke_tasks_failed": counts["failed"],
            "smoke_tasks_errored": counts["errors"],
        },
    )
    # The one required contract: last non-blank stdout line is a single
    # JSON object. Nothing after this line.
    print(json.dumps(summary, sort_keys=True))
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
