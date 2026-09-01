"""Holusight safe continuous-evaluation pilot (spec 017).

The smallest useful local, no-spend continuous-evaluation loop over
already-landed Holusight-AXI work (`consistency.py`, spec 013;
`cli_axi.py`/`axi_providers.py`, spec 015; `fleet_scorecard.py`, spec 016).
This module adds no new retrieval mechanism, no new provider, and no
production-default change. It is a thin evaluator over already-shipped
behavior:

1. A frozen, human-admitted case corpus
   (``tests/fixtures/holusight_eval_pilot_cases.jsonl``) - each case
   carries explicit provenance back to a reproduced real usage gap (a
   fixed bug, see ``cli-axi-provider-starvation-display-quota`` below) or
   a spec-documented deterministic contract. See
   ``docs/playbooks/eval-pilot-case-admission.md`` for how a case is
   admitted.
2. A bounded, deterministic runner (:func:`run_pilot`) that grades every
   case against the current repository state and records who/what
   produced the run (:class:`CandidateLineage`) - never raw prompts, file
   content, or absolute host paths.
3. For cases where a meaningful prior implementation exists
   (``kind: "comparative"``), the runner also grades a frozen **status-quo
   control** - a pinned, pre-fix reference implementation kept here *only*
   as a comparator, never wired into production - so a candidate's win is
   demonstrated, not assumed. See :func:`_naive_concatenate_then_slice`.
4. Two Fleet v1.2-shaped, content-free exports:
   :func:`build_pilot_aggregate_scorecard` (counts/rates only, no raw
   evidence) and :func:`pilot_domain_result_summary` (the minimal dict
   shape ``run_repo_eval.py``'s ``parse_domain_result()`` expects - see
   ``fleet_scorecard.py`` for the landed precedent this mirrors). Neither
   is wired as ``agentic/manifest.yaml``'s declared ``eval_entrypoint``
   (still ``just fleet-smoke``, unchanged) - this pilot is additive, not a
   replacement.

Non-goals (see specs/017-holusight-safe-continuous-evaluation-pilot.md and
the delegated policy it implements): no deployment, no private/production
content, no telemetry, no paid APIs, no external providers, no online
self-modification, no autonomous promotion. Results are advisory only -
nothing in this repository reads a verdict from this module and takes an
automatic action.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import ipaddress
import json
import os
import platform
import re
import resource
import shutil
import signal
import stat
import struct
import subprocess
import sys
import sysconfig
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Callable, Literal
from urllib.parse import unquote, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from .control_storage import (
    RESULTS_ROOT,
    UnsafeStoragePath,
    safe_atomic_create_or_read_identical,
    safe_atomic_write,
    validate_output_path,
)

FLEET_CONTRACT_REPO = "github.com/camilojourney/fleet-system"
FLEET_CONTRACT_COMMIT = "7d396b30f0250a414f9115964c945e29b7afb267"
FLEET_CONTRACT_PR = "https://github.com/camilojourney/fleet-system/pull/58"

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES_PATH = REPO_ROOT / "tests" / "fixtures" / "holusight_eval_pilot_cases.jsonl"

SCHEMA_CASE = "holus-eval-pilot-case/v1"
SCHEMA_RESULT = "holus-eval-pilot-result/v1"
SCHEMA_PILOT_SCORECARD = "fleet.eval_scorecard.v1.2"
SCHEMA_INTAKE_PROPOSAL = "holus-improve-intake/v1"
SCHEMA_EVALUATOR_PIN = "holus-evaluator-subject-pin/v1"
SCHEMA_TRUSTED_RECEIPT = "holus-trusted-evaluation-receipt/v1"
SCHEMA_PREPARED_EVALUATION = "holus-prepared-trusted-evaluation/v1"
SCHEMA_TRUSTED_FINALIZATION = "holus-trusted-evaluation-finalization/v2"
EVALUATOR_PATHS = (
    "src/codesight/control_storage.py",
    "src/codesight/eval_pilot.py",
    "src/codesight/trusted_eval_launcher.py",
)
CANONICAL_EVALUATOR_CASES_PATH = "tests/fixtures/holusight_eval_pilot_cases.jsonl"
G2_PROTOCOL_PIN_PATH = "specs/023-g2-external-acceptance.protocol.json"

_KNOWN_KINDS = frozenset({"regression", "comparative"})
_REQUIRED_PROVENANCE_FIELDS = frozenset({"origin", "description", "admitted_by", "admitted_at"})
_KNOWN_ORIGINS = frozenset(
    {"reproduced_usage_gap", "spec_documented_finding", "spec_documented_contract"}
)
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9._/-]{1,80}$")
_SECRET_LIKE = re.compile(
    r"(?i)(?:sk-[a-z0-9_-]{8,}|github_pat_[a-z0-9_]{8,}|gh[pousr]_[a-z0-9]{8,}|"
    r"gl(?:pat|ptt|rt|cbt|ft|imt|agent|soat|oas|dt|rtr|wt|ffct)-[a-z0-9_-]{8,}|"
    r"api[_ -]?key|"
    r"authorization:\s*bearer|private|raw\s+prompt|password|token)[^\s]{0,160}"
)
_CONTROLLED_COMPARATORS = frozenset({"grade_display_quota_case"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_hex(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical_result_digest(result: "PilotRunResult | dict[str, object]") -> str:
    """Hash the complete serialized result except its self-referential digest.

    This is the canonical representation for results at rest and is checked
    whenever a prior result is loaded.  A digest in mutable result bytes is an
    integrity check, not an independent promotion anchor.
    """
    payload = result.model_dump(mode="json") if isinstance(result, PilotRunResult) else dict(result)
    payload.pop("result_digest", None)
    return _sha256_hex(json.dumps(payload, sort_keys=True).encode("utf-8"))


def _public_cases_path(repo_root: Path, cases_path: Path) -> str:
    try:
        return str(cases_path.resolve().relative_to(repo_root.resolve()))
    except (ValueError, OSError):
        return "external-corpus"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class _ClosedResultModel(BaseModel):
    """Fail closed for every persisted result object, including nested fields."""

    model_config = ConfigDict(extra="forbid")


class CandidateLineage(_ClosedResultModel):
    """Who/what produced this run. Deliberately excludes any raw-prompt or
    free-text-content field - only identity/workflow metadata."""

    candidate_id: str
    repo_commit: str | None
    workflow: str
    tool: str
    model: str | None = None
    recorded_at: str = Field(default_factory=_now)
    repo_dirty: bool = False
    evaluator_digest: str | None = None
    candidate_digest: str | None = None
    comparator_digest: str | None = None


_GitOid = Annotated[str, Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")]
_Sha256 = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]


class EvaluationSubject(_ClosedResultModel):
    """The immutable Git subject this result was produced against (spec 021,
    closing the G1 gap identified against specs 017-020).

    A repository-relative link path is a locator, never identity - review-time
    applicability is recomputed against this subject's ``commit``/``tree``,
    never against ``branch``, which is annotation only per spec 021."""

    repository_id: str
    commit: _GitOid | None
    tree: _GitOid | None
    clean: bool
    branch: str | None = None

    @field_validator("repository_id")
    @classmethod
    def validate_repository_id(cls, value: str) -> str:
        if value == "local-no-remote" or _canonical_remote_identity(value) == value:
            return value
        raise ValueError("repository_id must be canonical and credential-free")

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, value: str | None) -> str | None:
        if value is None or (_SAFE_IDENTIFIER.fullmatch(value) and not _SECRET_LIKE.search(value)):
            return value
        raise ValueError("branch must be a bounded non-secret annotation")


class EvaluatorSubjectPin(_ClosedResultModel):
    """Human-reviewed evaluator identity rooted in a G1 Git subject.

    The result's self-declared evaluator digest is deliberately absent from
    this contract. Each evaluator, protocol, and corpus blob is independently
    resolved from ``subject.commit`` and rechecked against the candidate subject.
    """

    schema_version: str = SCHEMA_EVALUATOR_PIN
    protocol_revision: str
    subject: EvaluationSubject
    evaluator_blobs: dict[str, _GitOid]
    protocol_path: str = G2_PROTOCOL_PIN_PATH
    protocol_blob: _GitOid
    corpus_path: str = CANONICAL_EVALUATOR_CASES_PATH
    corpus_blob: _GitOid

    @field_validator("protocol_revision")
    @classmethod
    def validate_protocol_revision(cls, value: str) -> str:
        _validate_identifier("protocol_revision", value)
        return value

    @model_validator(mode="after")
    def validate_pin_shape(self) -> "EvaluatorSubjectPin":
        if self.schema_version != SCHEMA_EVALUATOR_PIN:
            raise ValueError("unsupported evaluator pin schema")
        if not self.subject.clean or not self.subject.commit or not self.subject.tree:
            raise ValueError("evaluator pin requires a clean immutable Git subject")
        if set(self.evaluator_blobs) != set(EVALUATOR_PATHS):
            raise ValueError("evaluator pin must cover the exact closed evaluator path set")
        if self.protocol_path != G2_PROTOCOL_PIN_PATH:
            raise ValueError("evaluator pin must use the canonical G2 protocol pin")
        if self.corpus_path != CANONICAL_EVALUATOR_CASES_PATH:
            raise ValueError("evaluator pin must use the canonical frozen case corpus")
        return self


class CaseGrade(_ClosedResultModel):
    case_id: str
    family: str
    kind: Literal["regression", "comparative"]
    verdict: Literal["pass", "fail", "error"]
    status_quo_verdict: Literal["pass", "fail"] | None = None
    detail: str
    provenance_origin: str


_Count = Annotated[StrictInt, Field(ge=0)]


class ResultCounts(_ClosedResultModel):
    """The exact, non-negative count partition persisted in every result."""

    total: _Count
    passed: _Count
    failed: _Count
    errored: _Count
    comparative_total: _Count
    comparative_with_status_quo_verdict: _Count

    def __getitem__(self, key: str) -> int:
        return getattr(self, key)


class PilotRunResult(_ClosedResultModel):
    schema_version: str = SCHEMA_RESULT
    run_id: str
    cases_file: str
    cases_file_hash: str
    lineage: CandidateLineage
    subject: EvaluationSubject
    egress_allowed: bool
    semantic_allowed: bool
    grades: list[CaseGrade]
    counts: ResultCounts
    status_quo_control: Literal["included", "not_applicable", "invalid"]
    corpus_trust: Literal["canonical", "untrusted_advisory"] = "canonical"
    result_digest: str | None = None


class EvaluationConfiguration(_ClosedResultModel):
    egress_allowed: bool = False
    semantic_allowed: bool = False


class ExternalAcceptanceBinding(_ClosedResultModel):
    """Authenticated external acceptance identity persisted with a receipt."""

    record_sha256: _Sha256
    replay_version: Literal[1] = 1
    replay_epoch: Annotated[StrictInt, Field(ge=1)]
    replay_sequence: Annotated[StrictInt, Field(ge=1)]
    configuration_sha256: _Sha256
    decision: Literal["accepted"] = "accepted"


class BaselineAnchor(_ClosedResultModel):
    result_path: str
    result_bytes_hash: _Sha256
    result_payload_hash: _Sha256
    result_digest: _Sha256
    manifest_path: str
    manifest_commit: _GitOid
    manifest_blob: _GitOid
    repository_id: str

    @model_validator(mode="after")
    def validate_paths(self) -> "BaselineAnchor":
        result_path = Path(self.result_path)
        manifest_path = Path(self.manifest_path)
        if (
            result_path.is_absolute()
            or ".." in result_path.parts
            or not result_path.is_relative_to(RESULTS_ROOT)
        ):
            raise ValueError("baseline result path must stay in derived results storage")
        if (
            manifest_path.is_absolute()
            or ".." in manifest_path.parts
            or manifest_path.parent != Path("specs")
            or not manifest_path.name.endswith(".change.json")
        ):
            raise ValueError("baseline manifest path must be a specs/*.change.json artifact")
        if self.repository_id != "local-no-remote" and (
            _canonical_remote_identity(self.repository_id) != self.repository_id
        ):
            raise ValueError("baseline anchor repository_id must be canonical")
        return self


class TrustedEvaluationReceipt(_ClosedResultModel):
    schema_version: str = SCHEMA_TRUSTED_RECEIPT
    receipt_id: str
    evaluator_pin: EvaluatorSubjectPin
    evaluator_pin_source: Literal["explicit", "derived"]
    baseline_result: PilotRunResult | None
    baseline_anchor: BaselineAnchor | None
    configuration: EvaluationConfiguration
    acceptance: ExternalAcceptanceBinding | None = None
    result: PilotRunResult
    promotion_allowed: Literal[False] = False

    @model_validator(mode="after")
    def validate_receipt(self) -> "TrustedEvaluationReceipt":
        if self.schema_version != SCHEMA_TRUSTED_RECEIPT:
            raise ValueError("unsupported trusted receipt schema")
        if self.configuration.egress_allowed != self.result.egress_allowed or (
            self.configuration.semantic_allowed != self.result.semantic_allowed
        ):
            raise ValueError("receipt configuration does not match evaluated result")
        if (self.baseline_result is None) != (self.baseline_anchor is None):
            raise ValueError("baseline result and anchor must be present or absent together")
        if (
            self.baseline_result is not None
            and self.baseline_anchor is not None
            and (
                self.baseline_result.result_digest != self.baseline_anchor.result_digest
                or _sha256_hex(
                    json.dumps(self.baseline_result.model_dump(mode="json"), sort_keys=True).encode(
                        "utf-8"
                    )
                )
                != self.baseline_anchor.result_payload_hash
            )
        ):
            raise ValueError("baseline anchor does not bind the embedded result payload")
        if self.receipt_id != canonical_receipt_digest(self):
            raise ValueError("trusted receipt digest mismatch")
        return self


class RunContext(BaseModel):
    repo_root: str
    allow_egress: bool = False
    allow_semantic: bool = False


@dataclass(frozen=True)
class PreparedTrustedEvaluation:
    result: PilotRunResult
    evaluator_pin: EvaluatorSubjectPin
    evaluator_pin_source: Literal["explicit", "derived"]
    baseline_result: PilotRunResult | None
    baseline_anchor: BaselineAnchor | None


def canonical_receipt_digest(receipt: "TrustedEvaluationReceipt | dict[str, object]") -> str:
    payload = (
        receipt.model_dump(mode="json")
        if isinstance(receipt, TrustedEvaluationReceipt)
        else dict(receipt)
    )
    payload.pop("receipt_id", None)
    return _sha256_hex(json.dumps(payload, sort_keys=True).encode("utf-8"))


def build_trusted_receipt(
    result: PilotRunResult,
    *,
    evaluator_pin: EvaluatorSubjectPin,
    evaluator_pin_source: Literal["explicit", "derived"],
    baseline_result: PilotRunResult | None,
    baseline_anchor: BaselineAnchor | None,
    acceptance: ExternalAcceptanceBinding | None = None,
) -> TrustedEvaluationReceipt:
    """Build advisory receipts only; accepted receipts are launcher-owned."""
    if acceptance is not None:
        raise ValueError("externally accepted receipts can only be built by the trusted launcher")
    payload = {
        "schema_version": SCHEMA_TRUSTED_RECEIPT,
        "evaluator_pin": evaluator_pin.model_dump(mode="json"),
        "evaluator_pin_source": evaluator_pin_source,
        "baseline_result": (
            baseline_result.model_dump(mode="json") if baseline_result is not None else None
        ),
        "baseline_anchor": (
            baseline_anchor.model_dump(mode="json") if baseline_anchor is not None else None
        ),
        "configuration": {
            "egress_allowed": result.egress_allowed,
            "semantic_allowed": result.semantic_allowed,
        },
        "acceptance": acceptance.model_dump(mode="json") if acceptance is not None else None,
        "result": result.model_dump(mode="json"),
        "promotion_allowed": False,
    }
    payload["receipt_id"] = canonical_receipt_digest(payload)
    return TrustedEvaluationReceipt.model_validate(payload)


def persist_trusted_receipt(
    repo_root: Path, receipt: TrustedEvaluationReceipt
) -> tuple[Path, TrustedEvaluationReceipt]:
    """Persist advisory receipts only; launcher receipts use held-directory storage."""
    if receipt.acceptance is not None:
        raise ValueError("externally accepted receipts can only be persisted by the trusted launcher")
    receipt_bytes = (
        json.dumps(receipt.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    receipt_name = receipt.receipt_id.removeprefix("sha256:") + ".json"
    relative = RESULTS_ROOT / "receipts" / receipt_name
    try:
        destination, persisted_bytes = safe_atomic_create_or_read_identical(
            repo_root,
            relative,
            receipt_bytes,
            allowed_repo_root=RESULTS_ROOT,
        )
    except UnsafeStoragePath as exc:
        raise ValueError(str(exc)) from exc
    loaded_payload = json.loads(persisted_bytes.decode("utf-8"))
    loaded = TrustedEvaluationReceipt.model_validate(loaded_payload)
    if loaded.receipt_id != receipt.receipt_id:
        raise ValueError("persisted trusted receipt identity changed")
    return destination, loaded


# ---------------------------------------------------------------------------
# Frozen case loading (read-only w.r.t. the case file - never written here)
# ---------------------------------------------------------------------------


def cases_file_hash(cases_path: Path) -> str:
    return _sha256_hex(cases_path.read_bytes())


def _parse_cases(cases_path: Path, corpus_bytes: bytes) -> list[dict]:
    try:
        corpus_text = corpus_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{cases_path}: case corpus must be valid UTF-8") from exc

    cases: list[dict] = []
    for lineno, raw_line in enumerate(corpus_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        case = json.loads(line)
        if case.get("schema_version") != SCHEMA_CASE:
            raise ValueError(
                f"{cases_path}:{lineno}: unsupported schema_version "
                f"{case.get('schema_version')!r} (expected {SCHEMA_CASE!r})"
            )
        if case.get("kind") not in _KNOWN_KINDS:
            raise ValueError(f"{cases_path}:{lineno}: unknown kind {case.get('kind')!r}")
        provenance_origin = case.get("provenance", {}).get("origin")
        if provenance_origin not in _KNOWN_ORIGINS:
            raise ValueError(
                f"{cases_path}:{lineno}: case {case.get('case_id')!r} has "
                f"unsupported provenance.origin {provenance_origin!r}"
            )
        provenance = case.get("provenance") or {}
        missing = _REQUIRED_PROVENANCE_FIELDS - provenance.keys()
        if missing:
            raise ValueError(
                f"{cases_path}:{lineno}: case {case.get('case_id')!r} missing "
                f"required provenance field(s): {sorted(missing)}"
            )
        if case.get("grader") not in GRADERS:
            raise ValueError(
                f"{cases_path}:{lineno}: case {case.get('case_id')!r} names unknown "
                f"grader {case.get('grader')!r}"
            )
        if not isinstance(case.get("case_id"), str):
            raise ValueError(f"{cases_path}:{lineno}: case_id must be a string")
        _validate_identifier("case_id", case["case_id"])
        if any(existing["case_id"] == case["case_id"] for existing in cases):
            raise ValueError(f"{cases_path}:{lineno}: duplicate case_id {case['case_id']!r}")
        if case["kind"] == "comparative" and case["grader"] not in _CONTROLLED_COMPARATORS:
            raise ValueError(
                f"{cases_path}:{lineno}: comparative case lacks a pinned status-quo control"
            )
        cases.append(case)
    if not cases:
        raise ValueError("case corpus must contain at least one valid case")
    return cases


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _validate_identifier(label: str, value: str | None) -> None:
    if value is None or not _SAFE_IDENTIFIER.fullmatch(value) or _SECRET_LIKE.search(value):
        raise ValueError(f"{label} must be a bounded non-secret identifier")


def _is_canonical_cases(cases_path: Path, repo_root: Path = REPO_ROOT) -> bool:
    try:
        return (
            cases_path.resolve()
            == (repo_root / "tests/fixtures/holusight_eval_pilot_cases.jsonl").resolve()
        )
    except OSError:
        return False


def load_cases(cases_path: Path) -> list[dict]:
    """Load and structurally validate the frozen case corpus. Every case
    must declare a supported schema_version, kind, and provenance block -
    a case admitted without full provenance is rejected rather than
    silently run, per the case-admission contract
    (docs/playbooks/eval-pilot-case-admission.md)."""
    return _parse_cases(cases_path, cases_path.read_bytes())


def build_intake_proposal(
    summary: str,
    *,
    origin: str = "reproduced_usage_gap",
    kind: str = "regression",
    diagnosis_ref: str | None = None,
    fix_ref: str | None = None,
    cases_path: Path | None = None,
    admitted_by: str | None = None,
    admitted_at: str | None = None,
    case_id: str | None = None,
    grader: str = "<unassigned>",
) -> dict:
    """Build an explicit content-minimized case intake payload for human review.

    This helper performs no writes and captures only an admission record plus
    optional provenance references.
    """
    if kind not in _KNOWN_KINDS:
        raise ValueError(f"unsupported kind {kind!r}")
    if origin not in _KNOWN_ORIGINS:
        raise ValueError(f"unsupported origin {origin!r}")

    trimmed = " ".join(summary.split())
    if not trimmed:
        raise ValueError("summary must contain at least one non-empty word")
    if _SECRET_LIKE.search(trimmed):
        raise ValueError("summary contains private or credential-like content")
    if admitted_by is not None:
        _validate_identifier("admitted_by", admitted_by)

    proposed_case_id = case_id or f"proposed-{_short_hash(trimmed)}"
    _validate_identifier("case_id", proposed_case_id)
    is_duplicate_case_id = False
    if cases_path and cases_path.exists():
        try:
            existing_case_ids = {c["case_id"] for c in load_cases(cases_path)}
            is_duplicate_case_id = proposed_case_id in existing_case_ids
        except Exception:
            # Intake can still proceed; the caller can decide whether to proceed
            # once they fix the case file schema.
            is_duplicate_case_id = False

    proposal = {
        "schema_version": SCHEMA_INTAKE_PROPOSAL,
        "case_id": proposed_case_id,
        "family": "regression",
        "kind": kind,
        "provenance": {
            "origin": origin,
            "description": trimmed[:240],
            "diagnosis_ref": diagnosis_ref,
            "fix_ref": fix_ref,
            "admitted_by": admitted_by or "unassigned",
            "admitted_at": admitted_at or _now().split("T", 1)[0],
        },
        "proposed_grader": grader,
        "fixture": {},
        "expected": {},
        "requires_semantic": False,
        "requires_index": False,
        "notes": "human-reviewed repository-local proposal; no raw prompts or private content",
    }
    return {
        "schema_version": SCHEMA_INTAKE_PROPOSAL,
        "intake": proposal,
        "intake_policy": {
            "status": "duplicate_case_id" if is_duplicate_case_id else "proposed",
            "content_minimized": True,
            "captures_prompt_or_private_content": False,
            "auto_placement": False,
        },
    }


def _recomputed_counts(grades: list[CaseGrade]) -> ResultCounts:
    return ResultCounts(
        total=len(grades),
        passed=sum(g.verdict == "pass" for g in grades),
        failed=sum(g.verdict == "fail" for g in grades),
        errored=sum(g.verdict == "error" for g in grades),
        comparative_total=sum(g.kind == "comparative" for g in grades),
        comparative_with_status_quo_verdict=sum(
            g.kind == "comparative" and g.status_quo_verdict is not None for g in grades
        ),
    )


def _validate_result(result: PilotRunResult) -> None:
    if result.schema_version != SCHEMA_RESULT:
        raise ValueError("prior result uses an unsupported schema")
    if not result.result_digest or result.result_digest != canonical_result_digest(result):
        raise ValueError("prior result digest does not match canonical result bytes")
    if (
        result.counts["passed"] + result.counts["failed"] + result.counts["errored"]
        != result.counts["total"]
    ):
        raise ValueError("prior result counts do not form a complete partition")
    if result.counts != _recomputed_counts(result.grades):
        raise ValueError("prior result counts do not match grades")
    for grade in result.grades:
        if grade.kind == "comparative" and grade.status_quo_verdict is None:
            raise ValueError("prior result has comparative grade without a status-quo verdict")
        if grade.kind == "regression" and grade.status_quo_verdict is not None:
            raise ValueError("prior result has status-quo verdict for a non-comparative grade")
    expected_status_quo_control = (
        "included" if result.counts["comparative_total"] else "not_applicable"
    )
    if result.status_quo_control != expected_status_quo_control:
        raise ValueError("prior result has invalid status-quo control state")
    if result.counts["comparative_total"] != result.counts["comparative_with_status_quo_verdict"]:
        raise ValueError("prior result has incomplete status-quo controls")
    if result.corpus_trust != "canonical" or result.lineage.repo_dirty:
        raise ValueError("prior result is not immutable promotion-relevant evidence")
    if not result.subject.clean or not result.subject.commit or not result.subject.tree:
        raise ValueError("prior result lacks a clean, resolvable immutable Git subject")
    if (
        not result.lineage.evaluator_digest
        or not result.lineage.candidate_digest
        or not result.lineage.comparator_digest
    ):
        raise ValueError("prior result lacks pinned evaluator, candidate, or comparator identity")


def _load_prior_run_bytes(path: Path, result_bytes: bytes) -> PilotRunResult:
    try:
        payload = json.loads(result_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path} must contain valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    required_keys = {
        "run_id",
        "counts",
        "lineage",
        "cases_file_hash",
        "cases_file",
        "schema_version",
    }
    if not required_keys <= set(payload):
        # Some callers may feed a summary-like artifact; fail fast to avoid false
        # confidence.
        raise ValueError(f"{path} does not look like a PilotRunResult")
    result = PilotRunResult.model_validate(payload)
    _validate_result(result)
    return result


def load_prior_run(path: Path) -> PilotRunResult:
    """Load and fully validate one prior result artifact."""
    if not path.exists():
        raise ValueError(f"{path} does not exist")
    return _load_prior_run_bytes(path, path.read_bytes())


def load_anchored_baseline(
    repo_root: Path, path: Path
) -> tuple[PilotRunResult, BaselineAnchor | None]:
    """Read baseline bytes once and bind those exact bytes to a Git manifest."""
    from . import improvement_control

    try:
        result_bytes, anchor_payload = improvement_control.load_trusted_evaluation_result_bytes(
            repo_root, path
        )
    except OSError as exc:
        raise ValueError(f"{path} must be a regular baseline result file") from exc
    result = _load_prior_run_bytes(path, result_bytes)
    if anchor_payload is None:
        return result, None
    anchor_payload["result_digest"] = result.result_digest
    anchor_payload["result_payload_hash"] = _sha256_hex(
        json.dumps(result.model_dump(mode="json"), sort_keys=True).encode("utf-8")
    )
    return result, BaselineAnchor.model_validate(anchor_payload)


def _comparison_progress(
    outcome: str,
    *,
    reason: str,
    next_step: str,
    research_needed: bool,
    stagnated: bool,
    review_eligible: bool,
    recommended_research: str | None,
) -> dict[str, object]:
    """Return comparison evidence without granting promotion relevance."""
    is_advisory = outcome == "research_needed" and reason.startswith("no prior")
    classification = "review_eligible" if review_eligible else (
        "advisory" if is_advisory else "invalid"
    )
    return {
        "outcome": outcome,
        "research_needed": research_needed,
        "stagnated": stagnated,
        "reason": reason,
        "recommended_research": recommended_research,
        "next_step": next_step,
        "comparison": {
            "classification": classification,
            "review_eligible": review_eligible,
            "promotion_relevant": False,
            "automatic_promotion": False,
        },
    }


def _is_ancestor_commit(repo_root: Path, ancestor: str, descendant: str) -> bool:
    result = _git_run(repo_root, "merge-base", "--is-ancestor", ancestor, descendant, text=True)
    return result.returncode == 0


def _evaluate_progress(
    current: PilotRunResult,
    previous: PilotRunResult | None,
    *,
    trusted_anchor: BaselineAnchor | None = None,
    repo_root: Path | None = None,
    evaluator_pin: EvaluatorSubjectPin | None = None,
) -> dict[str, object]:
    """Return a fail-closed, explicitly classified comparison outcome."""
    if previous is None:
        return _comparison_progress(
            "research_needed",
            reason="no prior run to compare against",
            next_step="run_compare_after_repair",
            research_needed=True,
            stagnated=False,
            review_eligible=False,
            recommended_research="normal_review",
        )

    try:
        _validate_result(current)
        _validate_result(previous)
    except ValueError as exc:
        return _comparison_progress(
            "invalid_comparison",
            reason=str(exc),
            next_step="repair_comparison_evidence",
            research_needed=True,
            stagnated=False,
            review_eligible=False,
            recommended_research="normal_review",
        )
    if not trusted_anchor:
        return _comparison_progress(
            "invalid_comparison",
            reason="prior result is not pinned by a clean tracked evaluated manifest",
            next_step="repair_comparison_evidence",
            research_needed=True,
            stagnated=False,
            review_eligible=False,
            recommended_research="normal_review",
        )
    if repo_root is None:
        return _comparison_progress(
            "invalid_comparison",
            reason="repository root is required for independent evaluator pin validation",
            next_step="repair_comparison_evidence",
            research_needed=True,
            stagnated=False,
            review_eligible=False,
            recommended_research="normal_review",
        )
    try:
        baseline_pin = evaluator_pin_for_result(repo_root, previous)
    except ValueError as exc:
        return _comparison_progress(
            "invalid_comparison",
            reason=f"cannot derive independent baseline evaluator pin: {exc}",
            next_step="repair_comparison_evidence",
            research_needed=True,
            stagnated=False,
            review_eligible=False,
            recommended_research="normal_review",
        )
    if evaluator_pin is None:
        evaluator_pin = baseline_pin
    elif (
        baseline_pin.evaluator_blobs != evaluator_pin.evaluator_blobs
        or baseline_pin.corpus_blob != evaluator_pin.corpus_blob
        or baseline_pin.corpus_path != evaluator_pin.corpus_path
    ):
        return _comparison_progress(
            "invalid_comparison",
            reason="baseline evaluator or frozen corpus does not match the approved pin",
            next_step="repair_comparison_evidence",
            research_needed=True,
            stagnated=False,
            review_eligible=False,
            recommended_research="normal_review",
        )
    pin_blockers = evaluator_pin_blockers(repo_root, evaluator_pin, current)
    if (
        current.cases_file_hash != previous.cases_file_hash
        or current.egress_allowed != previous.egress_allowed
        or current.semantic_allowed != previous.semantic_allowed
        or current.lineage.candidate_id != previous.lineage.candidate_id
        or not current.subject.commit
        or not previous.subject.commit
        or not _is_ancestor_commit(repo_root, previous.subject.commit, current.subject.commit)
        or pin_blockers
    ):
        reason = (
            "approved evaluator pin does not match the candidate result"
            if pin_blockers
            else "corpus, configuration, candidate, or immutable commit identity differs"
        )
        return _comparison_progress(
            "invalid_comparison",
            reason=reason,
            next_step="repair_comparison_evidence",
            research_needed=True,
            stagnated=False,
            review_eligible=False,
            recommended_research="normal_review",
        )

    current_rate = current.counts["passed"] / max(current.counts["total"], 1)
    previous_rate = previous.counts["passed"] / max(previous.counts["total"], 1)

    if current.counts["errored"] > previous.counts["errored"]:
        return _comparison_progress(
            "research_needed",
            reason="errored cases increased",
            next_step="isolate_instability",
            research_needed=True,
            stagnated=False,
            review_eligible=True,
            recommended_research="normal_review",
        )

    if current_rate > previous_rate:
        return _comparison_progress(
            "improved",
            reason="pass rate improved",
            next_step="candidate_readiness_for_review",
            research_needed=False,
            stagnated=False,
            review_eligible=True,
            recommended_research=None,
        )

    if current_rate < previous_rate:
        return _comparison_progress(
            "stagnated",
            reason="pass rate decreased",
            next_step="pause_promotion",
            research_needed=False,
            stagnated=True,
            review_eligible=True,
            recommended_research="gpt_deep_research",
        )

    return _comparison_progress(
        "stagnated",
        reason="no measurable change from prior run",
        next_step="add_new_cases",
        research_needed=False,
        stagnated=True,
        review_eligible=True,
        recommended_research="gpt_deep_research",
    )


def evaluate_progress(
    current: PilotRunResult,
    previous: PilotRunResult | None,
    *,
    trusted_anchor: BaselineAnchor | None = None,
    repo_root: Path | None = None,
    evaluator_pin: EvaluatorSubjectPin | None = None,
) -> dict[str, object]:
    """Return advisory progress outside the immutable receipt boundary."""
    progress = _evaluate_progress(
        current,
        previous,
        trusted_anchor=trusted_anchor,
        repo_root=repo_root,
        evaluator_pin=evaluator_pin,
    )
    if progress["outcome"] != "invalid_comparison":
        progress["comparison"]["classification"] = "advisory"
    return progress


def _baseline_anchor_blockers(repo_root: Path, receipt: TrustedEvaluationReceipt) -> list[str]:
    if receipt.baseline_anchor is None:
        return []
    anchor = receipt.baseline_anchor
    blockers: list[str] = []
    if anchor.repository_id != _repository_identity(repo_root):
        blockers.append("baseline_anchor_repository_mismatch")
    if anchor.manifest_commit != receipt.result.subject.commit:
        blockers.append("baseline_anchor_not_candidate_subject")
    if (
        _git_oid(repo_root, f"{anchor.manifest_commit}:{anchor.manifest_path}")
        != anchor.manifest_blob
    ):
        blockers.append("baseline_manifest_blob_mismatch")
        return blockers
    manifest_result = _git_run(
        repo_root, "show", f"{anchor.manifest_commit}:{anchor.manifest_path}"
    )
    try:
        manifest = json.loads(manifest_result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        blockers.append("baseline_manifest_invalid")
        return blockers
    if (
        manifest_result.returncode != 0
        or manifest.get("schema_version") != "holus-improvement-change/v1"
        or manifest.get("classification") != "evaluated"
        or anchor.result_path not in manifest.get("links", {}).get("evaluation_result", [])
        or manifest.get("link_hashes", {}).get(anchor.result_path) != anchor.result_bytes_hash
    ):
        blockers.append("baseline_manifest_binding_mismatch")
    return blockers


def evaluate_receipt_progress(
    receipt: TrustedEvaluationReceipt, *, repo_root: Path
) -> dict[str, object]:
    anchor_blockers = _baseline_anchor_blockers(repo_root, receipt)
    if anchor_blockers:
        return _comparison_progress(
            "invalid_comparison",
            reason="immutable baseline anchor is invalid: " + ", ".join(anchor_blockers),
            next_step="repair_comparison_evidence",
            research_needed=True,
            stagnated=False,
            review_eligible=False,
            recommended_research="normal_review",
        )
    progress = _evaluate_progress(
        receipt.result,
        receipt.baseline_result,
        trusted_anchor=receipt.baseline_anchor,
        repo_root=repo_root,
        evaluator_pin=receipt.evaluator_pin,
    )
    if progress["outcome"] != "invalid_comparison":
        progress["comparison"]["classification"] = "advisory"
    return progress


# ---------------------------------------------------------------------------
# Status-quo control comparator (frozen; never imported by production code)
# ---------------------------------------------------------------------------


_FROZEN_AUTO_PROVIDER_ORDER = ("exact", "structural", "consistency", "semantic")


def _naive_concatenate_then_slice(provider_item_counts: dict[str, int], cap: int) -> list[str]:
    """Pure re-implementation of the PRE-FIX merge strategy
    (`all_items[:_MAX_DISPLAY_ITEMS]` before PR #20), kept here *only* as a
    frozen status-quo-control comparator for this eval pilot.

    This function must never be edited to track a future candidate's
    behavior - doing so would erase the control condition the
    ``cli-axi-provider-starvation-display-quota`` case exists to preserve.
    Production code never imports this function; it always uses
    ``cli_axi._select_display_items``.
    """
    flat = [
        provider
        for provider in _FROZEN_AUTO_PROVIDER_ORDER
        for _ in range(provider_item_counts.get(provider, 0))
    ]
    return flat[:cap]


# ---------------------------------------------------------------------------
# Graders - one per registered case "grader" name. Each returns a CaseGrade
# and never raises for an ordinary fail (only for a fixture/programming
# error, which run_pilot catches and records as verdict="error").
# ---------------------------------------------------------------------------


_CANDIDATE_ADAPTER = r"""
import json
import os
import sys
import tempfile
import types
from pathlib import Path

package = types.ModuleType("codesight")
package.__path__ = [sys.argv.pop(1)]
package.__package__ = "codesight"
sys.modules["codesight"] = package
payload = json.load(sys.stdin)
operation = payload["operation"]
if operation == "display":
    from codesight import axi_providers, cli_axi

    results = []
    for name in axi_providers.MODE_PROVIDERS["auto"]:
        items = [
            axi_providers.EvidenceItem(
                provider=name,
                source=f"synthetic/{name}.txt",
                location=f"L{index + 1}",
                excerpt="synthetic fixture item",
            )
            for index in range(payload["counts"].get(name, 0))
        ]
        results.append(
            axi_providers.ProviderResult(
                provider=name,
                state=axi_providers.ProviderState.OK,
                detail="synthetic fixture",
                route_reason="synthetic fixture",
                items=items,
            )
        )
    selected = cli_axi._select_display_items(results, payload["cap"])
    output = {"providers": [item.provider for item in selected]}
elif operation == "dangling":
    from codesight import consistency

    _edges, dangling = consistency.extract_exact_references(
        payload["doc_path"], Path.cwd()
    )
    output = {"is_dangling": payload["expected_token"] in dangling}
elif operation == "refresh_check":
    from codesight import consistency

    with tempfile.TemporaryDirectory(prefix="holus-eval-pilot-") as temporary:
        root = Path(temporary)
        spec_path = root / "specs" / "001-alpha.md"
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(payload["spec_body"], encoding="utf-8")
        impl_path = root / "src" / "pkg" / "mod.py"
        impl_path.parent.mkdir(parents=True, exist_ok=True)
        impl_path.write_text(payload["impl_body"], encoding="utf-8")
        consistency.refresh(root)
        report = consistency.check_consistency(root, "specs/001-alpha.md")
    output = {"status": report.status.value}
elif operation == "no_egress":
    from codesight import axi_providers

    sentinel = "sk-eval-pilot-sentinel-value"
    saved = os.environ.get("VOYAGE_API_KEY")
    os.environ["VOYAGE_API_KEY"] = sentinel
    try:
        with axi_providers._no_egress_env():
            stripped = "VOYAGE_API_KEY" not in os.environ
        restored = os.environ.get("VOYAGE_API_KEY") == sentinel
    finally:
        if saved is None:
            os.environ.pop("VOYAGE_API_KEY", None)
        else:
            os.environ["VOYAGE_API_KEY"] = saved
    output = {"stripped": stripped, "restored": restored}
else:
    raise ValueError("unsupported candidate adapter operation")
print(json.dumps(output, sort_keys=True))
"""


@dataclass(frozen=True)
class _BoundedProcessResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    output_truncated: bool


@dataclass(frozen=True)
class _SandboxedCommand:
    argv: list[str]
    pass_fds: tuple[int, ...] = ()


def _uid_process_count() -> int:
    ps = shutil.which("ps")
    if ps is None:
        raise ValueError("resource-bounded execution requires process accounting")
    measured = subprocess.run(
        [ps, "-U", str(os.getuid()), "-o", "pid="],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": os.defpath, "LANG": "C"},
    )
    if measured.returncode != 0:
        raise ValueError("resource-bounded execution requires process accounting")
    return sum(1 for line in measured.stdout.splitlines() if line.strip())


def _process_limit_setter(
    *, cpu_seconds: int, memory_bytes: int, file_bytes: int, process_count: int
) -> Callable[[], None]:
    process_limit = _uid_process_count() + process_count

    def apply() -> None:
        limits = (
            ("RLIMIT_CORE", 0, 0),
            ("RLIMIT_CPU", cpu_seconds, cpu_seconds + 1),
            ("RLIMIT_FSIZE", file_bytes, file_bytes),
            ("RLIMIT_NOFILE", 64, 64),
            ("RLIMIT_NPROC", process_limit, process_limit),
            ("RLIMIT_AS", memory_bytes, memory_bytes),
            ("RLIMIT_DATA", memory_bytes, memory_bytes),
        )
        for name, soft, hard in limits:
            if sys.platform == "darwin" and name in {"RLIMIT_AS", "RLIMIT_DATA"}:
                continue
            kind = getattr(resource, name, None)
            if kind is None:
                continue
            current_soft, current_hard = resource.getrlimit(kind)
            bounded_hard = (
                hard if current_hard == resource.RLIM_INFINITY else min(hard, current_hard)
            )
            bounded_soft = min(soft, bounded_hard)
            resource.setrlimit(kind, (bounded_soft, bounded_hard))

    return apply


def _kill_process_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _monitor_process_memory(
    process: subprocess.Popen,
    *,
    memory_bytes: int,
    stop: threading.Event,
    exceeded: threading.Event,
) -> None:
    ps = shutil.which("ps")
    if ps is None:
        exceeded.set()
        _kill_process_group(process)
        return
    while not stop.wait(0.05):
        measured = subprocess.run(
            [ps, "-axo", "pgid=,rss="],
            capture_output=True,
            text=True,
            check=False,
            env={"PATH": os.defpath, "LANG": "C"},
        )
        if measured.returncode != 0:
            exceeded.set()
            _kill_process_group(process)
            return
        rss_kib = 0
        for line in measured.stdout.splitlines():
            columns = line.split()
            if len(columns) == 2 and columns[0] == str(process.pid):
                try:
                    rss_kib += int(columns[1])
                except ValueError:
                    exceeded.set()
                    _kill_process_group(process)
                    return
        if rss_kib * 1024 > memory_bytes:
            exceeded.set()
            _kill_process_group(process)
            return


def _run_bounded_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    input_text: str | None,
    timeout: int,
    output_dir: Path,
    cpu_seconds: int,
    memory_bytes: int,
    process_count: int,
    max_output_bytes: int,
    max_file_bytes: int | None = None,
    pass_fds: tuple[int, ...] = (),
) -> _BoundedProcessResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (
        tempfile.TemporaryFile(dir=output_dir) as stdout_file,
        tempfile.TemporaryFile(dir=output_dir) as stderr_file,
    ):
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
            stdout=stdout_file,
            stderr=stderr_file,
            text=True,
            start_new_session=True,
            pass_fds=pass_fds,
            preexec_fn=_process_limit_setter(
                cpu_seconds=cpu_seconds,
                memory_bytes=memory_bytes,
                file_bytes=max_file_bytes or max_output_bytes,
                process_count=process_count,
            ),
        )
        timed_out = False
        monitor_stop = threading.Event()
        memory_exceeded = threading.Event()
        monitor = None
        if sys.platform == "darwin":
            monitor = threading.Thread(
                target=_monitor_process_memory,
                kwargs={
                    "process": process,
                    "memory_bytes": memory_bytes,
                    "stop": monitor_stop,
                    "exceeded": memory_exceeded,
                },
                daemon=True,
            )
            monitor.start()
        try:
            process.communicate(input=input_text, timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_process_group(process)
            process.wait()
        finally:
            monitor_stop.set()
            if monitor is not None:
                monitor.join(timeout=1)
            _kill_process_group(process)
        stdout_file.seek(0, os.SEEK_END)
        stdout_size = stdout_file.tell()
        stderr_file.seek(0, os.SEEK_END)
        stderr_size = stderr_file.tell()
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout = stdout_file.read(max_output_bytes + 1).decode("utf-8", errors="replace")
        stderr = stderr_file.read(max_output_bytes + 1).decode("utf-8", errors="replace")
    return _BoundedProcessResult(
        returncode=process.returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        output_truncated=(
            stdout_size > max_output_bytes
            or stderr_size > max_output_bytes
            or memory_exceeded.is_set()
        ),
    )


def _linux_no_child_process_filter(scratch_root: Path) -> int:
    machine = platform.machine().lower()
    architecture = {
        "x86_64": (0xC000003E, (56, 57, 58, 435), True),
        "amd64": (0xC000003E, (56, 57, 58, 435), True),
        "aarch64": (0xC00000B7, (220, 435), False),
        "arm64": (0xC00000B7, (220, 435), False),
    }.get(machine)
    if architecture is None:
        raise ValueError("candidate adapter cannot deny child processes on this architecture")
    audit_arch, syscall_numbers, deny_x32 = architecture
    instructions = [
        (0x20, 0, 0, 4),
        (0x15, 1, 0, audit_arch),
        (0x06, 0, 0, 0x80000000),
        (0x20, 0, 0, 0),
    ]
    if deny_x32:
        instructions.extend(
            ((0x45, 0, 1, 0x40000000), (0x06, 0, 0, 0x00050000 | errno.EPERM))
        )
    for number in syscall_numbers:
        instructions.extend(
            ((0x15, 0, 1, number), (0x06, 0, 0, 0x00050000 | errno.EPERM))
        )
    instructions.append((0x06, 0, 0, 0x7FFF0000))
    filter_path = scratch_root / "candidate-no-child-processes.bpf"
    filter_path.write_bytes(b"".join(struct.pack("=HBBI", *item) for item in instructions))
    fd = os.open(filter_path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    os.set_inheritable(fd, True)
    return fd


def _sandboxed_candidate_command(
    command: list[str], *, candidate_snapshot: Path, scratch_root: Path
) -> _SandboxedCommand:
    runtime_paths = _runtime_read_paths()
    readonly_paths = list(
        dict.fromkeys(
            variant
            for path in [candidate_snapshot, *runtime_paths]
            for variant in (path, path.resolve())
        )
    )
    scratch_paths = list(dict.fromkeys((scratch_root, scratch_root.resolve())))
    if sys.platform == "darwin":
        sandbox_exec = shutil.which("sandbox-exec")
        if sandbox_exec is None:
            raise ValueError("candidate adapter requires an OS-enforced sandbox")
        metadata_paths = {Path("/")}
        for path in [*readonly_paths, *scratch_paths]:
            metadata_paths.add(path)
            metadata_paths.update(path.parents)
        python_paths = {Path(sys.executable), Path(sys.executable).resolve()}
        rules = [
            "(version 1)",
            "(deny default)",
            *(
                f"(allow process-exec* (literal {json.dumps(str(path))}))"
                for path in sorted(python_paths, key=str)
            ),
            "(allow signal (target same-sandbox))",
            *(
                f"(allow file-read-metadata (literal {json.dumps(str(path))}))"
                for path in sorted(metadata_paths, key=str)
            ),
            *(
                f"(allow file-read* ({'literal' if path.is_file() else 'subpath'} "
                f"{json.dumps(str(path))}))"
                for path in [*readonly_paths, *scratch_paths]
            ),
            "(allow file-map-executable)",
            '(allow file-read-data (literal "/"))',
            *(f"(allow file-write* (subpath {json.dumps(str(path))}))" for path in scratch_paths),
            '(allow file-read* (literal "/dev/null"))',
            '(allow file-write-data (literal "/dev/null"))',
            '(allow file-ioctl (literal "/dev/null"))',
            '(allow file-read* (literal "/dev/random"))',
            '(allow file-read* (literal "/dev/urandom"))',
            "(allow sysctl-read)",
            "(allow mach-lookup)",
        ]
        profile = scratch_root / "candidate.sb"
        profile.write_text("\n".join(rules) + "\n", encoding="utf-8")
        return _SandboxedCommand([sandbox_exec, "-f", str(profile), *command])
    if sys.platform.startswith("linux"):
        bwrap = shutil.which("bwrap")
        if bwrap is None:
            raise ValueError("candidate adapter requires an OS-enforced sandbox")
        seccomp_fd = _linux_no_child_process_filter(scratch_root)
        sandbox = [
            bwrap,
            "--die-with-parent",
            "--unshare-all",
            "--new-session",
            "--seccomp",
            str(seccomp_fd),
        ]
        for path in readonly_paths:
            sandbox.extend(("--ro-bind", str(path), str(path)))
        sandbox.extend(
            (
                "--bind",
                str(scratch_root),
                str(scratch_root),
                "--dev",
                "/dev",
                "--proc",
                "/proc",
                "--chdir",
                str(candidate_snapshot),
            )
        )
        return _SandboxedCommand([*sandbox, *command], (seccomp_fd,))
    raise ValueError("candidate adapter requires an OS-enforced sandbox")


def _run_candidate_adapter_local(
    repo_root: Path,
    operation: str,
    payload: dict[str, object],
    *,
    allow_egress: bool,
    scratch_root: Path | None = None,
) -> dict[str, object]:
    if allow_egress:
        raise ValueError("candidate adapters cannot run with egress")
    if scratch_root is None:
        with tempfile.TemporaryDirectory(prefix="holus-candidate-adapter-") as temporary:
            return _run_candidate_adapter_local(
                repo_root,
                operation,
                payload,
                allow_egress=False,
                scratch_root=Path(temporary),
            )
    candidate_package = repo_root / "src" / "codesight"
    if not (candidate_package / "axi_providers.py").is_file():
        raise ValueError("candidate snapshot does not contain the required adapter package")
    env = {
        "PATH": os.defpath,
        "HOME": str(scratch_root),
        "LANG": "C",
        "TMPDIR": str(scratch_root),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }
    command = [
        sys.executable,
        "-I",
        "-B",
        "-c",
        _CANDIDATE_ADAPTER,
        str(candidate_package),
    ]
    sandboxed = _sandboxed_candidate_command(
        command,
        candidate_snapshot=repo_root,
        scratch_root=scratch_root,
    )
    try:
        completed = _run_bounded_process(
            sandboxed.argv,
            cwd=repo_root,
            env=env,
            input_text=json.dumps({"operation": operation, **payload}),
            timeout=30,
            output_dir=scratch_root,
            cpu_seconds=20,
            memory_bytes=1_073_741_824,
            process_count=2,
            max_output_bytes=65_536,
            max_file_bytes=2_097_152,
            pass_fds=sandboxed.pass_fds,
        )
    finally:
        for fd in sandboxed.pass_fds:
            os.close(fd)
    if completed.returncode != 0 or completed.timed_out or completed.output_truncated:
        raise ValueError(f"candidate {operation} adapter failed")
    try:
        output = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"candidate {operation} adapter returned invalid output") from exc
    if not isinstance(output, dict):
        raise ValueError(f"candidate {operation} adapter returned invalid output")
    return output


def _read_broker_response(fd: int) -> dict[str, object]:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = os.read(fd, 65_536)
        if not chunk:
            raise ValueError("trusted candidate adapter broker closed unexpectedly")
        chunks.append(chunk)
        size += len(chunk)
        if size > 1_048_576:
            raise ValueError("trusted candidate adapter broker response exceeded limits")
        if b"\n" in chunk:
            break
    try:
        response = json.loads(b"".join(chunks).split(b"\n", 1)[0])
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("trusted candidate adapter broker returned invalid output") from exc
    if not isinstance(response, dict) or response.get("ok") is not True:
        raise ValueError("trusted candidate adapter broker rejected the request")
    output = response.get("output")
    if not isinstance(output, dict):
        raise ValueError("trusted candidate adapter broker returned invalid output")
    return output


def _run_candidate_adapter(
    repo_root: Path,
    operation: str,
    payload: dict[str, object],
    *,
    allow_egress: bool,
) -> dict[str, object]:
    """Always enter a fresh OS sandbox; environment descriptors grant no bypass."""
    return _run_candidate_adapter_local(
        repo_root,
        operation,
        payload,
        allow_egress=allow_egress,
    )


def _candidate_adapter_broker(
    request_fd: int,
    response_fd: int,
    *,
    candidate_snapshot: Path,
    scratch_root: Path,
) -> None:
    with os.fdopen(request_fd, "rb") as requests, os.fdopen(response_fd, "wb") as responses:
        for line in requests:
            response: dict[str, object]
            try:
                if len(line) > 1_048_576:
                    raise ValueError("candidate adapter broker request exceeded limits")
                request = json.loads(line)
                if (
                    not isinstance(request, dict)
                    or request.get("allow_egress") is not False
                    or not isinstance(request.get("operation"), str)
                    or not isinstance(request.get("payload"), dict)
                ):
                    raise ValueError("candidate adapter broker request is invalid")
                output = _run_candidate_adapter_local(
                    candidate_snapshot,
                    request["operation"],
                    request["payload"],
                    allow_egress=False,
                    scratch_root=scratch_root,
                )
                response = {"ok": True, "output": output}
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                response = {"ok": False}
            try:
                responses.write(json.dumps(response, sort_keys=True).encode("utf-8") + b"\n")
                responses.flush()
            except BrokenPipeError:
                return


def _candidate_display_providers(
    repo_root: Path,
    provider_item_counts: dict[str, int],
    cap: int,
    *,
    allow_egress: bool,
) -> list[str]:
    output = _run_candidate_adapter(
        repo_root,
        "display",
        {"counts": provider_item_counts, "cap": cap},
        allow_egress=allow_egress,
    )
    providers = output.get("providers")
    if (
        set(output) != {"providers"}
        or not isinstance(providers, list)
        or len(providers) > cap
        or not all(
            isinstance(provider, str) and provider in _FROZEN_AUTO_PROVIDER_ORDER
            for provider in providers
        )
    ):
        raise ValueError("candidate display adapter returned invalid output")
    return providers


def grade_display_quota_case(case: dict, repo_root: Path, ctx: RunContext) -> CaseGrade:
    fixture = case["fixture"]
    expected = case["expected"]
    cap = int(fixture["cap"])

    candidate_displayed = _candidate_display_providers(
        repo_root,
        fixture["provider_item_counts"],
        cap,
        allow_egress=ctx.allow_egress,
    )
    candidate_providers = set(candidate_displayed)

    status_quo_displayed = _naive_concatenate_then_slice(fixture["provider_item_counts"], cap)
    status_quo_providers = set(status_quo_displayed)

    candidate_ok = len(candidate_providers) >= int(expected["candidate_min_distinct_providers"])
    status_quo_ok = len(status_quo_providers) <= int(expected["status_quo_max_distinct_providers"])

    verdict = "pass" if candidate_ok else "fail"
    # The status-quo comparator's own verdict is "pass" when it reproduces
    # the historically-confirmed starvation (<= the expected max distinct
    # providers) - i.e. when it is still genuinely worse than the
    # candidate. If this ever flips, the frozen comparator itself has
    # drifted and no longer serves as a meaningful control.
    status_quo_verdict = "pass" if status_quo_ok else "fail"

    detail = (
        f"candidate displayed {len(candidate_displayed)} items from "
        f"{len(candidate_providers)} distinct provider(s) {sorted(candidate_providers)}; "
        f"status-quo comparator displayed {len(status_quo_displayed)} items from "
        f"{len(status_quo_providers)} distinct provider(s) {sorted(status_quo_providers)}"
    )
    return CaseGrade(
        case_id=case["case_id"],
        family=case["family"],
        kind=case["kind"],
        verdict=verdict,
        status_quo_verdict=status_quo_verdict,
        detail=detail,
        provenance_origin=case["provenance"]["origin"],
    )


def grade_known_dangling_reference_case(case: dict, repo_root: Path, ctx: RunContext) -> CaseGrade:
    fixture = case["fixture"]
    doc_path = fixture["doc_path"]
    expected_token = fixture["expected_dangling_token"]

    full = repo_root / doc_path
    if not full.exists():
        return CaseGrade(
            case_id=case["case_id"],
            family=case["family"],
            kind=case["kind"],
            verdict="error",
            detail=f"fixture document does not exist: {doc_path}",
            provenance_origin=case["provenance"]["origin"],
        )

    output = _run_candidate_adapter(
        repo_root,
        "dangling",
        {"doc_path": doc_path, "expected_token": expected_token},
        allow_egress=ctx.allow_egress,
    )
    if set(output) != {"is_dangling"} or not isinstance(output["is_dangling"], bool):
        raise ValueError("candidate dangling adapter returned invalid output")
    is_dangling = output["is_dangling"]
    verdict = "pass" if is_dangling == bool(case["expected"]["must_be_dangling"]) else "fail"
    return CaseGrade(
        case_id=case["case_id"],
        family=case["family"],
        kind=case["kind"],
        verdict=verdict,
        detail=f"expected reference dangling={is_dangling}",
        provenance_origin=case["provenance"]["origin"],
    )


def grade_refresh_then_check_up_to_date(case: dict, repo_root: Path, ctx: RunContext) -> CaseGrade:
    fixture = case["fixture"]
    expected_status = case["expected"]["status"]
    output = _run_candidate_adapter(
        repo_root,
        "refresh_check",
        {"spec_body": fixture["spec_body"], "impl_body": fixture["impl_body"]},
        allow_egress=ctx.allow_egress,
    )
    if set(output) != {"status"} or output["status"] not in {
        "up_to_date",
        "spec_changed_awaiting_implementation",
        "possible_undocumented_drift",
        "coordinated_change",
    }:
        raise ValueError("candidate refresh adapter returned invalid output")
    status = output["status"]
    verdict = "pass" if status == expected_status else "fail"
    return CaseGrade(
        case_id=case["case_id"],
        family=case["family"],
        kind=case["kind"],
        verdict=verdict,
        detail=f"status={status!r}",
        provenance_origin=case["provenance"]["origin"],
    )


def grade_no_egress_default(case: dict, repo_root: Path, ctx: RunContext) -> CaseGrade:
    expected = case["expected"]
    output = _run_candidate_adapter(repo_root, "no_egress", {}, allow_egress=ctx.allow_egress)
    if set(output) != {"stripped", "restored"} or not all(
        isinstance(output[key], bool) for key in output
    ):
        raise ValueError("candidate no-egress adapter returned invalid output")
    stripped = output["stripped"]
    restored = output["restored"]
    ok = stripped == bool(expected["key_stripped_without_allow_egress"]) and restored == bool(
        expected["key_restored_after_context_exit"]
    )
    verdict = "pass" if ok else "fail"
    return CaseGrade(
        case_id=case["case_id"],
        family=case["family"],
        kind=case["kind"],
        verdict=verdict,
        detail=f"stripped={stripped} restored={restored}",
        provenance_origin=case["provenance"]["origin"],
    )


GRADERS: dict[str, Callable[[dict, Path, RunContext], CaseGrade]] = {
    "grade_display_quota_case": grade_display_quota_case,
    "grade_known_dangling_reference_case": grade_known_dangling_reference_case,
    "grade_refresh_then_check_up_to_date": grade_refresh_then_check_up_to_date,
    "grade_no_egress_default": grade_no_egress_default,
}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def _read_regular_file_no_follow(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("evaluator pin must be a regular file")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            return handle.read()
    finally:
        os.close(fd)


def _load_clean_tracked_pin_bytes(repo_root: Path, relative: str) -> bytes:
    head_commit = _git_oid(repo_root, "HEAD")
    if head_commit is None:
        raise ValueError("evaluator pin requires a resolvable repository HEAD")
    head_blob = _git_oid(repo_root, f"{head_commit}:{relative}")
    index_blob = _git_oid(repo_root, f":{relative}")
    if head_blob is None or index_blob != head_blob:
        raise ValueError("evaluator pin must be a clean tracked repository artifact")
    immutable = _git_run(repo_root, "show", f"{head_commit}:{relative}")
    if (
        immutable.returncode != 0
        or _git_blob_oid_for_bytes(repo_root, immutable.stdout) != head_blob
    ):
        raise ValueError("evaluator pin cannot be loaded from its captured Git subject")
    try:
        worktree_bytes = _read_regular_file_no_follow(repo_root / relative)
    except (OSError, ValueError) as exc:
        raise ValueError("evaluator pin must be a clean tracked repository artifact") from exc
    if (
        _git_blob_oid_for_bytes(repo_root, worktree_bytes) != head_blob
        or _git_oid(repo_root, "HEAD") != head_commit
    ):
        raise ValueError("evaluator pin changed while its Git identity was captured")
    return immutable.stdout


def _pin_contract_identity(pin: EvaluatorSubjectPin) -> tuple[object, ...]:
    return (
        tuple(sorted(pin.evaluator_blobs.items())),
        pin.protocol_path,
        pin.protocol_blob,
        pin.corpus_path,
        pin.corpus_blob,
    )


def _historical_evaluator_pins(repo_root: Path) -> list[EvaluatorSubjectPin]:
    history = _git_run(
        repo_root,
        "log",
        "--format=%H",
        "--name-only",
        "--diff-filter=AM",
        "HEAD",
        "--",
        ":(glob)specs/*.evaluator-pin.json",
        text=True,
    )
    if history.returncode != 0:
        raise ValueError("cannot inspect evaluator pin revision history")
    commit: str | None = None
    versions: list[tuple[str, str]] = []
    for line in history.stdout.splitlines():
        value = line.strip()
        if _GIT_OID_RE.fullmatch(value):
            commit = value
        elif commit and value.startswith("specs/") and value.endswith(".evaluator-pin.json"):
            versions.append((commit, value))
    pins: list[EvaluatorSubjectPin] = []
    for revision, path in versions:
        loaded = _git_run(repo_root, "show", f"{revision}:{path}")
        if loaded.returncode != 0:
            continue
        try:
            pins.append(
                EvaluatorSubjectPin.model_validate(json.loads(loaded.stdout.decode("utf-8")))
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            continue
    return pins


def _enforce_protocol_revision_identity(repo_root: Path, candidate: EvaluatorSubjectPin) -> None:
    candidate_identity = _pin_contract_identity(candidate)
    for existing in _historical_evaluator_pins(repo_root):
        if (
            existing.protocol_revision == candidate.protocol_revision
            and _pin_contract_identity(existing) != candidate_identity
        ):
            raise ValueError(
                "evaluator revision requires a new separately reviewed protocol revision"
            )


def build_evaluator_pin(
    repo_root: Path, *, protocol_revision: str = "holus-g2-external-acceptance/v2"
) -> EvaluatorSubjectPin:
    """Build a candidate pin from the current clean Git subject.

    This is read-only. A tracked artifact remains advisory. Only the separate
    supervisor-owned descriptor protocol can grant launch authority.
    """
    _validate_identifier("protocol_revision", protocol_revision)
    subject = _current_subject(repo_root)
    if not subject.clean or not subject.commit or not subject.tree:
        raise ValueError("cannot build evaluator pin from a dirty or unresolved Git subject")
    evaluator_blobs = {
        path: oid
        for path in EVALUATOR_PATHS
        if (oid := _git_oid(repo_root, f"{subject.commit}:{path}")) is not None
    }
    protocol_blob = _git_oid(repo_root, f"{subject.commit}:{G2_PROTOCOL_PIN_PATH}")
    corpus_blob = _git_oid(repo_root, f"{subject.commit}:{CANONICAL_EVALUATOR_CASES_PATH}")
    if set(evaluator_blobs) != set(EVALUATOR_PATHS) or protocol_blob is None or corpus_blob is None:
        raise ValueError(
            "evaluator pin requires the exact evaluator sources, protocol pin, and frozen corpus"
        )
    pin = EvaluatorSubjectPin(
        protocol_revision=protocol_revision,
        subject=subject.model_copy(update={"branch": None}),
        evaluator_blobs=evaluator_blobs,
        protocol_blob=protocol_blob,
        corpus_blob=corpus_blob,
    )
    _enforce_protocol_revision_identity(repo_root, pin)
    return pin


def load_evaluator_pin(
    repo_root: Path,
    pin_path: Path,
    *,
    approved_blob: str | None = None,
) -> EvaluatorSubjectPin:
    """Load a clean tracked pin for advisory compatibility checks only."""
    repo_root = repo_root.resolve()
    candidate = pin_path if pin_path.is_absolute() else repo_root / pin_path
    try:
        relative_path = Path(os.path.abspath(candidate)).relative_to(repo_root)
    except (OSError, ValueError) as exc:
        raise ValueError("evaluator pin path must stay inside the repository") from exc
    relative = relative_path.as_posix()
    if (
        ".." in relative_path.parts
        or relative_path.parent != Path("specs")
        or not relative_path.name.endswith(".evaluator-pin.json")
    ):
        raise ValueError("evaluator pin must be a tracked specs/*.evaluator-pin.json artifact")
    if approved_blob is not None:
        if not _GIT_OID_RE.fullmatch(approved_blob):
            raise ValueError("approved evaluator pin blob is invalid")
        head_blob = _git_oid(repo_root, f"HEAD:{relative}")
        if head_blob != approved_blob:
            raise ValueError("candidate evaluator pin differs from the approved configuration")
    try:
        payload = json.loads(_load_clean_tracked_pin_bytes(repo_root, relative).decode("utf-8"))
        pin = EvaluatorSubjectPin.model_validate(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"invalid evaluator pin: {exc}") from exc
    subject_tree = _git_oid(repo_root, f"{pin.subject.commit}^{{tree}}")
    if subject_tree != pin.subject.tree:
        raise ValueError("evaluator pin subject tree does not resolve")
    if _repository_identity(repo_root) != pin.subject.repository_id:
        raise ValueError("evaluator pin belongs to a different repository")
    for path, expected in (
        *pin.evaluator_blobs.items(),
        (pin.protocol_path, pin.protocol_blob),
        (pin.corpus_path, pin.corpus_blob),
    ):
        if _git_oid(repo_root, f"{pin.subject.commit}:{path}") != expected:
            raise ValueError(f"evaluator pin blob does not match subject: {path}")
    _enforce_protocol_revision_identity(repo_root, pin)
    return pin


def load_accepted_evaluator_pin(
    repo_root: Path,
    pin_path: Path,
    *,
    approved_blob: str,
) -> EvaluatorSubjectPin:
    """Load pin bytes supplied by the external acceptance launcher.

    Unlike :func:`load_evaluator_pin`, this authority never consults a
    candidate-tracked pin path or candidate pin history. The launcher has
    already authenticated the exact external acceptance record and passes a
    scratch copy of the accepted Git blob into its evaluator sandbox.
    """
    if not _GIT_OID_RE.fullmatch(approved_blob):
        raise ValueError("approved evaluator pin blob is invalid")
    try:
        raw = _read_regular_file_no_follow(pin_path)
    except (OSError, ValueError) as exc:
        raise ValueError("accepted evaluator pin bytes are absent") from exc
    if _git_blob_oid_for_bytes(repo_root, raw) != approved_blob:
        raise ValueError("accepted evaluator pin bytes do not match acceptance")
    try:
        pin = EvaluatorSubjectPin.model_validate(json.loads(raw.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"invalid accepted evaluator pin: {exc}") from exc
    if _repository_identity(repo_root) != pin.subject.repository_id:
        raise ValueError("accepted evaluator pin belongs to a different repository")
    if _git_oid(repo_root, f"{pin.subject.commit}^{{tree}}") != pin.subject.tree:
        raise ValueError("accepted evaluator pin subject tree does not resolve")
    for path, expected in (
        *pin.evaluator_blobs.items(),
        (pin.protocol_path, pin.protocol_blob),
        (pin.corpus_path, pin.corpus_blob),
    ):
        if _git_oid(repo_root, f"{pin.subject.commit}:{path}") != expected:
            raise ValueError(f"accepted evaluator pin blob does not match subject: {path}")
    return pin


def evaluator_pin_for_result(repo_root: Path, result: PilotRunResult) -> EvaluatorSubjectPin:
    """Derive a compatibility pin from an independently anchored G1 result.

    This fallback preserves the pre-G2 command shape. It never reads any
    candidate-reported digest; the commit/tree and blobs come from Git.
    """
    subject = result.subject
    if not subject.clean or not subject.commit or not subject.tree:
        raise ValueError("prior result lacks a clean immutable subject for evaluator pinning")
    evaluator_blobs = {
        path: oid
        for path in EVALUATOR_PATHS
        if (oid := _git_oid(repo_root, f"{subject.commit}:{path}")) is not None
    }
    protocol_blob = _git_oid(repo_root, f"{subject.commit}:{G2_PROTOCOL_PIN_PATH}")
    corpus_blob = _git_oid(repo_root, f"{subject.commit}:{CANONICAL_EVALUATOR_CASES_PATH}")
    if set(evaluator_blobs) != set(EVALUATOR_PATHS) or protocol_blob is None or corpus_blob is None:
        raise ValueError("prior result subject does not contain the exact evaluator contract")
    return EvaluatorSubjectPin(
        protocol_revision=SCHEMA_RESULT,
        subject=subject,
        evaluator_blobs=evaluator_blobs,
        protocol_blob=protocol_blob,
        corpus_blob=corpus_blob,
    )


def evaluator_preflight_blockers(
    repo_root: Path, pin: EvaluatorSubjectPin, cases_path: Path
) -> list[str]:
    blockers: list[str] = []
    actual = _current_subject(repo_root)
    if not actual.commit or not actual.tree:
        blockers.append("unresolvable_current_subject")
    if not actual.clean:
        blockers.append("dirty_current_subject")
    if actual.repository_id != pin.subject.repository_id:
        blockers.append("wrong_repository_subject")
    if not pin.subject.commit or not pin.subject.tree:
        blockers.append("unresolvable_pinned_subject")
    elif _git_oid(repo_root, f"{pin.subject.commit}^{{tree}}") != pin.subject.tree:
        blockers.append("wrong_pinned_tree_oid")
    if pin.subject.commit and actual.commit:
        ancestry = _git_run(
            repo_root, "merge-base", "--is-ancestor", pin.subject.commit, actual.commit
        )
        if ancestry.returncode != 0:
            blockers.append("stale_evaluator_pin_subject")
    try:
        cases_relative = cases_path.resolve(strict=True).relative_to(repo_root.resolve()).as_posix()
    except (OSError, ValueError):
        cases_relative = None
    if cases_relative != pin.corpus_path:
        blockers.append("changed_evaluator_corpus_path")

    for path, expected in (
        *pin.evaluator_blobs.items(),
        (pin.protocol_path, pin.protocol_blob),
        (pin.corpus_path, pin.corpus_blob),
    ):
        pinned_blob = (
            _git_oid(repo_root, f"{pin.subject.commit}:{path}") if pin.subject.commit else None
        )
        current_blob = _git_oid(repo_root, f"{actual.commit}:{path}") if actual.commit else None
        full_path = repo_root / path
        worktree_blob = (
            _git_blob_oid_for_bytes(repo_root, full_path.read_bytes())
            if full_path.is_file() and not full_path.is_symlink()
            else None
        )
        if pinned_blob != expected or current_blob != expected or worktree_blob != expected:
            code = (
                "changed_evaluator_corpus"
                if path == pin.corpus_path
                else "changed_evaluator_artifact"
            )
            blockers.append(f"{code}:{path}")
    return blockers


_EVALUATOR_BOOTSTRAP = r"""
import importlib
import sys
import types

package = types.ModuleType("codesight")
package.__path__ = [sys.argv.pop(1)]
package.__package__ = "codesight"
sys.modules["codesight"] = package
module = importlib.import_module("codesight.eval_pilot")
raise SystemExit(module.main())
"""


def _runtime_read_paths() -> list[Path]:
    executable = Path(sys.executable)
    candidates = {
        executable,
        executable.resolve(),
        Path(sys.prefix),
        Path(sys.base_prefix),
    }
    link = executable
    for _ in range(8):
        if not link.is_symlink():
            break
        target = Path(os.readlink(link))
        link = target if target.is_absolute() else link.parent / target
        candidates.add(link)
        candidates.add(link.parent)
    for key in ("stdlib", "platstdlib", "purelib", "platlib"):
        value = sysconfig.get_paths().get(key)
        if value:
            candidates.add(Path(value))
    if git_path := shutil.which("git"):
        candidates.update((Path(git_path).parent, Path(git_path).resolve().parent))
    for value in (
        "/System/Library",
        "/System/Cryptexes/OS",
        "/usr/bin",
        "/usr/lib",
        "/usr/libexec",
        "/usr/share/locale",
        "/bin",
        "/lib",
        "/lib64",
        "/etc/ssl",
        "/private/etc/ssl",
        "/private/etc/localtime",
        "/private/var/db/timezone",
        "/private/var/select/developer_dir",
        "/Library/Developer/CommandLineTools",
        "/nix/store",
    ):
        candidates.add(Path(value))
    existing_set: set[Path] = set()
    for path in candidates:
        try:
            if path.exists():
                existing_set.update((path, path.resolve()))
        except OSError:
            # An enclosing evaluator sandbox may intentionally hide optional
            # host runtime paths. Hidden paths are not needed by the child.
            continue
    existing = sorted(existing_set, key=lambda path: len(path.parts))
    roots: list[Path] = []
    for path in existing:
        if not any(path == root or path.is_relative_to(root) for root in roots):
            roots.append(path)
    return roots


def _sandboxed_evaluator_command(
    command: list[str],
    *,
    evaluator_snapshot: Path,
    candidate_snapshot: Path,
    scratch_root: Path,
) -> list[str]:
    snapshot_paths = [evaluator_snapshot, candidate_snapshot]
    readonly_paths = list(
        dict.fromkeys(
            [
                variant
                for path in [*snapshot_paths, *_runtime_read_paths()]
                for variant in (path, path.resolve())
            ]
        )
    )
    scratch_paths = list(dict.fromkeys((scratch_root, scratch_root.resolve())))
    read_paths = [*readonly_paths, *scratch_paths]
    executable_paths = {Path(sys.executable), Path(sys.executable).resolve()}
    for executable in (
        shutil.which("sandbox-exec"),
        shutil.which("bwrap"),
        shutil.which("ps"),
        shutil.which("git"),
        "/usr/bin/git",
        "/usr/bin/xcrun",
        "/Library/Developer/CommandLineTools/usr/bin/git",
    ):
        if not executable:
            continue
        try:
            path = Path(executable)
            if path.exists():
                executable_paths.update((path, path.resolve()))
        except OSError:
            continue
    if sys.platform == "darwin":
        executable = shutil.which("sandbox-exec")
        if executable is None:
            raise ValueError("trusted evaluator requires an OS-enforced read-only sandbox")
        metadata_paths = {Path("/")}
        for path in read_paths:
            metadata_paths.add(path)
            metadata_paths.update(path.parents)
        rules = [
            "(version 1)",
            "(deny default)",
            "(allow process-fork)",
            "(allow process-info*)",
            *(
                f"(allow process-exec* (literal {json.dumps(str(path))}))"
                for path in sorted(executable_paths, key=str)
            ),
            "(allow signal (target same-sandbox))",
            *(
                f"(allow file-read-metadata (literal {json.dumps(str(path))}))"
                for path in sorted(metadata_paths, key=str)
            ),
            *(
                f"(allow file-read* ({'literal' if path.is_file() else 'subpath'} "
                f"{json.dumps(str(path))}))"
                for path in read_paths
            ),
            "(allow file-map-executable)",
            *(f"(allow file-write* (subpath {json.dumps(str(path))}))" for path in scratch_paths),
            '(allow file-read-data (literal "/"))',
            '(allow file-read* (literal "/dev/null"))',
            '(allow file-write-data (literal "/dev/null"))',
            '(allow file-ioctl (literal "/dev/null"))',
            '(allow file-read* (literal "/dev/random"))',
            '(allow file-read* (literal "/dev/urandom"))',
            "(allow sysctl-read)",
            "(allow mach-lookup)",
        ]
        profile = scratch_root / "evaluator.sb"
        profile.write_text("\n".join(rules) + "\n", encoding="utf-8")
        return [executable, "-f", str(profile), *command]
    if sys.platform.startswith("linux"):
        executable = shutil.which("bwrap")
        if executable is None:
            raise ValueError("trusted evaluator requires an OS-enforced read-only sandbox")
        sandbox = [executable, "--die-with-parent", "--unshare-all", "--new-session"]
        for path in readonly_paths:
            sandbox.extend(("--ro-bind", str(path), str(path)))
        sandbox.extend(
            (
                "--bind",
                str(scratch_root),
                str(scratch_root),
                "--dev",
                "/dev",
                "--proc",
                "/proc",
                "--chdir",
                str(evaluator_snapshot),
            )
        )
        return [*sandbox, *command]
    raise ValueError("trusted evaluator requires an OS-enforced read-only sandbox")


def run_pinned_pilot(
    repo_root: Path,
    *,
    pin: EvaluatorSubjectPin,
    cases_path: Path,
    lineage: CandidateLineage,
    allow_egress: bool = False,
    allow_semantic: bool = False,
) -> PilotRunResult:
    if allow_egress or allow_semantic:
        raise ValueError("trusted evaluator supports only local non-semantic frozen cases")
    blockers = evaluator_preflight_blockers(repo_root, pin, cases_path)
    if blockers:
        raise ValueError("trusted evaluator preflight blocked: " + ", ".join(blockers))
    actual = _current_subject(repo_root)
    if not actual.commit:
        raise ValueError("trusted evaluator requires a committed candidate subject")

    with tempfile.TemporaryDirectory(prefix="holus-trusted-eval-") as temporary:
        root = Path(temporary)
        readonly_root = root / "snapshots"
        readonly_root.mkdir()
        scratch_root = root / "scratch"
        scratch_root.mkdir()
        candidate_snapshot = readonly_root / "candidate"
        evaluator_snapshot = readonly_root / "evaluator"
        for snapshot, commit, label in (
            (candidate_snapshot, actual.commit, "candidate"),
            (evaluator_snapshot, pin.subject.commit, "evaluator"),
        ):
            clone = subprocess.run(
                [
                    "git",
                    "clone",
                    "--quiet",
                    "--no-local",
                    "--no-hardlinks",
                    "--no-checkout",
                    str(repo_root),
                    str(snapshot),
                ],
                capture_output=True,
                text=True,
                check=False,
                env=_canonical_git_env(),
            )
            checkout = (
                subprocess.run(
                    [
                        "git",
                        "--no-replace-objects",
                        "-C",
                        str(snapshot),
                        "checkout",
                        "--quiet",
                        "--detach",
                        commit,
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                    env=_canonical_git_env(),
                )
                if clone.returncode == 0
                else None
            )
            if clone.returncode != 0 or checkout is None or checkout.returncode != 0:
                failed = clone if clone.returncode != 0 else checkout
                detail = failed.stderr.strip() if failed is not None else "unknown Git failure"
                raise ValueError(f"could not create isolated {label} snapshot: {detail}")

        for snapshot in (candidate_snapshot, evaluator_snapshot):
            subprocess.run(
                [
                    "git",
                    "--no-replace-objects",
                    "-C",
                    str(snapshot),
                    "remote",
                    "remove",
                    "origin",
                ],
                capture_output=True,
                check=False,
                env=_canonical_git_env(),
            )
        if actual.repository_id != "local-no-remote":
            subprocess.run(
                [
                    "git",
                    "--no-replace-objects",
                    "-C",
                    str(candidate_snapshot),
                    "remote",
                    "add",
                    "origin",
                    actual.repository_id,
                ],
                capture_output=True,
                check=True,
                env=_canonical_git_env(),
            )

        command = [
            sys.executable,
            "-I",
            "-B",
            "-c",
            _EVALUATOR_BOOTSTRAP,
            str(evaluator_snapshot / "src" / "codesight"),
            "run",
            "--repo-root",
            str(candidate_snapshot),
            "--cases",
            str(candidate_snapshot / pin.corpus_path),
            "--candidate-id",
            lineage.candidate_id,
            "--workflow",
            lineage.workflow,
            "--tool",
            lineage.tool,
        ]
        if lineage.model:
            command.extend(("--model", lineage.model))
        if allow_egress:
            command.append("--allow-egress")
        if allow_semantic:
            command.append("--allow-semantic")
        sandbox_home = scratch_root / "home"
        sandbox_home.mkdir()
        discovered_git = shutil.which("git")
        trusted_git = Path(discovered_git).resolve() if discovered_git else None
        trusted_path = (
            f"{trusted_git.parent}{os.pathsep}{os.defpath}"
            if trusted_git is not None
            else os.defpath
        )
        env = {
            **{
                key: value
                for key, value in _canonical_git_env().items()
                if key.startswith("GIT_")
            },
            "PATH": trusted_path,
            "HOME": str(sandbox_home),
            "LANG": "C",
            "TMPDIR": str(scratch_root),
            "PYTHONPATH": str(evaluator_snapshot / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "HOLUS_PINNED_EVALUATOR_DIGEST": _sha256_hex(
                json.dumps(pin.evaluator_blobs, sort_keys=True).encode("utf-8")
            ),
            "HOLUS_PINNED_COMPARATOR_DIGEST": _sha256_hex(
                pin.evaluator_blobs["src/codesight/eval_pilot.py"].encode("ascii")
            ),
            "HOLUS_EVALUATOR_SNAPSHOT": str(evaluator_snapshot),
            "HOLUS_CANDIDATE_SNAPSHOT": str(candidate_snapshot),
            "HOLUS_EVALUATOR_SCRATCH": str(scratch_root),
        }
        command = _sandboxed_evaluator_command(
            command,
            evaluator_snapshot=evaluator_snapshot,
            candidate_snapshot=candidate_snapshot,
            scratch_root=scratch_root,
        )
        completed = _run_bounded_process(
            command,
            cwd=evaluator_snapshot,
            env=env,
            input_text=None,
            timeout=120,
            output_dir=scratch_root,
            cpu_seconds=110,
            memory_bytes=1_610_612_736,
            process_count=1024,
            max_output_bytes=1_048_576,
        )
        if completed.returncode not in {0, 1} or completed.timed_out or completed.output_truncated:
            detail = completed.stderr.strip() or f"returncode={completed.returncode}"
            raise ValueError(
                "isolated trusted evaluator failed before producing a result: " + detail
            )
        try:
            payload, _ = json.JSONDecoder().raw_decode(completed.stdout.lstrip())
            result = PilotRunResult.model_validate(payload)
            _validate_result(result)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError("isolated trusted evaluator returned an invalid result") from exc
        postflight = evaluator_pin_blockers(repo_root, pin, result)
        if postflight:
            raise ValueError("trusted evaluator postflight blocked: " + ", ".join(postflight))
        return result


def evaluator_pin_blockers(
    repo_root: Path, pin: EvaluatorSubjectPin, result: PilotRunResult
) -> list[str]:
    """Prove that result bytes match the already externally accepted pin."""
    blockers = evaluator_preflight_blockers(repo_root, pin, repo_root / pin.corpus_path)
    actual = _current_subject(repo_root)
    if not actual.commit or not actual.tree:
        blockers.append("unresolvable_current_subject")
    if result.subject.repository_id != pin.subject.repository_id:
        blockers.append("result_repository_subject_mismatch")
    if result.subject.commit != actual.commit or result.subject.tree != actual.tree:
        blockers.append("result_subject_not_current")
    if not result.subject.clean or result.lineage.repo_dirty:
        blockers.append("dirty_result_subject")
    if result.cases_file != pin.corpus_path:
        blockers.append("changed_evaluator_corpus_path")
    corpus = repo_root / pin.corpus_path
    if not corpus.is_file() or _sha256_hex(corpus.read_bytes()) != result.cases_file_hash:
        blockers.append("changed_evaluator_corpus_hash")
    return blockers


def execute_trusted_evaluation(
    repo_root: Path,
    *,
    evaluator_pin_path: Path | None = None,
    accepted_pin_path: Path | None = None,
    cases_path: Path,
    compare_path: Path | None,
    candidate_id: str,
    workflow: str,
    tool: str,
    model: str | None = None,
    allow_egress: bool = False,
    allow_semantic: bool = False,
    evaluator_subject: str | None = None,
    approved_pin_blob: str | None = None,
) -> PreparedTrustedEvaluation:
    repo_root = repo_root.resolve()
    for label, value in (
        ("candidate_id", candidate_id),
        ("workflow", workflow),
        ("tool", tool),
        ("model", model),
    ):
        if value is not None:
            _validate_identifier(label, value)
    if allow_egress or allow_semantic:
        raise ValueError("trusted evaluator supports only local non-semantic frozen cases")

    if accepted_pin_path is None:
        raise ValueError("trusted evaluation requires an external acceptance record pin")
    if approved_pin_blob is None:
        raise ValueError("trusted evaluation requires the accepted evaluator pin blob")
    if evaluator_subject is None:
        raise ValueError("trusted evaluation worker requires a pinned evaluator subject")
    evaluator_pin = load_accepted_evaluator_pin(
        repo_root, accepted_pin_path, approved_blob=approved_pin_blob
    )
    pin_source: Literal["explicit", "derived"] = "explicit"
    if evaluator_pin.subject.commit != evaluator_subject:
        raise ValueError("worker evaluator subject does not match the accepted pin")

    baseline_result = None
    baseline_anchor = None
    if compare_path is not None:
        validated_compare = validate_output_path(
            repo_root, compare_path, allowed_repo_root=RESULTS_ROOT
        )
        baseline_result, baseline_anchor = load_anchored_baseline(repo_root, validated_compare)
        if baseline_anchor is None:
            raise ValueError("comparison result is not independently anchored")

    current = _current_subject(repo_root)
    lineage = CandidateLineage(
        candidate_id=candidate_id,
        repo_commit=current.commit,
        workflow=workflow,
        tool=tool,
        model=model,
    )
    result = run_pinned_pilot(
        repo_root,
        pin=evaluator_pin,
        cases_path=cases_path,
        lineage=lineage,
        allow_egress=allow_egress,
        allow_semantic=allow_semantic,
    )
    return PreparedTrustedEvaluation(
        result=result,
        evaluator_pin=evaluator_pin,
        evaluator_pin_source=pin_source,
        baseline_result=baseline_result,
        baseline_anchor=baseline_anchor,
    )


def _tree_digest(repo_root: Path, prefixes: tuple[str, ...]) -> str:
    """Digest candidate/evaluator bytes without exporting paths or content."""
    digest = hashlib.sha256()
    for prefix in prefixes:
        base = repo_root / prefix
        if not base.exists() or base.is_symlink():
            continue
        files = (
            [base]
            if base.is_file()
            else sorted(p for p in base.rglob("*") if p.is_file() and not p.is_symlink())
        )
        for path in files:
            digest.update(str(path.relative_to(repo_root)).encode())
            digest.update(path.read_bytes())
    return "sha256:" + digest.hexdigest()


_SAFE_GIT_CONFIG = (
    ("core.fsmonitor", "false"),
    ("core.hooksPath", os.devnull),
    ("core.sshCommand", "false"),
    ("credential.helper", ""),
    ("diff.external", ""),
    ("interactive.diffFilter", ""),
    ("pager.config", "false"),
    ("pager.diff", "false"),
    ("pager.log", "false"),
    ("pager.show", "false"),
)


def _canonical_git_env() -> dict[str, str]:
    """Disable host and candidate executable Git configuration."""
    env = {"PATH": os.defpath, "LANG": "C", "LC_ALL": "C"}
    env.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_COUNT": str(len(_SAFE_GIT_CONFIG)),
            "GIT_GRAFT_FILE": os.devnull,
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    for index, (key, value) in enumerate(_SAFE_GIT_CONFIG):
        env[f"GIT_CONFIG_KEY_{index}"] = key
        env[f"GIT_CONFIG_VALUE_{index}"] = value
    return env


def _git_run(
    repo_root: Path,
    *args: str,
    text: bool = False,
    input: bytes | None = None,
) -> subprocess.CompletedProcess:
    command = ["git", "--no-replace-objects", "-C", str(repo_root), *args]
    env = _canonical_git_env()
    try:
        expected_root = repo_root.resolve(strict=True)
    except OSError:
        expected_root = None
    probe = subprocess.run(
        ["git", "--no-replace-objects", "-C", str(repo_root), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    try:
        actual_root = Path(probe.stdout.strip()).resolve(strict=True)
    except OSError:
        actual_root = None
    if probe.returncode != 0 or expected_root is None or actual_root != expected_root:
        empty = "" if text else b""
        error = "requested path is not the resolved Git worktree root"
        return subprocess.CompletedProcess(command, 128, empty, error if text else error.encode())
    return subprocess.run(
        command,
        input=input,
        capture_output=True,
        text=text,
        check=False,
        env=env,
    )


def _git_dirty(repo_root: Path) -> bool:
    result = _git_run(repo_root, "status", "--porcelain", text=True)
    return result.returncode != 0 or bool(result.stdout.strip())


_GIT_OID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_SCP_REMOTE_RE = re.compile(r"^(?:[^@/:\s]+@)?([^/@:#?\s]+):(.+)$")
_WINDOWS_DRIVE_REMOTE_RE = re.compile(r"^[A-Za-z]:")
_SAFE_REMOTE_SCHEMES = frozenset({"git", "http", "https", "ssh", "git+ssh"})


def _machine_local_host(host: str) -> bool:
    normalized = host.lower().rstrip(".")
    if normalized in {"localhost", "localhost.localdomain"} or normalized.endswith(
        (".local", ".localhost", ".home.arpa", ".internal")
    ):
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return "." not in normalized
    return not address.is_global


def _remote_component_contains_secret(value: str) -> bool:
    decoded = value
    for _ in range(3):
        if _SECRET_LIKE.search(decoded):
            return True
        unescaped = unquote(decoded)
        if unescaped == decoded:
            return False
        decoded = unescaped
    return bool(_SECRET_LIKE.search(decoded))


def _canonical_remote_identity(origin: str) -> str | None:
    if (
        not origin
        or len(origin) > 2048
        or any(char.isspace() for char in origin)
        or "\\" in origin
        or _WINDOWS_DRIVE_REMOTE_RE.match(origin)
    ):
        return None
    if "://" not in origin:
        match = _SCP_REMOTE_RE.fullmatch(origin)
        if not match:
            return None
        host, path = match.groups()
        if (
            _machine_local_host(host)
            or not path.strip("/")
            or "?" in path
            or "#" in path
            or _remote_component_contains_secret(host)
            or _remote_component_contains_secret(path)
        ):
            return None
        return f"ssh://{host.lower()}/{path.lstrip('/').rstrip('/')}"

    try:
        parsed = urlsplit(origin)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    scheme = parsed.scheme.lower()
    if (
        scheme not in _SAFE_REMOTE_SCHEMES
        or not host
        or _machine_local_host(host)
        or _remote_component_contains_secret(host)
    ):
        return None
    path = parsed.path.rstrip("/")
    if not path or _remote_component_contains_secret(path):
        return None
    host = host.lower()
    if ":" in host:
        host = f"[{host}]"
    default_ports = {"http": 80, "https": 443, "ssh": 22, "git+ssh": 22, "git": 9418}
    netloc = host if port is None or port == default_ports[scheme] else f"{host}:{port}"
    return urlunsplit((scheme, netloc, path, "", ""))


def _repository_identity(repo_root: Path) -> str:
    result = _git_run(repo_root, "remote", "get-url", "origin", text=True)
    if result.returncode != 0:
        return "local-no-remote"
    return _canonical_remote_identity(result.stdout.strip()) or "local-no-remote"


def _git_oid(repo_root: Path, rev: str) -> str | None:
    """Resolve ``rev`` to a full Git object id, or ``None`` if unresolvable."""
    result = _git_run(repo_root, "rev-parse", "--verify", "--quiet", rev, text=True)
    value = result.stdout.strip()
    return value if result.returncode == 0 and _GIT_OID_RE.fullmatch(value) else None


def _current_branch(repo_root: Path) -> str | None:
    """The current branch name, recorded as an annotation only - never an
    identity or applicability input (spec 021)."""
    result = _git_run(repo_root, "symbolic-ref", "--quiet", "--short", "HEAD", text=True)
    branch = result.stdout.strip()
    return (
        branch
        if result.returncode == 0
        and _SAFE_IDENTIFIER.fullmatch(branch)
        and not _SECRET_LIKE.search(branch)
        else None
    )


def _current_subject(repo_root: Path) -> EvaluationSubject:
    """The immutable Git subject this run is being produced against."""
    commit = _git_oid(repo_root, "HEAD")
    tree = _git_oid(repo_root, "HEAD^{tree}") if commit else None
    return EvaluationSubject(
        repository_id=_repository_identity(repo_root),
        commit=commit,
        tree=tree,
        clean=bool(commit and tree and not _git_dirty(repo_root)),
        branch=_current_branch(repo_root),
    )


def _git_blob_oid_for_bytes(repo_root: Path, content: bytes) -> str | None:
    result = _git_run(repo_root, "hash-object", "--stdin", input=content)
    try:
        value = result.stdout.decode("ascii").strip()
    except UnicodeDecodeError:
        return None
    return value if result.returncode == 0 and _GIT_OID_RE.fullmatch(value) else None


def _cases_match_subject(
    repo_root: Path,
    cases_path: Path,
    corpus_bytes: bytes,
    subject: EvaluationSubject,
) -> bool:
    if not subject.commit:
        return False
    try:
        relative = cases_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except (OSError, ValueError):
        return False
    evaluated_blob = _git_oid(repo_root, f"{subject.commit}:{relative}")
    return bool(
        evaluated_blob and _git_blob_oid_for_bytes(repo_root, corpus_bytes) == evaluated_blob
    )


def run_pilot(
    repo_root: Path,
    *,
    cases_path: Path | None = None,
    lineage: CandidateLineage,
    allow_egress: bool = False,
    allow_semantic: bool = False,
) -> PilotRunResult:
    """Grade every frozen case against the current repository state.

    Read-only w.r.t. the case file (never opened for writing) and w.r.t.
    this repository's tracked source - the ``consistency``-backed graders
    operate on synthetic ``tempfile.TemporaryDirectory`` repos, never this
    worktree's own ``.holusight/`` cache.
    """
    cases_path = cases_path or DEFAULT_CASES_PATH
    corpus_bytes = cases_path.read_bytes()
    file_hash = _sha256_hex(corpus_bytes)
    cases = _parse_cases(cases_path, corpus_bytes)
    corpus_trust = (
        "canonical" if _is_canonical_cases(cases_path, repo_root) else "untrusted_advisory"
    )
    subject = _current_subject(repo_root)
    cases_bound_to_subject = _cases_match_subject(repo_root, cases_path, corpus_bytes, subject)
    lineage.repo_dirty = not subject.clean
    lineage.evaluator_digest = os.environ.get("HOLUS_PINNED_EVALUATOR_DIGEST") or _tree_digest(
        repo_root, EVALUATOR_PATHS
    )
    lineage.candidate_digest = _tree_digest(repo_root, ("src/codesight",))
    lineage.comparator_digest = os.environ.get("HOLUS_PINNED_COMPARATOR_DIGEST") or _tree_digest(
        repo_root, ("src/codesight/eval_pilot.py",)
    )

    ctx = RunContext(
        repo_root=str(repo_root), allow_egress=allow_egress, allow_semantic=allow_semantic
    )

    grades: list[CaseGrade] = []
    for case in cases:
        if case.get("requires_semantic") and not allow_semantic:
            grades.append(
                CaseGrade(
                    case_id=case["case_id"],
                    family=case["family"],
                    kind=case["kind"],
                    verdict="error",
                    detail="case requires semantic provider; --allow-semantic not set",
                    provenance_origin=case["provenance"]["origin"],
                )
            )
            continue
        grader = GRADERS[case["grader"]]
        try:
            grades.append(grader(case, repo_root, ctx))
        except Exception as exc:  # defensive: a broken fixture is "error", not a crash
            grades.append(
                CaseGrade(
                    case_id=case["case_id"],
                    family=case["family"],
                    kind=case["kind"],
                    verdict="error",
                    detail=f"{type(exc).__name__}: {exc}",
                    provenance_origin=case["provenance"]["origin"],
                )
            )

    counts = _recomputed_counts(grades)
    status_quo_control = "not_applicable"
    if counts["comparative_total"]:
        status_quo_control = (
            "included"
            if counts["comparative_total"] == counts["comparative_with_status_quo_verdict"]
            else "invalid"
        )

    final_subject = _current_subject(repo_root)
    subject_stable = (
        subject.repository_id == final_subject.repository_id
        and subject.commit == final_subject.commit
        and subject.tree == final_subject.tree
        and subject.clean == final_subject.clean
    )
    if not subject_stable or not final_subject.clean or not cases_bound_to_subject:
        subject = subject.model_copy(update={"clean": False})
    lineage.repo_dirty = not subject.clean

    result = PilotRunResult(
        run_id=f"eval-pilot-{lineage.candidate_id}-{_now()}",
        cases_file=_public_cases_path(repo_root, cases_path),
        cases_file_hash=file_hash,
        lineage=lineage,
        subject=subject,
        egress_allowed=allow_egress,
        semantic_allowed=allow_semantic,
        grades=grades,
        counts=counts,
        status_quo_control=status_quo_control,
        corpus_trust=corpus_trust,
    )
    result.result_digest = canonical_result_digest(result)
    return result


# ---------------------------------------------------------------------------
# Fleet v1.2 aggregate export (content-free - counts/rates only)
# ---------------------------------------------------------------------------


def build_pilot_aggregate_scorecard(
    result: PilotRunResult,
    *,
    repo: str,
    repo_commit: str,
) -> dict:
    """Shape one :class:`PilotRunResult` into a content-free
    ``fleet.eval_scorecard.v1.2``-shaped aggregate: counts and rates only -
    no case questions, no excerpts, no file paths beyond this repo's own
    identity. Mirrors ``fleet_scorecard.build_eval_scorecard``'s honesty
    conventions (see that module's docstring) for a second, independent
    domain evaluator."""
    total = result.counts["total"] or 1  # guard divide-by-zero; total is always >=1 in practice
    pass_rate = result.counts["passed"] / total
    no_regressions = result.counts["failed"] == 0 and result.counts["errored"] == 0
    controls_complete = (
        result.counts["comparative_total"] == result.counts["comparative_with_status_quo_verdict"]
    )
    subject_commit = result.subject.commit or "unknown"
    if repo_commit != subject_commit:
        raise ValueError("repo_commit does not match the evaluation subject")
    promotion_relevant = (
        result.corpus_trust == "canonical"
        and result.subject.clean
        and result.subject.commit is not None
        and result.subject.tree is not None
        and not result.lineage.repo_dirty
    )
    gate_decision = (
        "pass"
        if no_regressions and controls_complete and promotion_relevant
        else ("hold" if not promotion_relevant else "fail")
    )
    hidden_status = "pass" if gate_decision == "pass" else "fail"

    result_payload = result.model_dump(mode="json")
    result_hash = _sha256_hex(json.dumps(result_payload, sort_keys=True).encode("utf-8"))
    input_hash = _sha256_hex(f"{result.cases_file_hash}:{subject_commit}".encode("utf-8"))

    return {
        "schema": SCHEMA_PILOT_SCORECARD,
        "repo": repo,
        "scorecard_id": f"sc-{result.run_id}",
        "trace_id": f"trace-{result.run_id}",
        "rubric_id": "holusight-eval-pilot-v1",
        "scores": {
            "cases_total": result.counts["total"],
            "cases_passed": result.counts["passed"],
            "cases_failed": result.counts["failed"],
            "cases_errored": result.counts["errored"],
            "pass_rate": round(pass_rate, 4),
            "comparative_cases_total": result.counts["comparative_total"],
            "status_quo_control": result.status_quo_control,
            "corpus_trust": result.corpus_trust,
        },
        "gate_decision": gate_decision,
        "input_hash": input_hash,
        "fixture_set_hash": result.cases_file_hash,
        "result_hash": result_hash,
        "evaluator_version": "codesight-eval-pilot/1",
        "repo_commit": subject_commit,
        "environment": {
            "egress_allowed": result.egress_allowed,
            "semantic_allowed": result.semantic_allowed,
        },
        "cross_project_metrics": {
            "hidden_correctness": {
                "status": hidden_status,
                "source": "domain_evaluator",
                "detail": (
                    f"{result.counts['passed']}/{result.counts['total']} frozen eval-pilot "
                    "cases passed; advisory only, no autonomous promotion"
                ),
            },
            "time_to_correct_result_seconds": None,
            "human_correction_burden": {"note": "not tracked by this pilot"},
            "regressions": result.counts["failed"],
            "total_cost_usd": 0.0,
            "handoff_loss": {"occurred": False},
            "fallbacks": 0,
            "operational_failures": result.counts["errored"],
        },
        "diagnostics": {"completion": True, "promotion_relevant": promotion_relevant},
        "artifacts": {},
        "provenance": {
            "fleet_contract_repo": FLEET_CONTRACT_REPO,
            "fleet_contract_commit": FLEET_CONTRACT_COMMIT,
            "fleet_contract_pr": FLEET_CONTRACT_PR,
        },
    }


def pilot_domain_result_summary(result: PilotRunResult) -> dict:
    """The minimal dict ``run_repo_eval.py``'s ``parse_domain_result()``
    expects as an entrypoint command's last stdout line - see
    ``fleet_scorecard.domain_result_summary`` for the landed precedent this
    mirrors. Not currently wired as ``agentic/manifest.yaml``'s
    ``eval_entrypoint`` (still ``just fleet-smoke``, unchanged)."""
    status = "pass" if result.counts["failed"] == 0 and result.counts["errored"] == 0 else "fail"
    return {
        "hidden_correctness": {
            "status": status,
            "source": "domain_evaluator",
            "detail": (
                f"eval-pilot: {result.counts['passed']}/{result.counts['total']} "
                "frozen cases passed (advisory only)"
            ),
        },
        "scores": {
            "cases_total": result.counts["total"],
            "cases_passed": result.counts["passed"],
            "cases_failed": result.counts["failed"],
            "cases_errored": result.counts["errored"],
        },
        "human_correction_burden": {},
        "regressions": result.counts["failed"],
        "total_cost_usd": 0.0,
        "handoff_loss": {"occurred": False},
    }


# ---------------------------------------------------------------------------
# CLI: `python -m codesight.eval_pilot run`
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(prog="python -m codesight.eval_pilot")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run the frozen eval-pilot case corpus")
    run_p.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    run_p.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    run_p.add_argument("--output", type=Path, default=None)
    run_p.add_argument("--candidate-id", default="current-worktree")
    run_p.add_argument("--workflow", default="manual")
    run_p.add_argument("--tool", default="eval_pilot-cli")
    run_p.add_argument("--model", default=None)
    run_p.add_argument("--allow-egress", action="store_true")
    run_p.add_argument("--allow-semantic", action="store_true")
    run_p.add_argument(
        "--scorecard",
        action="store_true",
        help="Also print the Fleet aggregate scorecard preview",
    )

    trusted_p = sub.add_parser("trusted-evaluation-worker", help=argparse.SUPPRESS)
    trusted_p.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    trusted_p.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    trusted_p.add_argument("--accepted-pin", type=Path, required=True)
    trusted_p.add_argument("--approved-pin-blob", required=True)
    trusted_p.add_argument("--evaluator-subject", required=True)
    trusted_p.add_argument("--compare-result", type=Path, default=None)
    trusted_p.add_argument("--candidate-id", default="current-worktree")
    trusted_p.add_argument("--workflow", default="manual")
    trusted_p.add_argument("--tool", default="eval-pilot-worker")
    trusted_p.add_argument("--model", default=None)

    args = parser.parse_args(argv)
    if args.command == "trusted-evaluation-worker":
        repo_root = args.repo_root.resolve()
        try:
            artifacts = execute_trusted_evaluation(
                repo_root,
                accepted_pin_path=args.accepted_pin,
                cases_path=args.cases,
                compare_path=args.compare_result,
                candidate_id=args.candidate_id,
                workflow=args.workflow,
                tool=args.tool,
                model=args.model,
                evaluator_subject=args.evaluator_subject,
                approved_pin_blob=args.approved_pin_blob,
            )
            progress = _evaluate_progress(
                artifacts.result,
                artifacts.baseline_result,
                trusted_anchor=artifacts.baseline_anchor,
                repo_root=repo_root,
                evaluator_pin=artifacts.evaluator_pin,
            )
            if progress["outcome"] != "invalid_comparison":
                progress["comparison"]["classification"] = "advisory"
            payload = {
                "schema_version": SCHEMA_PREPARED_EVALUATION,
                "result": artifacts.result.model_dump(mode="json"),
                "evaluator_pin": artifacts.evaluator_pin.model_dump(mode="json"),
                "evaluator_pin_source": artifacts.evaluator_pin_source,
                "baseline_result": (
                    artifacts.baseline_result.model_dump(mode="json")
                    if artifacts.baseline_result is not None
                    else None
                ),
                "baseline_anchor": (
                    artifacts.baseline_anchor.model_dump(mode="json")
                    if artifacts.baseline_anchor is not None
                    else None
                ),
                "progress": progress,
            }
        except (OSError, ValueError, json.JSONDecodeError, UnsafeStoragePath) as exc:
            print(f"trusted evaluation rejected: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(payload, indent=2, sort_keys=True))
        return (
            0 if artifacts.result.counts.failed == 0 and artifacts.result.counts.errored == 0 else 1
        )
    if args.command != "run":
        parser.print_help(sys.stderr)
        return 2

    repo_root = args.repo_root.resolve()
    commit = _current_subject(repo_root).commit

    _validate_identifier("candidate_id", args.candidate_id)
    lineage = CandidateLineage(
        candidate_id=args.candidate_id,
        repo_commit=commit,
        workflow=args.workflow,
        tool=args.tool,
        model=args.model,
    )

    result = run_pilot(
        repo_root,
        cases_path=args.cases,
        lineage=lineage,
        allow_egress=args.allow_egress,
        allow_semantic=args.allow_semantic,
    )

    payload = result.model_dump(mode="json")
    try:
        payload["cases_file"] = str(args.cases.resolve().relative_to(repo_root))
    except (ValueError, OSError):
        payload["cases_file"] = "external-corpus"
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        try:
            output = safe_atomic_write(
                repo_root,
                args.output,
                (text + "\n").encode("utf-8"),
                allowed_repo_root=RESULTS_ROOT,
            )
        except UnsafeStoragePath as exc:
            print(f"output rejected: {exc}", file=sys.stderr)
            return 2
        label = (
            str(output.relative_to(repo_root))
            if output.is_relative_to(repo_root)
            else "external result"
        )
        print(f"Wrote {label}", file=sys.stderr)
    else:
        print(text)

    if args.scorecard:
        scorecard = build_pilot_aggregate_scorecard(
            result, repo="holusight", repo_commit=commit or "unknown"
        )
        print(json.dumps(scorecard, indent=2, sort_keys=True))

    summary = pilot_domain_result_summary(result)
    print(json.dumps(summary, sort_keys=True))

    return 0 if summary["hidden_correctness"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
