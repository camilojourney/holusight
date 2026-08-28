"""Tests for AVO resource-limit and failure/restart launch gates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codesight.avo import resource_controller as rc

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "docs/avo/trial-manifest.v1.json"


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest_sha256(manifest: dict) -> str:
    return manifest["manifest_sha256"]


@pytest.fixture(scope="module")
def guardrails(manifest: dict) -> rc.ResourceGuardrails:
    parsed = rc.parse_resource_guardrails(manifest)
    assert parsed is not None
    return parsed


def test_parse_resource_guardrails_from_canonical_manifest(manifest: dict) -> None:
    guardrails = rc.parse_resource_guardrails(manifest)
    assert guardrails == rc.ResourceGuardrails(
        max_sustained_cpu_percent=80,
        max_memory_gib=48,
        nice_cpu_heavy=True,
        no_foreground_ui=True,
        pause_on_pressure=True,
    )


@pytest.mark.parametrize(
    "mutator",
    [
        lambda m: m.pop("resource_guardrails"),
        lambda m: m["resource_guardrails"].pop("pause_on_pressure"),
        lambda m: m["resource_guardrails"].update({"max_sustained_cpu_percent": 90}),
        lambda m: m["resource_guardrails"].update({"nice_cpu_heavy": False}),
    ],
    ids=["missing_block", "missing_field", "cpu_over_limit", "nice_disabled"],
)
def test_missing_or_invalid_guardrails_denies_launch(
    manifest: dict,
    manifest_sha256: str,
    mutator,
) -> None:
    broken = json.loads(json.dumps(manifest))
    mutator(broken)
    result = rc.assess_launch_gate(
        manifest=broken,
        lane_id="laptop-calibration-0001-0013",
        manifest_sha256=manifest_sha256,
        resource_state=None,
        restart_state=None,
    )
    assert result.launch_allowed is False
    assert result.countable is False
    assert "resource_guardrails_absent" in result.reason_codes


def test_missing_resource_state_denies_launch_and_count(
    manifest: dict,
    manifest_sha256: str,
) -> None:
    result = rc.assess_launch_gate(
        manifest=manifest,
        lane_id="laptop-calibration-0001-0013",
        manifest_sha256=manifest_sha256,
        resource_state=None,
        restart_state=rc.build_restart_state(
            lane_id="laptop-calibration-0001-0013",
            ledger_tail_sha256=rc.GENESIS_LEDGER_TAIL_SHA256,
            last_sequence=0,
            retained_crash_count=0,
            restart_generation=1,
            bound_at="2026-08-28T00:00:00Z",
        ),
    )
    assert result.launch_allowed is False
    assert result.countable is False
    assert "resource_controls_absent" in result.reason_codes


def test_inactive_resource_controls_denies_launch(
    manifest: dict,
    manifest_sha256: str,
    guardrails: rc.ResourceGuardrails,
) -> None:
    state = rc.build_resource_state(
        lane_id="laptop-calibration-0001-0013",
        manifest_sha256=manifest_sha256,
        guardrails=guardrails,
        declared_at="2026-08-28T00:00:00Z",
    )
    state["controls_active"] = False
    result = rc.assess_launch_gate(
        manifest=manifest,
        lane_id="laptop-calibration-0001-0013",
        manifest_sha256=manifest_sha256,
        resource_state=state,
        restart_state=rc.build_restart_state(
            lane_id="laptop-calibration-0001-0013",
            ledger_tail_sha256=rc.GENESIS_LEDGER_TAIL_SHA256,
            last_sequence=0,
            retained_crash_count=0,
            restart_generation=1,
            bound_at="2026-08-28T00:00:00Z",
        ),
    )
    assert result.launch_allowed is False
    assert "resource_controls_inactive" in result.reason_codes


def test_missing_restart_state_denies_launch_and_count(
    manifest: dict,
    manifest_sha256: str,
    guardrails: rc.ResourceGuardrails,
) -> None:
    resource_state = rc.build_resource_state(
        lane_id="laptop-calibration-0001-0013",
        manifest_sha256=manifest_sha256,
        guardrails=guardrails,
        declared_at="2026-08-28T00:00:00Z",
    )
    result = rc.assess_launch_gate(
        manifest=manifest,
        lane_id="laptop-calibration-0001-0013",
        manifest_sha256=manifest_sha256,
        resource_state=resource_state,
        restart_state=None,
    )
    assert result.launch_allowed is False
    assert result.countable is False
    assert "restart_state_absent" in result.reason_codes


def test_restart_state_ledger_tail_mismatch_denies_launch(
    manifest: dict,
    manifest_sha256: str,
    guardrails: rc.ResourceGuardrails,
) -> None:
    resource_state = rc.build_resource_state(
        lane_id="laptop-calibration-0001-0013",
        manifest_sha256=manifest_sha256,
        guardrails=guardrails,
        declared_at="2026-08-28T00:00:00Z",
    )
    restart_state = rc.build_restart_state(
        lane_id="laptop-calibration-0001-0013",
        ledger_tail_sha256="sha256:" + ("f" * 64),
        last_sequence=0,
        retained_crash_count=0,
        restart_generation=1,
        bound_at="2026-08-28T00:00:00Z",
    )
    result = rc.assess_launch_gate(
        manifest=manifest,
        lane_id="laptop-calibration-0001-0013",
        manifest_sha256=manifest_sha256,
        resource_state=resource_state,
        restart_state=restart_state,
    )
    assert result.launch_allowed is False
    assert "restart_state_ledger_tail_mismatch" in result.reason_codes


def test_crashed_outcome_without_crash_object_denies_count(
    manifest: dict,
    manifest_sha256: str,
    guardrails: rc.ResourceGuardrails,
) -> None:
    ledger = [
        {
            "sequence": 1,
            "outcome": "crashed",
        }
    ]
    resource_state = rc.build_resource_state(
        lane_id="laptop-calibration-0001-0013",
        manifest_sha256=manifest_sha256,
        guardrails=guardrails,
        declared_at="2026-08-28T00:00:00Z",
    )
    restart_state = rc.build_restart_state(
        lane_id="laptop-calibration-0001-0013",
        ledger_tail_sha256=rc.ledger_tail_sha256(ledger),
        last_sequence=1,
        retained_crash_count=1,
        restart_generation=1,
        bound_at="2026-08-28T00:00:00Z",
    )
    result = rc.assess_launch_gate(
        manifest=manifest,
        lane_id="laptop-calibration-0001-0013",
        manifest_sha256=manifest_sha256,
        resource_state=resource_state,
        restart_state=restart_state,
        ledger_entries=ledger,
    )
    assert result.launch_allowed is False
    assert result.countable is False
    assert "crash_retention_missing_crash_object" in result.reason_codes


def test_retained_crash_count_mismatch_denies_launch(
    manifest: dict,
    manifest_sha256: str,
    guardrails: rc.ResourceGuardrails,
) -> None:
    ledger = [
        {
            "sequence": 1,
            "outcome": "crashed",
            "crash": {"phase": "evaluate", "error_class": "RuntimeError"},
        }
    ]
    resource_state = rc.build_resource_state(
        lane_id="laptop-calibration-0001-0013",
        manifest_sha256=manifest_sha256,
        guardrails=guardrails,
        declared_at="2026-08-28T00:00:00Z",
    )
    restart_state = rc.build_restart_state(
        lane_id="laptop-calibration-0001-0013",
        ledger_tail_sha256=rc.ledger_tail_sha256(ledger),
        last_sequence=1,
        retained_crash_count=0,
        restart_generation=1,
        bound_at="2026-08-28T00:00:00Z",
    )
    result = rc.assess_launch_gate(
        manifest=manifest,
        lane_id="laptop-calibration-0001-0013",
        manifest_sha256=manifest_sha256,
        resource_state=resource_state,
        restart_state=restart_state,
        ledger_entries=ledger,
    )
    assert result.launch_allowed is False
    assert "restart_state_crash_count_mismatch" in result.reason_codes


def test_valid_controls_and_restart_state_allow_launch_and_count(
    manifest: dict,
    manifest_sha256: str,
    guardrails: rc.ResourceGuardrails,
) -> None:
    ledger = [
        {
            "sequence": 1,
            "outcome": "crashed",
            "crash": {"phase": "evaluate", "error_class": "RuntimeError"},
        },
        {
            "sequence": 2,
            "outcome": "rejected",
        },
    ]
    resource_state = rc.build_resource_state(
        lane_id="laptop-calibration-0001-0013",
        manifest_sha256=manifest_sha256,
        guardrails=guardrails,
        declared_at="2026-08-28T00:00:00Z",
    )
    restart_state = rc.build_restart_state(
        lane_id="laptop-calibration-0001-0013",
        ledger_tail_sha256=rc.ledger_tail_sha256(ledger),
        last_sequence=2,
        retained_crash_count=1,
        restart_generation=2,
        bound_at="2026-08-28T00:00:00Z",
    )
    result = rc.assess_launch_gate(
        manifest=manifest,
        lane_id="laptop-calibration-0001-0013",
        manifest_sha256=manifest_sha256,
        resource_state=resource_state,
        restart_state=restart_state,
        ledger_entries=ledger,
    )
    assert result.launch_allowed is True
    assert result.countable is True
    assert result.reason_codes == ()


def test_fresh_lane_with_genesis_restart_allows_launch(
    manifest: dict,
    manifest_sha256: str,
    guardrails: rc.ResourceGuardrails,
) -> None:
    resource_state = rc.build_resource_state(
        lane_id="laptop-calibration-0001-0013",
        manifest_sha256=manifest_sha256,
        guardrails=guardrails,
        declared_at="2026-08-28T00:00:00Z",
    )
    restart_state = rc.build_restart_state(
        lane_id="laptop-calibration-0001-0013",
        ledger_tail_sha256=rc.GENESIS_LEDGER_TAIL_SHA256,
        last_sequence=0,
        retained_crash_count=0,
        restart_generation=1,
        bound_at="2026-08-28T00:00:00Z",
    )
    result = rc.assess_launch_gate(
        manifest=manifest,
        lane_id="laptop-calibration-0001-0013",
        manifest_sha256=manifest_sha256,
        resource_state=resource_state,
        restart_state=restart_state,
        ledger_entries=[],
    )
    assert result.launch_allowed is True
    assert result.countable is True
