"""Tests for the Holusight continuous-improvement loop v1 (spec 018).

Covers the four new `holus improve-*` commands
(:mod:`codesight.cli_axi`, schema in :mod:`codesight.axi_schema`) built on
top of the already-landed eval pilot (spec 017, :mod:`codesight.eval_pilot`)
and consistency evaluator (spec 013). Per the launch checklist, this proves
the loop end to end (the already-reproduced `cli-axi-provider-starvation
-display-quota` regression via `improve-run`, and a duplicate-artifact
placement case via `improve-placement`) and adds negative tests refusing
evaluator mutation, private/raw-content export, automatic promotion,
external egress, and unsupported placement.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from codesight import cli_axi, eval_pilot

REPO_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = eval_pilot.DEFAULT_CASES_PATH


def _run(argv: list[str], cwd: Path = REPO_ROOT) -> tuple[dict, str, int]:
    import os

    old_cwd = os.getcwd()
    os.chdir(cwd)
    try:
        return cli_axi._dispatch(argv)
    finally:
        os.chdir(old_cwd)


def _subprocess_holus(args: list[str], cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "codesight.cli_axi", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# 1. `improve-status` -- discoverable, machine-readable lifecycle summary
# ---------------------------------------------------------------------------


def test_improve_status_reports_frozen_corpus_coverage():
    payload, fmt, exit_code = _run(["improve-status", "--format", "json"])
    assert exit_code == 0
    assert payload["coverage"]["cases_total"] >= 4
    assert payload["coverage"]["status_quo_supported"] is True
    assert payload["lifecycle"]["cases_file_hash"] == eval_pilot.cases_file_hash(CASES_PATH)


def test_improve_status_is_registered_in_schema_and_help():
    names = {cmd.name for cmd in cli_axi.AXI_COMMANDS}
    assert {"improve-status", "improve-intake", "improve-run", "improve-placement"} <= names


# ---------------------------------------------------------------------------
# 2. `improve-intake` -- opt-in, content-minimized, never writes a file
# ---------------------------------------------------------------------------


def test_improve_intake_never_writes_any_file(tmp_path):
    before = set(REPO_ROOT.rglob("*"))
    payload, _fmt, exit_code = _run(
        [
            "improve-intake",
            "a gap observed while using holus evidence in auto mode",
            "--origin",
            "reproduced_usage_gap",
            "--admitted-by",
            "test-suite",
            "--format",
            "json",
        ]
    )
    after = set(REPO_ROOT.rglob("*"))
    assert exit_code == 0
    assert before == after
    assert payload["intake_policy"]["auto_placement"] is False


def test_improve_intake_content_is_minimized_and_flagged():
    long_summary = "x" * 5000
    payload, _fmt, _exit = _run(
        ["improve-intake", long_summary, "--admitted-by", "test-suite", "--format", "json"]
    )
    assert len(payload["intake"]["provenance"]["description"]) <= 240
    assert payload["intake_policy"]["content_minimized"] is True
    assert payload["intake_policy"]["captures_prompt_or_private_content"] is False


def test_improve_intake_rejects_unsupported_origin():
    with pytest.raises(ValueError, match="unsupported origin"):
        eval_pilot.build_intake_proposal("x", origin="totally_made_up_origin")


def test_improve_intake_flags_duplicate_case_id_against_frozen_corpus():
    real_case_id = "cli-axi-provider-starvation-display-quota"
    result = eval_pilot.build_intake_proposal(
        "duplicate of the real starvation case",
        case_id=real_case_id,
        cases_path=CASES_PATH,
        admitted_by="test-suite",
    )
    assert result["intake_policy"]["status"] == "duplicate_case_id"


def test_cli_intake_requires_a_summary_argument():
    with pytest.raises(cli_axi.UsageError, match='missing required argument "summary"'):
        _run(["improve-intake"])


# ---------------------------------------------------------------------------
# 3. `improve-run` -- proves the already-reproduced regression end to end,
#    with immutable lineage and structured research_needed/stagnated output
# ---------------------------------------------------------------------------


def test_improve_run_reproduces_the_display_quota_regression_via_cli():
    payload, _fmt, exit_code = _run(
        ["improve-run", "--candidate-id", "test-suite-run", "--format", "json"]
    )
    assert exit_code == 0
    grades = {g["case_id"]: g for g in payload["run"]["grades"]}
    starvation = grades["cli-axi-provider-starvation-display-quota"]
    # The shipped fix (candidate) passes; the frozen pre-fix status-quo
    # comparator still reproduces the historical starvation on the same
    # synthetic fixture -- the concrete before/after demonstration.
    assert starvation["verdict"] == "pass"
    assert starvation["status_quo_verdict"] == "pass"
    assert payload["run"]["lineage"]["candidate_id"] == "test-suite-run"
    assert payload["run"]["lineage"]["repo_commit"]


def test_improve_run_never_writes_to_the_frozen_case_file():
    before = CASES_PATH.read_bytes()
    _run(["improve-run", "--format", "json"])
    assert CASES_PATH.read_bytes() == before


def test_improve_run_reports_structured_progress_outcome(tmp_path, monkeypatch):
    # Keep this contract test independent of the developer's uncommitted
    # implementation under test; production clean-worktree state is checked by
    # the subprocess E2E suite.
    monkeypatch.setattr(eval_pilot, "_git_dirty", lambda _repo: False)
    output_path = tmp_path / "first-run.json"
    _run(
        [
            "improve-run",
            "--candidate-id",
            "run-a",
            "--output",
            str(output_path),
            "--format",
            "json",
        ]
    )
    assert output_path.exists()

    # A mutable external baseline and a distinct candidate identity remain
    # structured invalid comparison evidence, never a promotion-relevant step.
    payload, _fmt, exit_code = _run(
        [
            "improve-run",
            "--candidate-id",
            "run-b",
            "--compare-result",
            str(output_path),
            "--format",
            "json",
        ]
    )
    assert exit_code == 0
    assert payload["progress"]["outcome"] == "invalid_comparison"
    assert payload["progress"]["comparison"]["promotion_relevant"] is False
    assert payload["progress"]["next_step"] != "candidate_readiness_for_review"


def test_improve_run_without_compare_result_reports_research_needed():
    payload, _fmt, _exit = _run(["improve-run", "--format", "json"])
    assert payload["progress"]["outcome"] == "research_needed"
    assert payload["progress"]["research_needed"] is True


def test_stagnation_recommends_ordinary_or_gpt_deep_research_never_launches_it():
    result = eval_pilot.run_pilot(
        REPO_ROOT, cases_path=CASES_PATH, lineage=_lineage("stagnation-a")
    )
    progress = eval_pilot.evaluate_progress(result, result)
    assert progress["outcome"] in {"stagnated", "invalid_comparison"}
    assert progress["recommended_research"] in {"gpt_deep_research", "normal_review", None}
    # A recommendation is a string, never a callable/launch action.
    assert isinstance(progress["recommended_research"], (str, type(None)))


def _lineage(candidate_id: str) -> eval_pilot.CandidateLineage:
    return eval_pilot.CandidateLineage(
        candidate_id=candidate_id,
        repo_commit="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        workflow="test",
        tool="pytest",
        model=None,
    )


# ---------------------------------------------------------------------------
# 4. `improve-placement` -- placement compliance, never edits files
# ---------------------------------------------------------------------------


def test_placement_ok_for_a_genuinely_new_canonical_path():
    payload, _fmt, exit_code = _run(
        [
            "improve-placement",
            "--artifact-type",
            "spec",
            "--proposed-path",
            "specs/999-improve-loop-placement-test.md",
            "--format",
            "json",
        ]
    )
    assert exit_code == 0
    assert payload["lifecycle"]["status"] == "ok"
    assert payload["placement"]["in_canonical_location"] is True


def test_placement_blocks_duplicate_artifact_name():
    """The concrete duplicate-artifact demonstration required by the launch
    checklist: proposing a test file whose name already exists elsewhere in
    the canonical `tests/` location must be blocked, not silently allowed."""
    payload, _fmt, exit_code = _run(
        [
            "improve-placement",
            "--artifact-type",
            "test",
            "--proposed-path",
            "tests/test_eval_pilot.py",
            "--format",
            "json",
        ]
    )
    assert exit_code == 0  # a blocked *result* is not a usage error
    assert payload["lifecycle"]["status"] == "blocked"
    assert "tests/test_eval_pilot.py" in payload["placement"]["duplicate_hits"]
    assert payload["recommended_action"] == "adjust_path_and_retry"


def test_placement_blocks_path_outside_canonical_location():
    payload, _fmt, _exit = _run(
        [
            "improve-placement",
            "--artifact-type",
            "spec",
            "--proposed-path",
            "docs/999-should-be-a-spec.md",
            "--format",
            "json",
        ]
    )
    assert payload["lifecycle"]["status"] == "blocked"
    assert payload["placement"]["in_canonical_location"] is False
    assert payload["placement"]["recommended_path"] == "specs/999-should-be-a-spec.md"


def test_placement_rejects_ad_hoc_docs_root_files():
    """Structure rule: docs/ has exactly four categories; ad-hoc files at
    its root (the RESEARCH.md/MARKET.md legacy violations AGENTS.md names)
    must never be recommended as a valid placement."""
    payload, _fmt, _exit = _run(
        [
            "improve-placement",
            "--artifact-type",
            "docs",
            "--proposed-path",
            "docs/NEW_NOTES.md",
            "--format",
            "json",
        ]
    )
    assert payload["lifecycle"]["status"] == "blocked"
    assert payload["placement"]["recommended_path"] is None
    assert "guidance" in payload["placement"]


def test_placement_rejects_spec_in_a_subdirectory():
    payload, _fmt, _exit = _run(
        [
            "improve-placement",
            "--artifact-type",
            "spec",
            "--proposed-path",
            "specs/nested/999-idea.md",
            "--format",
            "json",
        ]
    )
    assert payload["lifecycle"]["status"] == "blocked"
    assert payload["placement"]["in_canonical_location"] is False


def test_placement_never_creates_a_directory_on_disk(tmp_path):
    """Direct unit-level proof that the fallback-path recommender is
    read-only, independent of whether every schema-declared artifact
    type's root directory already happens to exist in this repository."""
    target_root = tmp_path / "does-not-exist-yet"
    assert not target_root.exists()
    cli_axi._recommended_new_path(tmp_path, "does-not-exist-yet", Path("thing.md"))
    assert not target_root.exists()


