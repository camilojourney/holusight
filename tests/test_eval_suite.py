"""Tests for the versioned suite/method/holdout dataset foundation (spec 022).

These tests cover schema validation, public fixture references, and
hash-manifest handling. They do not run an evaluator, compare candidates,
or open a hidden-holdout payload path.
"""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from codesight import eval_suite
from codesight.eval_pilot import EvaluationSubject

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "src" / "codesight" / "eval_suite.py"


def _load() -> eval_suite.LoadedSuite:
    return eval_suite.load_suite(REPO_ROOT)


def _subject(*, clean: bool = True) -> EvaluationSubject:
    return EvaluationSubject(
        repository_id="https://github.com/camilojourney/holusight.git",
        commit="a" * 40,
        tree="b" * 40,
        clean=clean,
        branch="annotation-only",
    )


def test_named_suite_loads_and_binds_public_85_and_hidden_32_identities():
    loaded = _load()
    assert loaded.suite_id == "holusight-local-retrieval-v1"
    assert loaded.suite.status == "dataset_foundation_only"
    assert loaded.suite.runner == "not_implemented"
    assert loaded.suite.evaluator_execution == "blocked_until_g2_trusted_sandbox"
    assert loaded.suite.promotion == "denied"
    assert loaded.suite.visible_development.case_count == 85
    assert loaded.suite.hidden_holdout.case_count == 32
    assert loaded.holdout_manifest.payload_present_in_repository is False
    assert loaded.holdout_manifest.payload_access == "none_in_this_slice"
    assert loaded.development_sha256.endswith(
        "71a44eb463c9d0b2a02fecaa03815bf718b72b769bb3bc6b48797da34650981f"
    )
    assert loaded.method.fusion.rrf_k == 60
    assert loaded.method.fusion.cnfb_alpha == 0.0
    assert loaded.method.model_default_change == "denied"
    assert loaded.suite_sha256.startswith("sha256:")
    assert loaded.method_sha256 == loaded.suite.method_config_sha256
    assert loaded.holdout_manifest_sha256 == loaded.suite.hidden_holdout.hash_manifest_sha256


def test_visible_development_fixture_bytes_are_the_existing_taxonomy():
    loaded = _load()
    raw = json.loads(loaded.development_path.read_text(encoding="utf-8"))
    assert len(raw) == 85
    assert {case["split"] for case in raw} == {"dev"}
    assert loaded.development_path == REPO_ROOT / "tests/fixtures/holusight_eval_taxonomy.json"


def test_bookstore_holdout_is_referenced_by_hash_not_payload():
    loaded = _load()
    manifest = loaded.holdout_manifest
    assert manifest.holdout_id == "bookstore-public-v1"
    assert manifest.case_count == 32
    assert len(manifest.case_ids) == 32
    assert manifest.payload.sha256.endswith(
        "ae996ee16ba8e73eb4da901682f8c5c441110bbadd9a5997f262cc17f11f6370"
    )
    assert manifest.corpus.commit == "a1d44ad56918e43038d4fed061305b5686ec3c87"
    assert manifest.corpus.tree == "516007f03e4dd0ecb6b36d3a218bf2cb2ab83ce2"
    assert manifest.corpus.license_spdx == "MIT"
    dumped = json.dumps(manifest.model_dump(mode="json"))
    assert "ForeignKeyInsertViolation" not in dumped
    assert "shopping cart" not in dumped
    assert "expected_file" not in dumped
    assert "exact_string" not in dumped


def test_unknown_suite_id_fails_closed():
    with pytest.raises(eval_suite.SuiteError, match="unknown suite_id"):
        eval_suite.load_suite(REPO_ROOT, "not-a-real-suite")


def test_path_traversal_in_method_ref_fails_closed(tmp_path: Path):
    suite_dir = tmp_path / "tests" / "fixtures" / "eval_suites"
    suite_dir.mkdir(parents=True)
    suite_file = REPO_ROOT / "tests/fixtures/eval_suites/holusight-local-retrieval-v1.suite.json"
    payload = json.loads(suite_file.read_text())
    payload["method_config_path"] = "../secret.json"
    (suite_dir / "holusight-local-retrieval-v1.suite.json").write_text(json.dumps(payload))
    with pytest.raises(eval_suite.SuiteError):
        eval_suite.load_suite(tmp_path)


def test_tampered_method_bytes_fail_closed(tmp_path: Path):
    loaded = _load()
    dest = tmp_path / "repo"
    for relative in (
        loaded.suite_path.relative_to(REPO_ROOT),
        loaded.method_path.relative_to(REPO_ROOT),
        loaded.holdout_manifest_path.relative_to(REPO_ROOT),
        loaded.development_path.relative_to(REPO_ROOT),
    ):
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO_ROOT / relative).read_bytes())
    method = dest / loaded.method_path.relative_to(REPO_ROOT)
    method.write_bytes(method.read_bytes() + b"\n")
    with pytest.raises(eval_suite.SuiteError, match="digest mismatch"):
        eval_suite.load_suite(dest)


def test_tampered_taxonomy_bytes_fail_closed(tmp_path: Path):
    loaded = _load()
    dest = tmp_path / "repo"
    for relative in (
        loaded.suite_path.relative_to(REPO_ROOT),
        loaded.method_path.relative_to(REPO_ROOT),
        loaded.holdout_manifest_path.relative_to(REPO_ROOT),
        loaded.development_path.relative_to(REPO_ROOT),
    ):
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO_ROOT / relative).read_bytes())
    taxonomy = dest / loaded.development_path.relative_to(REPO_ROOT)
    cases = json.loads(taxonomy.read_text(encoding="utf-8"))
    cases[0]["query"] = "weakened case"
    taxonomy.write_text(json.dumps(cases))
    with pytest.raises(eval_suite.SuiteError, match="digest mismatch"):
        eval_suite.load_suite(dest)


