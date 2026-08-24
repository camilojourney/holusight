"""Tests for the immutable evaluation-subject binding closure (spec 021).

Closes gap G1 from the completeness gap-map review of specs 017-020: a pilot
evaluation result must bind to an immutable Git commit/tree subject, and
pre-promotion review must recompute every consequential linked artifact's
applicability against that subject at review time — a repository-relative
path is a locator, never identity. See:

- specs/021-holusight-evidence-subject-binding.md (governing design record)
- docs/decisions/0017-immutable-evaluation-subject-binding.md (decision record)
- src/codesight/eval_pilot.py (``EvaluationSubject``, ``_current_subject``)
- src/codesight/improvement_control.py (``_subject_applicability_blockers``)
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from codesight import eval_pilot, improvement_control

REPO_ROOT = Path(__file__).resolve().parents[1]


def _lineage(candidate_id: str = "subject-test") -> eval_pilot.CandidateLineage:
    return eval_pilot.CandidateLineage(
        candidate_id=candidate_id,
        repo_commit=eval_pilot._git_oid(REPO_ROOT, "HEAD"),
        workflow="test",
        tool="pytest",
    )


# ---------------------------------------------------------------------------
# 1. Unit: EvaluationSubject / _current_subject
# ---------------------------------------------------------------------------


def test_current_subject_resolves_real_commit_and_tree_for_this_repo():
    subject = eval_pilot._current_subject(REPO_ROOT, repo_dirty=False)
    assert subject.commit == eval_pilot._git_oid(REPO_ROOT, "HEAD")
    assert subject.tree == eval_pilot._git_oid(REPO_ROOT, "HEAD^{tree}")
    assert subject.clean is True
    assert subject.repository_id


def test_current_subject_is_never_clean_when_the_run_recorded_it_dirty():
    subject = eval_pilot._current_subject(REPO_ROOT, repo_dirty=True)
    assert subject.clean is False


def test_current_subject_has_no_commit_or_tree_outside_a_git_repository(tmp_path):
    subject = eval_pilot._current_subject(tmp_path, repo_dirty=False)
    assert subject.commit is None
    assert subject.tree is None
    # A non-Git directory must never read as a clean subject -- the prior
    # loophole this closure removes was treating "no git" as "not dirty".
    assert subject.clean is False
    assert subject.repository_id == "local-no-remote"


def test_branch_is_populated_but_plays_no_part_in_the_subject_model():
    subject = eval_pilot._current_subject(REPO_ROOT, repo_dirty=False)
    assert subject.branch is None or isinstance(subject.branch, str)
    assert "branch" in eval_pilot.EvaluationSubject.model_fields


# ---------------------------------------------------------------------------
# 2. Contract: PilotRunResult.subject is required, closed, and load-time
#    validated
# ---------------------------------------------------------------------------


def test_run_pilot_result_always_carries_a_real_resolvable_subject():
    """Independent of whether this dev worktree happens to be clean right
    now, a run against a real Git repo must always resolve a real commit and
    tree, and ``clean`` must exactly track the recorded ``repo_dirty`` flag."""
    result = eval_pilot.run_pilot(
        REPO_ROOT, cases_path=eval_pilot.DEFAULT_CASES_PATH, lineage=_lineage()
    )
    assert result.subject.commit == eval_pilot._git_oid(REPO_ROOT, "HEAD")
    assert result.subject.tree == eval_pilot._git_oid(REPO_ROOT, "HEAD^{tree}")
    assert result.subject.clean == (not result.lineage.repo_dirty)


def test_pilot_result_schema_rejects_an_unknown_subject_field():
    payload = eval_pilot.run_pilot(
        REPO_ROOT, cases_path=eval_pilot.DEFAULT_CASES_PATH, lineage=_lineage()
    ).model_dump(mode="json")
    payload["subject"]["unexpected_subject_field"] = True
    with pytest.raises(ValueError):
        eval_pilot.PilotRunResult.model_validate(payload)


def test_pilot_result_schema_rejects_a_malformed_commit_or_tree_oid():
    payload = eval_pilot.run_pilot(
        REPO_ROOT, cases_path=eval_pilot.DEFAULT_CASES_PATH, lineage=_lineage()
    ).model_dump(mode="json")
    payload["subject"]["commit"] = "not-a-git-oid"
    with pytest.raises(ValueError):
        eval_pilot.PilotRunResult.model_validate(payload)


def test_validate_result_rejects_a_result_whose_subject_is_not_clean():
    payload = eval_pilot.run_pilot(
        REPO_ROOT, cases_path=eval_pilot.DEFAULT_CASES_PATH, lineage=_lineage()
    ).model_dump(mode="json")
    # Isolate the new subject check from the pre-existing repo_dirty check --
    # both must independently reject non-immutable evidence.
    payload["lineage"]["repo_dirty"] = False
    payload["subject"]["clean"] = False
    payload["result_digest"] = eval_pilot.canonical_result_digest(payload)
    parsed = eval_pilot.PilotRunResult.model_validate(payload)
    with pytest.raises(ValueError, match="clean, resolvable immutable Git subject"):
        eval_pilot._validate_result(parsed)


def test_validate_result_rejects_a_result_with_no_resolvable_commit():
    payload = eval_pilot.run_pilot(
        REPO_ROOT, cases_path=eval_pilot.DEFAULT_CASES_PATH, lineage=_lineage()
    ).model_dump(mode="json")
    payload["lineage"]["repo_dirty"] = False
    payload["subject"]["commit"] = None
    payload["subject"]["tree"] = None
    payload["subject"]["clean"] = False
    payload["result_digest"] = eval_pilot.canonical_result_digest(payload)
    parsed = eval_pilot.PilotRunResult.model_validate(payload)
    with pytest.raises(ValueError, match="clean, resolvable immutable Git subject"):
        eval_pilot._validate_result(parsed)


# ---------------------------------------------------------------------------
# 3. Unit: _stage() demotes away from "evaluated" for the new blocker prefix
# ---------------------------------------------------------------------------


def test_stage_demotes_away_from_evaluated_for_a_changed_consequential_artifact():
    links = {role: ["x"] for role in improvement_control.LINK_ROLES}
    blockers = [
        {"code": "changed_consequential_artifact", "evidence": "x", "role": "implementation"}
    ]
    assert improvement_control._stage("evaluated", links, blockers) == "implemented"


# ---------------------------------------------------------------------------
# 4. Public-command E2E: build a genuinely evaluated, committed repo, then
#    prove every G1 acceptance scenario through `holus improve-review`.
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Exercise the installed public console command, never an in-process handler."""
    public_command = Path(sys.executable).with_name("holus")
    assert public_command.is_file(), f"public holus command missing: {public_command}"
    return subprocess.run(
        [str(public_command), *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


def _case() -> dict:
    return {
        "schema_version": eval_pilot.SCHEMA_CASE,
        "case_id": "subject-binding-case",
        "family": "regression",
        "kind": "regression",
        "provenance": {
            "origin": "spec_documented_contract",
            "description": "evidence subject binding e2e",
            "admitted_by": "human",
            "admitted_at": "2026-08-24",
        },
        "grader": "grade_no_egress_default",
        "fixture": {},
        "expected": {
            "key_stripped_without_allow_egress": True,
            "key_restored_after_context_exit": True,
        },
    }


def _build_evaluated_repo(tmp_path: Path) -> tuple[Path, dict]:
    """A committed repo with a genuinely evaluated, pre-promotion-ready manifest."""
    repo = tmp_path
    (repo / ".gitignore").write_text(".holusight/\n", encoding="utf-8")
    (repo / "src/codesight").mkdir(parents=True)
    (repo / "src/codesight/eval_pilot.py").write_text("protected evaluator\n", encoding="utf-8")
    (repo / "src/codesight/implementation.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests/test_implementation.py").write_text(
        "def test_value():\n    assert True\n", encoding="utf-8"
    )
    (repo / "docs").mkdir()
    (repo / "docs/README.md").write_text("documentation\n", encoding="utf-8")
    (repo / "specs").mkdir()
    (repo / "specs/governing.md").write_text("**Status:** Evaluated\n", encoding="utf-8")
    cases_dir = repo / "tests/fixtures"
    cases_dir.mkdir()
    (cases_dir / "holusight_eval_pilot_cases.jsonl").write_text(
        json.dumps(_case()) + "\n", encoding="utf-8"
    )

    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "subject-e2e@example.test")
    _git(repo, "config", "user.name", "Subject E2E")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")

    result_relative = ".holusight/improvement-results/subject-result.json"
    run = _run(
        repo,
        "improve-run",
        "--cases",
        "tests/fixtures/holusight_eval_pilot_cases.jsonl",
        "--candidate-id",
        "subject-change",
        "--output",
        result_relative,
        "--format",
        "json",
    )
    assert run.returncode == 0, run.stdout

    links = {
        "governing": ["specs/governing.md"],
        "implementation": ["src/codesight/implementation.py"],
        "tests": ["tests/test_implementation.py"],
        "documentation": ["docs/README.md"],
        "evaluation_case": ["tests/fixtures/holusight_eval_pilot_cases.jsonl"],
        "evaluation_result": [result_relative],
    }
    manifest = {
        "schema_version": improvement_control.CHANGE_SCHEMA,
        "change_id": "subject-change",
        "classification": "evaluated",
        "classification_evidence": "evaluated",
        "structured_sections": ["context", "evidence", "decision"],
        "links": links,
        "link_hashes": {path: _sha256(repo / path) for paths in links.values() for path in paths},
        "lineage": {"candidate_id": "subject-change", "workflow": "e2e", "tool": "pytest"},
        "proposed_artifacts": [],
    }
    manifest_path = repo / "specs/subject.change.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return repo, {
        "manifest_path": manifest_path,
        "result_path": repo / result_relative,
        "result_relative": result_relative,
        "links": links,
    }


