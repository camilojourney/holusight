"""Static checks for future G2 runtime-enforcement adversarial vectors.

The fixture is intentionally declarative: these tests never create a child,
invoke an evaluator, allocate pressure, or inspect host resources.
"""

from __future__ import annotations

import json
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "runtime_enforcement_adversarial_vectors.v1.json"


def _load() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_runtime_vectors_are_static_and_execution_remains_paused():
    fixture = _load()

    assert fixture["schema_version"] == "holusight-runtime-enforcement-vectors/v1"
    assert fixture["status"] == "static_vectors_only"
    assert fixture["execution_gate"] == "blocked_until_g2_trusted_sandbox"
    assert fixture["valid_trials"] == "paused"
    assert fixture["network"] == "denied"
    assert fixture["telemetry"] == "denied"
    assert fixture["credentials"] == "not_accessed"
    assert "evaluator_lifecycle_command" in fixture["common_contract"]["forbidden_actions"]

    for vector in fixture["vectors"]:
        assert vector["synthetic_stimulus"]["executable_payload_present"] is False
        assert "command" not in vector["synthetic_stimulus"]


def test_runtime_vectors_cover_each_required_adversarial_boundary_independently():
    vectors = _load()["vectors"]
    categories = {vector["category"] for vector in vectors}

    assert {
        "cpu_exhaustion",
        "memory_exhaustion",
        "process_exhaustion",
        "file_exhaustion",
        "time_exhaustion",
        "child_process_containment",
        "cleanup_and_restart",
        "bounded_logs",
        "disk_floor",
        "safe_pause_recovery",
    } <= categories
    assert len({vector["vector_id"] for vector in vectors}) == len(vectors)
    assert len({vector["isolation_key"] for vector in vectors}) == len(vectors)

    for vector in vectors:
        assert vector["declared_limits"]
        assert all(
            isinstance(value, int) and value > 0
            for value in vector["declared_limits"].values()
        )
        assert vector["required_oracles"]["primary_terminal_reason"]


def test_runtime_vectors_fail_closed_and_prohibit_automatic_recovery():
    fixture = _load()
    contract = fixture["common_contract"]
    universal_oracles = contract["universal_oracles"]
    vectors = {vector["vector_id"]: vector["required_oracles"] for vector in fixture["vectors"]}

    assert contract["on_missing_capability"] == "fail_closed_no_trial"
    assert any(
        "missing, ambiguous, or unenforceable limit" in oracle for oracle in universal_oracles
    )
    assert any("No retry, restart, or resume" in oracle for oracle in universal_oracles)

    assert vectors["descendant-escape-containment"][
        "must_fail_if_any_descendant_identity_is_unknown"
    ]
    assert vectors["bounded-log-overflow"]["must_not_drop_terminal_reason_or_cleanup_receipt"]
    assert vectors["disk-reserve-floor"]["must_fail_if_free_space_measurement_is_unavailable"]
    assert vectors["pause-at-idempotent-boundary"]["must_not_auto_resume"]
    assert vectors["recovery-rejects-tampered-checkpoint"]["must_fail_closed_before_any_new_work"]
    assert vectors["cleanup-before-explicit-restart"][
        "must_refuse_restart_without_new_authorization"
    ]
