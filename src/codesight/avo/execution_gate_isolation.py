"""AVO execution-gate vector and process-isolation launch controls.

Denies trial launch and counting unless the manifest-frozen protected-gate vector
reports boolean outcomes for every gate, semantic matched-control and frozen-input
bindings hold, candidate and evaluator ownership stay separated, only manifest-approved
metrics appear, promotion remains permanently denied, and a schema-valid isolation
declaration plus pause/resume handoff are present.

This slice does not modify AQ-R24 identity binding, ledger/checkpoint schemas,
``avo_ledger.py``, G2 code, or purpose/leakage modules owned by sibling branches.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

CAMPAIGN_ID = "holusight-avo-v1"
EXECUTION_ISOLATION_STATE_SCHEMA = "holusight-avo-execution-isolation-state/v1"
GATE_OUTCOME_STATE_SCHEMA = "holusight-avo-gate-outcome-state/v1"
PAUSE_RESUME_HANDOFF_SCHEMA = "holusight-avo-pause-resume-handoff/v1"

CAPTAIN_MAX_CPU_PERCENT = 90
CAPTAIN_MAX_MEMORY_GIB = 56

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_LANE_ID_RE = re.compile(r"^[a-z0-9-]+$")
_EXPERIMENT_ID_RE = re.compile(r"^[0-9]{4}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_RELATIVE_PATH_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]*$")

_CONTROL_KINDS = frozenset({"baseline", "parent_lineage", "manifest_frozen"})
_CANDIDATE_INTERVENTION_KINDS = frozenset(
    {
        "display_selection",
        "scoring_weight",
        "abstention_threshold",
        "other_bounded",
    }
)
_EVALUATOR_INTERVENTION_KINDS = frozenset({"evaluator_method"})
_PAUSE_KINDS = frozenset(
    {
        "campaign_pause",
        "lane_close",
        "resource_custody",
        "conflict",
        "none",
    }
)

_REQUIRED_ISOLATION_FIELDS = (
    "disk_floor_bytes",
    "monitored_path",
    "cpu_measurement_scope",
    "cpu_measurement_window_seconds",
    "memory_measurement_scope",
    "memory_measurement_window_seconds",
    "concurrency_allowance",
    "dispatch_lock_id",
    "local_log_byte_cap",
    "local_log_sink",
    "child_process_group_cleanup",
    "worktree_ownership_bound",
    "egress_denied",
    "credential_minimized_env",
    "declared_max_cpu_percent",
    "declared_max_memory_gib",
)


@dataclass(frozen=True, slots=True)
class GateOutcomeVector:
    gate_id: str
    passed: bool


@dataclass(frozen=True, slots=True)
class FrozenInputBinding:
    candidate_digest: str
    parent_lineage_ref: str
    parent_lineage_digest: str
    evaluator_digest: str
    suite_manifest_digest: str
    ordering_digest: str
    frozen_input_digest: str


@dataclass(frozen=True, slots=True)
class ExecutionGateResult:
    launch_allowed: bool
    countable: bool
    reason_codes: tuple[str, ...]


def _sha256_canonical_json(value: Mapping[str, Any]) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(body).hexdigest()


def manifest_protected_gate_vector(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    gates = manifest.get("protected_gates")
    if not isinstance(gates, list) or not gates:
        return ()
    ordered: list[str] = []
    seen: set[str] = set()
    for gate in gates:
        if not isinstance(gate, str) or not gate:
            continue
        if gate in seen:
            continue
        seen.add(gate)
        ordered.append(gate)
    return tuple(ordered)


def approved_metric_names(manifest: Mapping[str, Any]) -> frozenset[str]:
    identities = manifest.get("metric_identities")
    if not isinstance(identities, dict):
        return frozenset()
    names: set[str] = set()
    for key in ("primary", "hard_constraints"):
        values = identities.get(key)
        if isinstance(values, list):
            names.update(str(item) for item in values if isinstance(item, str))
    return frozenset(names)


def parse_gate_outcome_vector(
    state: Mapping[str, Any] | None,
) -> tuple[GateOutcomeVector, ...] | None:
    if state is None or not isinstance(state, Mapping):
        return None
    raw = state.get("gate_outcomes")
    if not isinstance(raw, list) or not raw:
        return None
    parsed: list[GateOutcomeVector] = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        gate_id = item.get("gate_id")
        passed = item.get("passed")
        if not isinstance(gate_id, str) or not gate_id:
            return None
        if not isinstance(passed, bool):
            return None
        parsed.append(GateOutcomeVector(gate_id=gate_id, passed=passed))
    return tuple(parsed)


def validate_gate_outcome_vector(
    state: Mapping[str, Any] | None,
    *,
    manifest: Mapping[str, Any],
    lane_id: str,
    manifest_sha256: str,
) -> tuple[bool, tuple[str, ...], tuple[GateOutcomeVector, ...] | None]:
    errors: list[str] = []
    if state is None:
        return False, ("gate_outcome_state_absent",), None
    if state.get("schema_version") != GATE_OUTCOME_STATE_SCHEMA:
        errors.append("gate_outcome_state_schema_invalid")
    if state.get("campaign_id") != CAMPAIGN_ID:
        errors.append("gate_outcome_state_campaign_mismatch")
    if state.get("lane_id") != lane_id:
        errors.append("gate_outcome_state_lane_mismatch")
    if state.get("manifest_sha256") != manifest_sha256:
        errors.append("gate_outcome_state_manifest_mismatch")
    declared_at = state.get("declared_at")
    if not isinstance(declared_at, str) or not declared_at:
        errors.append("gate_outcome_state_declared_at_missing")

    required_gates = manifest_protected_gate_vector(manifest)
    if not required_gates:
        errors.append("manifest_protected_gates_missing")

    parsed = parse_gate_outcome_vector(state)
    if parsed is None:
        errors.append("gate_outcome_vector_malformed")
        return False, tuple(dict.fromkeys(errors)), None

    observed = {item.gate_id: item.passed for item in parsed}
    if len(observed) != len(parsed):
        errors.append("gate_outcome_duplicate_gate")

    missing = [gate for gate in required_gates if gate not in observed]
    if missing:
        errors.append("gate_outcome_vector_incomplete")
    extra = [gate for gate in observed if gate not in required_gates]
    if extra:
        errors.append("gate_outcome_unlisted_gate")

    for gate_id, passed in observed.items():
        if not passed:
            errors.append(f"gate_failed:{gate_id}")

    promotion = observed.get("gate.promotion.denied")
    if promotion is not True:
        errors.append("promotion_gate_not_denied")

    return (not errors, tuple(dict.fromkeys(errors)), parsed)


def validate_semantic_control_binding(
    trial: Mapping[str, Any],
    *,
    binding: FrozenInputBinding,
) -> tuple[bool, tuple[str, ...]]:
    errors: list[str] = []
    control = trial.get("control")
    if not isinstance(control, dict):
        return False, ("malformed_control",)

    kind = control.get("kind")
    digest = control.get("digest")
    if kind not in _CONTROL_KINDS:
        errors.append("invalid_control_kind")
    if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
        errors.append("malformed_control_digest")

    lineage_parent = trial.get("lineage_parent")
    if not isinstance(lineage_parent, str) or not lineage_parent:
        errors.append("missing_lineage_parent")
    elif not (
        _EXPERIMENT_ID_RE.fullmatch(lineage_parent)
        or _GIT_SHA_RE.fullmatch(lineage_parent)
        or lineage_parent == "0000"
    ):
        errors.append("invalid_lineage_parent_ref")

    if kind == "baseline" and digest != binding.frozen_input_digest:
        errors.append("control_baseline_digest_mismatch")
    elif kind == "parent_lineage":
        if digest != binding.parent_lineage_digest:
            errors.append("control_parent_digest_mismatch")
        if lineage_parent != binding.parent_lineage_ref:
            errors.append("control_parent_ref_mismatch")
    elif kind == "manifest_frozen":
        expected = _sha256_canonical_json(
            {
                "suite_manifest_digest": binding.suite_manifest_digest,
                "ordering_digest": binding.ordering_digest,
                "frozen_input_digest": binding.frozen_input_digest,
            }
        )
        if digest != expected:
            errors.append("control_manifest_frozen_digest_mismatch")

    intervention = trial.get("intervention")
    if isinstance(intervention, dict):
        intervention_digest = intervention.get("digest")
        if isinstance(intervention_digest, str) and intervention_digest == digest:
            errors.append("intervention_control_digest_collision")

    return (not errors, tuple(dict.fromkeys(errors)))


def validate_candidate_evaluator_separation(
    trial: Mapping[str, Any],
    *,
    binding: FrozenInputBinding,
) -> tuple[bool, tuple[str, ...]]:
    errors: list[str] = []
    intervention = trial.get("intervention")
    evaluator_identity = trial.get("evaluator_identity")

    if not isinstance(intervention, dict):
        return False, ("malformed_intervention",)
    if not isinstance(evaluator_identity, dict):
        return False, ("malformed_evaluator_identity",)

    kind = intervention.get("kind")
    intervention_digest = intervention.get("digest")
    evaluator_digest = evaluator_identity.get("digest")

    if not isinstance(kind, str):
        errors.append("invalid_intervention_kind")
    if not isinstance(intervention_digest, str) or not _SHA256_RE.fullmatch(intervention_digest):
        errors.append("malformed_intervention_digest")
    if not isinstance(evaluator_digest, str) or not _SHA256_RE.fullmatch(evaluator_digest):
        errors.append("malformed_evaluator_digest")

    if intervention_digest == evaluator_digest:
        errors.append("candidate_evaluator_digest_collision")

    if kind in _CANDIDATE_INTERVENTION_KINDS:
        if intervention_digest == binding.evaluator_digest:
            errors.append("candidate_intervention_binds_evaluator")
        if intervention_digest != binding.candidate_digest:
            errors.append("candidate_intervention_digest_unbound")
    elif kind in _EVALUATOR_INTERVENTION_KINDS:
        if intervention_digest == binding.candidate_digest:
            errors.append("evaluator_intervention_binds_candidate")
        if evaluator_digest != binding.evaluator_digest:
            errors.append("evaluator_identity_unbound")
    else:
        errors.append("unsupported_intervention_kind")

    method_sha = evaluator_identity.get("method_config_sha256")
    if not isinstance(method_sha, str) or not _SHA256_RE.fullmatch(method_sha):
        errors.append("malformed_method_config_sha256")

    return (not errors, tuple(dict.fromkeys(errors)))


def validate_manifest_approved_metrics(
    metrics: Mapping[str, Any] | None,
    *,
    manifest: Mapping[str, Any],
) -> tuple[bool, tuple[str, ...]]:
    if metrics is None:
        return True, ()
    if not isinstance(metrics, Mapping):
        return False, ("metrics_must_be_object",)
    allowed = approved_metric_names(manifest)
    if not allowed:
        return False, ("manifest_metrics_unavailable",)
    errors: list[str] = []
    for key, value in metrics.items():
        if not isinstance(key, str):
            errors.append("metrics_key_invalid")
            continue
        if key not in allowed:
            errors.append(f"metric_not_manifest_approved:{key}")
        if not isinstance(value, (int, float)):
            errors.append(f"metric_value_not_number:{key}")
    return (not errors, tuple(dict.fromkeys(errors)))


def validate_promotion_denied(
    promotion: Mapping[str, Any] | None,
) -> tuple[bool, tuple[str, ...]]:
    if promotion is None:
        return True, ()
    if not isinstance(promotion, Mapping):
        return False, ("promotion_must_be_object",)
    allowed = promotion.get("allowed")
    if allowed is not False:
        return False, ("promotion_not_permanently_denied",)
    return True, ()


def validate_isolation_state(
    state: Mapping[str, Any] | None,
    *,
    lane_id: str,
    manifest_sha256: str,
    manifest: Mapping[str, Any],
) -> tuple[bool, tuple[str, ...]]:
    if state is None:
        return False, ("execution_isolation_state_absent",)
    errors: list[str] = []
    if state.get("schema_version") != EXECUTION_ISOLATION_STATE_SCHEMA:
        errors.append("execution_isolation_state_schema_invalid")
    if state.get("campaign_id") != CAMPAIGN_ID:
        errors.append("execution_isolation_state_campaign_mismatch")
    if state.get("lane_id") != lane_id:
        errors.append("execution_isolation_state_lane_mismatch")
    if state.get("manifest_sha256") != manifest_sha256:
        errors.append("execution_isolation_state_manifest_mismatch")

    declaration = state.get("declaration")
    if not isinstance(declaration, dict):
        return False, tuple(dict.fromkeys([*errors, "isolation_declaration_missing"]))

    missing = [field for field in _REQUIRED_ISOLATION_FIELDS if field not in declaration]
    if missing:
        errors.append("isolation_declaration_incomplete")

    disk_floor = declaration.get("disk_floor_bytes")
    if not isinstance(disk_floor, int) or disk_floor < 1:
        errors.append("disk_floor_invalid")

    monitored_path = declaration.get("monitored_path")
    if not isinstance(monitored_path, str) or not _RELATIVE_PATH_RE.fullmatch(monitored_path):
        errors.append("monitored_path_not_relative")

    for scope_key in ("cpu_measurement_scope", "memory_measurement_scope"):
        scope = declaration.get(scope_key)
        if scope not in {"trial_process_group", "lane_executor"}:
            errors.append(f"{scope_key}_invalid")

    for window_key in ("cpu_measurement_window_seconds", "memory_measurement_window_seconds"):
        window = declaration.get(window_key)
        if not isinstance(window, (int, float)) or window <= 0:
            errors.append(f"{window_key}_invalid")

    concurrency = declaration.get("concurrency_allowance")
    if not isinstance(concurrency, int) or concurrency < 1:
        errors.append("concurrency_allowance_invalid")

    lock_id = declaration.get("dispatch_lock_id")
    if not isinstance(lock_id, str) or not lock_id:
        errors.append("dispatch_lock_id_missing")

    log_cap = declaration.get("local_log_byte_cap")
    if not isinstance(log_cap, int) or log_cap < 1:
        errors.append("local_log_byte_cap_invalid")

    log_sink = declaration.get("local_log_sink")
    if not isinstance(log_sink, str) or not _RELATIVE_PATH_RE.fullmatch(log_sink):
        errors.append("local_log_sink_not_relative")

    for flag_key in (
        "child_process_group_cleanup",
        "worktree_ownership_bound",
        "egress_denied",
        "credential_minimized_env",
    ):
        if declaration.get(flag_key) is not True:
            errors.append(f"{flag_key}_not_enforced")

    declared_cpu = declaration.get("declared_max_cpu_percent")
    declared_mem = declaration.get("declared_max_memory_gib")
    if not isinstance(declared_cpu, int) or declared_cpu < 1:
        errors.append("declared_max_cpu_invalid")
    elif declared_cpu > CAPTAIN_MAX_CPU_PERCENT:
        errors.append("declared_max_cpu_exceeds_captain_envelope")
    if not isinstance(declared_mem, int) or declared_mem < 1:
        errors.append("declared_max_memory_gib_invalid")
    elif declared_mem > CAPTAIN_MAX_MEMORY_GIB:
        errors.append("declared_max_memory_gib_exceeds_captain_envelope")

    guardrails = manifest.get("resource_guardrails")
    if isinstance(guardrails, dict):
        manifest_cpu = guardrails.get("max_sustained_cpu_percent")
        manifest_mem = guardrails.get("max_memory_gib")
        if isinstance(declared_cpu, int) and isinstance(manifest_cpu, int):
            if declared_cpu > manifest_cpu:
                errors.append("declared_max_cpu_exceeds_manifest")
        if isinstance(declared_mem, int) and isinstance(manifest_mem, int):
            if declared_mem > manifest_mem:
                errors.append("declared_max_memory_gib_exceeds_manifest")

    preflight_ok = state.get("preflight_verified")
    if preflight_ok is not True:
        errors.append("isolation_preflight_not_verified")

    declared_at = state.get("declared_at")
    if not isinstance(declared_at, str) or not declared_at:
        errors.append("execution_isolation_declared_at_missing")

    return (not errors, tuple(dict.fromkeys(errors)))


def validate_pause_resume_handoff(
    handoff: Mapping[str, Any] | None,
    *,
    lane_id: str,
) -> tuple[bool, tuple[str, ...], bool]:
    """Return (valid, errors, launch_permitted_by_pause_state)."""
    if handoff is None:
        return False, ("pause_resume_handoff_absent",), False
    errors: list[str] = []
    if handoff.get("schema_version") != PAUSE_RESUME_HANDOFF_SCHEMA:
        errors.append("pause_resume_handoff_schema_invalid")
    if handoff.get("campaign_id") != CAMPAIGN_ID:
        errors.append("pause_resume_handoff_campaign_mismatch")
    if handoff.get("lane_id") != lane_id:
        errors.append("pause_resume_handoff_lane_mismatch")

    pause_kind = handoff.get("pause_kind")
    if pause_kind not in _PAUSE_KINDS:
        errors.append("pause_kind_invalid")

    pause_active = handoff.get("pause_active")
    if not isinstance(pause_active, bool):
        errors.append("pause_active_missing")
        pause_active = True

    resume_authorized = handoff.get("resume_authorized")
    if not isinstance(resume_authorized, bool):
        errors.append("resume_authorized_missing")
        resume_authorized = False

    updated_at = handoff.get("updated_at")
    if not isinstance(updated_at, str) or not updated_at:
        errors.append("pause_resume_handoff_updated_at_missing")

    launch_permitted = True
    if pause_kind != "none" and pause_active:
        launch_permitted = False
        errors.append("pause_active_blocks_launch")
    if pause_kind != "none" and not resume_authorized:
        launch_permitted = False
        if "resume_not_authorized" not in errors:
            errors.append("resume_not_authorized")

    return (not errors, tuple(dict.fromkeys(errors)), launch_permitted)


def assess_execution_gate(
    *,
    manifest: Mapping[str, Any],
    lane_id: str,
    manifest_sha256: str,
    trial: Mapping[str, Any] | None,
    binding: FrozenInputBinding | None,
    gate_outcome_state: Mapping[str, Any] | None,
    isolation_state: Mapping[str, Any] | None,
    pause_resume_handoff: Mapping[str, Any] | None,
    promotion: Mapping[str, Any] | None = None,
) -> ExecutionGateResult:
    """Deny launch and counting unless every report-bounded gate precondition holds."""
    reason_codes: list[str] = []

    if not _LANE_ID_RE.fullmatch(lane_id):
        reason_codes.append("lane_id_invalid")

    gates_ok, gate_errors, _parsed = validate_gate_outcome_vector(
        gate_outcome_state,
        manifest=manifest,
        lane_id=lane_id,
        manifest_sha256=manifest_sha256,
    )
    if not gates_ok:
        reason_codes.extend(gate_errors)

    promo_ok, promo_errors = validate_promotion_denied(promotion)
    if not promo_ok:
        reason_codes.extend(promo_errors)

    isolation_ok, isolation_errors = validate_isolation_state(
        isolation_state,
        lane_id=lane_id,
        manifest_sha256=manifest_sha256,
        manifest=manifest,
    )
    if not isolation_ok:
        reason_codes.extend(isolation_errors)

    pause_ok, pause_errors, pause_permits_launch = validate_pause_resume_handoff(
        pause_resume_handoff,
        lane_id=lane_id,
    )
    if not pause_ok:
        reason_codes.extend(pause_errors)
    if not pause_permits_launch:
        reason_codes.append("pause_resume_blocks_launch")

    trial_ok = False
    if trial is not None and binding is not None:
        if not isinstance(trial, Mapping):
            reason_codes.append("trial_must_be_object")
        else:
            control_ok, control_errors = validate_semantic_control_binding(
                trial,
                binding=binding,
            )
            if not control_ok:
                reason_codes.extend(control_errors)

            separation_ok, separation_errors = validate_candidate_evaluator_separation(
                trial,
                binding=binding,
            )
            if not separation_ok:
                reason_codes.extend(separation_errors)

            metrics = trial.get("metrics")
            metrics_ok, metrics_errors = validate_manifest_approved_metrics(
                metrics if isinstance(metrics, Mapping) else None,
                manifest=manifest,
            )
            if not metrics_ok:
                reason_codes.extend(metrics_errors)

            trial_ok = control_ok and separation_ok and metrics_ok
    else:
        reason_codes.append("trial_or_binding_absent")

    launch_allowed = (
        gates_ok
        and promo_ok
        and isolation_ok
        and pause_ok
        and pause_permits_launch
        and trial_ok
    )
    return ExecutionGateResult(
        launch_allowed=launch_allowed,
        countable=launch_allowed,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
    )


def build_gate_outcome_state(
    *,
    lane_id: str,
    manifest_sha256: str,
    manifest: Mapping[str, Any],
    declared_at: str,
    all_passed: bool = True,
) -> dict[str, Any]:
    gate_outcomes = [
        {"gate_id": gate_id, "passed": all_passed}
        for gate_id in manifest_protected_gate_vector(manifest)
    ]
    if "gate.promotion.denied" in manifest_protected_gate_vector(manifest):
        gate_outcomes = [
            {
                "gate_id": item["gate_id"],
                "passed": True if item["gate_id"] == "gate.promotion.denied" else all_passed,
            }
            for item in gate_outcomes
        ]
    return {
        "schema_version": GATE_OUTCOME_STATE_SCHEMA,
        "campaign_id": CAMPAIGN_ID,
        "lane_id": lane_id,
        "manifest_sha256": manifest_sha256,
        "gate_outcomes": gate_outcomes,
        "declared_at": declared_at,
    }


def build_isolation_state(
    *,
    lane_id: str,
    manifest_sha256: str,
    manifest: Mapping[str, Any],
    dispatch_lock_id: str,
    declared_at: str,
) -> dict[str, Any]:
    guardrails = manifest.get("resource_guardrails")
    manifest_cpu = 80
    manifest_mem = 48
    if isinstance(guardrails, dict):
        cpu = guardrails.get("max_sustained_cpu_percent")
        mem = guardrails.get("max_memory_gib")
        if isinstance(cpu, int):
            manifest_cpu = cpu
        if isinstance(mem, int):
            manifest_mem = mem
    return {
        "schema_version": EXECUTION_ISOLATION_STATE_SCHEMA,
        "campaign_id": CAMPAIGN_ID,
        "lane_id": lane_id,
        "manifest_sha256": manifest_sha256,
        "preflight_verified": True,
        "declared_at": declared_at,
        "declaration": {
            "disk_floor_bytes": 1_073_741_824,
            "monitored_path": "docs/avo/lanes",
            "cpu_measurement_scope": "trial_process_group",
            "cpu_measurement_window_seconds": 30,
            "memory_measurement_scope": "lane_executor",
            "memory_measurement_window_seconds": 30,
            "concurrency_allowance": 1,
            "dispatch_lock_id": dispatch_lock_id,
            "local_log_byte_cap": 65536,
            "local_log_sink": "docs/avo/lanes/local.log",
            "child_process_group_cleanup": True,
            "worktree_ownership_bound": True,
            "egress_denied": True,
            "credential_minimized_env": True,
            "declared_max_cpu_percent": manifest_cpu,
            "declared_max_memory_gib": manifest_mem,
        },
    }


def build_pause_resume_handoff(
    *,
    lane_id: str,
    pause_kind: str = "none",
    pause_active: bool = False,
    resume_authorized: bool = True,
    updated_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": PAUSE_RESUME_HANDOFF_SCHEMA,
        "campaign_id": CAMPAIGN_ID,
        "lane_id": lane_id,
        "pause_kind": pause_kind,
        "pause_active": pause_active,
        "resume_authorized": resume_authorized,
        "updated_at": updated_at,
    }
