"""E2E regressions for the controlled evidence-routing variation program."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from codesight import retrieval_variation

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_baseline_and_benchmark_are_content_addressed_and_all_case_families_run():
    result = retrieval_variation.run_program(REPO_ROOT)
    assert result["program"]["benchmark_hash"].startswith("sha256:")
    assert result["program"]["source_fixture_hashes"]
    assert result["program"]["evaluator_digest"].startswith("sha256:")
    assert result["baseline"]["candidate"]["candidate_id"] == "baseline-legacy-concatenate-v1"
    families = {grade["family"] for grade in result["baseline"]["case_outcomes"]}
    assert families == {
        "exact", "hybrid", "graph_impact", "ambiguity", "no_evidence", "adversarial"
    }


def test_two_fixed_candidates_have_lineage_and_hard_constraints_are_separate_from_reward():
    result = retrieval_variation.run_program(REPO_ROOT)
    assert len(result["candidates"]) == 2
    for candidate in result["candidates"]:
        evaluation = candidate["evaluation"]
        assert evaluation["candidate"]["definition_hash"].startswith("sha256:")
        assert "hard_constraints" in evaluation
        assert "reward" in evaluation
        assert evaluation["reward"]["primary_metric"] == "mean_required_provider_coverage"
    winner, rejected = result["candidates"]
    assert winner["verdict"]["hard_constraints_pass"] is True
    assert rejected["verdict"]["hard_constraints_pass"] is False
    rejected_constraints = {
        item
        for grade in rejected["evaluation"]["case_outcomes"]
        for item in grade["hard_constraints"]
    }
    assert "available_capacity_unused" in rejected_constraints


def test_adversarial_provider_flood_is_fixed_only_by_candidate_and_baseline_stays_immutable():
    result = retrieval_variation.run_program(REPO_ROOT)
    baseline = next(
        grade
        for grade in result["baseline"]["case_outcomes"]
        if grade["case_id"] == "adversarial-provider-flood"
    )
    candidate = next(
        grade
        for grade in result["candidates"][0]["evaluation"]["case_outcomes"]
        if grade["case_id"] == "adversarial-provider-flood"
    )
    assert "required_provider_hidden" in baseline["hard_constraints"]
    assert candidate["hard_constraints"] == []
    baseline_identity = retrieval_variation._strategy_identity(retrieval_variation.BASELINE)
    baseline_hash = result["baseline"]["candidate"]["definition_hash"]
    assert baseline_hash == baseline_identity["definition_hash"]


def test_failed_and_inconclusive_outcomes_are_retained_and_never_promote():
    result = retrieval_variation.run_program(REPO_ROOT)
    statuses = {candidate["verdict"]["status"] for candidate in result["candidates"]}
    assert "inconclusive" in statuses
    first_verdict = result["candidates"][0]["verdict"]
    assert first_verdict["paired_sign_test_p_value"] >= 0.05
    assert "insufficient_paired_statistical_evidence" in first_verdict["reasons"]
    assert result["promotion"]["allowed"] is False
    for candidate in result["candidates"]:
        assert candidate["verdict"]["promotion"]["allowed"] is False
        assert candidate["verdict"]["promotion"]["candidate_self_promotion"] == "denied"


def test_invalid_or_tampered_or_partial_result_cannot_count_as_improvement():
    result = retrieval_variation.run_program(REPO_ROOT)
    tampered = json.loads(json.dumps(result))
    tampered["candidates"] = tampered["candidates"][:1]
    with pytest.raises(ValueError, match="digest"):
        retrieval_variation.validate_result(tampered)

    unknown = json.loads(json.dumps(result))
    unknown["untrusted_inferred_field"] = True
    unknown["result_digest"] = retrieval_variation._canonical_hash(
        {key: value for key, value in unknown.items() if key != "result_digest"}
    )
    with pytest.raises(ValueError, match="unsupported"):
        retrieval_variation.validate_result(unknown)

    partial = json.loads(json.dumps(result))
    partial["candidates"] = partial["candidates"][:1]
    partial["result_digest"] = retrieval_variation._canonical_hash(
        {key: value for key, value in partial.items() if key != "result_digest"}
    )
    with pytest.raises(ValueError, match="partial"):
        retrieval_variation.validate_result(partial)


def test_recording_preserves_failures_under_safe_derived_state_and_rejects_symlink(tmp_path):
    result = retrieval_variation.run_program(REPO_ROOT)
    record = retrieval_variation.record_run(REPO_ROOT, result)
    try:
        payload = json.loads((REPO_ROOT / record).read_text(encoding="utf-8"))
        assert any(item["status"] == "inconclusive" for item in payload["candidate_outcomes"])
    finally:
        (REPO_ROOT / record).unlink(missing_ok=True)

    root = tmp_path / "repo"
    root.mkdir()
    (root / ".holusight").symlink_to(tmp_path / "outside", target_is_directory=True)
    with pytest.raises(ValueError, match="unsafe"):
        retrieval_variation.record_run(root, result)


def test_feedback_is_aggregate_privacy_safe_and_review_only():
    feedback = retrieval_variation.build_feedback_proposal("failure_case", 2)
    assert feedback["review_queue"]["raw_prompt_retained"] is False
    assert feedback["review_queue"]["canonical_truth_changed"] is False
    assert feedback["privacy"]["external_egress"] == "denied"
    with pytest.raises(ValueError):
        retrieval_variation.build_feedback_proposal("raw_prompt", 1)


def test_public_operator_run_is_local_and_reports_no_automatic_promotion():
    completed = subprocess.run(
        [sys.executable, "-m", "codesight.cli_axi", "improve-variation-run", "--format", "json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["program"]["external_egress"] == "denied"
    assert result["promotion"]["allowed"] is False


def test_public_feedback_command_is_aggregate_only_and_schema_registered():
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "codesight.cli_axi",
            "improve-variation-feedback",
            "--signal",
            "failure_case",
            "--count",
            "2",
            "--format",
            "json",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["review_queue"]["canonical_truth_changed"] is False