def test_placement_absolute_path_never_touches_the_host_filesystem():
    payload, _fmt, exit_code = _run(
        [
            "improve-placement",
            "--artifact-type",
            "spec",
            "--proposed-path",
            "/etc/passwd",
            "--format",
            "json",
        ]
    )
    assert exit_code == 0
    assert payload["placement"]["in_canonical_location"] is False
    assert payload["placement"]["proposed_file_exists"] is False
    assert payload["placement"]["duplicate_hits"] == []


def test_placement_path_traversal_is_rejected_not_resolved():
    payload, _fmt, _exit = _run(
        [
            "improve-placement",
            "--artifact-type",
            "spec",
            "--proposed-path",
            "../../etc/passwd",
            "--format",
            "json",
        ]
    )
    assert payload["placement"]["in_canonical_location"] is False
    assert payload["placement"]["proposed_file_exists"] is False


def test_placement_command_makes_no_repository_changes():
    before = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True
    ).stdout
    _run(
        [
            "improve-placement",
            "--artifact-type",
            "playbook",
            "--proposed-path",
            "docs/playbooks/does-not-exist-999.md",
            "--format",
            "json",
        ]
    )
    after = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True
    ).stdout
    assert before == after


# ---------------------------------------------------------------------------
# 5. Negative tests: evaluator mutation, private/raw-content export,
#    automatic promotion, external egress, unsupported placement
# ---------------------------------------------------------------------------