def _review(repo: Path) -> dict:
    result = _run(
        repo,
        "improve-review",
        "specs/subject.change.json",
        "--phase",
        "pre_promotion",
        "--format",
        "json",
    )
    assert result.returncode == 0, result.stdout
    return json.loads(result.stdout)["review"]


def test_clean_evaluated_result_reaches_human_promotion_review(tmp_path):
    repo, _ctx = _build_evaluated_repo(tmp_path)
    review = _review(repo)
    assert review["stage"] == "evaluated"
    assert review["blockers"] == []
    assert review["next_permitted_action"] == "human_promotion_review"
    assert review["promotion"]["allowed"] is False


def test_later_unrelated_commit_with_identical_consequential_blobs_stays_applicable(tmp_path):
    """A manifest-only descendant commit remains applicable exactly when every
    consequential artifact blob is unchanged -- commit recency plays no part."""
    repo, _ctx = _build_evaluated_repo(tmp_path)
    (repo / "README.md").write_text("unrelated change\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "unrelated later commit")

    review = _review(repo)
    assert review["stage"] == "evaluated"
    assert review["next_permitted_action"] == "human_promotion_review"


def test_changed_implementation_after_result_is_indeterminate_never_ready(tmp_path):
    """Acceptance: change implementation and update only the manifest hash
    without rerunning -- pre-promotion review must return a subject mismatch
    and never become ready. Also covers "equal path, differing blob"."""
    repo, ctx = _build_evaluated_repo(tmp_path)
    impl = repo / "src/codesight/implementation.py"
    impl.write_text("VALUE = 2  # changed after evaluation\n", encoding="utf-8")
    manifest = json.loads(ctx["manifest_path"].read_text(encoding="utf-8"))
    manifest["link_hashes"]["src/codesight/implementation.py"] = _sha256(impl)
    ctx["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")

    review = _review(repo)
    codes = {item["code"] for item in review["blockers"]}
    assert "changed_consequential_artifact" in codes
    assert review["stage"] != "evaluated"
    assert review["next_permitted_action"] != "human_promotion_review"
    assert review["promotion"]["allowed"] is False


def test_tampered_tree_oid_is_indeterminate(tmp_path):
    """Acceptance: a result whose commit exists but whose tree OID is wrong
    must be indeterminate."""
    repo, ctx = _build_evaluated_repo(tmp_path)
    result = json.loads(ctx["result_path"].read_text(encoding="utf-8"))
    result["subject"]["tree"] = "0" * 40
    result["result_digest"] = eval_pilot.canonical_result_digest(result)
    ctx["result_path"].write_text(json.dumps(result), encoding="utf-8")
    manifest = json.loads(ctx["manifest_path"].read_text(encoding="utf-8"))
    manifest["link_hashes"][ctx["result_relative"]] = _sha256(ctx["result_path"])
    ctx["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")

    review = _review(repo)
    codes = {item["code"] for item in review["blockers"]}
    assert "wrong_tree_oid" in codes
    assert review["next_permitted_action"] != "human_promotion_review"


def test_unknown_evaluated_commit_is_indeterminate(tmp_path):
    """A tampered commit that never existed must be stale, not silently
    trusted."""
    repo, ctx = _build_evaluated_repo(tmp_path)
    result = json.loads(ctx["result_path"].read_text(encoding="utf-8"))
    result["subject"]["commit"] = "1234567890abcdef1234567890abcdef12345678"
    result["result_digest"] = eval_pilot.canonical_result_digest(result)
    ctx["result_path"].write_text(json.dumps(result), encoding="utf-8")
    manifest = json.loads(ctx["manifest_path"].read_text(encoding="utf-8"))
    manifest["link_hashes"][ctx["result_relative"]] = _sha256(ctx["result_path"])
    ctx["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")

    review = _review(repo)
    codes = {item["code"] for item in review["blockers"]}
    assert "stale_evaluation_subject" in codes
    assert review["next_permitted_action"] != "human_promotion_review"


def test_dirty_worktree_evaluation_can_never_become_ready(tmp_path):
    """Acceptance: dirty worktree evaluation must never become pass."""
    repo, ctx = _build_evaluated_repo(tmp_path)
    (repo / "untracked.txt").write_text("uncommitted\n", encoding="utf-8")
    rerun = _run(
        repo,
        "improve-run",
        "--cases",
        "tests/fixtures/holusight_eval_pilot_cases.jsonl",
        "--candidate-id",
        "subject-change",
        "--output",
        ctx["result_relative"],
        "--format",
        "json",
    )
    assert rerun.returncode == 0, rerun.stdout
    dirty_result = json.loads(ctx["result_path"].read_text(encoding="utf-8"))
    assert dirty_result["subject"]["clean"] is False
    assert dirty_result["lineage"]["repo_dirty"] is True

    manifest = json.loads(ctx["manifest_path"].read_text(encoding="utf-8"))
    manifest["link_hashes"][ctx["result_relative"]] = _sha256(ctx["result_path"])
    ctx["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")

    review = _review(repo)
    codes = {item["code"] for item in review["blockers"]}
    assert "invalid_evaluation_result" in codes
    assert review["stage"] != "evaluated"
    assert review["next_permitted_action"] != "human_promotion_review"


def test_renamed_implementation_path_after_result_is_indeterminate(tmp_path):
    """Acceptance: rename/rebase cases must create a new subject -- path is a
    locator, not identity. A rename with a matching current-bytes hash must
    still be blocked, because it never existed at the evaluated commit."""
    repo, ctx = _build_evaluated_repo(tmp_path)
    old_path = repo / "src/codesight/implementation.py"
    new_path = repo / "src/codesight/renamed_implementation.py"
    old_path.rename(new_path)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "rename implementation")

    manifest = json.loads(ctx["manifest_path"].read_text(encoding="utf-8"))
    manifest["links"]["implementation"] = ["src/codesight/renamed_implementation.py"]
    manifest["link_hashes"].pop("src/codesight/implementation.py")
    manifest["link_hashes"]["src/codesight/renamed_implementation.py"] = _sha256(new_path)
    ctx["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")

    review = _review(repo)
    codes = {item["code"] for item in review["blockers"]}
    assert "dangling_consequential_artifact" in codes
    assert review["next_permitted_action"] != "human_promotion_review"


# ---------------------------------------------------------------------------
# 5. Unit: _subject_applicability_blockers and its small git helpers directly
# ---------------------------------------------------------------------------


def test_subject_applicability_blockers_flags_wrong_repository_identity(tmp_path):
    repo, ctx = _build_evaluated_repo(tmp_path)
    result = eval_pilot.PilotRunResult.model_validate(
        json.loads(ctx["result_path"].read_text(encoding="utf-8"))
    )
    tampered = result.model_copy(
        update={
            "subject": result.subject.model_copy(
                update={"repository_id": "https://example.test/other.git"}
            )
        }
    )
    manifest = json.loads(ctx["manifest_path"].read_text(encoding="utf-8"))
    blockers = improvement_control._subject_applicability_blockers(repo, manifest, tampered)
    assert {
        "code": "wrong_repository_subject",
        "evidence": "https://example.test/other.git",
        "role": "evaluation_result",
    } in blockers


def test_worktree_blob_oid_is_none_for_a_missing_path(tmp_path):
    _git(tmp_path, "init", "-q")
    assert improvement_control._worktree_blob_oid(tmp_path, "does/not/exist.py") is None
