"""End-to-end tests for the deterministic Holusight improvement control plane."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from codesight import cli_axi, eval_pilot, improvement_control

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write(root: Path, rel: str, text: str = "x\n") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _repo(tmp_path: Path) -> Path:
    """A real, committed Git repo — a pilot evaluation result's immutable
    subject (spec 021) can only ever be clean and resolvable against one."""
    _write(tmp_path, ".gitignore", ".holusight/\n")
    _write(tmp_path, ".claude/rules/structure.md", "# structure\n")
    _write(tmp_path, "specs/019-control.md", "# Control\n\n**Status:** Evaluated\n")
    _write(tmp_path, "src/codesight/control_target.py", "VALUE = 1\n")
    _write(tmp_path, "tests/test_control_target.py", "def test_value():\n    assert True\n")
    _write(tmp_path, "docs/playbooks/control.md", "# Control explanation\n")
    case = {
        "schema_version": eval_pilot.SCHEMA_CASE,
        "case_id": "control-case",
        "family": "regression",
        "kind": "regression",
        "provenance": {
            "origin": "spec_documented_contract",
            "description": "control test",
            "admitted_by": "human",
            "admitted_at": "2026-08-23",
        },
        "grader": "grade_no_egress_default",
        "fixture": {},
        "expected": {
            "key_stripped_without_allow_egress": True,
            "key_restored_after_context_exit": True,
        },
    }
    _write(tmp_path, "tests/fixtures/holusight_eval_pilot_cases.jsonl", json.dumps(case) + "\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "control-plane@example.test")
    _git(tmp_path, "config", "user.name", "Control Plane Test")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def _manifest(root: Path, classification: str = "accepted") -> Path:
    links = {
        "governing": ["specs/019-control.md"],
        "implementation": ["src/codesight/control_target.py"],
        "tests": ["tests/test_control_target.py"],
        "documentation": ["docs/playbooks/control.md"],
        "evaluation_case": ["tests/fixtures/holusight_eval_pilot_cases.jsonl"],
        "evaluation_result": [".holusight/improvement-results/control-result.json"],
    }
    result = eval_pilot.run_pilot(
        root,
        cases_path=root / links["evaluation_case"][0],
        lineage=eval_pilot.CandidateLineage(
            candidate_id="control-change", repo_commit=None, workflow="pytest", tool="holus"
        ),
    )
    _write(root, links["evaluation_result"][0], json.dumps(result.model_dump(mode="json")))
    hashes = {path: _sha(root / path) for paths in links.values() for path in paths}
    manifest = {
        "schema_version": improvement_control.CHANGE_SCHEMA,
        "change_id": "control-change",
        "classification": "evaluated" if classification == "accepted" else classification,
        "structured_sections": ["context", "evidence", "decision"],
        "links": links,
        "link_hashes": hashes,
        "lineage": {"candidate_id": "candidate-1", "workflow": "pytest", "tool": "holus"},
    }
    return _write(root, "specs/019-control.change.json", json.dumps(manifest))


def _run(argv: list[str], cwd: Path) -> tuple[dict, str, int]:
    old = Path.cwd()
    os.chdir(cwd)
    try:
        return cli_axi._dispatch(argv)
    finally:
        os.chdir(old)


def test_real_starvation_regression_flows_from_intake_to_comparison_and_retention():
    """The PR #20 regression stays a retained, end-to-end control, not a claim.

    Intake remains opt-in/no-write; the frozen comparative case demonstrates
    the corrected candidate against its pre-fix status quo; the same case is
    still retained unchanged after the run.
    """
    before = eval_pilot.DEFAULT_CASES_PATH.read_bytes()
    intake, _fmt, intake_code = _run(
        [
            "improve-intake",
            "auto-mode evidence display starved successful providers",
            "--origin",
            "reproduced_usage_gap",
            "--admitted-by",
            "control-plane-test",
            "--format",
            "json",
        ],
        REPO_ROOT,
    )
    run, _fmt, run_code = _run(["improve-run", "--format", "json"], REPO_ROOT)
    starvation = {grade["case_id"]: grade for grade in run["run"]["grades"]}[
        "cli-axi-provider-starvation-display-quota"
    ]

    assert intake_code == run_code == 0
    assert intake["intake_policy"]["status"] == "proposed"
    assert starvation["verdict"] == "pass"  # corrected candidate
    assert starvation["status_quo_verdict"] == "pass"  # historical regression still reproduces
    assert eval_pilot.DEFAULT_CASES_PATH.read_bytes() == before
    assert "cli-axi-provider-starvation-display-quota" in {
        case["case_id"] for case in eval_pilot.load_cases(eval_pilot.DEFAULT_CASES_PATH)
    }


def test_complete_accepted_conclusion_has_deterministic_stage_and_links(tmp_path):
    root = _repo(tmp_path)
    manifest = _manifest(root)
    payload, _fmt, exit_code = _run(
        [
            "improve-review",
            str(manifest.relative_to(root)),
            "--phase",
            "pre_promotion",
            "--format",
            "json",
        ],
        root,
    )

    assert exit_code == 0
    assert payload["review"]["stage"] == "evaluated"
    assert payload["review"]["missing_evidence"] == []
    assert payload["review"]["next_permitted_action"] == "human_promotion_review"
    assert payload["review"]["promotion"]["allowed"] is False
    assert payload["review"]["promotion"]["blockers"] == ["human_promotion_required"]
    assert payload["research_needed"] is None


def test_oversized_evaluation_result_is_blocked_before_hashing_or_parsing(tmp_path):
    root = _repo(tmp_path)
    manifest = _manifest(root)
    value = json.loads(manifest.read_text(encoding="utf-8"))
    result_relative = value["links"]["evaluation_result"][0]
    result_path = root / result_relative
    with result_path.open("wb") as handle:
        handle.truncate(improvement_control._MAX_EVALUATION_RESULT_BYTES + 1)
    value["link_hashes"][result_relative] = "sha256:" + ("0" * 64)
    manifest.write_text(json.dumps(value), encoding="utf-8")

    payload, _fmt, _exit = _run(
        [
            "improve-review",
            str(manifest.relative_to(root)),
            "--phase",
            "pre_promotion",
            "--format",
            "json",
        ],
        root,
    )

    blocker_codes = {item["code"] for item in payload["review"]["blockers"]}
    assert "invalid_evaluation_result" in blocker_codes
    assert "stale_link" not in blocker_codes
    assert payload["review"]["promotion"]["allowed"] is False


def test_missing_accepted_implementation_and_evaluation_are_exact_blockers(tmp_path):
    root = _repo(tmp_path)
    manifest = _manifest(root)
    value = json.loads(manifest.read_text())
    value["links"]["implementation"] = []
    value["links"]["evaluation_case"] = ["tests/fixtures/missing.jsonl"]
    value["links"]["evaluation_result"] = []
    value["link_hashes"].pop("src/codesight/control_target.py")
    value["link_hashes"].pop("tests/fixtures/holusight_eval_pilot_cases.jsonl")
    value["link_hashes"].pop(".holusight/improvement-results/control-result.json")
    manifest.write_text(json.dumps(value), encoding="utf-8")

    payload, _fmt, _exit = _run(
        [
            "improve-review",
            "specs/019-control.change.json",
            "--phase",
            "after_implementation",
            "--format",
            "json",
        ],
        root,
    )
    blockers = {item["code"] for item in payload["review"]["blockers"]}
    assert {
        "missing_implementation",
        "dangling_evaluation_case",
        "missing_evaluation_result",
    } <= blockers
    assert payload["review"]["stage"] == "accepted"
    assert payload["review"]["next_permitted_action"] == "add_required_evidence"
    assert payload["research_needed"]["reason"] == "materially_incomplete_evidence"


def test_research_only_and_rejected_never_require_code_or_authority(tmp_path):
    root = _repo(tmp_path)
    for classification in ("research_only", "rejected", "superseded"):
        manifest = _manifest(root, classification)
        value = json.loads(manifest.read_text())
        value["links"] = {
            "governing": [],
            "implementation": [],
            "tests": [],
            "documentation": [],
            "evaluation_case": [],
            "evaluation_result": [],
        }
        value["link_hashes"] = {}
        manifest.write_text(json.dumps(value), encoding="utf-8")
        payload, _fmt, _exit = _run(
            [
                "improve-review",
                "specs/019-control.change.json",
                "--phase",
                "before_change",
                "--format",
                "json",
            ],
            root,
        )
        codes = {item["code"] for item in payload["review"]["blockers"]}
        assert "missing_implementation" not in codes
        assert "missing_governing" not in codes
        assert payload["review"]["stage"] == classification


def test_before_change_blocks_duplicate_and_misplaced_artifacts(tmp_path):
    root = _repo(tmp_path)
    manifest = _manifest(root)
    value = json.loads(manifest.read_text())
    value["proposed_artifacts"] = [
        {"artifact_type": "test", "path": "tests/test_control_target.py"},
        {"artifact_type": "spec", "path": "docs/020-wrong-place.md"},
    ]
    manifest.write_text(json.dumps(value), encoding="utf-8")
    payload, _fmt, _exit = _run(
        [
            "improve-review",
            "specs/019-control.change.json",
            "--phase",
            "before_change",
            "--format",
            "json",
        ],
        root,
    )
    codes = {item["code"] for item in payload["review"]["blockers"]}
    assert {"duplicate_artifact", "misplaced_artifact"} <= codes
    assert payload["review"]["next_permitted_action"] == "resolve_placement"


def test_detects_dangling_contradictory_duplicate_and_stale_links(tmp_path):
    root = _repo(tmp_path)
    manifest = _manifest(root)
    value = json.loads(manifest.read_text())
    value["links"]["governing"].append("specs/019-control.md")
    value["links"]["tests"].append("src/codesight/control_target.py")
    value["link_hashes"]["docs/playbooks/control.md"] = "sha256:" + ("0" * 64)
    value["classification_evidence"] = "rejected"
    manifest.write_text(json.dumps(value), encoding="utf-8")
    payload, _fmt, _exit = _run(
        [
            "improve-review",
            "specs/019-control.change.json",
            "--phase",
            "after_test",
            "--format",
            "json",
        ],
        root,
    )
    codes = {item["code"] for item in payload["review"]["blockers"]}
    assert {
        "duplicate_link",
        "contradictory_classification",
        "stale_link",
        "wrong_link_role",
    } <= codes
    assert payload["research_needed"]["reason"] == "contradictory_evidence"


def test_records_failed_candidate_history_and_rebuild_without_canonical_mutation(tmp_path):
    root = _repo(tmp_path)
    manifest = _manifest(root)
    canonical_before = manifest.read_bytes()
    payload, _fmt, _exit = _run(
        [
            "improve-review",
            "specs/019-control.change.json",
            "--phase",
            "after_test",
            "--record",
            "--format",
            "json",
        ],
        root,
    )
    record = root / payload["record"]["path"]
    assert record.exists()
    assert canonical_before == manifest.read_bytes()
    history, _fmt, _exit = _run(["improve-history", "control-change", "--format", "json"], root)
    assert history["history"]["records_total"] == 1
    assert history["history"]["records"][0]["outcome"] == "blocked"
    record.unlink()
    rebuilt, _fmt, _exit = _run(
        [
            "improve-review",
            "specs/019-control.change.json",
            "--phase",
            "after_test",
            "--record",
            "--format",
            "json",
        ],
        root,
    )
    assert rebuilt["review"] == payload["review"]
    assert manifest.read_bytes() == canonical_before


def test_repeated_stagnation_emits_precise_research_packet_without_egress(tmp_path):
    root = _repo(tmp_path)
    _manifest(root)
    for _ in range(2):
        _run(
            [
                "improve-review",
                "specs/019-control.change.json",
                "--phase",
                "after_test",
                "--record",
                "--format",
                "json",
            ],
            root,
        )
    payload, _fmt, _exit = _run(
        [
            "improve-review",
            "specs/019-control.change.json",
            "--phase",
            "after_test",
            "--format",
            "json",
        ],
        root,
    )
    packet = payload["research_needed"]
    assert packet["reason"] == "repeated_stagnation"
    assert packet["recommended_research"] == "gpt_deep_research"
    assert "question" in packet and packet["external_action"] == "not_launched"
    assert payload["safety"]["external_egress"] == "denied"


def test_unfamiliar_metadata_emits_normal_review_without_launching_research(tmp_path):
    root = _repo(tmp_path)
    manifest = _manifest(root)
    value = json.loads(manifest.read_text())
    value["evidence_state"] = "unfamiliar"
    manifest.write_text(json.dumps(value), encoding="utf-8")

    payload, _fmt, _exit = _run(
        ["improve-review", "specs/019-control.change.json", "--format", "json"], root
    )
    assert payload["research_needed"]["reason"] == "unfamiliar_evidence"
    assert payload["research_needed"]["recommended_research"] == "normal_review"
    assert payload["research_needed"]["external_action"] == "not_launched"


def test_refuses_raw_private_export_evaluator_mutation_auto_promotion_and_path_escape(tmp_path):
    root = _repo(tmp_path)
    manifest = _manifest(root)
    value = json.loads(manifest.read_text())
    value["raw_prompt"] = "secret"
    manifest.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(cli_axi.UsageError, match="forbidden field"):
        _run(["improve-review", "specs/019-control.change.json", "--format", "json"], root)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "codesight.cli_axi",
            "improve-review",
            "specs/019-control.change.json",
            "--format",
            "json",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "forbidden field" in result.stdout
    assert "secret" not in result.stdout

    value.pop("raw_prompt")
    value["proposed_artifacts"] = [
        {"artifact_type": "source", "path": "src/codesight/eval_pilot.py"}
    ]
    manifest.write_text(json.dumps(value), encoding="utf-8")
    payload, _fmt, _exit = _run(
        ["improve-review", "specs/019-control.change.json", "--format", "json"], root
    )
    assert "evaluator_mutation" in {item["code"] for item in payload["review"]["blockers"]}
    assert payload["review"]["promotion"]["allowed"] is False

    escaped = _write(
        root,
        "specs/escaped.change.json",
        json.dumps(
            {
                "schema_version": improvement_control.CHANGE_SCHEMA,
                "change_id": "escaped",
                "classification": "proposed",
                "structured_sections": ["context"],
                "links": {"governing": ["../../etc/passwd"]},
            }
        ),
    )
    escaped_payload, _fmt, _exit = _run(
        ["improve-review", str(escaped.relative_to(root)), "--format", "json"], root
    )
    assert "unsafe_link" in {item["code"] for item in escaped_payload["review"]["blockers"]}


def test_integration_output_is_stable_local_and_aggregate_next_actions_are_deterministic(tmp_path):
    root = _repo(tmp_path)
    _manifest(root)
    payload, _fmt, exit_code = _run(
        [
            "improve-integration",
            "specs/019-control.change.json",
            "--phase",
            "pre_promotion",
            "--format",
            "json",
        ],
        root,
    )
    assert exit_code == 0
    assert payload["integration_contract"] == improvement_control.INTEGRATION_SCHEMA
    assert payload["consumer"] == "local_advisory_only"
    assert payload["review"]["next_permitted_action"] == "human_promotion_review"
    assert payload["review"]["promotion"]["allowed"] is False
