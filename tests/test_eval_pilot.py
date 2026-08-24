"""Tests for the Holusight safe continuous-evaluation pilot (spec 017).

See specs/017-holusight-safe-continuous-evaluation-pilot.md for the design
record and src/codesight/eval_pilot.py for the module these tests exercise.
Covers, per the launch checklist: frozen-case provenance, evaluator
isolation, status-quo comparison, no-egress/no-key defaults, aggregate-only
Fleet export, candidate lineage with no raw content, failed-candidate
retention, and derived-state delete/rebuild equivalence.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from codesight import eval_pilot

REPO_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = eval_pilot.DEFAULT_CASES_PATH


def _lineage(candidate_id: str = "test-candidate") -> eval_pilot.CandidateLineage:
    return eval_pilot.CandidateLineage(
        candidate_id=candidate_id,
        repo_commit="abc123def4567890abc123def4567890abc123d",
        workflow="test",
        tool="pytest",
        model=None,
    )


# ---------------------------------------------------------------------------
# 1. Frozen-case provenance
# ---------------------------------------------------------------------------


def test_frozen_case_corpus_exists_and_is_nonempty():
    assert CASES_PATH.exists()
    cases = eval_pilot.load_cases(CASES_PATH)
    assert len(cases) >= 4


def test_every_frozen_case_has_full_provenance():
    cases = eval_pilot.load_cases(CASES_PATH)
    for case in cases:
        provenance = case["provenance"]
        assert provenance["origin"] in {
            "reproduced_usage_gap",
            "spec_documented_finding",
            "spec_documented_contract",
        }
        assert provenance["description"]
        assert provenance["admitted_by"]
        assert provenance["admitted_at"]


def test_provider_starvation_case_cites_the_real_fix_commit():
    cases = {c["case_id"]: c for c in eval_pilot.load_cases(CASES_PATH)}
    case = cases["cli-axi-provider-starvation-display-quota"]
    assert "e516db769f44f0b9b71c23216bc19b04d5219a22" in case["provenance"]["fix_ref"]
    assert case["provenance"]["origin"] == "reproduced_usage_gap"


def test_load_cases_rejects_case_missing_provenance_field(tmp_path):
    bad = tmp_path / "cases.jsonl"
    bad.write_text(
        json.dumps(
            {
                "schema_version": eval_pilot.SCHEMA_CASE,
                "case_id": "incomplete",
                "family": "regression",
                "kind": "regression",
                "provenance": {"origin": "spec_documented_contract", "description": "x"},
                "grader": "grade_no_egress_default",
                "fixture": {},
                "expected": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing required provenance"):
        eval_pilot.load_cases(bad)


def test_load_cases_rejects_unknown_grader(tmp_path):
    bad = tmp_path / "cases.jsonl"
    bad.write_text(
        json.dumps(
            {
                "schema_version": eval_pilot.SCHEMA_CASE,
                "case_id": "unknown-grader",
                "family": "regression",
                "kind": "regression",
                "provenance": {
                    "origin": "spec_documented_contract",
                    "description": "x",
                    "admitted_by": "human",
                    "admitted_at": "2026-08-23",
                },
                "grader": "grade_does_not_exist",
                "fixture": {},
                "expected": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown"):
        eval_pilot.load_cases(bad)


# ---------------------------------------------------------------------------
# 2. Evaluator isolation (candidates cannot modify their evaluator)
# ---------------------------------------------------------------------------


def test_run_pilot_never_writes_to_the_frozen_case_file():
    before_bytes = CASES_PATH.read_bytes()
    before_mtime = CASES_PATH.stat().st_mtime_ns

    eval_pilot.run_pilot(REPO_ROOT, cases_path=CASES_PATH, lineage=_lineage())

    assert CASES_PATH.read_bytes() == before_bytes
    assert CASES_PATH.stat().st_mtime_ns == before_mtime


def test_run_pilot_works_when_case_file_is_read_only(tmp_path):
    """A run must not require write access to its own evaluator input --
    proof, not just inspection, that the runner is structurally read-only
    w.r.t. the frozen case corpus."""
    import shutil

    copy_path = tmp_path / "cases.jsonl"
    shutil.copy(CASES_PATH, copy_path)
    copy_path.chmod(0o444)
    try:
        result = eval_pilot.run_pilot(REPO_ROOT, cases_path=copy_path, lineage=_lineage())
        assert result.counts["total"] >= 4
    finally:
        copy_path.chmod(0o644)


def test_cases_file_hash_recorded_and_detects_edits(tmp_path):
    import shutil

    copy_path = tmp_path / "cases.jsonl"
    shutil.copy(CASES_PATH, copy_path)

    result_before = eval_pilot.run_pilot(REPO_ROOT, cases_path=copy_path, lineage=_lineage())

    # Simulate a candidate silently editing its own evaluator input --
    # this must change the recorded hash, making the tamper visible.
    with copy_path.open("a") as fh:
        fh.write("\n")
    result_after = eval_pilot.run_pilot(REPO_ROOT, cases_path=copy_path, lineage=_lineage())

    assert result_before.cases_file_hash != result_after.cases_file_hash
    assert result_before.cases_file_hash == eval_pilot.cases_file_hash(CASES_PATH)


def test_naive_status_quo_comparator_is_not_imported_by_production_cli():
    """The frozen pre-fix comparator must stay a pilot-only fixture --
    production cli_axi must never call it."""
    import codesight.cli_axi as cli_axi_module

    source = Path(cli_axi_module.__file__).read_text(encoding="utf-8")
    assert "_naive_concatenate_then_slice" not in source


# ---------------------------------------------------------------------------
# 3. Status-quo comparison (mandatory control)
# ---------------------------------------------------------------------------


def test_comparative_case_reports_both_candidate_and_status_quo_verdicts():
    result = eval_pilot.run_pilot(REPO_ROOT, cases_path=CASES_PATH, lineage=_lineage())
    comparative = [g for g in result.grades if g.kind == "comparative"]
    assert comparative
    for grade in comparative:
        assert grade.status_quo_verdict is not None


def test_status_quo_control_is_included_whenever_comparative_cases_exist():
    result = eval_pilot.run_pilot(REPO_ROOT, cases_path=CASES_PATH, lineage=_lineage())
    assert result.status_quo_control == "included"
    assert result.counts["comparative_total"] > 0
    assert (
        result.counts["comparative_with_status_quo_verdict"] == result.counts["comparative_total"]
    )


def test_status_quo_control_not_applicable_when_no_comparative_cases(tmp_path):
    only_regression = tmp_path / "cases.jsonl"
    cases = eval_pilot.load_cases(CASES_PATH)
    regression_only = [c for c in cases if c["kind"] == "regression"]
    only_regression.write_text(
        "\n".join(json.dumps(c) for c in regression_only) + "\n", encoding="utf-8"
    )
    result = eval_pilot.run_pilot(REPO_ROOT, cases_path=only_regression, lineage=_lineage())
    assert result.status_quo_control == "not_applicable"
    assert result.counts["comparative_total"] == 0


def test_persisted_result_schema_rejects_unknown_fields_and_closed_vocabularies():
    payload = eval_pilot.run_pilot(REPO_ROOT, cases_path=CASES_PATH, lineage=_lineage()).model_dump(
        mode="json"
    )
    comparative_index = next(
        index for index, grade in enumerate(payload["grades"]) if grade["kind"] == "comparative"
    )

    invalid_payloads = []
    unknown_result = json.loads(json.dumps(payload))
    unknown_result["unexpected_result_field"] = True
    invalid_payloads.append(unknown_result)
    unknown_grade = json.loads(json.dumps(payload))
    unknown_grade["grades"][0]["unexpected_grade_field"] = True
    invalid_payloads.append(unknown_grade)
    unknown_count = json.loads(json.dumps(payload))
    unknown_count["counts"]["unexpected_count"] = 0
    invalid_payloads.append(unknown_count)
    unknown_lineage = json.loads(json.dumps(payload))
    unknown_lineage["lineage"]["unexpected_lineage_field"] = True
    invalid_payloads.append(unknown_lineage)
    invalid_verdict = json.loads(json.dumps(payload))
    invalid_verdict["grades"][0]["verdict"] = "not-a-verdict"
    invalid_payloads.append(invalid_verdict)
    invalid_status_quo_verdict = json.loads(json.dumps(payload))
    invalid_status_quo_verdict["grades"][comparative_index]["status_quo_verdict"] = "unknown"
    invalid_payloads.append(invalid_status_quo_verdict)
    invalid_status_quo_control = json.loads(json.dumps(payload))
    invalid_status_quo_control["status_quo_control"] = "unknown"
    invalid_payloads.append(invalid_status_quo_control)
    invalid_corpus_trust = json.loads(json.dumps(payload))
    invalid_corpus_trust["corpus_trust"] = "unknown"
    invalid_payloads.append(invalid_corpus_trust)

    for invalid_payload in invalid_payloads:
        with pytest.raises(ValueError):
            eval_pilot.PilotRunResult.model_validate(invalid_payload)


def test_result_validation_requires_exact_counts_and_complete_partition():
    payload = eval_pilot.run_pilot(REPO_ROOT, cases_path=CASES_PATH, lineage=_lineage()).model_dump(
        mode="json"
    )
    missing_count = json.loads(json.dumps(payload))
    del missing_count["counts"]["errored"]
    with pytest.raises(ValueError):
        eval_pilot.PilotRunResult.model_validate(missing_count)

    partition_mismatch = json.loads(json.dumps(payload))
    partition_mismatch["counts"]["passed"] += 1
    partition_mismatch["result_digest"] = eval_pilot.canonical_result_digest(partition_mismatch)
    parsed = eval_pilot.PilotRunResult.model_validate(partition_mismatch)
    with pytest.raises(ValueError, match="complete partition"):
        eval_pilot._validate_result(parsed)


def test_display_quota_candidate_beats_the_status_quo_comparator():
    """The concrete demonstration: the shipped fix (candidate) must pass
    while the frozen pre-fix comparator (status quo) reproduces the
    historically-confirmed starvation on the same synthetic fixture."""
    cases = {c["case_id"]: c for c in eval_pilot.load_cases(CASES_PATH)}
    case = cases["cli-axi-provider-starvation-display-quota"]
    ctx = eval_pilot.RunContext(repo_root=str(REPO_ROOT))
    grade = eval_pilot.grade_display_quota_case(case, REPO_ROOT, ctx)
    assert grade.verdict == "pass"
    assert grade.status_quo_verdict == "pass"  # the comparator still reproduces the old bug


# ---------------------------------------------------------------------------
# 4. No-egress / no-key defaults
# ---------------------------------------------------------------------------


def test_no_egress_default_case_passes_deterministically():
    cases = {c["case_id"]: c for c in eval_pilot.load_cases(CASES_PATH)}
    case = cases["axi-providers-no-egress-by-default"]
    ctx = eval_pilot.RunContext(repo_root=str(REPO_ROOT))
    grade = eval_pilot.grade_no_egress_default(case, REPO_ROOT, ctx)
    assert grade.verdict == "pass"


def test_run_pilot_default_does_not_allow_egress_or_semantic():
    result = eval_pilot.run_pilot(REPO_ROOT, cases_path=CASES_PATH, lineage=_lineage())
    assert result.egress_allowed is False
    assert result.semantic_allowed is False


def test_run_pilot_skips_semantic_required_cases_without_opt_in(tmp_path):
    semantic_case = {
        "schema_version": eval_pilot.SCHEMA_CASE,
        "case_id": "would-need-semantic",
        "family": "regression",
        "kind": "regression",
        "provenance": {
            "origin": "spec_documented_contract",
            "description": "x",
            "admitted_by": "human",
            "admitted_at": "2026-08-23",
        },
        "grader": "grade_no_egress_default",
        "fixture": {},
        "expected": {
            "key_stripped_without_allow_egress": True,
            "key_restored_after_context_exit": True,
        },
        "requires_semantic": True,
    }
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps(semantic_case) + "\n", encoding="utf-8")
    result = eval_pilot.run_pilot(
        REPO_ROOT, cases_path=path, lineage=_lineage(), allow_semantic=False
    )
    assert result.grades[0].verdict == "error"
    assert "allow-semantic" in result.grades[0].detail


def test_run_pilot_never_reads_a_real_voyage_key_by_accident(monkeypatch):
    monkeypatch.setenv("VOYAGE_API_KEY", "sk-should-never-leak-anywhere")
    result = eval_pilot.run_pilot(REPO_ROOT, cases_path=CASES_PATH, lineage=_lineage())
    serialized = json.dumps(result.model_dump(mode="json"))
    assert "sk-should-never-leak-anywhere" not in serialized


# ---------------------------------------------------------------------------
# 5. Aggregate-only Fleet export
# ---------------------------------------------------------------------------


def test_aggregate_scorecard_shape():
    result = eval_pilot.run_pilot(REPO_ROOT, cases_path=CASES_PATH, lineage=_lineage())
    scorecard = eval_pilot.build_pilot_aggregate_scorecard(
        result, repo="holusight", repo_commit=result.subject.commit or "unknown"
    )
    assert scorecard["schema"] == "fleet.eval_scorecard.v1.2"
    assert scorecard["gate_decision"] in {"pass", "fail", "hold"}
    assert scorecard["cross_project_metrics"]["hidden_correctness"]["source"] == "domain_evaluator"
    assert scorecard["cross_project_metrics"]["total_cost_usd"] == 0.0
    assert re.match(r"^sha256:[0-9a-f]{64}$", scorecard["result_hash"])
    assert re.match(r"^sha256:[0-9a-f]{64}$", scorecard["fixture_set_hash"])
    # the non-negotiable clause: gate_decision pass implies hidden_correctness pass
    if scorecard["gate_decision"] == "pass":
        assert scorecard["cross_project_metrics"]["hidden_correctness"]["status"] == "pass"


def test_aggregate_scorecard_contains_no_raw_case_content():
    result = eval_pilot.run_pilot(REPO_ROOT, cases_path=CASES_PATH, lineage=_lineage())
    scorecard = eval_pilot.build_pilot_aggregate_scorecard(
        result, repo="holusight", repo_commit=result.subject.commit or "unknown"
    )
    serialized = json.dumps(scorecard)
    # synthetic marker strings used only inside grade.detail must never
    # leak into the aggregate-only export
    assert "synthetic/exact.txt" not in serialized
    assert "docs/decisions/0006" not in serialized
    assert "dangling=" not in serialized
    # only counts/rates/hashes/gate fields -- no free-text case detail
    assert set(scorecard["scores"].keys()) == {
        "cases_total",
        "cases_passed",
        "cases_failed",
        "cases_errored",
        "pass_rate",
        "comparative_cases_total",
        "status_quo_control",
        "corpus_trust",
    }


def test_pilot_domain_result_summary_matches_fleet_smoke_precedent_shape():
    from codesight.fleet_scorecard import domain_result_summary

    result = eval_pilot.run_pilot(REPO_ROOT, cases_path=CASES_PATH, lineage=_lineage())
    summary = eval_pilot.pilot_domain_result_summary(result)
    reference = domain_result_summary(hidden_correctness_status="pass", detail="x", scores={})
    assert set(summary.keys()) == set(reference.keys())
    assert summary["hidden_correctness"]["source"] == "domain_evaluator"


def test_fleet_manifest_entrypoint_is_unchanged_by_this_pilot():
    """This pilot must not silently become the Fleet eval_entrypoint --
    that stays `just fleet-smoke` (spec 016), unchanged."""
    manifest_text = (REPO_ROOT / "agentic" / "manifest.yaml").read_text(encoding="utf-8")
    assert "command: just fleet-smoke" in manifest_text
    assert "eval-pilot" not in manifest_text or "eval_pilot" not in manifest_text.replace(
        "just fleet-smoke", ""
    ).replace("fleet_scorecard.py", "")


# ---------------------------------------------------------------------------
# 6. Candidate lineage with no raw content
# ---------------------------------------------------------------------------


def test_candidate_lineage_has_no_free_text_content_field():
    fields = set(eval_pilot.CandidateLineage.model_fields.keys())
    assert "prompt" not in fields
    assert "transcript" not in fields
    assert "content" not in fields
    assert fields == {
        "candidate_id",
        "repo_commit",
        "workflow",
        "tool",
        "model",
        "recorded_at",
        "repo_dirty",
        "evaluator_digest",
        "candidate_digest",
        "comparator_digest",
    }


def test_candidate_lineage_recorded_in_run_result():
    lineage = eval_pilot.CandidateLineage(
        candidate_id="candidate-42",
        repo_commit="deadbeef",
        workflow="crewmate",
        tool="eval_pilot-cli",
        model="claude-sonnet-5",
    )
    result = eval_pilot.run_pilot(REPO_ROOT, cases_path=CASES_PATH, lineage=lineage)
    assert result.lineage.candidate_id == "candidate-42"
    assert result.lineage.model == "claude-sonnet-5"


def test_grade_detail_never_contains_an_absolute_host_path():
    """Grade ``detail`` strings are free text surfaced in results/exports --
    they may legitimately be empty or repo-relative, but must never leak an
    absolute host filesystem path (which would expose machine-specific
    identity beyond this repository's own tracked content)."""
    result = eval_pilot.run_pilot(REPO_ROOT, cases_path=CASES_PATH, lineage=_lineage())
    home = str(Path.home())
    for grade in result.grades:
        assert home not in grade.detail
        assert str(REPO_ROOT) not in grade.detail


# ---------------------------------------------------------------------------
# 7. Failed-candidate retention (failures stay evidence, never rewrite truth)
# ---------------------------------------------------------------------------


def test_failing_grade_is_retained_in_run_result_not_dropped():
    bad_case = {
        "schema_version": eval_pilot.SCHEMA_CASE,
        "case_id": "deliberately-failing",
        "family": "regression",
        "kind": "regression",
        "provenance": {
            "origin": "spec_documented_contract",
            "description": "deliberately wrong expectation, for retention testing",
            "admitted_by": "human",
            "admitted_at": "2026-08-23",
        },
        "grader": "grade_no_egress_default",
        "fixture": {},
        "expected": {
            "key_stripped_without_allow_egress": False,
            "key_restored_after_context_exit": True,
        },
    }

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "cases.jsonl"
        path.write_text(json.dumps(bad_case) + "\n", encoding="utf-8")
        result = eval_pilot.run_pilot(REPO_ROOT, cases_path=path, lineage=_lineage())

    assert result.counts["total"] == 1
    assert result.counts["failed"] == 1
    assert len(result.grades) == 1
    assert result.grades[0].verdict == "fail"
    assert result.grades[0].case_id == "deliberately-failing"


def test_erroring_grader_is_retained_as_error_not_raised():
    broken_case = {
        "schema_version": eval_pilot.SCHEMA_CASE,
        "case_id": "missing-fixture-doc",
        "family": "regression",
        "kind": "regression",
        "provenance": {
            "origin": "spec_documented_finding",
            "description": "points at a document that does not exist",
            "admitted_by": "human",
            "admitted_at": "2026-08-23",
        },
        "grader": "grade_known_dangling_reference_case",
        "fixture": {
            "doc_path": "docs/decisions/9999-does-not-exist.md",
            "expected_dangling_token": "x",
        },
        "expected": {"must_be_dangling": True},
    }
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "cases.jsonl"
        path.write_text(json.dumps(broken_case) + "\n", encoding="utf-8")
        result = eval_pilot.run_pilot(REPO_ROOT, cases_path=path, lineage=_lineage())

    assert result.counts["errored"] == 1
    assert result.grades[0].verdict == "error"


def _always_fail(case, repo_root, ctx):
    return eval_pilot.CaseGrade(
        case_id=case["case_id"],
        family=case["family"],
        kind=case["kind"],
        verdict="fail",
        detail="forced failure for retention test",
        provenance_origin=case["provenance"]["origin"],
    )


def test_a_failing_run_does_not_mutate_the_frozen_case_expected_values():
    before = CASES_PATH.read_bytes()
    # Run the real corpus with a broken candidate wired via monkeypatched
    # grader, forcing at least one case to fail, and confirm the frozen
    # file's `expected` blocks are untouched afterward.
    original = eval_pilot.GRADERS["grade_no_egress_default"]
    try:
        eval_pilot.GRADERS["grade_no_egress_default"] = _always_fail
        result = eval_pilot.run_pilot(REPO_ROOT, cases_path=CASES_PATH, lineage=_lineage())
    finally:
        eval_pilot.GRADERS["grade_no_egress_default"] = original

    assert result.counts["failed"] >= 1
    assert CASES_PATH.read_bytes() == before


# ---------------------------------------------------------------------------
# 8. Derived-state delete/rebuild equivalence
# ---------------------------------------------------------------------------


def test_repeated_runs_over_the_same_content_are_equivalent():
    result_a = eval_pilot.run_pilot(REPO_ROOT, cases_path=CASES_PATH, lineage=_lineage("run-a"))
    result_b = eval_pilot.run_pilot(REPO_ROOT, cases_path=CASES_PATH, lineage=_lineage("run-b"))

    assert result_a.counts == result_b.counts
    assert result_a.cases_file_hash == result_b.cases_file_hash
    grades_a = {g.case_id: (g.verdict, g.status_quo_verdict) for g in result_a.grades}
    grades_b = {g.case_id: (g.verdict, g.status_quo_verdict) for g in result_b.grades}
    assert grades_a == grades_b


def test_consistency_case_survives_holusight_dir_delete_and_rebuild(tmp_path, monkeypatch):
    """Mirrors tests/test_fleet_smoke.py task 18: deleting derived state
    and rebuilding must reproduce the same verdict for unchanged content."""
    from codesight import consistency

    spec_path = tmp_path / "specs" / "001-alpha.md"
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text("# Alpha Feature\n\nImplemented by `src/pkg/mod.py`.\n", encoding="utf-8")
    impl_path = tmp_path / "src" / "pkg" / "mod.py"
    impl_path.parent.mkdir(parents=True)
    impl_path.write_text("VALUE = 1\n", encoding="utf-8")

    consistency.refresh(tmp_path)
    report_first = consistency.check_consistency(tmp_path, "specs/001-alpha.md")

    import shutil

    shutil.rmtree(tmp_path / ".holusight")

    consistency.refresh(tmp_path)
    report_second = consistency.check_consistency(tmp_path, "specs/001-alpha.md")

    assert report_first.status == report_second.status == consistency.ConsistencyStatus.UP_TO_DATE


# ---------------------------------------------------------------------------
# 9. CLI end-to-end (advisory only, no side effects)
# ---------------------------------------------------------------------------


def test_cli_run_exits_zero_on_all_pass(capsys):
    exit_code = eval_pilot.main(["run"])
    assert exit_code == 0
    captured = capsys.readouterr()
    # the run prints a multi-line indented JSON block followed by a final
    # single-line summary -- confirm the final line parses and is the
    # minimal domain-result contract
    last_line = [line for line in captured.out.splitlines() if line.strip()][-1]
    summary = json.loads(last_line)
    assert "hidden_correctness" in summary
    assert summary["hidden_correctness"]["source"] == "domain_evaluator"