def test_unknown_schema_version_fails_closed():
    with pytest.raises((eval_suite.SuiteError, ValidationError)):
        eval_suite.MethodConfigManifest.model_validate(
            {"schema_version": "holusight-eval-method-config/v0", "method_id": "x"}
        )


def test_extra_fields_fail_closed():
    loaded = _load()
    payload = loaded.method.model_dump(mode="json")
    payload["extra"] = "nope"
    with pytest.raises(Exception):
        eval_suite.MethodConfigManifest.model_validate(payload)


def test_verify_holdout_payload_bytes_matches_declared_digest():
    manifest = _load().holdout_manifest
    # Reconstruct only the digest/length contract with caller-supplied bytes.
    fake = eval_suite.HoldoutPayloadIdentity(
        filename="synthetic-holdout.json",
        byte_length=4,
        sha256=eval_suite.sha256_digest(b"abcd"),
    )
    synthetic = manifest.model_copy(update={"payload": fake})
    assert eval_suite.verify_holdout_payload_bytes(synthetic, b"abcd").startswith("sha256:")
    with pytest.raises(eval_suite.SuiteError):
        eval_suite.verify_holdout_payload_bytes(synthetic, b"abce")
    with pytest.raises(eval_suite.SuiteError, match="length"):
        eval_suite.verify_holdout_payload_bytes(synthetic, b"abc")


def test_module_has_no_holdout_access_path_or_runner():
    forbidden = {
        "load_holdout_payload",
        "open_holdout",
        "read_holdout",
        "run_suite",
        "run_eval",
        "compare_candidates",
        "promote",
        "write_receipt",
    }
    names = set(dir(eval_suite))
    assert forbidden.isdisjoint(names)
    source = ast.parse(SOURCE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(source):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
            imported.update(alias.name for alias in node.names)
    assert "eval_harness" not in imported
    assert "eval_baselines" not in imported
    assert "eval_holusight" not in imported
    assert "eval_variants" not in imported
    assert "socket" not in imported
    assert "urllib" not in imported
    assert "requests" not in imported
    # Dataset loading is public; evaluation is not.
    assert inspect.isfunction(eval_suite.load_suite)
    assert inspect.isfunction(eval_suite.verify_holdout_payload_bytes)


def test_comparison_identity_schema_requires_five_bindings_and_is_not_ready():
    loaded = _load()
    binding = eval_suite.parse_comparison_identity(
        {
            "schema_version": "holusight-eval-comparison-identity/v1",
            "git_subject": _subject().model_dump(mode="json"),
            "corpus_sha256": loaded.development_sha256,
            "evaluator": {"status": "blocked_until_g2_trusted_sandbox"},
            "configuration_sha256": loaded.method_sha256,
            "suite_sha256": loaded.suite_sha256,
            "holdout_manifest_sha256": loaded.holdout_manifest_sha256,
        }
    )
    assert binding.git_subject.branch == "annotation-only"
    assert eval_suite.comparison_identity_is_ready(binding) is False


def test_comparison_identity_rejects_blocked_pin_that_smuggles_a_subject():
    loaded = _load()
    with pytest.raises(eval_suite.SuiteError):
        eval_suite.parse_comparison_identity(
            {
                "schema_version": "holusight-eval-comparison-identity/v1",
                "git_subject": _subject().model_dump(mode="json"),
                "corpus_sha256": loaded.development_sha256,
                "evaluator": {
                    "status": "blocked_until_g2_trusted_sandbox",
                    "digest": loaded.method_sha256,
                },
                "configuration_sha256": loaded.method_sha256,
                "suite_sha256": loaded.suite_sha256,
            }
        )


def test_comparison_identity_pin_without_clean_subject_fails_closed():
    loaded = _load()
    with pytest.raises(eval_suite.SuiteError):
        eval_suite.parse_comparison_identity(
            {
                "schema_version": "holusight-eval-comparison-identity/v1",
                "git_subject": _subject(clean=False).model_dump(mode="json"),
                "corpus_sha256": loaded.development_sha256,
                "evaluator": {
                    "status": "pinned",
                    "subject": _subject(clean=False).model_dump(mode="json"),
                    "digest": loaded.method_sha256,
                },
                "configuration_sha256": loaded.method_sha256,
                "suite_sha256": loaded.suite_sha256,
            }
        )


def test_comparison_ready_only_with_clean_git_subject_and_g2_pin():
    loaded = _load()
    binding = eval_suite.parse_comparison_identity(
        {
            "schema_version": "holusight-eval-comparison-identity/v1",
            "git_subject": _subject().model_dump(mode="json"),
            "corpus_sha256": loaded.development_sha256,
            "evaluator": {
                "status": "pinned",
                "subject": _subject().model_dump(mode="json"),
                "digest": loaded.method_sha256,
            },
            "configuration_sha256": loaded.method_sha256,
            "suite_sha256": loaded.suite_sha256,
            "holdout_manifest_sha256": loaded.holdout_manifest_sha256,
        }
    )
    assert eval_suite.comparison_identity_is_ready(binding) is True
    dirty = binding.model_copy(update={"git_subject": _subject(clean=False)})
    assert eval_suite.comparison_identity_is_ready(dirty) is False
