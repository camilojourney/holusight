"""Unit tests for src/codesight/fleet_scorecard.py.

Complements tests/test_fleet_smoke.py (the Fleet v1.2 no-spend smoke
suite, which exercises the four consistency outcomes end to end via
synthetic repos). This file covers the module's own contract in
isolation: hash determinism, id/environment defaults, and the exact
minimal shape `domain_result_summary()` must produce.
"""

from __future__ import annotations

import re

from codesight import consistency
from codesight.fleet_scorecard import (
    FLEET_CONTRACT_COMMIT,
    FLEET_CONTRACT_PR,
    FLEET_CONTRACT_REPO,
    SCHEMA_EVAL_SCORECARD,
    SCORECARD_ELIGIBLE_STATUSES,
    build_eval_scorecard,
    domain_result_summary,
)

_COMMIT = "abc123def4567890abc123def4567890abc123d"


def _report(status: consistency.ConsistencyStatus) -> consistency.ConsistencyReport:
    return consistency.ConsistencyReport(
        concept_id="specs/001-alpha.md",
        status=status,
        canonical_changed=False,
        linked_changed=[],
        linked_unchanged=["src/pkg/mod.py"],
        notes="synthetic",
    )


def test_provenance_constants_are_the_exact_landed_commit():
    """These constants are what makes the scorecard's provenance claim
    checkable -- pin them to the exact values recorded in
    docs/decisions/0012-fleet-v1.2-protocol-wiring.md and
    specs/016-fleet-v1.2-protocol-pilot.md, so a future accidental edit to
    one and not the other is caught by a diff, not silently."""
    assert FLEET_CONTRACT_REPO == "github.com/camilojourney/fleet-system"
    assert FLEET_CONTRACT_COMMIT == "7d396b30f0250a414f9115964c945e29b7afb267"
    assert FLEET_CONTRACT_PR == "https://github.com/camilojourney/fleet-system/pull/58"


def test_scorecard_eligible_statuses_is_exactly_the_four_outcomes():
    assert SCORECARD_ELIGIBLE_STATUSES == {
        consistency.ConsistencyStatus.UP_TO_DATE,
        consistency.ConsistencyStatus.SPEC_CHANGED_AWAITING_IMPLEMENTATION,
        consistency.ConsistencyStatus.POSSIBLE_UNDOCUMENTED_DRIFT,
        consistency.ConsistencyStatus.COORDINATED_CHANGE,
    }
    assert consistency.ConsistencyStatus.UNKNOWN_CONCEPT not in SCORECARD_ELIGIBLE_STATUSES


def test_build_eval_scorecard_default_environment_reports_python_version():
    scorecard = build_eval_scorecard(
        _report(consistency.ConsistencyStatus.UP_TO_DATE), repo="r", repo_commit=_COMMIT
    )
    assert "python" in scorecard["environment"]
    assert all(isinstance(v, str) for v in scorecard["environment"].values())


def test_build_eval_scorecard_custom_environment_is_passed_through():
    scorecard = build_eval_scorecard(
        _report(consistency.ConsistencyStatus.UP_TO_DATE),
        repo="r",
        repo_commit=_COMMIT,
        environment={"python": "3.99", "os": "test-fixture"},
    )
    assert scorecard["environment"] == {"python": "3.99", "os": "test-fixture"}


def test_build_eval_scorecard_ids_are_unique_when_not_supplied():
    a = build_eval_scorecard(
        _report(consistency.ConsistencyStatus.UP_TO_DATE), repo="r", repo_commit=_COMMIT
    )
    b = build_eval_scorecard(
        _report(consistency.ConsistencyStatus.UP_TO_DATE), repo="r", repo_commit=_COMMIT
    )
    assert a["scorecard_id"] != b["scorecard_id"]
    assert a["trace_id"] != b["trace_id"]
    # But content-derived hashes for the identical report are equal.
    assert a["result_hash"] == b["result_hash"]
    assert a["input_hash"] == b["input_hash"]


def test_build_eval_scorecard_ids_honor_explicit_override():
    scorecard = build_eval_scorecard(
        _report(consistency.ConsistencyStatus.UP_TO_DATE),
        repo="r",
        repo_commit=_COMMIT,
        scorecard_id="sc-fixed",
        trace_id="trace-fixed",
    )
    assert scorecard["scorecard_id"] == "sc-fixed"
    assert scorecard["trace_id"] == "trace-fixed"


def test_build_eval_scorecard_evaluator_version_defaults_to_installed_package():
    scorecard = build_eval_scorecard(
        _report(consistency.ConsistencyStatus.UP_TO_DATE), repo="r", repo_commit=_COMMIT
    )
    assert scorecard["evaluator_version"].startswith("codesight-consistency/")


def test_build_eval_scorecard_schema_string_is_exact():
    scorecard = build_eval_scorecard(
        _report(consistency.ConsistencyStatus.UP_TO_DATE), repo="r", repo_commit=_COMMIT
    )
    assert scorecard["schema"] == "fleet.eval_scorecard.v1.2"
    assert SCHEMA_EVAL_SCORECARD == "fleet.eval_scorecard.v1.2"


def test_domain_result_summary_exact_minimal_shape():
    """Matches run_repo_eval.py's parse_domain_result() contract exactly:
    an optional hidden_correctness, an optional scores, and any of
    human_correction_burden/regressions/total_cost_usd/handoff_loss --
    nothing else."""
    summary = domain_result_summary(
        hidden_correctness_status="fail", detail="d", scores={"x": 1}
    )
    assert set(summary) == {
        "hidden_correctness",
        "scores",
        "human_correction_burden",
        "regressions",
        "total_cost_usd",
        "handoff_loss",
    }
    assert set(summary["hidden_correctness"]) == {"status", "source", "detail"}
    assert summary["hidden_correctness"]["source"] == "domain_evaluator"


def test_domain_result_summary_regressions_and_cost_are_zero_by_construction():
    summary = domain_result_summary(hidden_correctness_status="pass", detail="d", scores={})
    assert summary["regressions"] == 0
    assert summary["total_cost_usd"] == 0.0
    assert summary["handoff_loss"] == {"occurred": False}


def test_result_hash_changes_when_report_notes_differ():
    """result_hash is a genuine digest of the report content, not a
    constant -- two reports differing only in `notes` must hash
    differently."""
    r1 = _report(consistency.ConsistencyStatus.UP_TO_DATE)
    r2 = r1.model_copy(update={"notes": "different notes"})
    s1 = build_eval_scorecard(r1, repo="r", repo_commit=_COMMIT)
    s2 = build_eval_scorecard(r2, repo="r", repo_commit=_COMMIT)
    assert s1["result_hash"] != s2["result_hash"]


def test_hash_fields_are_real_sha256_not_truncated():
    """Distinguishes this Fleet-facing full-64-hex sha256 convention from
    this repo's own internal sha256[:16] content-hash convention
    (ARCHITECTURE.md's content-hash invariant) -- they are different
    conventions for different consumers, not a violation of either."""
    scorecard = build_eval_scorecard(
        _report(consistency.ConsistencyStatus.UP_TO_DATE), repo="r", repo_commit=_COMMIT
    )
    for field in ("input_hash", "fixture_set_hash", "result_hash"):
        digest = scorecard[field].removeprefix("sha256:")
        assert len(digest) == 64
        assert re.fullmatch(r"[0-9a-f]{64}", digest)
