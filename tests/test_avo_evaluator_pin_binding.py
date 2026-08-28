"""Tests for AVO evaluator pin and immutable identity launch gates.

Proves the campaign cannot launch or count a trial without a final G2 evaluator
implementation and immutable evaluator identity/pin. Exercises public spec 022
contract behavior only; does not overlap AQ-R24 manifest-identity binding.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codesight import eval_suite
from codesight.avo import evaluator_pin_binding as epb
from codesight.eval_pilot import EvaluationSubject

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "docs/avo/trial-manifest.v1.json"
FIXTURE_METHOD_SHA256 = "sha256:8507da9e978b3a313f3ab6d8b0c28b752a223b8b27dac13e4a9781f5f62b335a"
FIXTURE_EVALUATOR_DIGEST = "sha256:" + ("a" * 64)
LANE_ID = "laptop-calibration-0001-0013"


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest_sha256(manifest: dict) -> str:
    return manifest["manifest_sha256"]


@pytest.fixture(scope="module")
def loaded_suite() -> eval_suite.LoadedSuite:
    return eval_suite.load_suite(REPO_ROOT)


def _subject(*, clean: bool = True) -> EvaluationSubject:
    return EvaluationSubject(
        repository_id="https://github.com/camilojourney/holusight.git",
        commit="a" * 40,
        tree="b" * 40,
        clean=clean,
        branch="annotation-only",
    )


def _pinned_pin_state(
    manifest_sha256: str,
    *,
    evaluator_digest: str = FIXTURE_EVALUATOR_DIGEST,
    method_config_sha256: str = FIXTURE_METHOD_SHA256,
) -> dict:
    return epb.build_evaluator_pin_state(
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
        evaluator_status=epb.G2_PINNED_STATUS,
        evaluator_digest=evaluator_digest,
        method_config_sha256=method_config_sha256,
        bound_at="2026-08-28T00:00:00Z",
    )


def _trial_entry(*, evaluator_digest: str, method_config_sha256: str) -> dict:
    return {
        "sequence": 1,
        "outcome": "completed",
        "trial": {
            "evaluator_identity": {
                "digest": evaluator_digest,
                "method_config_sha256": method_config_sha256,
            }
        },
    }


def test_public_suite_contract_blocks_g2_evaluator(loaded_suite: eval_suite.LoadedSuite) -> None:
    assert loaded_suite.suite.evaluator_execution == epb.G2_BLOCKED_STATUS
    assert loaded_suite.suite.runner == "not_implemented"
    assert epb.is_public_g2_evaluator_blocked(REPO_ROOT) is True


def test_comparison_identity_is_not_ready_under_public_contract(
    loaded_suite: eval_suite.LoadedSuite,
) -> None:
    binding = eval_suite.parse_comparison_identity(
        {
            "schema_version": "holusight-eval-comparison-identity/v1",
            "git_subject": _subject().model_dump(mode="json"),
            "corpus_sha256": loaded_suite.development_sha256,
            "evaluator": {"status": epb.G2_BLOCKED_STATUS},
            "configuration_sha256": loaded_suite.method_sha256,
            "suite_sha256": loaded_suite.suite_sha256,
            "holdout_manifest_sha256": loaded_suite.holdout_manifest_sha256,
        }
    )
    assert eval_suite.comparison_identity_is_ready(binding) is False


def test_canonical_manifest_requires_evaluator_identity_field(manifest: dict) -> None:
    assert "evaluator_identity" in manifest["trial_contract"]["required_fields"]


def test_compute_evaluator_identity_digest_is_stable() -> None:
    digest = epb.compute_evaluator_identity_digest(
        digest=FIXTURE_EVALUATOR_DIGEST,
        method_config_sha256=FIXTURE_METHOD_SHA256,
    )
    again = epb.compute_evaluator_identity_digest(
        digest=FIXTURE_EVALUATOR_DIGEST,
        method_config_sha256=FIXTURE_METHOD_SHA256,
    )
    assert digest == again
    assert digest.startswith("sha256:")


def test_missing_pin_state_denies_launch_and_count(manifest_sha256: str) -> None:
    result = epb.assess_evaluator_pin_gate(
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
        pin_state=None,
        suite_evaluator_blocked=True,
    )
    assert result.launch_allowed is False
    assert result.countable is False
    assert "evaluator_pin_state_absent" in result.reason_codes
    assert "g2_evaluator_not_implemented" in result.reason_codes


def test_blocked_pin_state_denies_launch_and_count(manifest_sha256: str) -> None:
    pin_state = epb.build_evaluator_pin_state(
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
        evaluator_status=epb.G2_BLOCKED_STATUS,
        bound_at="2026-08-28T00:00:00Z",
    )
    result = epb.assess_evaluator_pin_gate(
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
        pin_state=pin_state,
        suite_evaluator_blocked=True,
    )
    assert result.launch_allowed is False
    assert result.countable is False
    assert "evaluator_pin_blocked" in result.reason_codes


def test_blocked_pin_state_cannot_smuggle_identity_fields(manifest_sha256: str) -> None:
    pin_state = epb.build_evaluator_pin_state(
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
        evaluator_status=epb.G2_BLOCKED_STATUS,
        bound_at="2026-08-28T00:00:00Z",
    )
    pin_state["evaluator_digest"] = FIXTURE_EVALUATOR_DIGEST
    ok, errors, identity = epb.validate_evaluator_pin_state(
        pin_state,
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
    )
    assert ok is False
    assert identity is None
    assert "evaluator_pin_blocked_carries_identity" in errors


def test_public_g2_block_denies_launch_even_with_pinned_state(manifest_sha256: str) -> None:
    pin_state = _pinned_pin_state(manifest_sha256)
    result = epb.assess_evaluator_pin_gate(
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
        pin_state=pin_state,
        suite_evaluator_blocked=True,
        comparison_ready=True,
    )
    assert result.launch_allowed is False
    assert result.countable is False
    assert "g2_evaluator_not_implemented" in result.reason_codes


def test_pinned_state_without_comparison_ready_denies_launch(manifest_sha256: str) -> None:
    pin_state = _pinned_pin_state(manifest_sha256)
    result = epb.assess_evaluator_pin_gate(
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
        pin_state=pin_state,
        suite_evaluator_blocked=False,
        comparison_ready=False,
    )
    assert result.launch_allowed is False
    assert "evaluator_comparison_identity_not_ready" in result.reason_codes


def test_pinned_state_with_ready_comparison_allows_launch_when_g2_unblocked(
    manifest_sha256: str,
) -> None:
    pin_state = _pinned_pin_state(manifest_sha256)
    ledger = [_trial_entry(
        evaluator_digest=FIXTURE_EVALUATOR_DIGEST,
        method_config_sha256=FIXTURE_METHOD_SHA256,
    )]
    identity_digest = pin_state["evaluator_identity_digest"]
    result = epb.assess_evaluator_pin_gate(
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
        pin_state=pin_state,
        suite_evaluator_blocked=False,
        comparison_ready=True,
        ledger_entries=ledger,
        checkpoint_evaluator_digest=identity_digest,
    )
    assert result.launch_allowed is True
    assert result.countable is True
    assert result.reason_codes == ()


def test_trial_evaluator_identity_mismatch_denies_count(manifest_sha256: str) -> None:
    pin_state = _pinned_pin_state(manifest_sha256)
    ledger = [_trial_entry(
        evaluator_digest="sha256:" + ("b" * 64),
        method_config_sha256=FIXTURE_METHOD_SHA256,
    )]
    result = epb.assess_evaluator_pin_gate(
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
        pin_state=pin_state,
        suite_evaluator_blocked=False,
        comparison_ready=True,
        ledger_entries=ledger,
    )
    assert result.launch_allowed is False
    assert result.countable is False
    assert "trial_evaluator_identity_mismatch" in result.reason_codes


def test_missing_trial_evaluator_identity_denies_count(manifest_sha256: str) -> None:
    pin_state = _pinned_pin_state(manifest_sha256)
    ledger = [{"sequence": 1, "outcome": "completed", "trial": {}}]
    result = epb.assess_evaluator_pin_gate(
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
        pin_state=pin_state,
        suite_evaluator_blocked=False,
        comparison_ready=True,
        ledger_entries=ledger,
    )
    assert result.countable is False
    assert "trial_evaluator_identity_absent" in result.reason_codes


def test_checkpoint_evaluator_digest_mismatch_denies_count(manifest_sha256: str) -> None:
    pin_state = _pinned_pin_state(manifest_sha256)
    ledger = [_trial_entry(
        evaluator_digest=FIXTURE_EVALUATOR_DIGEST,
        method_config_sha256=FIXTURE_METHOD_SHA256,
    )]
    result = epb.assess_evaluator_pin_gate(
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
        pin_state=pin_state,
        suite_evaluator_blocked=False,
        comparison_ready=True,
        ledger_entries=ledger,
        checkpoint_evaluator_digest="sha256:" + ("c" * 64),
    )
    assert result.countable is False
    assert "checkpoint_evaluator_digest_mismatch" in result.reason_codes


def test_pin_state_manifest_mismatch_is_rejected(manifest_sha256: str) -> None:
    pin_state = _pinned_pin_state("sha256:" + ("d" * 64))
    ok, errors, identity = epb.validate_evaluator_pin_state(
        pin_state,
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
    )
    assert ok is False
    assert identity is None
    assert "evaluator_pin_state_manifest_mismatch" in errors


def test_validate_trial_evaluator_binding_accepts_matching_identity(
    manifest_sha256: str,
) -> None:
    pin_state = _pinned_pin_state(manifest_sha256)
    ok, errors, bound = epb.validate_evaluator_pin_state(
        pin_state,
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
    )
    assert ok is True
    assert errors == ()
    assert bound is not None
    trial_ok, trial_errors = epb.validate_trial_evaluator_binding(
        {
            "digest": FIXTURE_EVALUATOR_DIGEST,
            "method_config_sha256": FIXTURE_METHOD_SHA256,
        },
        bound,
    )
    assert trial_ok is True
    assert trial_errors == ()


def test_real_repo_public_contract_denies_launch_end_to_end(manifest_sha256: str) -> None:
    """Report-bounded proof: canonical repo state cannot launch or count trials."""
    loaded = eval_suite.load_suite(REPO_ROOT)
    pin_state = epb.build_evaluator_pin_state(
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
        evaluator_status=epb.G2_BLOCKED_STATUS,
        bound_at="2026-08-28T00:00:00Z",
    )
    binding = eval_suite.parse_comparison_identity(
        {
            "schema_version": "holusight-eval-comparison-identity/v1",
            "git_subject": _subject().model_dump(mode="json"),
            "corpus_sha256": loaded.development_sha256,
            "evaluator": {"status": epb.G2_BLOCKED_STATUS},
            "configuration_sha256": loaded.method_sha256,
            "suite_sha256": loaded.suite_sha256,
            "holdout_manifest_sha256": loaded.holdout_manifest_sha256,
        }
    )
    result = epb.assess_evaluator_pin_gate(
        lane_id=LANE_ID,
        manifest_sha256=manifest_sha256,
        pin_state=pin_state,
        suite_evaluator_blocked=epb.is_public_g2_evaluator_blocked(REPO_ROOT),
        comparison_ready=eval_suite.comparison_identity_is_ready(binding),
    )
    assert result.launch_allowed is False
    assert result.countable is False
    assert "g2_evaluator_not_implemented" in result.reason_codes
