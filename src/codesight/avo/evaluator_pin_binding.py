"""AVO evaluator pin and immutable identity launch gates (spec 023 remediation slice).

Lanes must not launch or count valid trials unless the final G2 evaluator is pinned
with an immutable evaluator identity that matches ledger trial records and checkpoint
digests. This slice reads the public suite contract (spec 022) without modifying G2
code, AQ-R24 identity binding, ledger schemas, resource controls, or purpose schemas.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from codesight import eval_suite

CAMPAIGN_ID = "holusight-avo-v1"
EVALUATOR_PIN_STATE_SCHEMA = "holusight-avo-evaluator-pin-state/v1"
G2_BLOCKED_STATUS = "blocked_until_g2_trusted_sandbox"
G2_PINNED_STATUS = "pinned"

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_LANE_ID_RE = re.compile(r"^[a-z0-9-]+$")

_COUNTABLE_OUTCOMES = frozenset(
    {"completed", "kept", "discarded", "indeterminate", "crashed", "rejected"}
)


@dataclass(frozen=True, slots=True)
class AvoEvaluatorIdentity:
    digest: str
    method_config_sha256: str


@dataclass(frozen=True, slots=True)
class EvaluatorPinGateResult:
    launch_allowed: bool
    countable: bool
    reason_codes: tuple[str, ...]


def _sha256_canonical_json(value: Mapping[str, Any]) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(body).hexdigest()


def compute_evaluator_identity_digest(*, digest: str, method_config_sha256: str) -> str:
    """Canonical digest for AVO trial evaluator_identity and checkpoint binding."""
    if not _SHA256_RE.fullmatch(digest):
        raise ValueError("digest must be sha256:<64 lowercase hex>")
    if not _SHA256_RE.fullmatch(method_config_sha256):
        raise ValueError("method_config_sha256 must be sha256:<64 lowercase hex>")
    return _sha256_canonical_json(
        {"digest": digest, "method_config_sha256": method_config_sha256}
    )


def parse_evaluator_identity(payload: Mapping[str, Any] | None) -> AvoEvaluatorIdentity | None:
    if payload is None or not isinstance(payload, Mapping):
        return None
    digest = payload.get("digest")
    method_sha = payload.get("method_config_sha256")
    if not isinstance(digest, str) or not isinstance(method_sha, str):
        return None
    if not _SHA256_RE.fullmatch(digest) or not _SHA256_RE.fullmatch(method_sha):
        return None
    return AvoEvaluatorIdentity(digest=digest, method_config_sha256=method_sha)


def is_public_g2_evaluator_blocked(repo_root: Path) -> bool:
    """Return True when the public suite contract still blocks G2 evaluator execution."""
    loaded = eval_suite.load_suite(repo_root)
    return loaded.suite.evaluator_execution == G2_BLOCKED_STATUS


def validate_evaluator_pin_state(
    state: Mapping[str, Any] | None,
    *,
    lane_id: str,
    manifest_sha256: str,
) -> tuple[bool, tuple[str, ...], AvoEvaluatorIdentity | None]:
    if state is None:
        return False, ("evaluator_pin_state_absent",), None

    errors: list[str] = []
    if state.get("schema_version") != EVALUATOR_PIN_STATE_SCHEMA:
        errors.append("evaluator_pin_state_schema_invalid")
    if state.get("campaign_id") != CAMPAIGN_ID:
        errors.append("evaluator_pin_state_campaign_mismatch")
    if state.get("lane_id") != lane_id:
        errors.append("evaluator_pin_state_lane_mismatch")
    if state.get("manifest_sha256") != manifest_sha256:
        errors.append("evaluator_pin_state_manifest_mismatch")

    status = state.get("evaluator_status")
    bound_at = state.get("bound_at")
    if not isinstance(bound_at, str) or not bound_at:
        errors.append("evaluator_pin_state_bound_at_missing")

    identity: AvoEvaluatorIdentity | None = None
    if status == G2_BLOCKED_STATUS:
        if any(
            state.get(key) is not None
            for key in (
                "evaluator_identity_digest",
                "evaluator_digest",
                "method_config_sha256",
            )
        ):
            errors.append("evaluator_pin_blocked_carries_identity")
    elif status == G2_PINNED_STATUS:
        digest = state.get("evaluator_digest")
        method_sha = state.get("method_config_sha256")
        identity_digest = state.get("evaluator_identity_digest")
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            errors.append("evaluator_pin_missing_evaluator_digest")
        if not isinstance(method_sha, str) or not _SHA256_RE.fullmatch(method_sha):
            errors.append("evaluator_pin_missing_method_config_sha256")
        if not isinstance(identity_digest, str) or not _SHA256_RE.fullmatch(identity_digest):
            errors.append("evaluator_pin_missing_identity_digest")
        elif isinstance(digest, str) and isinstance(method_sha, str):
            expected = compute_evaluator_identity_digest(
                digest=digest,
                method_config_sha256=method_sha,
            )
            if identity_digest != expected:
                errors.append("evaluator_pin_identity_digest_mismatch")
            else:
                identity = AvoEvaluatorIdentity(digest=digest, method_config_sha256=method_sha)
    else:
        errors.append("evaluator_pin_status_invalid")

    ok = not errors
    return ok, tuple(dict.fromkeys(errors)), identity if ok else None


def validate_trial_evaluator_binding(
    trial_identity: Mapping[str, Any] | None,
    bound: AvoEvaluatorIdentity,
) -> tuple[bool, tuple[str, ...]]:
    parsed = parse_evaluator_identity(trial_identity)
    if parsed is None:
        return False, ("trial_evaluator_identity_absent",)
    expected_digest = compute_evaluator_identity_digest(
        digest=bound.digest,
        method_config_sha256=bound.method_config_sha256,
    )
    actual_digest = compute_evaluator_identity_digest(
        digest=parsed.digest,
        method_config_sha256=parsed.method_config_sha256,
    )
    if actual_digest != expected_digest:
        return False, ("trial_evaluator_identity_mismatch",)
    return True, ()


def validate_checkpoint_evaluator_digest(
    checkpoint_digest: str | None,
    bound: AvoEvaluatorIdentity,
) -> tuple[bool, tuple[str, ...]]:
    if checkpoint_digest is None:
        return False, ("checkpoint_evaluator_digest_absent",)
    if not isinstance(checkpoint_digest, str) or not _SHA256_RE.fullmatch(checkpoint_digest):
        return False, ("checkpoint_evaluator_digest_invalid",)
    expected = compute_evaluator_identity_digest(
        digest=bound.digest,
        method_config_sha256=bound.method_config_sha256,
    )
    if checkpoint_digest != expected:
        return False, ("checkpoint_evaluator_digest_mismatch",)
    return True, ()


def _extract_trial_identity(entry: Mapping[str, Any]) -> Mapping[str, Any] | None:
    trial = entry.get("trial")
    if not isinstance(trial, Mapping):
        return None
    identity = trial.get("evaluator_identity")
    return identity if isinstance(identity, Mapping) else None


def assess_evaluator_pin_gate(
    *,
    lane_id: str,
    manifest_sha256: str,
    pin_state: Mapping[str, Any] | None,
    suite_evaluator_blocked: bool,
    comparison_ready: bool | None = None,
    ledger_entries: list[Mapping[str, Any]] | None = None,
    checkpoint_evaluator_digest: str | None = None,
) -> EvaluatorPinGateResult:
    """Deny launch and counting until G2 evaluator pin and identity binding are satisfied."""
    reason_codes: list[str] = []

    if not _LANE_ID_RE.fullmatch(lane_id):
        reason_codes.append("lane_id_invalid")

    if suite_evaluator_blocked:
        reason_codes.append("g2_evaluator_not_implemented")

    pin_ok, pin_errors, bound_identity = validate_evaluator_pin_state(
        pin_state,
        lane_id=lane_id,
        manifest_sha256=manifest_sha256,
    )
    if not pin_ok:
        reason_codes.extend(pin_errors)
    elif pin_state is not None and pin_state.get("evaluator_status") == G2_BLOCKED_STATUS:
        reason_codes.append("evaluator_pin_blocked")

    if pin_ok and bound_identity is not None:
        if comparison_ready is False:
            reason_codes.append("evaluator_comparison_identity_not_ready")
        elif comparison_ready is None:
            reason_codes.append("evaluator_comparison_identity_unverified")

    ledger = ledger_entries or []
    if bound_identity is not None and ledger:
        for entry in ledger:
            outcome = entry.get("outcome")
            if outcome not in _COUNTABLE_OUTCOMES:
                continue
            trial_ok, trial_errors = validate_trial_evaluator_binding(
                _extract_trial_identity(entry),
                bound_identity,
            )
            if not trial_ok:
                reason_codes.extend(trial_errors)
                break

    if bound_identity is not None and checkpoint_evaluator_digest is not None:
        checkpoint_ok, checkpoint_errors = validate_checkpoint_evaluator_digest(
            checkpoint_evaluator_digest,
            bound_identity,
        )
        if not checkpoint_ok:
            reason_codes.extend(checkpoint_errors)

    launch_allowed = (
        not suite_evaluator_blocked
        and pin_ok
        and bound_identity is not None
        and comparison_ready is True
        and not reason_codes
    )
    countable = launch_allowed
    if bound_identity is None:
        countable = False
    elif reason_codes:
        countable = False

    return EvaluatorPinGateResult(
        launch_allowed=launch_allowed,
        countable=countable,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
    )


def build_evaluator_pin_state(
    *,
    lane_id: str,
    manifest_sha256: str,
    evaluator_status: str,
    evaluator_digest: str | None = None,
    method_config_sha256: str | None = None,
    bound_at: str,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "schema_version": EVALUATOR_PIN_STATE_SCHEMA,
        "campaign_id": CAMPAIGN_ID,
        "lane_id": lane_id,
        "manifest_sha256": manifest_sha256,
        "evaluator_status": evaluator_status,
        "bound_at": bound_at,
    }
    if evaluator_status == G2_PINNED_STATUS:
        if evaluator_digest is None or method_config_sha256 is None:
            raise ValueError("pinned evaluator pin requires digest and method_config_sha256")
        state["evaluator_digest"] = evaluator_digest
        state["method_config_sha256"] = method_config_sha256
        state["evaluator_identity_digest"] = compute_evaluator_identity_digest(
            digest=evaluator_digest,
            method_config_sha256=method_config_sha256,
        )
    return state
