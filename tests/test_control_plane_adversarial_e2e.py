"""Adversarial public-command regressions for the improvement control plane."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from codesight import eval_pilot


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "codesight.cli_axi", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


def _case(*, comparative: bool = False, semantic: bool = False) -> dict:
    return {
        "schema_version": eval_pilot.SCHEMA_CASE,
        "case_id": "e2e-case",
        "family": "regression",
        "kind": "comparative" if comparative else "regression",
        "provenance": {
            "origin": "spec_documented_contract",
            "description": "public e2e",
            "admitted_by": "human",
            "admitted_at": "2026-08-23",
        },
        "grader": "grade_no_egress_default",
        "fixture": {},
        "expected": {
            "key_stripped_without_allow_egress": True,
            "key_restored_after_context_exit": True,
        },
        "requires_semantic": semantic,
    }


def _repo(tmp_path: Path) -> Path:
    (tmp_path / ".gitignore").write_text(".holusight/\n", encoding="utf-8")
    structure = tmp_path / ".claude/rules/structure.md"
    structure.parent.mkdir(parents=True)
    structure.write_text("tests/fixtures/\n", encoding="utf-8")
    (tmp_path / "src/codesight").mkdir(parents=True)
    (tmp_path / "src/codesight/eval_pilot.py").write_text("protected evaluator\n", encoding="utf-8")
    cases = tmp_path / "tests/fixtures/holusight_eval_pilot_cases.jsonl"
    cases.parent.mkdir(parents=True)
    cases.write_text(json.dumps(_case()) + "\n", encoding="utf-8")
    return tmp_path


def test_e2e_output_cannot_overwrite_evaluator_corpus_or_symlink_alias(tmp_path):
    repo = _repo(tmp_path)
    evaluator = repo / "src/codesight/eval_pilot.py"
    corpus = repo / "tests/fixtures/holusight_eval_pilot_cases.jsonl"
    before_evaluator, before_corpus = evaluator.read_bytes(), corpus.read_bytes()
    for target in (
        "src/codesight/eval_pilot.py",
        "tests/fixtures/holusight_eval_pilot_cases.jsonl",
    ):
        result = _run(
            repo, "improve-run", "--candidate-id", "e2e", "--output", target, "--format", "json"
        )
        assert result.returncode == 2
        assert "output rejected" in result.stdout
    alias = repo / ".holusight/improvement-results/alias"
    alias.parent.mkdir(parents=True)
    alias.symlink_to(evaluator)
    result = _run(
        repo,
        "improve-run",
        "--candidate-id",
        "e2e",
        "--output",
        str(alias.relative_to(repo)),
        "--format",
        "json",
    )
    assert result.returncode == 2
    assert evaluator.read_bytes() == before_evaluator
    assert corpus.read_bytes() == before_corpus


def test_e2e_comparative_without_control_and_failed_evaluation_are_nonzero_json(tmp_path):
    repo = _repo(tmp_path)
    invalid = repo / "comparative.jsonl"
    invalid.write_text(json.dumps(_case(comparative=True)) + "\n", encoding="utf-8")
    missing_control = _run(
        repo, "improve-run", "--cases", str(invalid), "--candidate-id", "e2e", "--format", "json"
    )
    assert missing_control.returncode == 2
    assert json.loads(missing_control.stdout)["error"]["code"] == "USAGE_ERROR"

    semantic = repo / "semantic.jsonl"
    semantic.write_text(json.dumps(_case(semantic=True)) + "\n", encoding="utf-8")
    failed = _run(
        repo, "improve-run", "--cases", str(semantic), "--candidate-id", "e2e", "--format", "json"
    )
    assert failed.returncode == 1
    payload = json.loads(failed.stdout)
    assert payload["run"]["counts"]["errored"] == 1
    assert payload["scorecard"] if "scorecard" in payload else True


def test_e2e_mutated_prior_is_invalid_not_improved(tmp_path):
    repo = _repo(tmp_path)
    prior = ".holusight/improvement-results/prior.json"
    first = _run(
        repo,
        "improve-run",
        "--cases",
        "tests/fixtures/holusight_eval_pilot_cases.jsonl",
        "--candidate-id",
        "e2e",
        "--output",
        prior,
        "--format",
        "json",
    )
    assert first.returncode == 0
    prior_path = repo / prior
    payload = json.loads(prior_path.read_text())
    payload["counts"]["passed"] = 0
    payload["counts"]["failed"] = 1
    prior_path.write_text(json.dumps(payload), encoding="utf-8")
    compared = _run(
        repo,
        "improve-run",
        "--cases",
        "tests/fixtures/holusight_eval_pilot_cases.jsonl",
        "--candidate-id",
        "e2e",
        "--compare-result",
        prior,
        "--format",
        "json",
    )
    assert compared.returncode == 2
    assert "counts do not match grades" in compared.stdout


def test_e2e_case_placement_enforces_jsonl_and_correct_action(tmp_path):
    repo = _repo(tmp_path)
    invalid = _run(
        repo,
        "improve-placement",
        "--artifact-type",
        "case",
        "--proposed-path",
        "tests/fixtures/not-a-case.py",
        "--format",
        "json",
    )
    assert invalid.returncode == 0
    invalid_payload = json.loads(invalid.stdout)
    assert invalid_payload["lifecycle"]["status"] == "blocked"
    assert invalid_payload["recommended_action"] == "adjust_path_and_retry"
    valid = _run(
        repo,
        "improve-placement",
        "--artifact-type",
        "case",
        "--proposed-path",
        "tests/fixtures/new-case.jsonl",
        "--format",
        "json",
    )
    assert valid.returncode == 0
    assert json.loads(valid.stdout)["recommended_action"] == "create_at_recommended_path"


def test_e2e_secret_intake_and_unsafe_history_are_rejected_or_visible(tmp_path):
    repo = _repo(tmp_path)
    intake = _run(repo, "improve-intake", "API key sk-live-PRIVATE123", "--format", "json")
    assert intake.returncode == 2
    assert "sk-live" not in intake.stdout

    manifest = {
        "schema_version": "holus-improvement-change/v1",
        "change_id": "e2e-change",
        "classification": "proposed",
        "structured_sections": ["context"],
        "links": {},
        "link_hashes": {},
        "lineage": {},
    }
    path = repo / "specs/e2e.change.json"
    path.parent.mkdir()
    path.write_text(json.dumps(manifest), encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (repo / ".holusight").mkdir()
    (repo / ".holusight/improvement-runs").symlink_to(outside, target_is_directory=True)
    unsafe = _run(repo, "improve-review", "specs/e2e.change.json", "--record", "--format", "json")
    assert unsafe.returncode == 2
    assert not list(outside.iterdir())
