"""Tests for AVO AQ-R24 and immutable manifest/evaluator identity launch gates.

Proves launch and valid-trial counting remain denied unless visible AQ-R24,
manifest commit/tree binding, manifest self-hash, and expected evaluator identity
hashes are present and valid. Machine-independent; no G2 modification.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from codesight import eval_suite
from codesight.avo import aqr24_identities as aqr

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "docs/avo/trial-manifest.v1.json"
AQ_R24_FIXTURE = REPO_ROOT / "tests/fixtures/holusight_aq_r24_v1.jsonl"
METHOD_SHA256 = "sha256:8507da9e978b3a313f3ab6d8b0c28b752a223b8b27dac13e4a9781f5f62b335a"


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def loaded_suite() -> eval_suite.LoadedSuite:
    return eval_suite.load_suite(REPO_ROOT)


def _gate(
    manifest: dict,
    *,
    actual_commit: str | None = None,
    actual_tree: str | None = None,
    suite_evaluator_blocked: bool | None = None,
    pin_state: dict | None = None,
) -> aqr.Aqr24IdentityGateResult:
    git_base = manifest["git_base"]
    return aqr.assess_aqr24_identity_gate(
        repo_root=REPO_ROOT,
        manifest=manifest,
        actual_commit=actual_commit or git_base["commit"],
        actual_tree=actual_tree or git_base["tree"],
        suite_evaluator_blocked=suite_evaluator_blocked,
        pin_state=pin_state,
    )


def test_aq_r24_fixture_is_visible_and_content_bound() -> None:
    assert AQ_R24_FIXTURE.is_file()
    text = AQ_R24_FIXTURE.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line.strip()]
    assert len(lines) == 24
    case_ids = {json.loads(line)["case_id"] for line in lines}
    assert case_ids == {f"AQ-{i:02d}" for i in range(1, 25)}
    assert "AQ-R24" not in AQ_R24_FIXTURE.read_text(encoding="utf-8")
    assert "AQ-24" in case_ids


def test_manifest_self_hash_recomputes(manifest: dict) -> None:
    ok, errors = aqr.verify_manifest_self_hash(manifest)
    assert ok is True
    assert errors == ()
    assert aqr.compute_manifest_self_hash(manifest) == manifest["manifest_sha256"]


def test_manifest_git_binding_requires_exact_commit_and_tree(manifest: dict) -> None:
    ok, _ = aqr.verify_manifest_git_binding(
        manifest,
        actual_commit=manifest["git_base"]["commit"],
        actual_tree=manifest["git_base"]["tree"],
    )
    assert ok is True

    bad_commit, _ = aqr.verify_manifest_git_binding(
        manifest,
        actual_commit="a" * 40,
        actual_tree=manifest["git_base"]["tree"],
    )
    assert bad_commit is False

    bad_tree, errors = aqr.verify_manifest_git_binding(
        manifest,
        actual_commit=manifest["git_base"]["commit"],
        actual_tree="b" * 40,
    )
    assert bad_tree is False
    assert "manifest_git_tree_mismatch" in errors


def test_aq_r24_binding_verifies_fixture_hash(manifest: dict) -> None:
    ok, errors, cases = aqr.verify_aq_r24_binding(REPO_ROOT, manifest)
    assert ok is True
    assert errors == ()
    assert cases is not None
    assert len(cases) == 24
    assert manifest["aq_r24"]["fixture_sha256"] == aqr.sha256_bytes(AQ_R24_FIXTURE.read_bytes())


def test_expected_evaluator_identity_requires_blocked_status_while_g2_absent(
    manifest: dict,
    loaded_suite: eval_suite.LoadedSuite,
) -> None:
    assert loaded_suite.suite.evaluator_execution == aqr.G2_BLOCKED_STATUS
    ok, errors = aqr.verify_expected_evaluator_identity(
        manifest,
        suite_evaluator_blocked=True,
    )
    assert ok is False
    assert "g2_evaluator_not_implemented" in errors


def test_launch_denied_under_public_g2_block(manifest: dict) -> None:
    result = _gate(manifest, suite_evaluator_blocked=True)
    assert result.launch_allowed is False
    assert result.countable is False
    assert "g2_evaluator_not_implemented" in result.reason_codes


def test_launch_denied_when_aq_r24_binding_removed(manifest: dict) -> None:
    broken = copy.deepcopy(manifest)
    del broken["aq_r24"]
    result = _gate(broken)
    assert result.launch_allowed is False
    assert "aq_r24_binding_absent" in result.reason_codes


def test_launch_denied_when_aq_r24_fixture_hash_mismatch(manifest: dict) -> None:
    broken = copy.deepcopy(manifest)
    broken["aq_r24"] = copy.deepcopy(broken["aq_r24"])
    broken["aq_r24"]["fixture_sha256"] = "sha256:" + ("0" * 64)
    result = _gate(broken)
    assert result.launch_allowed is False
    assert "aq_r24_fixture_hash_mismatch" in result.reason_codes


def test_launch_denied_when_manifest_self_hash_mismatch(manifest: dict) -> None:
    broken = copy.deepcopy(manifest)
    broken["manifest_sha256"] = "sha256:" + ("1" * 64)
    result = _gate(broken)
    assert result.launch_allowed is False
    assert "manifest_self_hash_mismatch" in result.reason_codes


def test_launch_denied_when_git_commit_substituted(manifest: dict) -> None:
    result = _gate(
        manifest,
        actual_commit="f" * 40,
        actual_tree=manifest["git_base"]["tree"],
    )
    assert result.launch_allowed is False
    assert "manifest_git_commit_mismatch" in result.reason_codes


def test_launch_denied_when_expected_evaluator_identity_absent(manifest: dict) -> None:
    broken = copy.deepcopy(manifest)
    del broken["expected_evaluator_identity"]
    result = _gate(broken, suite_evaluator_blocked=True)
    assert result.launch_allowed is False
    assert "expected_evaluator_identity_absent" in result.reason_codes


def test_launch_denied_when_evaluator_pin_method_config_mismatches_manifest(
    manifest: dict,
) -> None:
    pin_state = {
        "method_config_sha256": "sha256:" + ("2" * 64),
        "evaluator_digest": "sha256:" + ("3" * 64),
    }
    result = _gate(manifest, suite_evaluator_blocked=True, pin_state=pin_state)
    assert result.launch_allowed is False
    assert "evaluator_pin_method_config_mismatch" in result.reason_codes


def test_countability_tracks_launch_denial(manifest: dict) -> None:
    denied = _gate(manifest, suite_evaluator_blocked=True)
    assert denied.countable is False
    assert denied.launch_allowed is False


def test_canonical_tree_has_aq_r24_occurrence_only_in_binding_not_fixture_text() -> None:
    manifest_text = MANIFEST_PATH.read_text(encoding="utf-8")
    assert "aq_r24" in manifest_text
    fixture_text = AQ_R24_FIXTURE.read_text(encoding="utf-8")
    assert "AQ-R24" not in fixture_text
    compact = fixture_text.replace(" ", "")
    assert '"case_id": "AQ-24"' in fixture_text or '"case_id":"AQ-24"' in compact


def test_review_evidence_launch_remains_denied_before_g2_and_full_bindings(manifest: dict) -> None:
    """Machine-independent evidence that corrected bindings still deny launch."""
    result = _gate(manifest, suite_evaluator_blocked=True)
    assert result.launch_allowed is False
    assert result.countable is False
    required_denials = {
        "g2_evaluator_not_implemented",
    }
    assert required_denials.issubset(set(result.reason_codes))
    assert manifest["aq_r24"]["case_count"] == 24
    assert manifest["expected_evaluator_identity"]["method_config_sha256"] == METHOD_SHA256
    assert aqr.verify_manifest_self_hash(manifest)[0] is True
