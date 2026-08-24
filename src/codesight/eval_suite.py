"""Versioned local-evaluation suite and method/config manifests (spec 022).

This module is the dataset-only foundation for a later named frozen-suite
entrypoint. It validates project-owned suite, method/config, and hidden-holdout
hash-manifest documents, verifies public development-fixture hashes, and
records the identity tuple later comparisons must bind.

It does not run evaluators, compare candidates, promote, persist receipts,
open a network path, change retrieval models, capture queries, store secrets,
or read hidden-holdout payloads.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from .eval_pilot import EvaluationSubject

SCHEMA_SUITE = "holusight-eval-suite/v1"
SCHEMA_METHOD = "holusight-eval-method-config/v1"
SCHEMA_HOLDOUT_MANIFEST = "holusight-eval-holdout-hash-manifest/v1"
SCHEMA_COMPARISON_IDENTITY = "holusight-eval-comparison-identity/v1"

DEFAULT_SUITE_ID = "holusight-local-retrieval-v1"
SUITE_MANIFEST_RELATIVE = {
    DEFAULT_SUITE_ID: Path("tests/fixtures/eval_suites/holusight-local-retrieval-v1.suite.json"),
}

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,80}$")
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
_GIT_OID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_RELATIVE_PATH = re.compile(r"^(?!\.\./)(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9._][A-Za-z0-9._/\-]*$")

_DEV_FAMILIES = (
    "exact_lookup",
    "conceptual_localization",
    "symbol_reference",
    "doc_synthesis",
    "config_lookup",
    "test_coverage",
    "contradiction_no_answer",
)
_HOLDOUT_FAMILIES = (
    "exact_lookup",
    "nl_to_code",
    "docs_to_code",
    "api_data_relationships",
    "cross_file_concept",
    "ambiguous_terms",
    "misleading_lexical_overlap",
    "no_answer",
)
_SIGNALS = ("exact", "bm25", "semantic", "graphify_structural", "hybrid")
_METRICS = (
    "Recall@1",
    "Recall@5",
    "Recall@10",
    "MRR@10",
    "nDCG@10",
    "evidence_completeness",
)


class SuiteError(ValueError):
    """Closed failure for suite/method/holdout-manifest validation."""


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


_Count = Annotated[StrictInt, Field(ge=1)]


def sha256_digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _require_sha256(value: str) -> str:
    if not _SHA256.fullmatch(value):
        raise ValueError("expected sha256:<64 lowercase hex>")
    return value


def _require_id(value: str) -> str:
    if not _SAFE_ID.fullmatch(value):
        raise ValueError("identifier is not a bounded safe token")
    return value


def _require_relative_path(value: str) -> str:
    if not _RELATIVE_PATH.fullmatch(value) or value.startswith("/"):
        raise ValueError("path must be repository-relative without traversal")
    return value


def contained_path(repo_root: Path, relative: str) -> Path:
    """Resolve ``relative`` inside ``repo_root`` or fail closed."""
    declared = _require_relative_path(relative)
    root = repo_root.resolve()
    path = (root / declared).resolve()
    if not path.is_relative_to(root):
        raise SuiteError(f"path escapes repository root: {relative}")
    return path


# ---------------------------------------------------------------------------
# Method / config
# ---------------------------------------------------------------------------


class FusionConfig(_Closed):
    rrf_k: Literal[60]
    cnfb_alpha: float
    query_enhancement: StrictBool
    reranker: Literal["disabled_unless_independently_pinned"]

    @field_validator("cnfb_alpha")
    @classmethod
    def validate_cnfb_alpha(cls, value: float) -> float:
        if value != 0.0:
            raise ValueError("v1 method identity freezes CNFB alpha at the current default 0.0")
        return value


class MethodConfigManifest(_Closed):
    schema_version: Literal["holusight-eval-method-config/v1"]
    method_id: str
    status: Literal["identity_declaration_only"]
    evaluator_execution: Literal["blocked_until_g2_trusted_sandbox"]
    promotion: Literal["denied"]
    network: Literal["denied"]
    paid_apis: Literal["denied"]
    model_default_change: Literal["denied"]
    judge: Literal["deterministic_rank_and_exact_file_evidence_matching"]
    llm_judge: Literal["not_used"]
    signals: list[Literal["exact", "bm25", "semantic", "graphify_structural", "hybrid"]]
    fusion: FusionConfig
    metrics: list[
        Literal[
            "Recall@1",
            "Recall@5",
            "Recall@10",
            "MRR@10",
            "nDCG@10",
            "evidence_completeness",
        ]
    ]
    no_answer: Literal["diagnostic_only"]
    seed: Literal[20260824]
    parser_chunker_policy: Literal["existing_ast_plus_fallback_unchanged"]
    chunk_content_hash_guard: Literal["sha256(chunk_content)[:16]"]
    notes: str | None = None

    @field_validator("method_id")
    @classmethod
    def validate_method_id(cls, value: str) -> str:
        return _require_id(value)

    @field_validator("signals")
    @classmethod
    def validate_signals(cls, value: list[str]) -> list[str]:
        if tuple(value) != _SIGNALS:
            raise ValueError(
                "signals must be the frozen v1 exact/BM25/semantic/graphify/hybrid set"
            )
        return value

    @field_validator("metrics")
    @classmethod
    def validate_metrics(cls, value: list[str]) -> list[str]:
        if tuple(value) != _METRICS:
            raise ValueError("metrics must be the frozen v1 deterministic metric set")
        return value


# ---------------------------------------------------------------------------
# Hidden-holdout hash-manifest (no payload)
# ---------------------------------------------------------------------------


class HoldoutPayloadIdentity(_Closed):
    filename: str
    byte_length: _Count
    sha256: str

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        if not _SAFE_FILENAME.fullmatch(value) or "/" in value or "\\" in value:
            raise ValueError("payload filename is an artifact name, not a path")
        return value

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        return _require_sha256(value)


class HoldoutCorpusPin(_Closed):
    role: Literal["protected_public_cross_repository_generalization"]
    repository_url: Literal["https://github.com/makiftutuncu/bookstore.git"]
    commit: str
    tree: str
    license_spdx: Literal["MIT"]
    license_file: Literal["LICENSE.md"]
    license_blob_sha1: str
    included_paths: list[str]
    included_file_count: Literal[63]
    content_hashes: dict[str, str]

    @field_validator("commit", "tree", "license_blob_sha1")
    @classmethod
    def validate_oid(cls, value: str) -> str:
        if not _GIT_OID.fullmatch(value):
            raise ValueError("expected a full Git object id")
        return value

    @field_validator("included_paths")
    @classmethod
    def validate_included_paths(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("included_paths must be a non-empty explicit pin")
        for item in value:
            if item.startswith("/") or ".." in Path(item).parts:
                raise ValueError(f"included path is not a safe relative pin: {item}")
        return value

    @field_validator("content_hashes")
    @classmethod
    def validate_content_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        if "full_tree_sha1" not in value:
            raise ValueError("content_hashes must include full_tree_sha1")
        for digest in value.values():
            if not _GIT_OID.fullmatch(digest):
                raise ValueError("content hash must be a full Git object id")
        return value


class HoldoutHashManifest(_Closed):
    schema_version: Literal["holusight-eval-holdout-hash-manifest/v1"]
    holdout_id: str
    visibility: Literal["hidden_from_candidate"]
    evaluation_split: Literal["public_holdout"]
    payload_present_in_repository: Literal[False]
    payload_access: Literal["none_in_this_slice"]
    case_count: Literal[32]
    case_ids: list[str]
    family_counts: dict[str, StrictInt]
    payload: HoldoutPayloadIdentity
    corpus: HoldoutCorpusPin
    notes: str | None = None

    @field_validator("holdout_id")
    @classmethod
    def validate_holdout_id(cls, value: str) -> str:
        return _require_id(value)

    @field_validator("case_ids")
    @classmethod
    def validate_case_ids(cls, value: list[str]) -> list[str]:
        if len(value) != 32 or len(set(value)) != 32:
            raise ValueError("holdout case_ids must be 32 unique identifiers")
        for case_id in value:
            _require_id(case_id)
        return value

    @field_validator("family_counts")
    @classmethod
    def validate_family_counts(cls, value: dict[str, int]) -> dict[str, int]:
        if tuple(value.keys()) != _HOLDOUT_FAMILIES:
            raise ValueError("holdout family_counts must use the frozen Bookstore family set")
        if sum(value.values()) != 32:
            raise ValueError("holdout family_counts must sum to 32")
        if any(count != 4 for count in value.values()):
            raise ValueError("v1 Bookstore holdout has four cases per family")
        return value

    @model_validator(mode="after")
    def validate_payload_count(self) -> HoldoutHashManifest:
        if self.payload.byte_length < 1:
            raise ValueError("payload byte_length must be positive")
        return self


# ---------------------------------------------------------------------------
# Suite
# ---------------------------------------------------------------------------


class VisibleDevelopmentRef(_Closed):
    role: Literal["visible_development_evidence_not_generalization"]
    fixture_path: str
    sha256: str
    case_count: Literal[85]
    split: Literal["dev"]
    family_counts: dict[str, StrictInt]

    @field_validator("fixture_path")
    @classmethod
    def validate_fixture_path(cls, value: str) -> str:
        return _require_relative_path(value)

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        return _require_sha256(value)

    @field_validator("family_counts")
    @classmethod
    def validate_family_counts(cls, value: dict[str, int]) -> dict[str, int]:
        if tuple(value.keys()) != _DEV_FAMILIES:
            raise ValueError("development family_counts must match the 85-case taxonomy")
        if sum(value.values()) != 85:
            raise ValueError("development family_counts must sum to 85")
        return value


class HiddenHoldoutRef(_Closed):
    role: Literal["hidden_from_candidate"]
    holdout_id: str
    hash_manifest_path: str
    hash_manifest_sha256: str
    case_count: Literal[32]
    payload_present_in_repository: Literal[False]

    @field_validator("holdout_id")
    @classmethod
    def validate_holdout_id(cls, value: str) -> str:
        return _require_id(value)

    @field_validator("hash_manifest_path")
    @classmethod
    def validate_manifest_path(cls, value: str) -> str:
        return _require_relative_path(value)

    @field_validator("hash_manifest_sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        return _require_sha256(value)


class IdentityBindingExpectation(_Closed):
    git_subject: str
    corpus: str
    evaluator: str
    configuration: str
    suite_manifest: str
    comparison_rule: str


class SuiteManifest(_Closed):
    schema_version: Literal["holusight-eval-suite/v1"]
    suite_id: str
    status: Literal["dataset_foundation_only"]
    runner: Literal["not_implemented"]
    evaluator_execution: Literal["blocked_until_g2_trusted_sandbox"]
    promotion: Literal["denied"]
    method_config_path: str
    method_config_sha256: str
    visible_development: VisibleDevelopmentRef
    hidden_holdout: HiddenHoldoutRef
    identity_binding: IdentityBindingExpectation
    notes: str | None = None

    @field_validator("suite_id")
    @classmethod
    def validate_suite_id(cls, value: str) -> str:
        return _require_id(value)

    @field_validator("method_config_path")
    @classmethod
    def validate_method_path(cls, value: str) -> str:
        return _require_relative_path(value)

    @field_validator("method_config_sha256")
    @classmethod
    def validate_method_sha256(cls, value: str) -> str:
        return _require_sha256(value)


# ---------------------------------------------------------------------------
# Later comparison identity (schema only; not comparison-ready here)
# ---------------------------------------------------------------------------


class EvaluatorPin(_Closed):
    """Independent evaluator identity for a later G2-trusted comparison."""

    status: Literal["blocked_until_g2_trusted_sandbox", "pinned"]
    subject: EvaluationSubject | None = None
    digest: str | None = None

    @field_validator("digest")
    @classmethod
    def validate_digest(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _require_sha256(value)

    @model_validator(mode="after")
    def validate_pin_state(self) -> EvaluatorPin:
        if self.status == "pinned":
            if self.subject is None or self.digest is None:
                raise ValueError("a pinned evaluator requires subject and digest")
            if not self.subject.clean or self.subject.commit is None or self.subject.tree is None:
                raise ValueError("a pinned evaluator subject must be a clean commit/tree")
        elif self.subject is not None or self.digest is not None:
            raise ValueError("blocked evaluator pin cannot carry a subject or digest")
        return self


class ComparisonIdentityBinding(_Closed):
    """The five identities a later baseline/candidate comparison must bind.

    This slice only validates the shape. ``comparison_identity_is_ready`` is
    false until a trusted G2 evaluator sandbox supplies a real pin.
    """

    schema_version: Literal["holusight-eval-comparison-identity/v1"]
    git_subject: EvaluationSubject
    corpus_sha256: str
    evaluator: EvaluatorPin
    configuration_sha256: str
    suite_sha256: str
    holdout_manifest_sha256: str | None = None

    @field_validator("corpus_sha256", "configuration_sha256", "suite_sha256")
    @classmethod
    def validate_required_digests(cls, value: str) -> str:
        return _require_sha256(value)

    @field_validator("holdout_manifest_sha256")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _require_sha256(value)


def comparison_identity_is_ready(binding: ComparisonIdentityBinding) -> bool:
    """Return True only when every later-comparison identity is actually bound.

    Dataset foundation cannot satisfy this: evaluator execution remains blocked
    until the trusted G2 sandbox is approved and landed.
    """
    if binding.evaluator.status != "pinned":
        return False
    subject = binding.git_subject
    if not subject.clean or subject.commit is None or subject.tree is None:
        return False
    return True


# ---------------------------------------------------------------------------
# Load / verify
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LoadedSuite:
    """Validated suite plus referenced manifests and content hashes.

    No evaluator result, no holdout payload, and no comparison outcome.
    """

    suite_id: str
    suite: SuiteManifest
    method: MethodConfigManifest
    holdout_manifest: HoldoutHashManifest
    suite_sha256: str
    method_sha256: str
    holdout_manifest_sha256: str
    development_sha256: str
    development_path: Path
    suite_path: Path
    method_path: Path
    holdout_manifest_path: Path


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SuiteError(f"missing manifest: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SuiteError(f"invalid JSON: {path}") from exc


def _parse_model(model: type[BaseModel], payload: Any, label: str) -> BaseModel:
    try:
        return model.model_validate(payload)
    except Exception as exc:
        raise SuiteError(f"{label} failed validation: {exc}") from exc


def verify_file_digest(path: Path, expected: str) -> str:
    digest = sha256_digest(path.read_bytes())
    if digest != expected:
        raise SuiteError(f"digest mismatch for {path}: expected {expected}, got {digest}")
    return digest


def verify_holdout_payload_bytes(manifest: HoldoutHashManifest, payload: bytes) -> str:
    """Verify caller-supplied hidden-holdout bytes against the hash-manifest.

    The caller already holds the bytes. This module never locates, opens, or
    mounts a holdout payload path.
    """
    if len(payload) != manifest.payload.byte_length:
        raise SuiteError("hidden-holdout payload length does not match the hash-manifest")
    digest = sha256_digest(payload)
    if digest != manifest.payload.sha256:
        raise SuiteError("hidden-holdout payload digest does not match the hash-manifest")
    return digest


def verify_visible_development_fixture(path: Path, ref: VisibleDevelopmentRef) -> str:
    digest = verify_file_digest(path, ref.sha256)
    payload = _read_json(path)
    if not isinstance(payload, list):
        raise SuiteError("visible development fixture must be a JSON array")
    if len(payload) != ref.case_count:
        raise SuiteError(
            f"visible development fixture count {len(payload)} != declared {ref.case_count}"
        )
    ids: list[str] = []
    families: list[str] = []
    for index, case in enumerate(payload):
        if not isinstance(case, dict):
            raise SuiteError(f"development case {index} is not an object")
        case_id = case.get("id")
        if not isinstance(case_id, str):
            raise SuiteError(f"development case {index} is missing id")
        ids.append(case_id)
        split = case.get("split")
        if split != ref.split:
            raise SuiteError(f"development case {case_id} split {split!r} != {ref.split!r}")
        family = case.get("family")
        if not isinstance(family, str):
            raise SuiteError(f"development case {case_id} is missing family")
        families.append(family)
    if len(set(ids)) != len(ids):
        raise SuiteError("visible development fixture has duplicate case ids")
    observed = dict(Counter(families))
    if observed != dict(ref.family_counts):
        raise SuiteError("visible development family_counts do not match fixture bytes")
    return digest


def load_suite(repo_root: Path, suite_id: str = DEFAULT_SUITE_ID) -> LoadedSuite:
    """Load and hash-verify one named suite. Does not run evaluation."""
    relative = SUITE_MANIFEST_RELATIVE.get(suite_id)
    if relative is None:
        raise SuiteError(f"unknown suite_id {suite_id!r}")
    suite_path = contained_path(repo_root, str(relative))
    suite = _parse_model(SuiteManifest, _read_json(suite_path), "suite manifest")
    assert isinstance(suite, SuiteManifest)
    if suite.suite_id != suite_id:
        raise SuiteError(f"suite_id mismatch: registry {suite_id!r} vs document {suite.suite_id!r}")

    method_path = contained_path(repo_root, suite.method_config_path)
    method = _parse_model(MethodConfigManifest, _read_json(method_path), "method/config manifest")
    assert isinstance(method, MethodConfigManifest)
    method_sha256 = verify_file_digest(method_path, suite.method_config_sha256)

    holdout_path = contained_path(repo_root, suite.hidden_holdout.hash_manifest_path)
    holdout = _parse_model(HoldoutHashManifest, _read_json(holdout_path), "holdout hash-manifest")
    assert isinstance(holdout, HoldoutHashManifest)
    holdout_sha256 = verify_file_digest(holdout_path, suite.hidden_holdout.hash_manifest_sha256)
    if holdout.holdout_id != suite.hidden_holdout.holdout_id:
        raise SuiteError("holdout_id does not match the suite reference")
    if holdout.case_count != suite.hidden_holdout.case_count:
        raise SuiteError("holdout case_count does not match the suite reference")

    development_path = contained_path(repo_root, suite.visible_development.fixture_path)
    development_sha256 = verify_visible_development_fixture(
        development_path, suite.visible_development
    )

    return LoadedSuite(
        suite_id=suite.suite_id,
        suite=suite,
        method=method,
        holdout_manifest=holdout,
        suite_sha256=sha256_digest(suite_path.read_bytes()),
        method_sha256=method_sha256,
        holdout_manifest_sha256=holdout_sha256,
        development_sha256=development_sha256,
        development_path=development_path,
        suite_path=suite_path,
        method_path=method_path,
        holdout_manifest_path=holdout_path,
    )


def parse_comparison_identity(payload: dict[str, Any]) -> ComparisonIdentityBinding:
    parsed = _parse_model(ComparisonIdentityBinding, payload, "comparison identity")
    assert isinstance(parsed, ComparisonIdentityBinding)
    return parsed