def test_refuses_evaluator_mutation_via_intake_or_run():
    before = CASES_PATH.read_bytes()
    _run(["improve-intake", "some gap", "--admitted-by", "x", "--format", "json"])
    _run(["improve-run", "--format", "json"])
    assert CASES_PATH.read_bytes() == before


def test_refuses_private_or_raw_content_export_in_scorecard():
    payload, _fmt, _exit = _run(["improve-run", "--scorecard", "--format", "json"])
    serialized = json.dumps(payload["scorecard"])
    assert "synthetic/exact.txt" not in serialized
    assert set(payload["scorecard"]["scores"].keys()) == {
        "cases_total",
        "cases_passed",
        "cases_failed",
        "cases_errored",
        "pass_rate",
        "comparative_cases_total",
        "status_quo_control",
        "corpus_trust",
    }


def test_refuses_private_or_raw_content_export_via_intake_summary_truncation():
    secret_like = "sk-live-should-not-leak " * 20
    with pytest.raises(cli_axi.UsageError, match="credential-like"):
        _run(["improve-intake", secret_like, "--admitted-by", "x", "--format", "json"])


def test_refuses_automatic_promotion_regardless_of_outcome():
    payload, _fmt, _exit = _run(["improve-run", "--format", "json"])
    assert payload["lifecycle"]["promotion"]["allowed"] is False
    assert payload["lifecycle"]["promotion"]["status"] == "human_review_required"


def test_refuses_external_egress_by_default(monkeypatch):
    monkeypatch.setenv("VOYAGE_API_KEY", "sk-should-never-be-used")
    payload, _fmt, _exit = _run(["improve-run", "--format", "json"])
    assert payload["run"]["egress_allowed"] is False
    assert payload["run"]["semantic_allowed"] is False
    serialized = json.dumps(payload)
    assert "sk-should-never-be-used" not in serialized


def test_refuses_unsupported_placement_artifact_type_as_usage_error():
    with pytest.raises(cli_axi.UsageError, match="invalid value 'not-a-real-type'"):
        _run(
            [
                "improve-placement",
                "--artifact-type",
                "not-a-real-type",
                "--proposed-path",
                "specs/x.md",
            ]
        )


def test_e2e_unsupported_placement_type_exits_2():
    result = _subprocess_holus(
        ["improve-placement", "--artifact-type", "not-a-real-type", "--proposed-path", "specs/x.md"]
    )
    assert result.returncode == 2


def test_naive_status_quo_comparator_still_not_imported_by_production_cli():
    """Extends the spec-017 guarantee: the loop's new commands must not
    reintroduce an import of the frozen status-quo-only comparator."""
    source = Path(cli_axi.__file__).read_text(encoding="utf-8")
    assert "_naive_concatenate_then_slice" not in source
