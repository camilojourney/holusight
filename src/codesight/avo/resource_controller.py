"""Host-independent AVO resource-limit and failure/restart launch gates.

Lanes must not launch or count valid trials unless manifest resource guardrails
are present, a matching resource-state artifact declares active controls, crash
outcomes are retained in the ledger, and restart state binds to the ledger tail.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

CAMPAIGN_ID = "holusight-avo-v1"
RESOURCE_STATE_SCHEMA = "holusight-avo-resource-state/v1"
RESTART_STATE_SCHEMA = "holusight-avo-restart-state/v1"
GENESIS_LEDGER_TAIL_SHA256 = "sha256:" + ("0" * 64)

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_LANE_ID_RE = re.compile(r"^[a-z0-9-]+$")
_CRASH_PHASES = frozenset(
    {"preflight", "intervention_apply", "evaluate", "record", "checkpoint"}
)

_REQUIRED_GUARDRAIL_FIELDS = (
    "max_sustained_cpu_percent",
    "max_memory_gib",
    "nice_cpu_heavy",
    "no_foreground_ui",
    "pause_on_pressure",
)


@dataclass(frozen=True, slots=True)
class ResourceGuardrails:
    max_sustained_cpu_percent: int
    max_memory_gib: int
    nice_cpu_heavy: bool
    no_foreground_ui: bool
    pause_on_pressure: bool


@dataclass(frozen=True, slots=True)
class RestartState:
    schema_version: str
    campaign_id: str
    lane_id: str
    ledger_tail_sha256: str
    last_sequence: int
    retained_crash_count: int
    restart_generation: int
    bound_at: str


@dataclass(frozen=True, slots=True)
class LaunchGateResult:
    launch_allowed: bool
    countable: bool
    reason_codes: tuple[str, ...]


def _sha256_canonical_json(value: Mapping[str, Any]) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(body).hexdigest()


def compute_guardrails_digest(guardrails: Mapping[str, Any]) -> str:
    return _sha256_canonical_json(dict(guardrails))


def parse_resource_guardrails(manifest: Mapping[str, Any]) -> ResourceGuardrails | None:
    raw = manifest.get("resource_guardrails")
    if not isinstance(raw, dict):
        return None
    if set(raw.keys()) != set(_REQUIRED_GUARDRAIL_FIELDS):
        return None
    try:
        max_cpu = raw["max_sustained_cpu_percent"]
        max_mem = raw["max_memory_gib"]
        if not isinstance(max_cpu, int) or not isinstance(max_mem, int):
            return None
        if max_cpu < 1 or max_cpu > 80 or max_mem < 1:
            return None
        if raw["nice_cpu_heavy"] is not True:
            return None
        if raw["no_foreground_ui"] is not True:
            return None
        if raw["pause_on_pressure"] is not True:
            return None
    except KeyError:
        return None
    return ResourceGuardrails(
        max_sustained_cpu_percent=max_cpu,
        max_memory_gib=max_mem,
        nice_cpu_heavy=True,
        no_foreground_ui=True,
        pause_on_pressure=True,
    )


def validate_resource_state(
    state: Mapping[str, Any] | None,
    *,
    lane_id: str,
    manifest_sha256: str,
    guardrails: ResourceGuardrails,
) -> tuple[bool, tuple[str, ...]]:
    if state is None:
        return False, ("resource_controls_absent",)
    errors: list[str] = []
    if state.get("schema_version") != RESOURCE_STATE_SCHEMA:
        errors.append("resource_state_schema_invalid")
    if state.get("campaign_id") != CAMPAIGN_ID:
        errors.append("resource_state_campaign_mismatch")
    if state.get("lane_id") != lane_id:
        errors.append("resource_state_lane_mismatch")
    if state.get("manifest_sha256") != manifest_sha256:
        errors.append("resource_state_manifest_mismatch")
    expected_digest = compute_guardrails_digest(
        {
            "max_sustained_cpu_percent": guardrails.max_sustained_cpu_percent,
            "max_memory_gib": guardrails.max_memory_gib,
            "nice_cpu_heavy": guardrails.nice_cpu_heavy,
            "no_foreground_ui": guardrails.no_foreground_ui,
            "pause_on_pressure": guardrails.pause_on_pressure,
        }
    )
    if state.get("guardrails_digest") != expected_digest:
        errors.append("resource_state_guardrails_digest_mismatch")
    if state.get("controls_active") is not True:
        errors.append("resource_controls_inactive")
    declared_at = state.get("declared_at")
    if not isinstance(declared_at, str) or not declared_at:
        errors.append("resource_state_declared_at_missing")
    return (not errors, tuple(errors))


def validate_restart_state(
    state: Mapping[str, Any] | None,
    *,
    lane_id: str,
    ledger_tail_sha256: str,
    retained_crash_count: int,
    last_sequence: int,
) -> tuple[bool, tuple[str, ...]]:
    if state is None:
        return False, ("restart_state_absent",)
    errors: list[str] = []
    if state.get("schema_version") != RESTART_STATE_SCHEMA:
        errors.append("restart_state_schema_invalid")
    if state.get("campaign_id") != CAMPAIGN_ID:
        errors.append("restart_state_campaign_mismatch")
    if state.get("lane_id") != lane_id:
        errors.append("restart_state_lane_mismatch")
    tail = state.get("ledger_tail_sha256")
    if tail != ledger_tail_sha256:
        errors.append("restart_state_ledger_tail_mismatch")
    elif not isinstance(tail, str) or not _SHA256_RE.fullmatch(tail):
        errors.append("restart_state_ledger_tail_invalid")
    seq = state.get("last_sequence")
    if not isinstance(seq, int) or seq < 0:
        errors.append("restart_state_last_sequence_invalid")
    elif seq != last_sequence:
        errors.append("restart_state_last_sequence_mismatch")
    crash_count = state.get("retained_crash_count")
    if not isinstance(crash_count, int) or crash_count < 0:
        errors.append("restart_state_crash_count_invalid")
    elif crash_count != retained_crash_count:
        errors.append("restart_state_crash_count_mismatch")
    generation = state.get("restart_generation")
    if not isinstance(generation, int) or generation < 1:
        errors.append("restart_state_generation_invalid")
    bound_at = state.get("bound_at")
    if not isinstance(bound_at, str) or not bound_at:
        errors.append("restart_state_bound_at_missing")
    return (not errors, tuple(errors))


def _ledger_entry_sha256(entry: Mapping[str, Any]) -> str:
    return _sha256_canonical_json(entry)


def ledger_tail_sha256(entries: list[Mapping[str, Any]]) -> str:
    if not entries:
        return GENESIS_LEDGER_TAIL_SHA256
    return _ledger_entry_sha256(entries[-1])


def validate_crash_retention(
    entries: list[Mapping[str, Any]],
) -> tuple[bool, tuple[str, ...], int]:
    """Ensure crashed outcomes retain required crash metadata and sequence continuity."""
    return _assess_crash_retention(entries)


def assess_launch_gate(
    *,
    manifest: Mapping[str, Any],
    lane_id: str,
    manifest_sha256: str,
    resource_state: Mapping[str, Any] | None,
    restart_state: Mapping[str, Any] | None,
    ledger_entries: list[Mapping[str, Any]] | None = None,
) -> LaunchGateResult:
    """Deny launch and counting when resource controls or restart binding are absent."""
    reason_codes: list[str] = []
    if not _LANE_ID_RE.fullmatch(lane_id):
        reason_codes.append("lane_id_invalid")

    guardrails = parse_resource_guardrails(manifest)
    if guardrails is None:
        reason_codes.append("resource_guardrails_absent")

    ledger = ledger_entries or []
    retention_ok, retention_errors, retained_crash_count = _assess_crash_retention(ledger)
    if not retention_ok:
        reason_codes.extend(retention_errors)

    tail_sha = ledger_tail_sha256(ledger)
    last_sequence = ledger[-1]["sequence"] if ledger else 0

    resource_ok = False
    if guardrails is not None:
        resource_ok, resource_errors = validate_resource_state(
            resource_state,
            lane_id=lane_id,
            manifest_sha256=manifest_sha256,
            guardrails=guardrails,
        )
        if not resource_ok:
            reason_codes.extend(resource_errors)

    restart_ok = False
    if retention_ok:
        restart_ok, restart_errors = validate_restart_state(
            restart_state,
            lane_id=lane_id,
            ledger_tail_sha256=tail_sha,
            retained_crash_count=retained_crash_count,
            last_sequence=last_sequence,
        )
        if not restart_ok:
            reason_codes.extend(restart_errors)

    launch_allowed = guardrails is not None and resource_ok and restart_ok and retention_ok
    countable = launch_allowed
    return LaunchGateResult(
        launch_allowed=launch_allowed,
        countable=countable,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
    )


def _assess_crash_retention(
    ledger: list[Mapping[str, Any]],
) -> tuple[bool, tuple[str, ...], int]:
    if not ledger:
        return True, (), 0
    errors: list[str] = []
    expected_sequence = 1
    retained_crash_count = 0
    for entry in ledger:
        sequence = entry.get("sequence")
        if sequence != expected_sequence:
            errors.append("crash_retention_sequence_gap")
            break
        expected_sequence += 1
        if entry.get("outcome") == "crashed":
            retained_crash_count += 1
            crash = entry.get("crash")
            if not isinstance(crash, dict):
                errors.append("crash_retention_missing_crash_object")
                continue
            if crash.get("phase") not in _CRASH_PHASES:
                errors.append("crash_retention_invalid_crash_phase")
            error_class = crash.get("error_class")
            if not isinstance(error_class, str) or not error_class:
                errors.append("crash_retention_missing_error_class")
    return (not errors, tuple(dict.fromkeys(errors)), retained_crash_count)


def build_resource_state(
    *,
    lane_id: str,
    manifest_sha256: str,
    guardrails: ResourceGuardrails,
    declared_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": RESOURCE_STATE_SCHEMA,
        "campaign_id": CAMPAIGN_ID,
        "lane_id": lane_id,
        "manifest_sha256": manifest_sha256,
        "guardrails_digest": compute_guardrails_digest(
            {
                "max_sustained_cpu_percent": guardrails.max_sustained_cpu_percent,
                "max_memory_gib": guardrails.max_memory_gib,
                "nice_cpu_heavy": guardrails.nice_cpu_heavy,
                "no_foreground_ui": guardrails.no_foreground_ui,
                "pause_on_pressure": guardrails.pause_on_pressure,
            }
        ),
        "controls_active": True,
        "declared_at": declared_at,
    }


def build_restart_state(
    *,
    lane_id: str,
    ledger_tail_sha256: str,
    last_sequence: int,
    retained_crash_count: int,
    restart_generation: int,
    bound_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": RESTART_STATE_SCHEMA,
        "campaign_id": CAMPAIGN_ID,
        "lane_id": lane_id,
        "ledger_tail_sha256": ledger_tail_sha256,
        "last_sequence": last_sequence,
        "retained_crash_count": retained_crash_count,
        "restart_generation": restart_generation,
        "bound_at": bound_at,
    }
