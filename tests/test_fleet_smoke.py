"""Fleet v1.2 protocol pilot: local, no-spend smoke suite.

This IS ``agentic/manifest.yaml``'s declared ``eval_entrypoint`` test
surface (invoked via ``just fleet-smoke`` -> ``python -m
codesight.fleet_scorecard smoke`` -> this file). See
``specs/016-fleet-v1.2-protocol-pilot.md`` for the design record and
``src/codesight/fleet_scorecard.py`` for the scorecard bridge these tests
exercise.

Scope, by design:

- Only the ``exact`` and ``structural`` consistency providers are ever
  exercised here. ``refresh()`` is always called with its default
  ``run_semantic=False``; nothing in this file passes ``run_semantic=True``
  or an ``embed_fn``. Task 5 asserts this directly.
- Every fixture is a synthetic repo built under ``tmp_path``. No test reads
  or writes this actual repository's own ``.holusight/`` state, and nothing
  here makes a network call -- task 15 asserts the resulting scorecard's
  own ``total_cost_usd`` is genuinely ``0.0``, not merely unmeasured.
- Tasks are numbered and independently runnable (`pytest -k task_07 ...`)
  so a partial run still reports which specific claims held.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from codesight import consistency
from codesight.consistency_store import ConsistencyStore
from codesight.fleet_scorecard import (
    SCHEMA_EVAL_SCORECARD,
    build_eval_scorecard,
    domain_result_summary,
)

_FAKE_COMMIT = "abc123def4567890abc123def4567890abc123d"  # 40 hex chars, well-formed


def _write(root: Path, rel_path: str, text: str) -> Path:
    full = root / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(text, encoding="utf-8")
    return full


def _minimal_repo(tmp_path: Path) -> Path:
    """A synthetic repo with one spec referencing one real impl file and
    one dangling reference -- same shape as test_consistency.py's fixture,
    kept local to this file so the smoke suite has no cross-file test
    dependency."""
    _write(
        tmp_path,
        "specs/001-alpha.md",
        "# Alpha Feature\n\nImplemented by `src/pkg/mod.py`.\n"
        "Also mentions `src/pkg/missing.py`, which does not exist.\n",
    )
    _write(tmp_path, "src/pkg/mod.py", "VALUE = 1\n")
    return tmp_path


def _scorecard_for(tmp_path: Path, mutate=None) -> dict:
    """Refresh, optionally mutate, check, and build a scorecard for
    specs/001-alpha.md in one synthetic repo."""
    _minimal_repo(tmp_path)
    consistency.refresh(tmp_path)
    if mutate:
        mutate(tmp_path)
    report = consistency.check_consistency(tmp_path, "specs/001-alpha.md")
    return build_eval_scorecard(report, repo="holusight-smoke", repo_commit=_FAKE_COMMIT)


# ---------------------------------------------------------------------------
# Task 1-2: exact provider
# ---------------------------------------------------------------------------


def test_task_01_exact_provider_resolves_real_reference(tmp_path):
    _minimal_repo(tmp_path)
    edges, dangling = consistency.extract_exact_references("specs/001-alpha.md", tmp_path)
    assert any(e.to_ref == "artifact:src/pkg/mod.py" for e in edges)


def test_task_02_exact_provider_flags_dangling_reference(tmp_path):
    _minimal_repo(tmp_path)
    _, dangling = consistency.extract_exact_references("specs/001-alpha.md", tmp_path)
    assert "src/pkg/missing.py" in dangling


# ---------------------------------------------------------------------------
# Task 3-4: structural provider partial-result survival
# ---------------------------------------------------------------------------


def test_task_03_structural_provider_degrades_when_graph_missing(tmp_path):
    """No graphify-out/graph.json at all: the structural provider must
    report unavailable, not raise."""
    _minimal_repo(tmp_path)
    index = consistency._load_structural_index(tmp_path)
    assert index.available is False
    stale, commit = consistency.structural_graph_freshness(index, tmp_path)
    assert stale is True
    assert commit is None
    # refresh() must still complete using exact-only edges.
    result = consistency.refresh(tmp_path)
    assert result.structural_graph_stale is True
    assert result.artifacts_scanned > 0


def test_task_04_structural_provider_degrades_when_graph_corrupt(tmp_path):
    """A corrupt (non-JSON) graphify-out/graph.json must also degrade to
    unavailable rather than raising -- this is the partial-result-survival
    case a real repo hits when Graphify tooling is unavailable mid-write."""
    _write(tmp_path, "graphify-out/graph.json", "{not valid json")
    _minimal_repo(tmp_path)
    index = consistency._load_structural_index(tmp_path)
    assert index.available is False
    result = consistency.refresh(tmp_path)
    assert result.structural_graph_stale is True
    assert result.artifacts_scanned > 0
    assert result.concepts == 1


# ---------------------------------------------------------------------------
# Task 5-6: provider scope discipline
# ---------------------------------------------------------------------------


def test_task_05_refresh_never_invokes_semantic_by_default(tmp_path):
    _minimal_repo(tmp_path)
    consistency.refresh(tmp_path)  # no run_semantic kwarg passed anywhere in this file
    store = ConsistencyStore(consistency.consistency_db_path(tmp_path))
    try:
        providers = {row["provider"] for row in store.all_edges()}
    finally:
        store.close()
    assert consistency.ProviderKind.SEMANTIC.value not in providers


def test_task_06_refresh_completes_with_exact_and_structural_only(tmp_path):
    _minimal_repo(tmp_path)
    result = consistency.refresh(tmp_path)
    store = ConsistencyStore(consistency.consistency_db_path(tmp_path))
    try:
        providers = {row["provider"] for row in store.all_edges()}
    finally:
        store.close()
    allowed = {consistency.ProviderKind.EXACT.value, consistency.ProviderKind.STRUCTURAL.value}
    assert providers <= allowed
    assert result.concepts == 1


# ---------------------------------------------------------------------------
# Task 7-10: the four consistency outcomes map to honest gate decisions
# ---------------------------------------------------------------------------


def test_task_07_check_up_to_date_maps_to_pass(tmp_path):
    scorecard = _scorecard_for(tmp_path)
    assert scorecard["gate_decision"] == "pass"
    assert scorecard["cross_project_metrics"]["hidden_correctness"]["status"] == "pass"


def test_task_08_check_spec_changed_maps_to_hold(tmp_path):
    def mutate(root):
        _write(
            root, "specs/001-alpha.md",
            "# Alpha Feature\n\nImplemented by `src/pkg/mod.py`. New sentence.\n"
            "Also mentions `src/pkg/missing.py`, which does not exist.\n",
        )

    scorecard = _scorecard_for(tmp_path, mutate)
    assert scorecard["gate_decision"] == "hold"
    assert scorecard["cross_project_metrics"]["hidden_correctness"]["status"] == "unknown"


def test_task_09_check_possible_drift_maps_to_fail(tmp_path):
    def mutate(root):
        _write(root, "src/pkg/mod.py", "VALUE = 999  # behavior changed\n")

    scorecard = _scorecard_for(tmp_path, mutate)
    assert scorecard["gate_decision"] == "fail"
    assert scorecard["cross_project_metrics"]["hidden_correctness"]["status"] == "fail"


def test_task_10_check_coordinated_change_maps_to_hold(tmp_path):
    def mutate(root):
        _write(
            root, "specs/001-alpha.md",
            "# Alpha Feature\n\nImplemented by `src/pkg/mod.py`. Updated together.\n"
            "Also mentions `src/pkg/missing.py`, which does not exist.\n",
        )
        _write(root, "src/pkg/mod.py", "VALUE = 3  # coordinated update\n")

    scorecard = _scorecard_for(tmp_path, mutate)
    assert scorecard["gate_decision"] == "hold"
    assert scorecard["cross_project_metrics"]["hidden_correctness"]["status"] == "unknown"


def test_task_11_unknown_concept_has_no_scorecard(tmp_path):
    _minimal_repo(tmp_path)
    consistency.refresh(tmp_path)
    report = consistency.check_consistency(tmp_path, "specs/does-not-exist.md")
    assert report.status == consistency.ConsistencyStatus.UNKNOWN_CONCEPT
    with pytest.raises(ValueError):
        build_eval_scorecard(report, repo="holusight-smoke", repo_commit=_FAKE_COMMIT)


# ---------------------------------------------------------------------------
# Task 12-17: scorecard shape matches the Fleet v1.2 contract, honestly
# ---------------------------------------------------------------------------


def test_task_12_scorecard_schema_is_v1_2(tmp_path):
    scorecard = _scorecard_for(tmp_path)
    assert scorecard["schema"] == SCHEMA_EVAL_SCORECARD == "fleet.eval_scorecard.v1.2"


def test_task_13_scorecard_hashes_match_fleet_pattern(tmp_path):
    scorecard = _scorecard_for(tmp_path)
    hash_re = r"^sha256:[0-9a-f]{64}$"
    for field in ("input_hash", "fixture_set_hash", "result_hash"):
        assert re.match(hash_re, scorecard[field]), scorecard[field]


def test_task_14_scorecard_repo_commit_matches_fleet_pattern(tmp_path):
    scorecard = _scorecard_for(tmp_path)
    assert re.match(r"^[0-9a-f]{7,40}$", scorecard["repo_commit"])


def test_task_15_scorecard_total_cost_is_zero_no_spend(tmp_path):
    scorecard = _scorecard_for(tmp_path)
    assert scorecard["cross_project_metrics"]["total_cost_usd"] == 0.0


def test_task_16_scorecard_artifacts_block_is_honestly_empty(tmp_path):
    scorecard = _scorecard_for(tmp_path)
    # additionalProperties:true and no required sub-field on `artifacts` in
    # the Fleet schema means {} is a valid, honest "produces none of these"
    # -- never a reference to a file this evaluator never wrote.
    assert scorecard["artifacts"] == {}


def test_task_17_gate_pass_implies_hidden_correctness_pass_invariant(tmp_path):
    """Self-check of the Fleet schema's own non-negotiable clause: for
    every one of the four outcomes, gate_decision == "pass" iff
    hidden_correctness.status == "pass". This proves the mapping table in
    fleet_scorecard.py can never produce the forbidden combination
    (gate_decision: pass without a passing hidden_correctness) by
    construction, across all four outcomes, not just the one exercised
    above."""
    _minimal_repo(tmp_path)
    consistency.refresh(tmp_path)
    for status in consistency.ConsistencyStatus:
        if status not in {
            consistency.ConsistencyStatus.UP_TO_DATE,
            consistency.ConsistencyStatus.SPEC_CHANGED_AWAITING_IMPLEMENTATION,
            consistency.ConsistencyStatus.POSSIBLE_UNDOCUMENTED_DRIFT,
            consistency.ConsistencyStatus.COORDINATED_CHANGE,
        }:
            continue
        report = consistency.ConsistencyReport(
            concept_id="specs/001-alpha.md",
            status=status,
            canonical_changed=False,
            linked_changed=[],
            linked_unchanged=[],
            notes="synthetic",
        )
        scorecard = build_eval_scorecard(report, repo="holusight-smoke", repo_commit=_FAKE_COMMIT)
        gate_pass = scorecard["gate_decision"] == "pass"
        hidden_pass = scorecard["cross_project_metrics"]["hidden_correctness"]["status"] == "pass"
        assert gate_pass == hidden_pass


# ---------------------------------------------------------------------------
# Task 18: .holusight/ delete/rebuild equivalence, in scorecard terms
# ---------------------------------------------------------------------------


def test_task_18_holusight_dir_delete_and_rebuild_yields_equivalent_scorecard(tmp_path):
    """.holusight/ is gitignored derived state, never canonical truth (see
    ARCHITECTURE.md). Deleting it and refreshing must reproduce an
    equivalent scorecard for the same on-disk content -- not merely an
    equivalent artifact count (already covered by test_consistency.py),
    but the same Fleet-shaped gate_decision and hidden_correctness that a
    caller would actually act on."""
    import shutil

    _minimal_repo(tmp_path)
    consistency.refresh(tmp_path)
    report_before = consistency.check_consistency(tmp_path, "specs/001-alpha.md")
    scorecard_before = build_eval_scorecard(
        report_before, repo="holusight-smoke", repo_commit=_FAKE_COMMIT
    )

    shutil.rmtree(tmp_path / ".holusight")
    assert not (tmp_path / ".holusight").exists()

    consistency.refresh(tmp_path)
    report_after = consistency.check_consistency(tmp_path, "specs/001-alpha.md")
    scorecard_after = build_eval_scorecard(
        report_after, repo="holusight-smoke", repo_commit=_FAKE_COMMIT
    )

    assert scorecard_after["gate_decision"] == scorecard_before["gate_decision"]
    assert (
        scorecard_after["cross_project_metrics"]["hidden_correctness"]
        == scorecard_before["cross_project_metrics"]["hidden_correctness"]
    )
    assert scorecard_after["scores"] == scorecard_before["scores"]
    # Content-derived hashes are deterministic functions of the same
    # concept_id/commit/linked-path set, so they must match too, even
    # though scorecard_id/trace_id (random per call) will not.
    assert scorecard_after["input_hash"] == scorecard_before["input_hash"]
    assert scorecard_after["fixture_set_hash"] == scorecard_before["fixture_set_hash"]
    assert scorecard_after["result_hash"] == scorecard_before["result_hash"]


# ---------------------------------------------------------------------------
# Task 19-20: the entrypoint's own domain-result contract
# ---------------------------------------------------------------------------


def test_task_19_domain_result_summary_last_line_is_parseable_json():
    """Mirrors run_repo_eval.py's parse_domain_result(): only the last
    non-blank line of stdout is considered, and it must parse as one JSON
    object."""
    summary = domain_result_summary(
        hidden_correctness_status="pass", detail="synthetic", scores={"a": 1}
    )
    line = json.dumps(summary, sort_keys=True)
    parsed = json.loads(line)
    assert isinstance(parsed, dict)
    assert parsed["hidden_correctness"]["status"] == "pass"


def test_task_20_domain_result_summary_never_claims_pass_without_source():
    summary = domain_result_summary(
        hidden_correctness_status="pass", detail="synthetic", scores={}
    )
    hc = summary["hidden_correctness"]
    assert hc["source"] == "domain_evaluator"
    # domain_evaluator is one of run_repo_eval.py's ALLOWED_CORRECTNESS_SOURCES
    # ("domain_evaluator", "hidden_acceptance_gate", "human_review") -- never
    # completion/pr_created/output_bytes/self_reported_success, which this
    # summary does not even include.
    assert "pr_created" not in summary
    assert "self_reported_success" not in summary
    assert "completion" not in summary
