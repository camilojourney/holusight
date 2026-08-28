"""Tests for AVO leakage boundary, purpose mapping, and trial-schema validation.

Mini-report-bounded slice: denies missing or malformed canonical fields, unsafe
persisted values, unsupported purpose mappings, and invalid matched-control or
protected-gate declarations. See ``docs/avo/purpose-mapping.v1.json`` and
``docs/avo/leakage-boundary.md``.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from codesight import avo_leakage, avo_purpose

REPO_ROOT = Path(__file__).resolve().parents[1]
VALID_DIGEST = "sha256:" + "a" * 64


def _minimal_trial(**overrides: object) -> dict[str, object]:
    trial = {
        "purpose_id": "evaluator_method_calibration",
        "hypothesis": "Calibration improves coverage mean",
        "target_failure_mode": "under-covered required providers",
        "intervention": {
            "kind": "evaluator_method",
            "summary": "bounded display tweak",
            "digest": VALID_DIGEST,
        },
        "expected_effect": "coverage mean increases",
        "falsifier": "coverage mean decreases",
        "control": {"kind": "baseline", "digest": VALID_DIGEST},
        "protected_gates": ["gate.g2.blocked", "gate.egress.off"],
        "lineage_parent": "0000",
        "decision_informed": "calibration",
        "seed": 926223,
        "evaluator_identity": {
            "digest": VALID_DIGEST,
            "method_config_sha256": VALID_DIGEST,
        },
    }
    trial.update(overrides)
    return trial


def test_purpose_mapping_digest_and_allocation_are_frozen():
    mapping = avo_purpose.load_purpose_mapping(REPO_ROOT)
    avo_purpose.verify_purpose_mapping_digest(mapping)
    issues = avo_purpose.validate_purpose_mapping_structure(mapping)
    assert issues == []
    assert mapping["total_valid_trials"] == 1000
    assert mapping["remediation_report_commit"] == "f5b5ddfde08ba16e87397f0b6fc07f8ea4174078"


@pytest.mark.parametrize(
    ("experiment_id", "host", "expected"),
    [
        ("0001", "laptop", "evaluator_method_calibration"),
        ("0050", "laptop", "evaluator_method_calibration"),
        ("0051", "laptop", "product_intervention"),
        ("0500", "laptop", "product_intervention"),
        ("0501", "mini", "evaluator_method_calibration"),
        ("0550", "mini", "evaluator_method_calibration"),
        ("0551", "mini", "product_intervention"),
        ("1000", "mini", "product_intervention"),
    ],
)
def test_resolve_purpose_for_experiment_matches_report(experiment_id, host, expected):
    mapping = avo_purpose.load_purpose_mapping(REPO_ROOT)
    assert (
        avo_purpose.resolve_purpose_for_experiment(
            mapping,
            experiment_id=experiment_id,
            host=host,
        )
        == expected
    )


def test_validate_purpose_mapping_rejects_overlap():
    mapping = avo_purpose.load_purpose_mapping(REPO_ROOT)
    broken = copy.deepcopy(mapping)
    broken["partitions"].append(copy.deepcopy(broken["partitions"][0]))
    issues = avo_purpose.validate_purpose_mapping_structure(broken)
    assert any(issue.code == "overlapping_experiment_id" for issue in issues)


def test_validate_purpose_mapping_rejects_gap():
    mapping = avo_purpose.load_purpose_mapping(REPO_ROOT)
    broken = copy.deepcopy(mapping)
    broken["partitions"][0]["experiment_id_range"]["end"] = "0049"
    issues = avo_purpose.validate_purpose_mapping_structure(broken)
    assert any(issue.code in {"allocation_gap", "allocation_gap_or_shortfall"} for issue in issues)


def test_validate_trial_preflight_accepts_calibration_trial():
    avo_purpose.validate_trial_preflight(
        REPO_ROOT,
        experiment_id="0010",
        host="laptop",
        trial=_minimal_trial(),
    )


def test_validate_trial_preflight_accepts_product_trial_with_parent_control():
    trial = _minimal_trial(
        purpose_id="product_intervention",
        control={"kind": "parent_lineage", "digest": VALID_DIGEST},
        decision_informed="product_improvement",
    )
    avo_purpose.validate_trial_preflight(
        REPO_ROOT,
        experiment_id="0100",
        host="laptop",
        trial=trial,
    )


@pytest.mark.parametrize(
    "missing_field",
    [
        "purpose_id",
        "hypothesis",
        "target_failure_mode",
        "intervention",
        "expected_effect",
        "falsifier",
        "control",
        "protected_gates",
        "lineage_parent",
        "decision_informed",
        "seed",
        "evaluator_identity",
    ],
)
def test_validate_trial_preflight_denies_missing_canonical_field(missing_field):
    trial = _minimal_trial()
    trial.pop(missing_field)
    with pytest.raises(avo_purpose.AvoPurposeError, match="missing_canonical_field"):
        avo_purpose.validate_trial_preflight(
            REPO_ROOT,
            experiment_id="0010",
            host="laptop",
            trial=trial,
        )


def test_validate_trial_preflight_denies_unsupported_purpose_mapping():
    trial = _minimal_trial(purpose_id="product_intervention")
    with pytest.raises(avo_purpose.AvoPurposeError, match="unsupported_purpose_mapping"):
        avo_purpose.validate_trial_preflight(
            REPO_ROOT,
            experiment_id="0010",
            host="laptop",
            trial=trial,
        )


def test_validate_trial_preflight_denies_invalid_control_for_calibration():
    trial = _minimal_trial(control={"kind": "parent_lineage", "digest": VALID_DIGEST})
    with pytest.raises(avo_purpose.AvoPurposeError, match="unsupported_control_for_purpose"):
        avo_purpose.validate_trial_preflight(
            REPO_ROOT,
            experiment_id="0010",
            host="laptop",
            trial=trial,
        )


def test_validate_trial_preflight_denies_malformed_control_digest():
    trial = _minimal_trial(control={"kind": "baseline", "digest": "not-a-digest"})
    with pytest.raises(avo_purpose.AvoPurposeError, match="malformed_control_digest"):
        avo_purpose.validate_trial_preflight(
            REPO_ROOT,
            experiment_id="0010",
            host="laptop",
            trial=trial,
        )


def test_validate_trial_preflight_denies_unsupported_protected_gate():
    trial = _minimal_trial(protected_gates=["gate.g2.blocked", "gate.custom.unknown"])
    with pytest.raises(avo_purpose.AvoPurposeError, match="unsupported_protected_gate"):
        avo_purpose.validate_trial_preflight(
            REPO_ROOT,
            experiment_id="0010",
            host="laptop",
            trial=trial,
        )


def test_validate_trial_preflight_denies_empty_protected_gates():
    trial = _minimal_trial(protected_gates=[])
    with pytest.raises(avo_purpose.AvoPurposeError, match="empty_canonical_field: protected_gates"):
        avo_purpose.validate_trial_preflight(
            REPO_ROOT,
            experiment_id="0010",
            host="laptop",
            trial=trial,
        )


def test_validate_trial_preflight_denies_experiment_outside_allocation():
    trial = _minimal_trial(purpose_id="product_intervention")
    with pytest.raises(avo_purpose.AvoPurposeError, match="experiment_id_outside_allocation"):
        avo_purpose.validate_trial_preflight(
            REPO_ROOT,
            experiment_id="9999",
            host="laptop",
            trial=trial,
        )


def test_leakage_scan_denies_forbidden_export_keys():
    record = {"prompt": "hidden prompt text"}
    violations = avo_leakage.scan_for_leakage(record)
    assert any(v.code == "forbidden_export_key" for v in violations)


def test_leakage_scan_denies_secret_like_values():
    record = {"notes": "Authorization: Bearer sk-testsecretvalue1234567890"}
    violations = avo_leakage.scan_for_leakage(record)
    assert any(v.code == "secret_like_value" for v in violations)


def test_leakage_scan_denies_absolute_paths():
    record = {"notes": "wrote /Users/camilo/project/output.json"}
    violations = avo_leakage.scan_for_leakage(record)
    assert any(v.code == "absolute_path" for v in violations)


def test_validate_export_record_rejects_unsafe_persisted_values():
    with pytest.raises(avo_leakage.AvoLeakageError, match="forbidden_export_key"):
        avo_leakage.validate_export_record({"telemetry": {"tokens": 42}})


def test_validate_export_record_rejects_oversized_payload():
    huge = {"notes": "x" * 20_000}
    with pytest.raises(avo_leakage.AvoLeakageError, match="record_bytes_exceeded"):
        avo_leakage.validate_export_record(huge)


def test_validate_trial_preflight_rejects_leakage_in_trial_record():
    trial = _minimal_trial(notes="api_key=sk-testsecretvalue1234567890")
    with pytest.raises(avo_leakage.AvoLeakageError):
        avo_purpose.validate_trial_preflight(
            REPO_ROOT,
            experiment_id="0010",
            host="laptop",
            trial=trial,
        )


def test_leakage_boundary_doc_is_visible():
    assert avo_leakage.leakage_boundary_doc_exists(REPO_ROOT)


def test_purpose_mapping_file_matches_schema_fields():
    mapping = json.loads((REPO_ROOT / avo_purpose.PURPOSE_MAPPING_RELATIVE).read_text())
    assert mapping["schema_version"] == avo_purpose.SCHEMA_PURPOSE_MAPPING
    assert "control_policy" in mapping
    assert "canonical_trial_fields" in mapping
