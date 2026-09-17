"""Unit tests for advisory proper-eval orchestration."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from codesight import proper_eval
from codesight.eval_pilot import (
    CandidateLineage,
    CaseGrade,
    EvaluationSubject,
    PilotRunResult,
    ResultCounts,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _pilot(*, failed: int = 0, errored: int = 0, total: int = 4) -> PilotRunResult:
    passed = total - failed - errored
    grades = [
        CaseGrade(
            case_id=f"c{i}",
            family="regression",
            kind="regression",
            verdict="pass" if i < passed else ("error" if errored and i >= passed + failed else "fail"),
            detail="t",
            provenance_origin="spec_documented_contract",
        )
        for i in range(total)
    ]
    # simplify: one grade reflecting aggregate
    grades = [
        CaseGrade(
            case_id="c0",
            family="regression",
            kind="regression",
            verdict="pass" if failed == 0 and errored == 0 else "fail",
            detail="t",
            provenance_origin="spec_documented_contract",
        )
    ]
    return PilotRunResult(
        run_id="test",
        cases_file="tests/fixtures/holusight_eval_pilot_cases.jsonl",
        cases_file_hash="0" * 64,
        lineage=CandidateLineage(
            candidate_id="t",
            repo_commit="a" * 40,
            workflow="test",
            tool="test",
        ),
        subject=EvaluationSubject(
            repository_id="local-no-remote",
            commit="a" * 40,
            tree="b" * 40,
            clean=True,
        ),
        egress_allowed=False,
        semantic_allowed=False,
        grades=grades,
        counts=ResultCounts(
            total=total,
            passed=passed,
            failed=failed,
            errored=errored,
            comparative_total=0,
            comparative_with_status_quo_verdict=0,
        ),
        status_quo_control="not_applicable",
    )


def test_aggregate_pass_when_surfaces_ok_and_subject_clean():
    subject = EvaluationSubject(
        repository_id="local-no-remote",
        commit="a" * 40,
        tree="b" * 40,
        clean=True,
    )
    with (
        mock.patch.object(proper_eval, "_current_subject", return_value=subject),
        mock.patch.object(proper_eval, "_run_smoke_suite", return_value=(0, {"passed": 20, "failed": 0, "errors": 0})),
        mock.patch.object(proper_eval, "run_pilot", return_value=_pilot()),
    ):
        payload = proper_eval.run_proper_eval(REPO_ROOT, skip_smoke=False)
    assert payload["verdict"] == "pass"
    assert payload["promotion"]["allowed"] is False
    assert payload["judge"]["selectable_by_candidate"] is False
    assert payload["hidden_holdout"]["scored"] is False


def test_aggregate_block_when_pilot_fails():
    subject = EvaluationSubject(
        repository_id="local-no-remote",
        commit="a" * 40,
        tree="b" * 40,
        clean=True,
    )
    with (
        mock.patch.object(proper_eval, "_current_subject", return_value=subject),
        mock.patch.object(proper_eval, "_run_smoke_suite", return_value=(0, {"passed": 20, "failed": 0, "errors": 0})),
        mock.patch.object(proper_eval, "run_pilot", return_value=_pilot(failed=1)),
    ):
        payload = proper_eval.run_proper_eval(REPO_ROOT)
    assert payload["verdict"] == "block"


def test_aggregate_indeterminate_when_dirty_subject():
    subject = EvaluationSubject(
        repository_id="local-no-remote",
        commit="a" * 40,
        tree="b" * 40,
        clean=False,
    )
    with (
        mock.patch.object(proper_eval, "_current_subject", return_value=subject),
        mock.patch.object(proper_eval, "_run_smoke_suite", return_value=(0, {"passed": 20, "failed": 0, "errors": 0})),
        mock.patch.object(proper_eval, "run_pilot", return_value=_pilot()),
    ):
        payload = proper_eval.run_proper_eval(REPO_ROOT)
    assert payload["verdict"] == "indeterminate"
    assert payload["promotion"]["allowed"] is False


def test_judge_is_pinned_module():
    subject = EvaluationSubject(
        repository_id="local-no-remote",
        commit="a" * 40,
        tree="b" * 40,
        clean=True,
    )
    with (
        mock.patch.object(proper_eval, "_current_subject", return_value=subject),
        mock.patch.object(proper_eval, "run_pilot", return_value=_pilot()),
    ):
        payload = proper_eval.run_proper_eval(REPO_ROOT, skip_smoke=True)
    assert payload["judge"]["id"] == proper_eval.JUDGE_ID
    assert payload["judge"]["digest"].startswith("sha256:")
