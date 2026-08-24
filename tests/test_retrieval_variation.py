"""E2E regressions for the controlled evidence-routing variation program."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from codesight import cli_axi, improvement_control, retrieval_variation

REPO_ROOT = Path(__file__).resolve().parents[1]


def _git(root: Path, *args: str) -> None:
    completed = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr


def _write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _frozen_repo(tmp_path: Path, benchmark: dict | None = None) -> Path:
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    _write(root, ".gitignore", ".holusight/\n")
    paths = (
        retrieval_variation.BENCHMARK_PATH,
        Path("tests/fixtures/holusight_eval_pilot_cases.jsonl"),
        retrieval_variation.RETRIEVAL_SOURCE_PATH,
        retrieval_variation.PRODUCTION_SELECTOR_SOURCE_PATH,
    )
    for relative in paths:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / relative, destination)
    if benchmark is not None:
        (root / retrieval_variation.BENCHMARK_PATH).write_text(
            json.dumps(benchmark), encoding="utf-8"
        )
    _git(root, "init", "-q")
    _git(root, "add", ".")
    _git(
        root,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "freeze inputs",
    )
    return root


def test_baseline_and_benchmark_are_content_addressed_and_all_case_families_run():
    result = retrieval_variation.run_program(REPO_ROOT)
    assert result["program"]["benchmark_hash"].startswith("sha256:")
    assert result["program"]["source_fixture_hashes"]
    assert result["program"]["evaluator_digest"].startswith("sha256:")
    assert set(result["program"]["implementation_hashes"]) == {
        "src/codesight/retrieval_variation.py",
        "src/codesight/cli_axi.py",
    }
    assert result["baseline"]["candidate"]["candidate_id"] == (
        "baseline-legacy-concatenate-v1"
    )
    families = {grade["family"] for grade in result["baseline"]["case_outcomes"]}
    assert families == {
        "exact",
        "hybrid",
        "graph_impact",
        "ambiguity",
        "no_evidence",
        "adversarial",
    }


def test_two_fixed_candidates_have_lineage_and_hard_constraints_are_separate_from_reward():
    result = retrieval_variation.run_program(REPO_ROOT)
    assert len(result["candidates"]) == 2
    for candidate in result["candidates"]:
        evaluation = candidate["evaluation"]
        assert evaluation["candidate"]["definition_hash"].startswith("sha256:")
        assert evaluation["candidate"]["implementation_hashes"]
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


def test_program_candidate_executes_the_production_display_boundary(monkeypatch):
    def concatenate(results, cap):
        return [item for result in results for item in result.items][:cap]

    monkeypatch.setattr(cli_axi, "_select_display_items", concatenate)
    result = retrieval_variation.run_program(REPO_ROOT)
    adversarial = next(
        grade
        for grade in result["candidates"][0]["evaluation"]["case_outcomes"]
        if grade["case_id"] == "adversarial-provider-flood"
    )
    assert "required_provider_hidden" in adversarial["hard_constraints"]


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
    source_hashes = result["program"]["implementation_hashes"]
    baseline_identity = retrieval_variation._strategy_identity(
        retrieval_variation.BASELINE, source_hashes
    )
    assert result["baseline"]["candidate"]["definition_hash"] == baseline_identity[
        "definition_hash"
    ]


def test_failed_and_inconclusive_outcomes_are_retained_and_never_promote():
    result = retrieval_variation.run_program(REPO_ROOT)
    statuses = {candidate["verdict"]["status"] for candidate in result["candidates"]}
    assert statuses == {"failed", "inconclusive"}
    first_verdict = result["candidates"][0]["verdict"]
    assert first_verdict["paired_sign_test_p_value"] >= 0.05
    assert "insufficient_paired_statistical_evidence" in first_verdict["reasons"]
    assert result["promotion"]["allowed"] is False
    for candidate in result["candidates"]:
        assert candidate["verdict"]["promotion"]["allowed"] is False
        assert candidate["verdict"]["promotion"]["candidate_self_promotion"] == "denied"


def test_result_validation_recomputes_frozen_evidence_after_digest_resealing():
    result = retrieval_variation.run_program(REPO_ROOT)
    tampered = json.loads(json.dumps(result))
    tampered["candidates"][0]["evaluation"]["reward"]["primary_value"] = 0.123456
    tampered["result_digest"] = retrieval_variation._canonical_hash(
        {key: value for key, value in tampered.items() if key != "result_digest"}
    )
    with pytest.raises(ValueError, match="recomputed"):
        retrieval_variation.validate_result(tampered, repo_root=REPO_ROOT)

    partial = json.loads(json.dumps(result))
    partial["candidates"] = partial["candidates"][:1]
    partial["result_digest"] = retrieval_variation._canonical_hash(
        {key: value for key, value in partial.items() if key != "result_digest"}
    )
    with pytest.raises(ValueError, match="partial"):
        retrieval_variation.validate_result(partial, repo_root=REPO_ROOT)


def test_benchmark_rejects_unbounded_counts_dirty_bytes_and_alternate_paths(tmp_path):
    benchmark = json.loads(
        (REPO_ROOT / retrieval_variation.BENCHMARK_PATH).read_text(encoding="utf-8")
    )
    benchmark["cases"][0]["provider_item_counts"]["exact"] = (
        retrieval_variation.MAX_PROVIDER_ITEMS + 1
    )
    oversized_root = _frozen_repo(tmp_path / "oversized", benchmark)
    with pytest.raises(ValueError, match="provider declarations"):
        retrieval_variation.load_benchmark(oversized_root)

    clean_root = _frozen_repo(tmp_path / "clean")
    benchmark_path = clean_root / retrieval_variation.BENCHMARK_PATH
    benchmark_path.write_text(benchmark_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="clean and tracked"):
        retrieval_variation.load_benchmark(clean_root)

    alternate = _write(clean_root, "tests/fixtures/alternate.json", "{}")
    with pytest.raises(ValueError, match="canonical frozen"):
        retrieval_variation.load_benchmark(clean_root, alternate.relative_to(clean_root))


def test_recording_preserves_typed_run_and_safe_content_minimized_history(tmp_path):
    result = retrieval_variation.run_program(REPO_ROOT)
    record_path = retrieval_variation.record_run(REPO_ROOT, result)
    result_path = retrieval_variation.persist_result(REPO_ROOT, result)
    try:
        record = json.loads((REPO_ROOT / record_path).read_text(encoding="utf-8"))
        assert {item["status"] for item in record["candidate_outcomes"]} == {
            "failed",
            "inconclusive",
        }
        assert retrieval_variation.load_result(REPO_ROOT, Path(result_path)) == result
    finally:
        (REPO_ROOT / record_path).unlink(missing_ok=True)
        (REPO_ROOT / result_path).unlink(missing_ok=True)

    root = _frozen_repo(tmp_path / "unsafe")
    unsafe_result = retrieval_variation.run_program(root)
    (root / ".holusight").symlink_to(tmp_path / "outside", target_is_directory=True)
    with pytest.raises(ValueError, match="unsafe"):
        retrieval_variation.record_run(root, unsafe_result)


def test_variation_result_reaches_existing_independent_review_boundary(tmp_path):
    root = _frozen_repo(tmp_path / "review")
    _write(root, "specs/020-control.md", "# Control\n\n**Status:** Evaluated\n")
    _write(root, "tests/test_control.py", "def test_control():\n    assert True\n")
    _write(root, "docs/playbooks/control.md", "# Control\n")
    _git(root, "add", ".")
    _git(
        root,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "add review evidence",
    )

    result = retrieval_variation.run_program(root)
    result_path = retrieval_variation.persist_result(root, result)
    links = {
        "governing": ["specs/020-control.md"],
        "implementation": sorted(result["program"]["implementation_hashes"]),
        "tests": ["tests/test_control.py"],
        "documentation": ["docs/playbooks/control.md"],
        "evaluation_case": [
            retrieval_variation.BENCHMARK_PATH.as_posix(),
            *sorted(result["program"]["source_fixture_hashes"]),
        ],
        "evaluation_result": [result_path],
    }
    manifest = {
        "schema_version": improvement_control.CHANGE_SCHEMA,
        "change_id": "controlled-display-variation",
        "classification": "evaluated",
        "structured_sections": ["context", "evidence", "decision"],
        "links": links,
        "link_hashes": {
            path: _sha(root / path) for paths in links.values() for path in paths
        },
        "lineage": {
            "candidate_id": "candidate-round-robin-v1",
            "workflow": "pytest",
            "tool": "holus",
        },
    }
    manifest_path = _write(
        root, "specs/020-control.change.json", json.dumps(manifest, sort_keys=True)
    )
    _git(root, "add", manifest_path.relative_to(root).as_posix())
    _git(
        root,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "anchor variation result",
    )

    review = improvement_control.review_change(
        root, manifest_path.relative_to(root).as_posix(), phase="pre_promotion"
    )
    blocker_codes = {item["code"] for item in review["review"]["blockers"]}
    assert "invalid_evaluation_result" not in blocker_codes
    assert "inapplicable_evaluation_result" not in blocker_codes
    assert "untrusted_evaluation_anchor" not in blocker_codes
    assert blocker_codes == {"variation_result_not_eligible"}
    assert review["review"]["promotion"]["allowed"] is False


def test_feedback_is_aggregate_privacy_safe_and_review_only():
    feedback = retrieval_variation.build_feedback_proposal("failure_case", 2)
    assert feedback["review_queue"]["raw_prompt_retained"] is False
    assert feedback["review_queue"]["canonical_truth_changed"] is False
    assert feedback["privacy"]["external_egress"] == "denied"
    with pytest.raises(ValueError):
        retrieval_variation.build_feedback_proposal("raw_prompt", 1)


def test_public_operator_run_and_record_envelope_are_closed_and_non_promoting():
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

    recorded = subprocess.run(
        [
            sys.executable,
            "-m",
            "codesight.cli_axi",
            "improve-variation-run",
            "--record",
            "--format",
            "json",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert recorded.returncode == 0, recorded.stderr
    envelope = json.loads(recorded.stdout)
    retrieval_variation.validate_result(envelope["run"], repo_root=REPO_ROOT)
    assert set(envelope) == {"schema_version", "run", "derived_state"}
    for path in envelope["derived_state"].values():
        (REPO_ROOT / path).unlink(missing_ok=True)


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
