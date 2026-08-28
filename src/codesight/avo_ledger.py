"""Executable AVO ledger/checkpoint validation (remediation slice).

Validates canonical ledger and checkpoint documents against the published schemas
with deterministic experiment-ID allocation, duplicate prevention, crash retention,
required per-trial contract fields, matched control, protected gates, lineage parent,
decision informed, and Git-only checkpoint acceptance rules.

This module does not run trials, touch G2, bind AQ-R24 identities, enforce resource
controls, or modify leakage or purpose schemas.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

SCHEMA_LEDGER = "holusight-avo-ledger/v1"
SCHEMA_CHECKPOINT = "holusight-avo-checkpoint/v1"
CAMPAIGN_ID = "holusight-avo-v1"

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_EXPERIMENT_ID = re.compile(r"^[0-9]{4}$")
_LANE_ID = re.compile(r"^[a-z0-9-]+$")
_BRANCH = re.compile(r"^fm/holusight-avo-[a-z0-9-]+$")
_GIT_OID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_FORBIDDEN_KEYS = frozenset(
    {"prompt", "snippet", "api_key", "token", "telemetry", "path_absolute"}
)
_GENESIS_PREV = "sha256:" + ("0" * 64)

MANIFEST_RELATIVE = Path("docs/avo/trial-manifest.v1.json")


class AvoLedgerError(ValueError):
    """Closed failure for AVO ledger/checkpoint validation."""


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


def sha256_digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _require_sha256(value: str) -> str:
    if not _SHA256.fullmatch(value):
        raise ValueError("expected sha256:<64 lowercase hex>")
    return value


def derive_trial_seed(experiment_id: str, global_seed: int) -> int:
    """Derive the manifest-frozen per-trial seed."""
    if not _EXPERIMENT_ID.fullmatch(experiment_id):
        raise AvoLedgerError(f"experiment_id must be four digits: {experiment_id}")
    digest = hashlib.sha256(f"{experiment_id}:{global_seed}".encode()).hexdigest()[:8]
    return int(digest, 16)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def ledger_entry_line_sha256(entry: dict[str, Any]) -> str:
    """Hash the canonical JSON representation of one ledger entry (no trailing newline)."""
    return sha256_digest(canonical_json_bytes(entry))


def ledger_entry_sha256_from_line(line: str) -> str:
    """Hash the canonical JSON for one ledger JSONL line."""
    return ledger_entry_line_sha256(json.loads(line.strip()))


# ---------------------------------------------------------------------------
# Manifest context (read-only; does not modify purpose/resource/leakage schemas)
# ---------------------------------------------------------------------------


class ExperimentIdRange(_Closed):
    start: str
    end: str

    @field_validator("start", "end")
    @classmethod
    def validate_experiment_id(cls, value: str) -> str:
        if not _EXPERIMENT_ID.fullmatch(value):
            raise ValueError("experiment_id range bounds must be four digits")
        return value


class LaneRegistration(_Closed):
    lane_id: str
    branch: str
    host: Literal["laptop", "mini"]
    experiment_id_range: ExperimentIdRange


class CheckpointPolicy(_Closed):
    checkpoint_schema: Literal["holusight-avo-checkpoint/v1"] = Field(alias="schema")
    interval_valid_trials: Annotated[int, Field(ge=1)]
    branch_name_pattern: str
    max_checkpoint_bytes: Annotated[int, Field(ge=1)]

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class DeterministicSeeds(_Closed):
    global_seed: int
    derivation: Literal["sha256(experiment_id + global_seed)[:8] as uint32"]
    replay_required: Literal[True]


class AvoManifestContext(_Closed):
    """Minimal manifest view for ledger/checkpoint validation."""

    model_config = ConfigDict(extra="ignore")

    schema_version: Literal["holusight-avo-trial-manifest/v1"]
    campaign_id: Literal["holusight-avo-v1"]
    manifest_sha256: str
    deterministic_seeds: DeterministicSeeds
    checkpoint_policy: CheckpointPolicy
    protected_gates: list[str]
    lane_registry: list[LaneRegistration]

    @field_validator("manifest_sha256")
    @classmethod
    def validate_manifest_sha256(cls, value: str) -> str:
        return _require_sha256(value)

    @field_validator("protected_gates")
    @classmethod
    def validate_protected_gates(cls, value: list[str]) -> list[str]:
        if not value or len(set(value)) != len(value):
            raise ValueError("protected_gates must be a non-empty unique list")
        return value

    @field_validator("lane_registry")
    @classmethod
    def validate_lane_registry(cls, value: list[LaneRegistration]) -> list[LaneRegistration]:
        if not value:
            raise ValueError("lane_registry must be non-empty")
        lane_ids = [lane.lane_id for lane in value]
        if len(set(lane_ids)) != len(lane_ids):
            raise ValueError("lane_registry lane_id values must be unique")
        branches = [lane.branch for lane in value]
        if len(set(branches)) != len(branches):
            raise ValueError("lane_registry branch values must be unique")
        return value

    def lane_for_id(self, lane_id: str) -> LaneRegistration:
        for lane in self.lane_registry:
            if lane.lane_id == lane_id:
                return lane
        raise AvoLedgerError(f"lane_id not registered in manifest: {lane_id}")

    def lane_for_branch(self, branch: str) -> LaneRegistration:
        for lane in self.lane_registry:
            if lane.branch == branch:
                return lane
        raise AvoLedgerError(f"branch not registered in manifest lane_registry: {branch}")


def verify_manifest_self_hash(raw: dict[str, Any]) -> str:
    """Recompute and verify manifest_sha256 against manifest bytes."""
    expected = raw.get("manifest_sha256")
    if not isinstance(expected, str):
        raise AvoLedgerError("manifest_sha256 missing")
    _require_sha256(expected)
    body = {key: value for key, value in raw.items() if key != "manifest_sha256"}
    computed = sha256_digest(canonical_json_bytes(body))
    if expected != computed:
        raise AvoLedgerError(
            f"manifest hash mismatch: expected {expected}, got {computed}"
        )
    return expected


def load_manifest_context(path: Path) -> AvoManifestContext:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AvoLedgerError(f"cannot read manifest: {path}") from exc
    verify_manifest_self_hash(raw)
    try:
        return AvoManifestContext.model_validate(raw)
    except Exception as exc:
        raise AvoLedgerError(f"manifest context invalid: {exc}") from exc


def load_default_manifest_context(repo_root: Path) -> AvoManifestContext:
    return load_manifest_context(repo_root / MANIFEST_RELATIVE)


# ---------------------------------------------------------------------------
# Ledger / checkpoint models
# ---------------------------------------------------------------------------


class TrialIntervention(_Closed):
    kind: Literal[
        "evaluator_method",
        "display_selection",
        "scoring_weight",
        "abstention_threshold",
        "other_bounded",
    ]
    summary: Annotated[str, Field(max_length=256)]
    digest: str

    @field_validator("digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        return _require_sha256(value)


class TrialControl(_Closed):
    kind: Literal["baseline", "parent_lineage", "manifest_frozen"]
    digest: str

    @field_validator("digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        return _require_sha256(value)


class EvaluatorIdentity(_Closed):
    digest: str
    method_config_sha256: str

    @field_validator("digest", "method_config_sha256")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        return _require_sha256(value)


class TrialRecord(_Closed):
    purpose_id: str
    hypothesis: Annotated[str, Field(max_length=512)]
    target_failure_mode: Annotated[str, Field(max_length=512)]
    intervention: TrialIntervention
    expected_effect: Annotated[str, Field(max_length=512)]
    falsifier: Annotated[str, Field(max_length=512)]
    control: TrialControl
    protected_gates: list[str]
    lineage_parent: str
    decision_informed: Literal[
        "calibration",
        "product_improvement",
        "supervisor_directive",
        "gate_recovery",
    ]
    seed: Annotated[int, Field(ge=0)]
    evaluator_identity: EvaluatorIdentity
    metrics: dict[str, float] | None = None
    hard_constraint_violations: list[str] | None = None
    notes: Annotated[str, Field(max_length=256)] | None = None

    @field_validator("purpose_id")
    @classmethod
    def validate_purpose_id(cls, value: str) -> str:
        if not re.fullmatch(r"^[a-z0-9._-]+$", value):
            raise ValueError("purpose_id must be a bounded safe token")
        return value

    @field_validator("protected_gates")
    @classmethod
    def validate_protected_gates(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("protected_gates must be non-empty")
        return value

    @field_validator("lineage_parent")
    @classmethod
    def validate_lineage_parent(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("lineage_parent must be non-empty")
        if not (_EXPERIMENT_ID.fullmatch(value) or _GIT_OID.fullmatch(value)):
            raise ValueError("lineage_parent must be a Git oid or experiment_id")
        return value


class CrashRecord(_Closed):
    phase: Literal[
        "preflight",
        "intervention_apply",
        "evaluate",
        "record",
        "checkpoint",
    ]
    error_class: Annotated[str, Field(max_length=128)]


class RejectionRecord(_Closed):
    reason_code: Literal[
        "manifest_mismatch",
        "gate_violation",
        "duplicate_experiment_id",
        "invalid_intervention",
        "resource_limit",
        "replay_mismatch",
        "supervisor_veto",
        "schema_invalid",
    ]


class LedgerChain(_Closed):
    prev_entry_sha256: str

    @field_validator("prev_entry_sha256")
    @classmethod
    def validate_prev(cls, value: str) -> str:
        return _require_sha256(value)


class LedgerEntry(_Closed):
    schema_version: Literal["holusight-avo-ledger/v1"]
    campaign_id: Literal["holusight-avo-v1"]
    lane_id: str
    sequence: Annotated[int, Field(ge=1)]
    recorded_at: str
    experiment_id: str
    outcome: Literal[
        "completed",
        "kept",
        "discarded",
        "rejected",
        "indeterminate",
        "crashed",
    ]
    trial: TrialRecord
    crash: CrashRecord | None = None
    rejection: RejectionRecord | None = None
    ledger_chain: LedgerChain | None = None

    @field_validator("lane_id")
    @classmethod
    def validate_lane_id(cls, value: str) -> str:
        if not _LANE_ID.fullmatch(value):
            raise ValueError("lane_id must be lowercase alphanumeric with hyphens")
        return value

    @field_validator("experiment_id")
    @classmethod
    def validate_experiment_id(cls, value: str) -> str:
        if not _EXPERIMENT_ID.fullmatch(value):
            raise ValueError("experiment_id must be four digits")
        return value

    @model_validator(mode="after")
    def validate_outcome_payload(self) -> LedgerEntry:
        if self.outcome == "crashed" and self.crash is None:
            raise ValueError("crashed outcome requires crash block")
        if self.outcome != "crashed" and self.crash is not None:
            raise ValueError("crash block is only valid for crashed outcome")
        if self.outcome == "rejected" and self.rejection is None:
            raise ValueError("rejected outcome requires rejection block")
        if self.outcome != "rejected" and self.rejection is not None:
            raise ValueError("rejection block is only valid for rejected outcome")
        return self


class OutcomeCounts(_Closed):
    completed: Annotated[int, Field(ge=0)]
    kept: Annotated[int, Field(ge=0)]
    discarded: Annotated[int, Field(ge=0)]
    crashed: Annotated[int, Field(ge=0)]
    rejected: Annotated[int, Field(ge=0)]
    indeterminate: Annotated[int, Field(ge=0)]


class Checkpoint(_Closed):
    schema_version: Literal["holusight-avo-checkpoint/v1"]
    campaign_id: Literal["holusight-avo-v1"]
    lane_id: str
    branch: str
    checkpoint_sequence: Annotated[int, Field(ge=1)]
    created_at: str
    manifest_sha256: str
    last_experiment_id: str
    lineage_head: str
    evaluator_identity_digest: str
    counts: OutcomeCounts
    ledger_tail_sha256: str

    @field_validator("lane_id")
    @classmethod
    def validate_lane_id(cls, value: str) -> str:
        if not _LANE_ID.fullmatch(value):
            raise ValueError("lane_id must be lowercase alphanumeric with hyphens")
        return value

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, value: str) -> str:
        if not _BRANCH.fullmatch(value):
            raise ValueError("branch must match fm/holusight-avo-<slug>")
        return value

    @field_validator("manifest_sha256", "evaluator_identity_digest", "ledger_tail_sha256")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        return _require_sha256(value)

    @field_validator("last_experiment_id")
    @classmethod
    def validate_experiment_id(cls, value: str) -> str:
        if not _EXPERIMENT_ID.fullmatch(value):
            raise ValueError("last_experiment_id must be four digits")
        return value

    @field_validator("lineage_head")
    @classmethod
    def validate_lineage_head(cls, value: str) -> str:
        if not _GIT_OID.fullmatch(value):
            raise ValueError("lineage_head must be a Git commit oid")
        return value


# ---------------------------------------------------------------------------
# Allocation / semantic validation
# ---------------------------------------------------------------------------


def experiment_id_in_range(experiment_id: str, start: str, end: str) -> bool:
    return int(start) <= int(experiment_id) <= int(end)


def validate_trial_contract(
    entry: LedgerEntry,
    *,
    manifest: AvoManifestContext,
    lane: LaneRegistration,
) -> None:
    """Validate per-trial contract fields beyond bare schema shape."""
    trial = entry.trial
    expected_seed = derive_trial_seed(
        entry.experiment_id, manifest.deterministic_seeds.global_seed
    )
    if trial.seed != expected_seed:
        raise AvoLedgerError(
            f"sequence {entry.sequence}: trial.seed {trial.seed} != "
            f"deterministic allocation {expected_seed}"
        )

    if not experiment_id_in_range(
        entry.experiment_id,
        lane.experiment_id_range.start,
        lane.experiment_id_range.end,
    ):
        raise AvoLedgerError(
            f"sequence {entry.sequence}: experiment_id {entry.experiment_id} "
            f"outside lane range {lane.experiment_id_range.start}-"
            f"{lane.experiment_id_range.end}"
        )

    manifest_gates = set(manifest.protected_gates)
    declared_gates = set(trial.protected_gates)
    missing = manifest_gates - declared_gates
    if missing:
        raise AvoLedgerError(
            f"sequence {entry.sequence}: trial missing manifest protected_gates: "
            f"{sorted(missing)}"
        )

    if trial.control.kind == "parent_lineage" and trial.lineage_parent == entry.experiment_id:
        raise AvoLedgerError(
            f"sequence {entry.sequence}: matched control parent_lineage cannot self-reference"
        )

    required_fields = {
        "purpose_id",
        "hypothesis",
        "target_failure_mode",
        "intervention",
        "expected_effect",
        "falsifier",
        "control",
        "protected_gates",
        "lineage_parent",
        "decision_informed",
        "seed",
        "evaluator_identity",
    }
    present = set(trial.model_dump(exclude_none=True).keys())
    if not required_fields.issubset(present):
        missing_fields = sorted(required_fields - present)
        raise AvoLedgerError(
            f"sequence {entry.sequence}: trial missing required fields: {missing_fields}"
        )

    if entry.outcome in {"completed", "kept"} and not trial.control.digest:
        raise AvoLedgerError(
            f"sequence {entry.sequence}: {entry.outcome} trial requires matched control digest"
        )


def _parse_ledger_line(line: str, line_no: int) -> LedgerEntry:
    stripped = line.strip()
    if not stripped:
        raise AvoLedgerError(f"line {line_no}: empty ledger line")
    try:
        raw = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise AvoLedgerError(f"line {line_no}: invalid JSON") from exc
    try:
        return LedgerEntry.model_validate(raw)
    except Exception as exc:
        raise AvoLedgerError(f"line {line_no}: schema invalid: {exc}") from exc


@dataclass(frozen=True)
class ValidatedLedger:
    lane_id: str
    entries: tuple[LedgerEntry, ...]
    raw_lines: tuple[str, ...]
    outcome_counts: OutcomeCounts
    experiment_ids: frozenset[str]
    crashed_experiment_ids: frozenset[str]


def validate_ledger_text(
    text: str,
    *,
    manifest: AvoManifestContext,
    lane_id: str,
) -> ValidatedLedger:
    """Validate append-only lane ledger semantics and crash retention."""
    lane = manifest.lane_for_id(lane_id)
    lines = text.splitlines()
    if text and not lines:
        lines = []

    entries: list[LedgerEntry] = []
    raw_lines: list[str] = []
    seen_experiment_ids: dict[str, int] = {}
    prev_hash = _GENESIS_PREV

    for line_no, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        entry = _parse_ledger_line(line, line_no)
        raw_lines.append(line.rstrip("\n"))

        if entry.lane_id != lane_id:
            raise AvoLedgerError(
                f"line {line_no}: lane_id {entry.lane_id} != expected {lane_id}"
            )
        if entry.sequence != len(entries) + 1:
            raise AvoLedgerError(
                f"line {line_no}: sequence {entry.sequence} != expected {len(entries) + 1}"
            )

        if entry.ledger_chain is not None:
            if entry.ledger_chain.prev_entry_sha256 != prev_hash:
                raise AvoLedgerError(
                    f"line {line_no}: ledger_chain prev_entry_sha256 mismatch"
                )

        validate_trial_contract(entry, manifest=manifest, lane=lane)

        if entry.experiment_id in seen_experiment_ids:
            prior_seq = seen_experiment_ids[entry.experiment_id]
            if not (
                entry.outcome == "rejected"
                and entry.rejection is not None
                and entry.rejection.reason_code == "duplicate_experiment_id"
            ):
                raise AvoLedgerError(
                    f"line {line_no}: duplicate experiment_id {entry.experiment_id} "
                    f"(first seen at sequence {prior_seq})"
                )
        else:
            seen_experiment_ids[entry.experiment_id] = entry.sequence

        entries.append(entry)
        entry_dict = json.loads(line.strip())
        prev_hash = ledger_entry_line_sha256(entry_dict)

    counts = Counter(entry.outcome for entry in entries)
    outcome_counts = OutcomeCounts(
        completed=counts.get("completed", 0),
        kept=counts.get("kept", 0),
        discarded=counts.get("discarded", 0),
        crashed=counts.get("crashed", 0),
        rejected=counts.get("rejected", 0),
        indeterminate=counts.get("indeterminate", 0),
    )

    crashed_ids = frozenset(
        entry.experiment_id for entry in entries if entry.outcome == "crashed"
    )
    for entry in entries:
        if entry.outcome == "crashed" and entry.crash is None:
            raise AvoLedgerError(
                f"sequence {entry.sequence}: crashed outcome missing crash retention block"
            )

    return ValidatedLedger(
        lane_id=lane_id,
        entries=tuple(entries),
        raw_lines=tuple(raw_lines),
        outcome_counts=outcome_counts,
        experiment_ids=frozenset(seen_experiment_ids),
        crashed_experiment_ids=crashed_ids,
    )


def validate_ledger_file(
    path: Path,
    *,
    manifest: AvoManifestContext,
    lane_id: str,
) -> ValidatedLedger:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AvoLedgerError(f"cannot read ledger: {path}") from exc
    return validate_ledger_text(text, manifest=manifest, lane_id=lane_id)


# ---------------------------------------------------------------------------
# Leakage / checkpoint helpers
# ---------------------------------------------------------------------------


def find_forbidden_keys(value: Any, *, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            key_path = f"{path}.{key}" if path else key
            if key in _FORBIDDEN_KEYS:
                found.append(key_path)
            found.extend(find_forbidden_keys(nested, path=key_path))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            found.extend(find_forbidden_keys(nested, path=f"{path}[{index}]"))
    return found


def parse_checkpoint(raw: dict[str, Any]) -> Checkpoint:
    try:
        return Checkpoint.model_validate(raw)
    except Exception as exc:
        raise AvoLedgerError(f"checkpoint schema invalid: {exc}") from exc


def validate_checkpoint_payload(
    checkpoint: Checkpoint,
    *,
    manifest: AvoManifestContext,
    ledger: ValidatedLedger | None = None,
) -> None:
    """Validate checkpoint semantics against manifest and optional ledger tail."""
    if checkpoint.manifest_sha256 != manifest.manifest_sha256:
        raise AvoLedgerError("checkpoint manifest_sha256 does not match verified manifest")

    lane = manifest.lane_for_id(checkpoint.lane_id)
    if checkpoint.branch != lane.branch:
        raise AvoLedgerError(
            f"checkpoint branch {checkpoint.branch} != registered branch {lane.branch}"
        )

    pattern = re.compile(manifest.checkpoint_policy.branch_name_pattern)
    if not pattern.fullmatch(checkpoint.branch):
        raise AvoLedgerError(
            f"checkpoint branch {checkpoint.branch} fails manifest branch_name_pattern"
        )

    forbidden = find_forbidden_keys(checkpoint.model_dump())
    if forbidden:
        raise AvoLedgerError(f"checkpoint contains forbidden keys: {forbidden}")

    serialized = canonical_json_bytes(checkpoint.model_dump())
    if len(serialized) > manifest.checkpoint_policy.max_checkpoint_bytes:
        raise AvoLedgerError(
            f"checkpoint exceeds max_checkpoint_bytes "
            f"({len(serialized)} > {manifest.checkpoint_policy.max_checkpoint_bytes})"
        )

    if ledger is not None:
        if ledger.lane_id != checkpoint.lane_id:
            raise AvoLedgerError("checkpoint lane_id does not match ledger lane_id")
        if checkpoint.counts != ledger.outcome_counts:
            raise AvoLedgerError("checkpoint counts do not match ledger outcome totals")
        if not ledger.raw_lines:
            if checkpoint.ledger_tail_sha256 != _GENESIS_PREV:
                raise AvoLedgerError("empty ledger requires genesis ledger_tail_sha256")
        else:
            tail_hash = ledger_entry_sha256_from_line(ledger.raw_lines[-1])
            if checkpoint.ledger_tail_sha256 != tail_hash:
                raise AvoLedgerError("checkpoint ledger_tail_sha256 mismatch")
            last_entry = ledger.entries[-1]
            if checkpoint.last_experiment_id != last_entry.experiment_id:
                raise AvoLedgerError("checkpoint last_experiment_id mismatch")


def _git_rev_parse(repo_root: Path, ref: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", ref],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _git_ls_files(repo_root: Path, path: str, ref: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", ref, "--", path],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    if result.returncode != 0:
        return False
    names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return path in names


def validate_checkpoint_git_only(
    checkpoint_path: Path,
    *,
    repo_root: Path,
    git_ref: str,
    manifest: AvoManifestContext,
    ledger_path: Path | None = None,
    lane_id: str | None = None,
) -> Checkpoint:
    """Accept a checkpoint only when it is Git-published and schema-valid."""
    if _git_rev_parse(repo_root, git_ref) is None:
        raise AvoLedgerError(f"git ref not resolved: {git_ref}")

    repo_relative = checkpoint_path
    try:
        repo_relative = checkpoint_path.resolve().relative_to(repo_root.resolve())
    except ValueError as exc:
        raise AvoLedgerError("checkpoint path must be inside repository root") from exc

    rel_posix = repo_relative.as_posix()
    if not _git_ls_files(repo_root, rel_posix, git_ref):
        raise AvoLedgerError(
            f"checkpoint not tracked in Git at {git_ref}: {rel_posix}"
        )

    try:
        raw_bytes = checkpoint_path.read_bytes()
    except OSError as exc:
        raise AvoLedgerError(f"cannot read checkpoint: {checkpoint_path}") from exc

    if len(raw_bytes) > manifest.checkpoint_policy.max_checkpoint_bytes:
        raise AvoLedgerError("checkpoint file exceeds max_checkpoint_bytes")

    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AvoLedgerError("checkpoint is not valid UTF-8 JSON") from exc

    checkpoint = parse_checkpoint(raw)
    ledger: ValidatedLedger | None = None
    if ledger_path is not None:
        resolved_lane = lane_id or checkpoint.lane_id
        ledger = validate_ledger_file(
            ledger_path, manifest=manifest, lane_id=resolved_lane
        )
    validate_checkpoint_payload(checkpoint, manifest=manifest, ledger=ledger)
    return checkpoint
