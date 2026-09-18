"""Local advisory named-suite validation and execution (spec 022).

The module validates the project-owned suite, method/config, and hidden-holdout
hash-manifest documents, then runs only the named suite's visible development
fixture through the existing retrieval harness. It emits a bounded local
advisory result with a clean immutable Git subject and one of ``pass``,
``block``, or ``indeterminate``.

It never opens a hidden-holdout payload, compares candidates, promotes,
persists receipts, changes retrieval models, captures queries, stores secrets,
or permits network egress. A ``pass`` means the bounded local development run
completed, never that a candidate is accepted or promotable. G2 and AVO remain
owners of independent external acceptance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
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
    ValidationError,
    field_validator,
    model_validator,
)

from .eval_pilot import (
    EvaluationSubject,
    _current_subject,
    _git_blob_oid_for_bytes,
    _git_oid,
)

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
    status: Literal["local_advisory_execution"]
    evaluator_execution: Literal["local_visible_development_only"]
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
    status: Literal["local_advisory_execution"]
    runner: Literal["python -m codesight.eval_suite run"]
    evaluator_execution: Literal["local_visible_development_only"]
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

    The local named-suite runner does not create a comparison. This schema
    remains false until a trusted G2 evaluator sandbox supplies a real pin.
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

    A local visible-development run cannot satisfy this: independent evaluation
    remains blocked until the trusted G2 sandbox is approved and landed.
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

    Loading neither executes the visible-development runner nor accesses a
    holdout payload or creates a comparison outcome.
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


# ---------------------------------------------------------------------------
# Local named-suite runner - visible development fixture only
# ---------------------------------------------------------------------------

SCHEMA_RUN_RESULT = "holusight-eval-suite-run/v1"


class LocalMetrics(_Closed):
    """The bounded aggregate copied from the existing public harness output."""

    cases_total: _Count
    cases_graded: _Count
    cases_hit: StrictInt = Field(ge=0)
    diagnostic_probes: StrictInt = Field(ge=0)
    hit_rate: float = Field(ge=0.0, le=1.0)
    recall_at_1: float = Field(ge=0.0, le=1.0)
    recall_at_5: float = Field(ge=0.0, le=1.0)
    recall_at_10: float = Field(ge=0.0, le=1.0)
    mrr_at_10: float = Field(ge=0.0, le=1.0)
    ndcg_at_10: float = Field(ge=0.0, le=1.0)
    evidence_completeness: float = Field(ge=0.0, le=1.0)


class SuiteRunEvidence(_Closed):
    """Content-free, bounded evidence for an advisory suite result."""

    suite_sha256: str | None = None
    method_sha256: str | None = None
    development_sha256: str | None = None
    holdout_manifest_sha256: str | None = None
    evaluator_digest: str | None = None
    harness_exit_code: StrictInt | None = None
    harness_stdout_sha256: str | None = None
    harness_stderr_sha256: str | None = None
    metrics: LocalMetrics | None = None

    @field_validator(
        "suite_sha256",
        "method_sha256",
        "development_sha256",
        "holdout_manifest_sha256",
        "evaluator_digest",
        "harness_stdout_sha256",
        "harness_stderr_sha256",
    )
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _require_sha256(value)


class SuiteRunResult(_Closed):
    """A local advisory result. It is explicitly not a promotion decision."""

    schema_version: Literal["holusight-eval-suite-run/v1"] = SCHEMA_RUN_RESULT
    suite_id: str
    outcome: Literal["pass", "block", "indeterminate"]
    reason: str
    subject: EvaluationSubject
    promotion: Literal["denied"] = "denied"
    hidden_holdout_access: Literal["none"] = "none"
    network: Literal["denied"] = "denied"
    evidence: SuiteRunEvidence

    @field_validator("suite_id")
    @classmethod
    def validate_suite_id(cls, value: str) -> str:
        return _require_id(value)


def _evaluator_digest(repo_root: Path) -> str:
    """Content-address the existing evaluator implementation without exporting it."""
    digest = hashlib.sha256()
    for relative in (
        Path("tests/eval_holusight.py"),
        Path("tests/eval_harness.py"),
        Path("tests/eval_baselines.py"),
    ):
        path = contained_path(repo_root, str(relative))
        digest.update(str(relative).encode("utf-8"))
        digest.update(path.read_bytes())
    return "sha256:" + digest.hexdigest()


def _subject_binds_paths(
    repo_root: Path, subject: EvaluationSubject, paths: tuple[Path, ...]
) -> bool:
    """Require each consequential byte to equal the evaluated Git blob."""
    if not subject.clean or subject.commit is None:
        return False
    root = repo_root.resolve()
    for path in paths:
        try:
            relative = path.resolve().relative_to(root).as_posix()
            working_blob = _git_blob_oid_for_bytes(repo_root, path.read_bytes())
        except (OSError, ValueError):
            return False
        evaluated_blob = _git_oid(repo_root, f"{subject.commit}:{relative}")
        if not working_blob or working_blob != evaluated_blob:
            return False
    return True


def _base_evidence(loaded: LoadedSuite | None, repo_root: Path) -> SuiteRunEvidence:
    if loaded is None:
        return SuiteRunEvidence()
    return SuiteRunEvidence(
        suite_sha256=loaded.suite_sha256,
        method_sha256=loaded.method_sha256,
        development_sha256=loaded.development_sha256,
        holdout_manifest_sha256=loaded.holdout_manifest_sha256,
        evaluator_digest=_evaluator_digest(repo_root),
    )


def _local_harness_environment(data_dir: Path) -> dict[str, str]:
    """A child environment with no API credentials and disposable index state."""
    blocked = (
        "VOYAGE_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
    )
    env = {key: value for key, value in os.environ.items() if key not in blocked}
    env.update(
        {
            "CODESIGHT_DATA_DIR": str(data_dir),
            "CODESIGHT_EMBEDDING_BACKEND": "local",
            "CODESIGHT_EMBEDDING_MODEL": "sentence-transformers/all-MiniLM-L6-v2",
            "CODESIGHT_RERANKER": "false",
            "CODESIGHT_QUERY_ENHANCEMENT": "false",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        }
    )
    return env


def _execute_visible_development_harness(
    repo_root: Path, loaded: LoadedSuite, top_k: int
) -> tuple[int | None, bytes, bytes, dict[str, Any] | None]:
    """Run the existing harness on public fixture bytes in disposable state.

    No query-level output leaves the temporary child result. The caller retains
    only a digest and a fixed aggregate projection.
    """
    with tempfile.TemporaryDirectory(prefix="holusight-eval-suite-") as tmp:
        temp_root = Path(tmp)
        output = temp_root / "harness.json"
        command = [
            sys.executable,
            str(repo_root / "tests" / "eval_holusight.py"),
            "--repo-path",
            str(repo_root),
            "--queries",
            str(loaded.development_path),
            "--baselines",
            "hybrid",
            "--top-k",
            str(top_k),
            "--output",
            str(output),
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=str(repo_root),
                env=_local_harness_environment(temp_root / "data"),
                capture_output=True,
                timeout=600,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return None, exc.stdout or b"", exc.stderr or b"", None
        try:
            payload = json.loads(output.read_text(encoding="utf-8")) if output.exists() else None
        except (OSError, json.JSONDecodeError):
            payload = None
        return completed.returncode, completed.stdout, completed.stderr, payload


def _metrics_from_harness_payload(payload: dict[str, Any], expected_cases: int) -> LocalMetrics:
    """Project only fixed aggregate fields from the established harness report."""
    results = payload.get("results")
    if not isinstance(results, dict):
        raise ValueError("harness result lacks baseline reports")
    hybrid = results.get("hybrid")
    if not isinstance(hybrid, dict):
        raise ValueError("harness result lacks the hybrid baseline")
    recall = hybrid.get("recall_at_k")
    if not isinstance(recall, dict):
        raise ValueError("harness result lacks recall metrics")
    metrics = LocalMetrics(
        cases_total=hybrid.get("num_queries"),
        cases_graded=hybrid.get("num_graded"),
        cases_hit=hybrid.get("num_hits"),
        diagnostic_probes=hybrid.get("num_diagnostic_probes"),
        hit_rate=hybrid.get("hit_rate"),
        recall_at_1=recall.get("1"),
        recall_at_5=recall.get("5"),
        recall_at_10=recall.get("10"),
        mrr_at_10=hybrid.get("mrr_at_10"),
        ndcg_at_10=hybrid.get("ndcg_at_10"),
        evidence_completeness=hybrid.get("evidence_completeness"),
    )
    if metrics.cases_total != expected_cases:
        raise ValueError("harness case count does not match the suite manifest")
    if metrics.cases_hit > metrics.cases_graded:
        raise ValueError("harness hit count exceeds graded case count")
    return metrics


def _run_named_suite(repo_root: Path, suite_id: str, top_k: int) -> SuiteRunResult:
    """Run one named local suite, returning advisory evidence only."""
    subject = _current_subject(repo_root)
    try:
        loaded = load_suite(repo_root, suite_id)
        evidence = _base_evidence(loaded, repo_root)
    except (SuiteError, OSError, ValueError):
        return SuiteRunResult(
            suite_id=suite_id,
            outcome="block",
            reason="suite manifests failed local verification",
            subject=subject,
            evidence=SuiteRunEvidence(),
        )

    consequential_paths = (
        loaded.suite_path,
        loaded.method_path,
        loaded.holdout_manifest_path,
        loaded.development_path,
        repo_root / "tests" / "eval_holusight.py",
        repo_root / "tests" / "eval_harness.py",
        repo_root / "tests" / "eval_baselines.py",
    )
    if not _subject_binds_paths(repo_root, subject, consequential_paths):
        return SuiteRunResult(
            suite_id=suite_id,
            outcome="indeterminate",
            reason="current worktree is not a clean immutable subject for the suite evidence",
            subject=subject,
            evidence=evidence,
        )

    returncode, stdout, stderr, payload = _execute_visible_development_harness(
        repo_root, loaded, top_k
    )
    evidence = evidence.model_copy(
        update={
            "harness_exit_code": returncode,
            "harness_stdout_sha256": sha256_digest(stdout),
            "harness_stderr_sha256": sha256_digest(stderr),
        }
    )
    final_subject = _current_subject(repo_root)
    final_subject_is_bound = _subject_binds_paths(
        repo_root, final_subject, consequential_paths
    )
    if final_subject != subject or not final_subject_is_bound:
        return SuiteRunResult(
            suite_id=suite_id,
            outcome="indeterminate",
            reason="Git subject changed while the local suite was running",
            subject=final_subject,
            evidence=evidence,
        )
    if returncode != 0:
        return SuiteRunResult(
            suite_id=suite_id,
            outcome="block",
            reason="local visible-development harness did not complete successfully",
            subject=subject,
            evidence=evidence,
        )
    if not isinstance(payload, dict):
        return SuiteRunResult(
            suite_id=suite_id,
            outcome="indeterminate",
            reason="local harness output could not be verified as a bounded report",
            subject=subject,
            evidence=evidence,
        )
    try:
        metrics = _metrics_from_harness_payload(
            payload, loaded.suite.visible_development.case_count
        )
    except (TypeError, ValueError, ValidationError):
        return SuiteRunResult(
            suite_id=suite_id,
            outcome="indeterminate",
            reason="local harness report does not match the named suite contract",
            subject=subject,
            evidence=evidence,
        )
    return SuiteRunResult(
        suite_id=suite_id,
        outcome="pass",
        reason=(
            "local visible-development run completed; advisory only, not acceptance or promotion"
        ),
        subject=subject,
        evidence=evidence.model_copy(update={"metrics": metrics}),
    )


def main(argv: list[str] | None = None) -> int:
    """CLI boundary for the named local advisory runner."""
    parser = argparse.ArgumentParser(prog="python -m codesight.eval_suite")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run a named local advisory development suite")
    run.add_argument("--suite", default=DEFAULT_SUITE_ID)
    run.add_argument("--repo-root", type=Path, default=Path.cwd())
    run.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args(argv)
    if args.command != "run" or args.top_k < 1:
        parser.error("run requires --top-k >= 1")
    result = _run_named_suite(args.repo_root.resolve(), args.suite, args.top_k)
    print(json.dumps(result.model_dump(mode="json"), sort_keys=True))
    return {"pass": 0, "block": 1, "indeterminate": 2}[result.outcome]


def parse_comparison_identity(payload: dict[str, Any]) -> ComparisonIdentityBinding:
    parsed = _parse_model(ComparisonIdentityBinding, payload, "comparison identity")
    assert isinstance(parsed, ComparisonIdentityBinding)
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
