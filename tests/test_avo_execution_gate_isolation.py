"""Tests for AVO execution-gate vector and process-isolation launch controls.

Report-bounded slice: denies launch and counting unless the manifest-frozen
protected-gate vector is complete with boolean outcomes, semantic matched-control
and frozen-input bindings hold, candidate/evaluator ownership is separated,
metrics are manifest-approved, promotion stays permanently denied, and
schema-valid isolation plus pause/resume handoff artifacts are present.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codesight.avo import execution_gate_isolation as eg

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "docs/avo/trial-manifest.v1.json"
VALID_DIGEST = "sha256:" + "a" * 64
PARENT_DIGEST = "sha256:" + "b" * 64
SUITE_DIGEST = "sha256:" + "c" * 64
ORDER_DIGEST = "sha256:" + "d" * 64
FROZEN_DIGEST = "sha256:" + "e" * 64
EVALUATOR_DIGEST = "sha256:" + "f" * 64
CANDIDATE_DIGEST = "sha256:" + "1" * 64
METHOD_SHA = "sha256:" + "2" * 64
LANE_ID = "laptop-calibration-0001-0013"
TIMESTAMP = "2026-08-28T00:00:00Z"


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest_sha256(manifest: dict) -> str:
    return manifest["manifest_sha256"]


@pytest.fixture(scope="module")
def binding() -> eg.FrozenInputBinding:
    return eg.FrozenInputBinding(
        candidate_digest=CANDIDATE_DIGEST,
        parent_lineage_ref="0001",
        parent_lineage_digest=PARENT_DIGEST,
        evaluator_digest=EVALUATOR_DIGEST,
        suite_manifest_digest=SUITE_DIGEST,
        ordering_digest=ORDER_DIGEST,
        frozen_input_digest=FROZEN_DIGEST,
    )


def _candidate_trial(**overrides: object) -> dict[str, object]:
    trial = {
        "purpose_id": "evaluator_method_calibration",
        "hypothesis": "Calibration improves coverage mean",
        "target_failure_mode": "under-covered required providers",
        "intervention": {
            "kind": "display_selection",
            "summary": "bounded display tweak",
            "digest": CANDIDATE_DIGEST,
        },
        "expected_effect": "coverage mean increases",
        "falsifier": "coverage mean decreases",
        "control": {"kind": "baseline", "digest": FROZEN_DIGEST},
        "protected_gates": list(eg.manifest_protected_gate_vector({})),
        "lineage_parent": "0001",
        "decision_informed": "calibration",
        "seed": 926223,
        "evaluator_identity": {
            "digest": EVALUATOR_DIGEST,
            "method_config_sha256": METHOD_SHA,
        },
        "metrics": {
            "required_provider_coverage_mean": 0.91,
            "hard_constraint_pass": 1.0,
        },
    }
    trial.update(overrides)
    return trial


def _evaluator_trial(**overrides: object) -> dict[str, object]:
    trial = _candidate_trial(
        intervention={
            "kind": "evaluator_method",
            "summary": "bounded evaluator tweak",
            "digest": VALID_DIGEST,
        },
        control={
            "kind": "manifest_frozen",
            "digest": eg._sha256_canonical_json(
                {
                    "suite_manifest_digest": SUITE_DIGEST,
                    "ordering_digest": ORDER_DIGEST,
                    "frozen_input_digest": FROZEN_DIGEST,
                }
            ),
        },
        **overrides,
    )
    return trial


def _full_gate_state(manifest: dict, manifest_sha256: str, **overrides: object) -> dict:
    state = eg.build_gate_outcome_state(
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
        manifest=manifest,
        declared_at=TIMESTAMP,
        all_passed=True,
    )
    state.update(overrides)
    return state


def _full_isolation_state(manifest: dict, manifest_sha256: str, **overrides: object) -> dict:
    state = eg.build_isolation_state(
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
        manifest=manifest,
        dispatch_lock_id=f"{LANE_ID}:dispatch",
        declared_at=TIMESTAMP,
    )
    state.update(overrides)
    return state


def _full_pause_handoff(**overrides: object) -> dict:
    handoff = eg.build_pause_resume_handoff(
        lane_id=LANE_ID,
        pause_kind="none",
        pause_active=False,
        resume_authorized=True,
        updated_at=TIMESTAMP,
    )
    handoff.update(overrides)
    return handoff


def test_manifest_protected_gate_vector_matches_canonical_manifest(manifest: dict) -> None:
    gates = eg.manifest_protected_gate_vector(manifest)
    assert len(gates) == 8
    assert "gate.promotion.denied" in gates
    assert "gate.g2.blocked" in gates


def test_approved_metric_names_match_scoring_policy(manifest: dict) -> None:
    names = eg.approved_metric_names(manifest)
    assert "required_provider_coverage_mean" in names
    assert "eval_pilot_pass_rate" in names
    assert "hard_constraint_pass" in names
    assert "unrelated_proxy" not in names


def test_default_assessment_denies_launch_and_count(manifest: dict, manifest_sha256: str) -> None:
    result = eg.assess_execution_gate(
        manifest=manifest,
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
        trial=None,
        binding=None,
        gate_outcome_state=None,
        isolation_state=None,
        pause_resume_handoff=None,
    )
    assert result.launch_allowed is False
    assert result.countable is False
    assert "gate_outcome_state_absent" in result.reason_codes
    assert "execution_isolation_state_absent" in result.reason_codes
    assert "pause_resume_handoff_absent" in result.reason_codes
    assert "trial_or_binding_absent" in result.reason_codes


def test_complete_gate_vector_passes_with_all_manifest_gates(
    manifest: dict,
    manifest_sha256: str,
) -> None:
    state = _full_gate_state(manifest, manifest_sha256)
    ok, errors, parsed = eg.validate_gate_outcome_vector(
        state,
        manifest=manifest,
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
    )
    assert ok is True
    assert errors == ()
    assert parsed is not None
    assert len(parsed) == len(eg.manifest_protected_gate_vector(manifest))


@pytest.mark.parametrize(
    "mutator",
    [
        lambda s: s.pop("gate_outcomes"),
        lambda s: s["gate_outcomes"].pop(),
        lambda s: s["gate_outcomes"].append(
            {"gate_id": "gate.not.in.manifest", "passed": True}
        ),
        lambda s: next(
            item.update({"passed": False})
            for item in s["gate_outcomes"]
            if item["gate_id"] == "gate.g2.blocked"
        ),
        lambda s: next(
            item.update({"passed": False})
            for item in s["gate_outcomes"]
            if item["gate_id"] == "gate.promotion.denied"
        ),
    ],
    ids=["missing_outcomes", "incomplete_vector", "extra_gate", "failed_gate", "promotion_allowed"],
)
def test_incomplete_or_failed_gate_vector_denies(
    manifest: dict,
    manifest_sha256: str,
    mutator,
) -> None:
    state = _full_gate_state(manifest, manifest_sha256)
    mutator(state)
    ok, errors, _parsed = eg.validate_gate_outcome_vector(
        state,
        manifest=manifest,
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
    )
    assert ok is False
    assert errors


def test_promotion_state_must_remain_denied() -> None:
    ok, errors = eg.validate_promotion_denied({"allowed": True})
    assert ok is False
    assert "promotion_not_permanently_denied" in errors

    ok_allowed, errors_allowed = eg.validate_promotion_denied({"allowed": False})
    assert ok_allowed is True
    assert errors_allowed == ()


def test_semantic_baseline_control_binds_frozen_input(binding: eg.FrozenInputBinding) -> None:
    trial = _candidate_trial()
    ok, errors = eg.validate_semantic_control_binding(trial, binding=binding)
    assert ok is True
    assert errors == ()


def test_semantic_control_rejects_digest_mismatch(binding: eg.FrozenInputBinding) -> None:
    trial = _candidate_trial(control={"kind": "baseline", "digest": VALID_DIGEST})
    ok, errors = eg.validate_semantic_control_binding(trial, binding=binding)
    assert ok is False
    assert "control_baseline_digest_mismatch" in errors


def test_semantic_parent_lineage_control_binds_parent(binding: eg.FrozenInputBinding) -> None:
    trial = _candidate_trial(
        control={"kind": "parent_lineage", "digest": PARENT_DIGEST},
        lineage_parent="0001",
    )
    ok, errors = eg.validate_semantic_control_binding(trial, binding=binding)
    assert ok is True
    assert errors == ()


def test_semantic_manifest_frozen_control_binds_suite_and_ordering(
    binding: eg.FrozenInputBinding,
) -> None:
    trial = _evaluator_trial()
    ok, errors = eg.validate_semantic_control_binding(trial, binding=binding)
    assert ok is True
    assert errors == ()


def test_candidate_evaluator_separation_accepts_candidate_intervention(
    binding: eg.FrozenInputBinding,
) -> None:
    trial = _candidate_trial()
    ok, errors = eg.validate_candidate_evaluator_separation(trial, binding=binding)
    assert ok is True
    assert errors == ()


def test_candidate_evaluator_separation_rejects_digest_collision(
    binding: eg.FrozenInputBinding,
) -> None:
    trial = _candidate_trial(
        intervention={
            "kind": "display_selection",
            "summary": "bad",
            "digest": EVALUATOR_DIGEST,
        }
    )
    ok, errors = eg.validate_candidate_evaluator_separation(trial, binding=binding)
    assert ok is False
    assert "candidate_evaluator_digest_collision" in errors


def test_candidate_evaluator_separation_rejects_evaluator_bound_candidate_kind(
    binding: eg.FrozenInputBinding,
) -> None:
    trial = _candidate_trial(
        intervention={
            "kind": "display_selection",
            "summary": "bad",
            "digest": binding.evaluator_digest,
        }
    )
    ok, errors = eg.validate_candidate_evaluator_separation(trial, binding=binding)
    assert ok is False
    assert "candidate_intervention_binds_evaluator" in errors


def test_evaluator_intervention_requires_pinned_evaluator_identity(
    binding: eg.FrozenInputBinding,
) -> None:
    trial = _evaluator_trial(
        evaluator_identity={
            "digest": VALID_DIGEST,
            "method_config_sha256": METHOD_SHA,
        }
    )
    ok, errors = eg.validate_candidate_evaluator_separation(trial, binding=binding)
    assert ok is False
    assert "evaluator_identity_unbound" in errors


def test_manifest_approved_metrics_rejects_proxy(manifest: dict) -> None:
    ok, errors = eg.validate_manifest_approved_metrics(
        {"unrelated_proxy": 1.0},
        manifest=manifest,
    )
    assert ok is False
    assert any(code.startswith("metric_not_manifest_approved:") for code in errors)


def test_manifest_approved_metrics_accepts_primary_and_constraints(manifest: dict) -> None:
    ok, errors = eg.validate_manifest_approved_metrics(
        {
            "required_provider_coverage_mean": 0.5,
            "eval_pilot_pass_rate": 0.8,
            "hard_constraint_pass": 1.0,
        },
        manifest=manifest,
    )
    assert ok is True
    assert errors == ()


@pytest.mark.parametrize(
    "mutator",
    [
        lambda d: d.pop("disk_floor_bytes"),
        lambda d: d.update({"monitored_path": "/absolute/path"}),
        lambda d: d.update({"local_log_sink": "/tmp/log"}),
        lambda d: d.update({"egress_denied": False}),
        lambda d: d.update({"credential_minimized_env": False}),
        lambda d: d.update({"child_process_group_cleanup": False}),
        lambda d: d.update({"concurrency_allowance": 0}),
        lambda d: d.update({"declared_max_cpu_percent": 95}),
        lambda d: d.update({"declared_max_memory_gib": 64}),
    ],
    ids=[
        "missing_disk_floor",
        "absolute_monitored_path",
        "absolute_log_sink",
        "egress_allowed",
        "credentials_not_minimized",
        "no_process_group_cleanup",
        "zero_concurrency",
        "cpu_over_captain_envelope",
        "memory_over_captain_envelope",
    ],
)
def test_isolation_declaration_fail_closed(
    manifest: dict,
    manifest_sha256: str,
    mutator,
) -> None:
    state = _full_isolation_state(manifest, manifest_sha256)
    mutator(state["declaration"])
    ok, errors = eg.validate_isolation_state(
        state,
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
        manifest=manifest,
    )
    assert ok is False
    assert errors


def test_isolation_declaration_accepts_canonical_envelope(
    manifest: dict,
    manifest_sha256: str,
) -> None:
    state = _full_isolation_state(manifest, manifest_sha256)
    ok, errors = eg.validate_isolation_state(
        state,
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
        manifest=manifest,
    )
    assert ok is True
    assert errors == ()


def test_pause_resume_handoff_blocks_active_pause() -> None:
    handoff = _full_pause_handoff(
        pause_kind="campaign_pause",
        pause_active=True,
        resume_authorized=False,
    )
    ok, errors, launch_permitted = eg.validate_pause_resume_handoff(handoff, lane_id=LANE_ID)
    assert ok is False
    assert launch_permitted is False
    assert "pause_active_blocks_launch" in errors
    assert "resume_not_authorized" in errors


def test_pause_resume_handoff_permits_launch_when_inactive() -> None:
    handoff = _full_pause_handoff()
    ok, errors, launch_permitted = eg.validate_pause_resume_handoff(handoff, lane_id=LANE_ID)
    assert ok is True
    assert errors == ()
    assert launch_permitted is True


def test_full_execution_gate_allows_launch_when_all_preconditions_hold(
    manifest: dict,
    manifest_sha256: str,
    binding: eg.FrozenInputBinding,
) -> None:
    trial = _candidate_trial()
    result = eg.assess_execution_gate(
        manifest=manifest,
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
        trial=trial,
        binding=binding,
        gate_outcome_state=_full_gate_state(manifest, manifest_sha256),
        isolation_state=_full_isolation_state(manifest, manifest_sha256),
        pause_resume_handoff=_full_pause_handoff(),
        promotion={"allowed": False},
    )
    assert result.launch_allowed is True
    assert result.countable is True
    assert result.reason_codes == ()


def test_full_execution_gate_denies_when_proxy_metric_present(
    manifest: dict,
    manifest_sha256: str,
    binding: eg.FrozenInputBinding,
) -> None:
    trial = _candidate_trial(metrics={"unrelated_proxy": 1.0})
    result = eg.assess_execution_gate(
        manifest=manifest,
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
        trial=trial,
        binding=binding,
        gate_outcome_state=_full_gate_state(manifest, manifest_sha256),
        isolation_state=_full_isolation_state(manifest, manifest_sha256),
        pause_resume_handoff=_full_pause_handoff(),
    )
    assert result.launch_allowed is False
    assert result.countable is False
    assert any(code.startswith("metric_not_manifest_approved:") for code in result.reason_codes)


def test_full_execution_gate_denies_when_promotion_not_denied(
    manifest: dict,
    manifest_sha256: str,
    binding: eg.FrozenInputBinding,
) -> None:
    trial = _candidate_trial()
    result = eg.assess_execution_gate(
        manifest=manifest,
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
        trial=trial,
        binding=binding,
        gate_outcome_state=_full_gate_state(manifest, manifest_sha256),
        isolation_state=_full_isolation_state(manifest, manifest_sha256),
        pause_resume_handoff=_full_pause_handoff(),
        promotion={"allowed": True},
    )
    assert result.launch_allowed is False
    assert "promotion_not_permanently_denied" in result.reason_codes


def test_captain_envelope_constants_match_report() -> None:
    assert eg.CAPTAIN_MAX_CPU_PERCENT == 90
    assert eg.CAPTAIN_MAX_MEMORY_GIB == 56
