"""AVO purpose mapping and canonical trial-schema validation.

Freezes and validates the Mini-report-bounded purpose allocation, canonical
per-trial fields, matched-control declarations, and protected-gate references.
This module reads ``docs/avo/purpose-mapping.v1.json`` and the published manifest
for gate lists only; it does not alter manifest identity bindings, ledger/checkpoint
schemas, G2 code, or resource controllers.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .avo_leakage import validate_export_record

SCHEMA_PURPOSE_MAPPING = "holusight-avo-purpose-mapping/v1"
PURPOSE_MAPPING_RELATIVE = Path("docs/avo/purpose-mapping.v1.json")
MANIFEST_RELATIVE = Path("docs/avo/trial-manifest.v1.json")

_EXPERIMENT_ID_RE = re.compile(r"^[0-9]{4}$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_PURPOSE_ID_RE = re.compile(r"^[a-z0-9._-]+$")
_DECISION_INFORMED = frozenset(
    {
        "calibration",
        "product_improvement",
        "supervisor_directive",
        "gate_recovery",
    }
)
_CONTROL_KINDS = frozenset({"baseline", "parent_lineage", "manifest_frozen"})
_INTERVENTION_KINDS = frozenset(
    {
        "evaluator_method",
        "display_selection",
        "scoring_weight",
        "abstention_threshold",
        "other_bounded",
    }
)
_FIELD_MAX_LENGTH = {
    "hypothesis": 512,
    "target_failure_mode": 512,
    "expected_effect": 512,
    "falsifier": 512,
}


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    evidence: str


class AvoPurposeError(ValueError):
    """Closed failure for AVO purpose or trial-schema validation."""


def sha256_digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _experiment_id_int(experiment_id: str) -> int:
    if not _EXPERIMENT_ID_RE.fullmatch(experiment_id):
        raise AvoPurposeError(f"invalid_experiment_id: {experiment_id}")
    return int(experiment_id, 10)


def _in_range(experiment_id: str, start: str, end: str, *, inclusive: bool) -> bool:
    value = _experiment_id_int(experiment_id)
    low = _experiment_id_int(start)
    high = _experiment_id_int(end)
    if inclusive:
        return low <= value <= high
    return low <= value < high


def load_purpose_mapping(repo_root: Path) -> dict[str, Any]:
    path = repo_root / PURPOSE_MAPPING_RELATIVE
    if not path.is_file():
        raise AvoPurposeError(f"missing purpose mapping: {PURPOSE_MAPPING_RELATIVE}")
    try:
        mapping = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AvoPurposeError("purpose mapping must be valid JSON") from exc
    if not isinstance(mapping, dict):
        raise AvoPurposeError("purpose mapping must be a JSON object")
    if mapping.get("schema_version") != SCHEMA_PURPOSE_MAPPING:
        raise AvoPurposeError(
            f"purpose mapping schema_version must be {SCHEMA_PURPOSE_MAPPING!r}",
        )
    return mapping


def verify_purpose_mapping_digest(mapping: dict[str, Any]) -> None:
    declared = mapping.get("mapping_sha256")
    if not isinstance(declared, str) or not _SHA256_RE.fullmatch(declared):
        raise AvoPurposeError("purpose mapping missing valid mapping_sha256")

    body = dict(mapping)
    body.pop("mapping_sha256", None)
    computed = sha256_digest(_canonical_json_bytes(body))
    if computed != declared:
        raise AvoPurposeError(
            f"purpose mapping digest mismatch: expected {declared}, got {computed}",
        )


def validate_purpose_mapping_structure(mapping: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if mapping.get("campaign_id") != "holusight-avo-v1":
        issues.append(ValidationIssue("invalid_campaign_id", str(mapping.get("campaign_id"))))

    if mapping.get("total_valid_trials") != 1000:
        issues.append(
            ValidationIssue(
                "invalid_total_valid_trials",
                str(mapping.get("total_valid_trials")),
            ),
        )

    partitions = mapping.get("partitions")
    if not isinstance(partitions, list) or not partitions:
        issues.append(ValidationIssue("missing_partitions", "partitions"))
        return issues

    covered: set[int] = set()
    for index, partition in enumerate(partitions):
        if not isinstance(partition, dict):
            issues.append(ValidationIssue("invalid_partition", f"partitions[{index}]"))
            continue
        purpose_id = partition.get("purpose_id")
        host = partition.get("host")
        id_range = partition.get("experiment_id_range")
        if purpose_id not in {
            "evaluator_method_calibration",
            "product_intervention",
        }:
            issues.append(
                ValidationIssue("unsupported_purpose_id", f"partitions[{index}].purpose_id"),
            )
        if host not in {"laptop", "mini"}:
            issues.append(ValidationIssue("unsupported_host", f"partitions[{index}].host"))
        if not isinstance(id_range, dict):
            issues.append(
                ValidationIssue("missing_experiment_id_range", f"partitions[{index}]"),
            )
            continue
        start = id_range.get("start")
        end = id_range.get("end")
        if not isinstance(start, str) or not isinstance(end, str):
            issues.append(
                ValidationIssue("invalid_experiment_id_range", f"partitions[{index}]"),
            )
            continue
        try:
            low = _experiment_id_int(start)
            high = _experiment_id_int(end)
        except AvoPurposeError:
            issues.append(
                ValidationIssue("invalid_experiment_id_range", f"partitions[{index}]"),
            )
            continue
        if low > high:
            issues.append(
                ValidationIssue("inverted_experiment_id_range", f"partitions[{index}]"),
            )
            continue
        for value in range(low, high + 1):
            if value in covered:
                issues.append(
                    ValidationIssue(
                        "overlapping_experiment_id",
                        f"{value:04d} in partitions[{index}]",
                    ),
                )
            covered.add(value)

    if len(covered) != 1000:
        issues.append(
            ValidationIssue(
                "allocation_gap_or_shortfall",
                f"covered={len(covered)} expected=1000",
            ),
        )

    expected = set(range(1, 1001))
    if covered != expected:
        missing = sorted(expected - covered)
        extra = sorted(covered - expected)
        if missing:
            issues.append(
                ValidationIssue(
                    "allocation_gap",
                    ",".join(f"{value:04d}" for value in missing[:5]),
                ),
            )
        if extra:
            issues.append(
                ValidationIssue(
                    "allocation_out_of_range",
                    ",".join(f"{value:04d}" for value in extra[:5]),
                ),
            )

    control_policy = mapping.get("control_policy")
    if not isinstance(control_policy, dict):
        issues.append(ValidationIssue("missing_control_policy", "control_policy"))
    else:
        for purpose_id in ("evaluator_method_calibration", "product_intervention"):
            policy = control_policy.get(purpose_id)
            if not isinstance(policy, dict):
                issues.append(
                    ValidationIssue("missing_control_policy_entry", purpose_id),
                )
                continue
            kinds = policy.get("allowed_control_kinds")
            if not isinstance(kinds, list) or not kinds:
                issues.append(
                    ValidationIssue("missing_allowed_control_kinds", purpose_id),
                )
                continue
            for kind in kinds:
                if kind not in _CONTROL_KINDS:
                    issues.append(
                        ValidationIssue("unsupported_control_kind", f"{purpose_id}:{kind}"),
                    )

    canonical_fields = mapping.get("canonical_trial_fields")
    if not isinstance(canonical_fields, list) or len(canonical_fields) < 11:
        issues.append(ValidationIssue("missing_canonical_trial_fields", "canonical_trial_fields"))
    elif len(set(canonical_fields)) != len(canonical_fields):
        issues.append(ValidationIssue("duplicate_canonical_trial_fields", "canonical_trial_fields"))

    return issues


def resolve_purpose_for_experiment(
    mapping: dict[str, Any],
    *,
    experiment_id: str,
    host: str,
) -> str | None:
    partitions = mapping.get("partitions")
    if not isinstance(partitions, list):
        return None
    for partition in partitions:
        if not isinstance(partition, dict):
            continue
        if partition.get("host") != host:
            continue
        id_range = partition.get("experiment_id_range")
        if not isinstance(id_range, dict):
            continue
        start = id_range.get("start")
        end = id_range.get("end")
        inclusive = id_range.get("inclusive", True)
        if not isinstance(start, str) or not isinstance(end, str):
            continue
        if _in_range(experiment_id, start, end, inclusive=bool(inclusive)):
            purpose_id = partition.get("purpose_id")
            return purpose_id if isinstance(purpose_id, str) else None
    return None


def load_manifest_protected_gates(repo_root: Path) -> frozenset[str]:
    path = repo_root / MANIFEST_RELATIVE
    if not path.is_file():
        raise AvoPurposeError(f"missing manifest: {MANIFEST_RELATIVE}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    gates = manifest.get("protected_gates")
    if not isinstance(gates, list) or not gates:
        raise AvoPurposeError("manifest protected_gates missing or empty")
    return frozenset(str(gate) for gate in gates)


def validate_canonical_trial_fields(
    trial: dict[str, Any],
    *,
    required_fields: list[str],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not isinstance(trial, dict):
        return [ValidationIssue("trial_must_be_object", "trial")]

    for field in required_fields:
        if field not in trial:
            issues.append(ValidationIssue("missing_canonical_field", field))
        elif trial[field] in (None, "", [], {}):
            issues.append(ValidationIssue("empty_canonical_field", field))

    purpose_id = trial.get("purpose_id")
    if isinstance(purpose_id, str) and not _PURPOSE_ID_RE.fullmatch(purpose_id):
        issues.append(ValidationIssue("malformed_purpose_id", purpose_id))

    for field, max_len in _FIELD_MAX_LENGTH.items():
        value = trial.get(field)
        if isinstance(value, str) and len(value) > max_len:
            issues.append(ValidationIssue("field_too_long", field))

    intervention = trial.get("intervention")
    if intervention is not None and not isinstance(intervention, dict):
        issues.append(ValidationIssue("malformed_intervention", "intervention"))
    elif isinstance(intervention, dict):
        kind = intervention.get("kind")
        if kind not in _INTERVENTION_KINDS:
            issues.append(ValidationIssue("invalid_intervention_kind", str(kind)))
        digest = intervention.get("digest")
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            issues.append(ValidationIssue("malformed_intervention_digest", "intervention.digest"))

    decision = trial.get("decision_informed")
    if decision is not None and decision not in _DECISION_INFORMED:
        issues.append(ValidationIssue("invalid_decision_informed", str(decision)))

    seed = trial.get("seed")
    if seed is not None and (not isinstance(seed, int) or seed < 0):
        issues.append(ValidationIssue("invalid_seed", str(seed)))

    evaluator_identity = trial.get("evaluator_identity")
    if evaluator_identity is not None:
        if not isinstance(evaluator_identity, dict):
            issues.append(ValidationIssue("malformed_evaluator_identity", "evaluator_identity"))
        else:
            for key in ("digest", "method_config_sha256"):
                value = evaluator_identity.get(key)
                if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
                    issues.append(ValidationIssue("malformed_evaluator_identity", key))

    return issues


def validate_matched_control(
    control: Any,
    *,
    purpose_id: str,
    mapping: dict[str, Any],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not isinstance(control, dict):
        return [ValidationIssue("malformed_control", "control")]

    kind = control.get("kind")
    digest = control.get("digest")
    if kind not in _CONTROL_KINDS:
        issues.append(ValidationIssue("invalid_control_kind", str(kind)))
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        issues.append(ValidationIssue("malformed_control_digest", "control.digest"))

    policy = mapping.get("control_policy")
    if isinstance(policy, dict):
        purpose_policy = policy.get(purpose_id)
        if isinstance(purpose_policy, dict):
            allowed = purpose_policy.get("allowed_control_kinds")
            if isinstance(allowed, list) and kind not in allowed:
                issues.append(
                    ValidationIssue(
                        "unsupported_control_for_purpose",
                        f"{purpose_id}:{kind}",
                    ),
                )
    return issues


def validate_protected_gates(
    gates: Any,
    *,
    manifest_gates: frozenset[str],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not isinstance(gates, list) or not gates:
        return [ValidationIssue("missing_protected_gates", "protected_gates")]
    if len(set(gates)) != len(gates):
        issues.append(ValidationIssue("duplicate_protected_gate", "protected_gates"))
    for gate in gates:
        if not isinstance(gate, str) or not gate:
            issues.append(ValidationIssue("malformed_protected_gate", str(gate)))
            continue
        if gate not in manifest_gates:
            issues.append(ValidationIssue("unsupported_protected_gate", gate))
    return issues


def validate_trial_preflight(
    repo_root: Path,
    *,
    experiment_id: str,
    host: str,
    trial: dict[str, Any],
) -> None:
    """Reject trial preflight records that violate purpose or schema rules."""
    mapping = load_purpose_mapping(repo_root)
    verify_purpose_mapping_digest(mapping)

    structure_issues = validate_purpose_mapping_structure(mapping)
    if structure_issues:
        first = structure_issues[0]
        raise AvoPurposeError(f"{first.code}: {first.evidence}")

    validate_export_record(trial)

    required_fields = mapping.get("canonical_trial_fields")
    if not isinstance(required_fields, list):
        raise AvoPurposeError("missing_canonical_trial_fields")

    issues = validate_canonical_trial_fields(trial, required_fields=list(required_fields))

    expected_purpose = resolve_purpose_for_experiment(
        mapping,
        experiment_id=experiment_id,
        host=host,
    )
    if expected_purpose is None:
        issues.append(
            ValidationIssue(
                "experiment_id_outside_allocation",
                f"{host}:{experiment_id}",
            ),
        )
    else:
        declared_purpose = trial.get("purpose_id")
        if declared_purpose != expected_purpose:
            issues.append(
                ValidationIssue(
                    "unsupported_purpose_mapping",
                    f"expected={expected_purpose} got={declared_purpose}",
                ),
            )
        issues.extend(
            validate_matched_control(
                trial.get("control"),
                purpose_id=expected_purpose,
                mapping=mapping,
            ),
        )

    manifest_gates = load_manifest_protected_gates(repo_root)
    issues.extend(
        validate_protected_gates(
            trial.get("protected_gates"),
            manifest_gates=manifest_gates,
        ),
    )

    if issues:
        first = issues[0]
        raise AvoPurposeError(f"{first.code}: {first.evidence}")
