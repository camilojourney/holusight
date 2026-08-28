"""AVO AQ-R24 and immutable manifest/evaluator identity launch gates (spec 023 remediation slice).

Lanes must not launch or count valid trials unless visible content-bound AQ-R24,
immutable manifest commit/tree binding, and expected evaluator identity hashes are
present and valid. Does not modify G2 code, ledger/checkpoint schemas, resource
controls, leakage policy, or purpose schemas.
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
AQ_R24_BINDING_SCHEMA = "holusight-avo-aq-r24-binding/v1"
AQ_R24_CASE_SCHEMA = "holus-answer-quality-case/v1"
G2_BLOCKED_STATUS = "blocked_until_g2_trusted_sandbox"
G2_PINNED_STATUS = "pinned"
MANIFEST_RELATIVE = Path("docs/avo/trial-manifest.v1.json")

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_OID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_RELATIVE_PATH_RE = re.compile(
    r"^(?!\.\./)(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9._][A-Za-z0-9._/\-]*$"
)
_CASE_ID_RE = re.compile(r"^AQ-[0-9]{2}$")
_EXPECTED_MODES = frozenset({"ANSWER", "CONTRADICTION", "UNKNOWN", "ABSTAIN"})


@dataclass(frozen=True, slots=True)
class Aqr24IdentityGateResult:
    launch_allowed: bool
    countable: bool
    reason_codes: tuple[str, ...]


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_canonical_json(value: Mapping[str, Any]) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return sha256_bytes(body)


def compute_manifest_self_hash(manifest: Mapping[str, Any]) -> str:
    body = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    return sha256_canonical_json(body)


def verify_manifest_self_hash(manifest: Mapping[str, Any]) -> tuple[bool, tuple[str, ...]]:
    declared = manifest.get("manifest_sha256")
    if not isinstance(declared, str) or not _SHA256_RE.fullmatch(declared):
        return False, ("manifest_sha256_absent_or_invalid",)
    computed = compute_manifest_self_hash(manifest)
    if declared != computed:
        return False, ("manifest_self_hash_mismatch",)
    return True, ()


def verify_manifest_git_binding(
    manifest: Mapping[str, Any],
    *,
    actual_commit: str,
    actual_tree: str,
) -> tuple[bool, tuple[str, ...]]:
    git_base = manifest.get("git_base")
    if not isinstance(git_base, Mapping):
        return False, ("manifest_git_base_absent",)

    errors: list[str] = []
    expected_commit = git_base.get("commit")
    expected_tree = git_base.get("tree")

    if not isinstance(expected_commit, str) or not _GIT_OID_RE.fullmatch(expected_commit):
        errors.append("manifest_git_commit_unpinned")
    elif expected_commit != actual_commit:
        errors.append("manifest_git_commit_mismatch")

    if not isinstance(expected_tree, str) or not _GIT_OID_RE.fullmatch(expected_tree):
        errors.append("manifest_git_tree_unpinned")
    elif expected_tree != actual_tree:
        errors.append("manifest_git_tree_mismatch")

    return not errors, tuple(dict.fromkeys(errors))


def verify_aq_r24_binding(
    repo_root: Path,
    manifest: Mapping[str, Any],
) -> tuple[bool, tuple[str, ...], list[dict[str, Any]] | None]:
    binding = manifest.get("aq_r24")
    if not isinstance(binding, Mapping):
        return False, ("aq_r24_binding_absent",), None

    errors: list[str] = []
    if binding.get("schema_version") != AQ_R24_BINDING_SCHEMA:
        errors.append("aq_r24_schema_invalid")

    fixture_path = binding.get("fixture_path")
    expected_sha = binding.get("fixture_sha256")
    expected_count = binding.get("case_count")

    if not isinstance(fixture_path, str) or not _RELATIVE_PATH_RE.fullmatch(fixture_path):
        errors.append("aq_r24_fixture_path_invalid")
        return False, tuple(dict.fromkeys(errors)), None

    if not isinstance(expected_sha, str) or not _SHA256_RE.fullmatch(expected_sha):
        errors.append("aq_r24_fixture_sha256_invalid")

    resolved = repo_root / fixture_path
    if not resolved.is_file():
        errors.append("aq_r24_fixture_absent")
        return False, tuple(dict.fromkeys(errors)), None

    actual_sha = sha256_bytes(resolved.read_bytes())
    if expected_sha != actual_sha:
        errors.append("aq_r24_fixture_hash_mismatch")

    cases: list[dict[str, Any]] = []
    for line_no, line in enumerate(resolved.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"aq_r24_fixture_line_invalid:{line_no}")
            continue
        if not isinstance(case, dict):
            errors.append(f"aq_r24_case_not_object:{line_no}")
            continue
        if case.get("schema_version") != AQ_R24_CASE_SCHEMA:
            errors.append(f"aq_r24_case_schema_invalid:{line_no}")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not _CASE_ID_RE.fullmatch(case_id):
            errors.append(f"aq_r24_case_id_invalid:{line_no}")
        mode = case.get("expected_mode")
        if mode not in _EXPECTED_MODES:
            errors.append(f"aq_r24_case_mode_invalid:{line_no}")
        cases.append(case)

    if isinstance(expected_count, int) and len(cases) != expected_count:
        errors.append("aq_r24_case_count_mismatch")

    protected = binding.get("protected_case_ids")
    if isinstance(protected, list):
        case_ids = {c.get("case_id") for c in cases}
        for pid in protected:
            if pid not in case_ids:
                errors.append(f"aq_r24_protected_case_missing:{pid}")

    ok = not errors
    return ok, tuple(dict.fromkeys(errors)), cases if ok else None


def verify_expected_evaluator_identity(
    manifest: Mapping[str, Any],
    *,
    suite_evaluator_blocked: bool,
    pin_state: Mapping[str, Any] | None = None,
) -> tuple[bool, tuple[str, ...]]:
    expected = manifest.get("expected_evaluator_identity")
    if not isinstance(expected, Mapping):
        return False, ("expected_evaluator_identity_absent",)

    errors: list[str] = []
    status = expected.get("status")
    method_sha = expected.get("method_config_sha256")

    if status not in {G2_BLOCKED_STATUS, G2_PINNED_STATUS}:
        errors.append("expected_evaluator_status_invalid")

    if not isinstance(method_sha, str) or not _SHA256_RE.fullmatch(method_sha):
        errors.append("expected_evaluator_method_sha256_invalid")

    digest = expected.get("digest")
    identity_digest = expected.get("identity_digest")

    if status == G2_BLOCKED_STATUS:
        if digest is not None or identity_digest is not None:
            errors.append("expected_evaluator_blocked_carries_digest")
        if suite_evaluator_blocked:
            errors.append("g2_evaluator_not_implemented")
    elif status == G2_PINNED_STATUS:
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            errors.append("expected_evaluator_digest_absent")
        if not isinstance(identity_digest, str) or not _SHA256_RE.fullmatch(identity_digest):
            errors.append("expected_evaluator_identity_digest_absent")

    if pin_state is not None:
        pin_method = pin_state.get("method_config_sha256")
        if isinstance(method_sha, str) and pin_method != method_sha:
            errors.append("evaluator_pin_method_config_mismatch")
        pin_digest = pin_state.get("evaluator_digest")
        if status == G2_PINNED_STATUS and isinstance(digest, str) and pin_digest != digest:
            errors.append("evaluator_pin_digest_mismatch")

    return not errors, tuple(dict.fromkeys(errors))


def load_manifest(repo_root: Path) -> dict[str, Any]:
    path = repo_root / MANIFEST_RELATIVE
    if not path.is_file():
        raise FileNotFoundError(f"missing AVO manifest: {MANIFEST_RELATIVE}")
    return json.loads(path.read_text(encoding="utf-8"))


def is_public_g2_evaluator_blocked(repo_root: Path) -> bool:
    loaded = eval_suite.load_suite(repo_root)
    return loaded.suite.evaluator_execution == G2_BLOCKED_STATUS


def assess_aqr24_identity_gate(
    *,
    repo_root: Path,
    manifest: Mapping[str, Any],
    actual_commit: str,
    actual_tree: str,
    suite_evaluator_blocked: bool | None = None,
    pin_state: Mapping[str, Any] | None = None,
) -> Aqr24IdentityGateResult:
    """Deny launch and counting until AQ-R24 and identity bindings validate."""
    reason_codes: list[str] = []

    if manifest.get("campaign_id") != CAMPAIGN_ID:
        reason_codes.append("manifest_campaign_mismatch")

    self_ok, self_errors = verify_manifest_self_hash(manifest)
    if not self_ok:
        reason_codes.extend(self_errors)

    git_ok, git_errors = verify_manifest_git_binding(
        manifest,
        actual_commit=actual_commit,
        actual_tree=actual_tree,
    )
    if not git_ok:
        reason_codes.extend(git_errors)

    aq_ok, aq_errors, _cases = verify_aq_r24_binding(repo_root, manifest)
    if not aq_ok:
        reason_codes.extend(aq_errors)

    if suite_evaluator_blocked is None:
        suite_evaluator_blocked = is_public_g2_evaluator_blocked(repo_root)

    eval_ok, eval_errors = verify_expected_evaluator_identity(
        manifest,
        suite_evaluator_blocked=suite_evaluator_blocked,
        pin_state=pin_state,
    )
    if not eval_ok:
        reason_codes.extend(eval_errors)

    launch_allowed = not reason_codes
    return Aqr24IdentityGateResult(
        launch_allowed=launch_allowed,
        countable=launch_allowed,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
    )
