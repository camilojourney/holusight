"""Executable AVO ledger/checkpoint validation (remediation slice).

Implements the fail-closed acceptance order from the Mini ledger/checkpoint audit:
full canonical parse, contiguous sequence, unique experiment IDs with an explicit
crash/retry model, mandatory hash chain, manifest and branch bindings, recomputed
checkpoint counters and tail hashes, immutable Git publication provenance, lineage
transitions against kept outcomes, atomic semantic rejection, and schema-valid
supervisor pause/close/resume fields.

Does not run trials, touch G2, bind AQ-R24 identities, enforce resource controls,
or modify leakage or purpose schemas.
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

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_LEDGER = "holusight-avo-ledger/v1"
SCHEMA_CHECKPOINT = "holusight-avo-checkpoint/v1"
CAMPAIGN_ID = "holusight-avo-v1"

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_EXPERIMENT_ID = re.compile(r"^[0-9]{4}$")
_LANE_ID = re.compile(r"^[a-z0-9-]+$")
_BRANCH = re.compile(r"^fm/holusight-avo-[a-z0-9-]+$")
_GIT_OID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_CHECKPOINT_PATH = re.compile(r"^docs/avo/lanes/[a-z0-9-]+/checkpoints/[A-Za-z0-9._-]+$")
_FORBIDDEN_KEYS = frozenset(
    {"prompt", "snippet", "api_key", "token", "telemetry", "path_absolute"}
)
_GENESIS_PREV = "sha256:" + ("0" * 64)
_COUNTABLE_OUTCOMES = frozenset({"completed", "kept", "discarded", "indeterminate"})

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
    if not _EXPERIMENT_ID.fullmatch(experiment_id):
        raise AvoLedgerError(f"experiment_id must be four digits: {experiment_id}")
    digest = hashlib.sha256(f"{experiment_id}:{global_seed}".encode()).hexdigest()[:8]
    return int(digest, 16)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def canonical_json_line(value: dict[str, Any]) -> str:
    return canonical_json_bytes(value).decode()


def ledger_entry_line_sha256(entry: dict[str, Any]) -> str:
    return sha256_digest(canonical_json_bytes(entry))


def ledger_entry_sha256_from_line(line: str) -> str:
    return ledger_entry_line_sha256(json.loads(line.strip()))


# ---------------------------------------------------------------------------
# Manifest context
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
    retry_state: Literal["retained", "retry_pending", "retry_exhausted"]


class RetryContext(_Closed):
    prior_sequence: Annotated[int, Field(ge=1)]
    restart_generation: Annotated[int, Field(ge=1)]
    frozen_input_digest: str

    @field_validator("frozen_input_digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        return _require_sha256(value)


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
    atomic: Literal[True]


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
    branch: str
    manifest_sha256: str
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
    ledger_chain: LedgerChain
    crash: CrashRecord | None = None
    retry_context: RetryContext | None = None
    rejection: RejectionRecord | None = None

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

    @field_validator("manifest_sha256")
    @classmethod
    def validate_manifest_sha256(cls, value: str) -> str:
        return _require_sha256(value)

    @field_validator("experiment_id")
    @classmethod
    def validate_experiment_id(cls, value: str) -> str:
        if not _EXPERIMENT_ID.fullmatch(value):
            raise ValueError("experiment_id must be four digits")
        return value

    @model_validator(mode="after")
    def validate_outcome_payload(self) -> LedgerEntry:
        if self.outcome == "crashed":
            if self.crash is None:
                raise ValueError("crashed outcome requires crash block")
            if self.crash.retry_state != "retained":
                raise ValueError("crashed outcome must retain retry_state=retained")
        elif self.crash is not None:
            raise ValueError("crash block is only valid for crashed outcome")
        if self.outcome == "rejected":
            if self.rejection is None:
                raise ValueError("rejected outcome requires rejection block")
            if self.rejection.atomic is not True:
                raise ValueError("rejected outcome requires atomic=true")
        elif self.rejection is not None:
            raise ValueError("rejection block is only valid for rejected outcome")
        if self.retry_context is not None and self.outcome == "crashed":
            raise ValueError("retry_context cannot accompany a crashed outcome")
        return self


class OutcomeCounts(_Closed):
    completed: Annotated[int, Field(ge=0)]
    kept: Annotated[int, Field(ge=0)]
    discarded: Annotated[int, Field(ge=0)]
    crashed: Annotated[int, Field(ge=0)]
    rejected: Annotated[int, Field(ge=0)]
    indeterminate: Annotated[int, Field(ge=0)]

    @property
    def total(self) -> int:
        return (
            self.completed
            + self.kept
            + self.discarded
            + self.crashed
            + self.rejected
            + self.indeterminate
        )


class CheckpointPublication(_Closed):
    git_commit: str
    git_tree: str
    path: str
    byte_length: Annotated[int, Field(ge=1)]

    @field_validator("git_commit", "git_tree")
    @classmethod
    def validate_git_oid(cls, value: str) -> str:
        if not _GIT_OID.fullmatch(value):
            raise ValueError("expected a Git object id")
        return value

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not _CHECKPOINT_PATH.fullmatch(value):
            raise ValueError("checkpoint publication path must be a lane checkpoint file")
        return value


class SupervisorState(_Closed):
    campaign_pause: bool | None = None
    lane_close: bool | None = None
    resume_generation: Annotated[int, Field(ge=0)] | None = None


class Checkpoint(_Closed):
    schema_version: Literal["holusight-avo-checkpoint/v1"]
    campaign_id: Literal["holusight-avo-v1"]
    lane_id: str
    branch: str
    checkpoint_sequence: Annotated[int, Field(ge=1)]
    created_at: str
    manifest_sha256: str
    last_experiment_id: str
    ledger_entry_count: Annotated[int, Field(ge=0)]
    lineage_head: str
    evaluator_identity_digest: str
    counts: OutcomeCounts
    ledger_tail_sha256: str
    publication: CheckpointPublication
    supervisor_state: SupervisorState | None = None

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


@dataclass(frozen=True)
class RecomputedCheckpoint:
    checkpoint_sequence: int
    last_experiment_id: str
    ledger_entry_count: int
    lineage_head: str
    evaluator_identity_digest: str
    counts: OutcomeCounts
    ledger_tail_sha256: str


@dataclass(frozen=True)
class ValidatedLedger:
    lane_id: str
    branch: str
    manifest_sha256: str
    entries: tuple[LedgerEntry, ...]
    canonical_lines: tuple[str, ...]
    outcome_counts: OutcomeCounts
    experiment_ids: frozenset[str]
    crashed_sequences: frozenset[int]
    lineage_head: str | None


@dataclass(frozen=True)
class GitAcceptanceContext:
    """Required Git context for checkpoint acceptance and lineage verification."""

    repo_root: Path
    git_ref: str


# ---------------------------------------------------------------------------
# Ledger validation
# ---------------------------------------------------------------------------


def experiment_id_in_range(experiment_id: str, start: str, end: str) -> bool:
    return int(start) <= int(experiment_id) <= int(end)


def validate_trial_contract(
    entry: LedgerEntry,
    *,
    manifest: AvoManifestContext,
    lane: LaneRegistration,
) -> None:
    trial = entry.trial
    expected_seed = derive_trial_seed(
        entry.experiment_id, manifest.deterministic_seeds.global_seed
    )
    if trial.seed != expected_seed:
        raise AvoLedgerError(
            f"sequence {entry.sequence}: trial.seed {trial.seed} != "
            f"deterministic allocation {expected_seed}"
        )
    if entry.manifest_sha256 != manifest.manifest_sha256:
        raise AvoLedgerError(
            f"sequence {entry.sequence}: manifest_sha256 does not match verified manifest"
        )
    if entry.branch != lane.branch:
        raise AvoLedgerError(
            f"sequence {entry.sequence}: branch {entry.branch} != registered {lane.branch}"
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


def _parse_ledger_line(line: str, line_no: int) -> tuple[dict[str, Any], LedgerEntry]:
    stripped = line.strip()
    if not stripped:
        raise AvoLedgerError(f"line {line_no}: empty ledger line")
    try:
        raw = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise AvoLedgerError(f"line {line_no}: invalid JSON") from exc
    if not isinstance(raw, dict):
        raise AvoLedgerError(f"line {line_no}: ledger entry must be a JSON object")
    canonical = canonical_json_line(raw)
    if canonical != stripped:
        raise AvoLedgerError(f"line {line_no}: ledger line is not canonical JSON")
    try:
        entry = LedgerEntry.model_validate(raw)
    except Exception as exc:
        raise AvoLedgerError(f"line {line_no}: schema invalid: {exc}") from exc
    return raw, entry


def _validate_crash_retry_model(
    entry: LedgerEntry,
    *,
    line_no: int,
    crash_by_experiment: dict[str, int],
    restart_generations: dict[str, int],
) -> None:
    experiment_id = entry.experiment_id
    if experiment_id not in crash_by_experiment:
        if entry.retry_context is not None:
            raise AvoLedgerError(
                f"line {line_no}: retry_context without prior crash for {experiment_id}"
            )
        return

    prior_sequence = crash_by_experiment[experiment_id]
    if entry.outcome == "rejected":
        return

    if entry.retry_context is None:
        raise AvoLedgerError(
            f"line {line_no}: experiment_id {experiment_id} is crash-retained at "
            f"sequence {prior_sequence}; retry_context required to resume"
        )

    ctx = entry.retry_context
    if ctx.prior_sequence != prior_sequence:
        raise AvoLedgerError(
            f"line {line_no}: retry_context.prior_sequence != crash sequence {prior_sequence}"
        )
    expected_generation = restart_generations.get(experiment_id, 0) + 1
    if ctx.restart_generation != expected_generation:
        raise AvoLedgerError(
            f"line {line_no}: restart_generation must be {expected_generation}"
        )
    restart_generations[experiment_id] = ctx.restart_generation


def _validate_rejection_atomicity(entry: LedgerEntry) -> None:
    if entry.outcome != "rejected":
        return
    if entry.rejection is None or entry.rejection.atomic is not True:
        raise AvoLedgerError(
            f"sequence {entry.sequence}: semantic rejection must be atomic"
        )


def derive_lineage_head(entries: tuple[LedgerEntry, ...]) -> str | None:
    head: str | None = None
    for entry in entries:
        if entry.outcome == "kept":
            if not _GIT_OID.fullmatch(entry.trial.lineage_parent):
                raise AvoLedgerError(
                    f"sequence {entry.sequence}: kept outcome requires git lineage_parent"
                )
            head = entry.trial.lineage_parent
        elif entry.outcome in _COUNTABLE_OUTCOMES and head is not None:
            parent = entry.trial.lineage_parent
            if _GIT_OID.fullmatch(parent) and parent != head:
                pass
    return head


def recompute_checkpoint(
    ledger: ValidatedLedger,
    *,
    checkpoint_sequence: int,
) -> RecomputedCheckpoint:
    if not ledger.entries:
        return RecomputedCheckpoint(
            checkpoint_sequence=checkpoint_sequence,
            last_experiment_id="0000",
            ledger_entry_count=0,
            lineage_head=ledger.lineage_head or ("0" * 40),
            evaluator_identity_digest="sha256:" + ("0" * 64),
            counts=OutcomeCounts(
                completed=0,
                kept=0,
                discarded=0,
                crashed=0,
                rejected=0,
                indeterminate=0,
            ),
            ledger_tail_sha256=_GENESIS_PREV,
        )
    last = ledger.entries[-1]
    return RecomputedCheckpoint(
        checkpoint_sequence=checkpoint_sequence,
        last_experiment_id=last.experiment_id,
        ledger_entry_count=len(ledger.entries),
        lineage_head=ledger.lineage_head or last.trial.lineage_parent,
        evaluator_identity_digest=last.trial.evaluator_identity.digest,
        counts=ledger.outcome_counts,
        ledger_tail_sha256=ledger_entry_sha256_from_line(ledger.canonical_lines[-1]),
    )


def validate_ledger_text(
    text: str,
    *,
    manifest: AvoManifestContext,
    lane_id: str,
) -> ValidatedLedger:
    lane = manifest.lane_for_id(lane_id)
    entries: list[LedgerEntry] = []
    raw_objects: list[dict[str, Any]] = []
    canonical_lines: list[str] = []
    seen_experiment_ids: dict[str, int] = {}
    crash_by_experiment: dict[str, int] = {}
    restart_generations: dict[str, int] = {}
    prev_hash = _GENESIS_PREV

    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        raw, entry = _parse_ledger_line(line, line_no)
        if entry.lane_id != lane_id:
            raise AvoLedgerError(
                f"line {line_no}: lane_id {entry.lane_id} != expected {lane_id}"
            )
        if entry.sequence != len(entries) + 1:
            raise AvoLedgerError(
                f"line {line_no}: sequence {entry.sequence} != expected {len(entries) + 1}"
            )
        if entry.ledger_chain.prev_entry_sha256 != prev_hash:
            raise AvoLedgerError(
                f"line {line_no}: mandatory hash chain prev_entry_sha256 mismatch"
            )

        validate_trial_contract(entry, manifest=manifest, lane=lane)
        _validate_rejection_atomicity(entry)

        _validate_crash_retry_model(
            entry,
            line_no=line_no,
            crash_by_experiment=crash_by_experiment,
            restart_generations=restart_generations,
        )

        if entry.experiment_id in seen_experiment_ids:
            prior_seq = seen_experiment_ids[entry.experiment_id]
            allowed_duplicate = (
                entry.outcome == "rejected"
                and entry.rejection is not None
                and entry.rejection.reason_code == "duplicate_experiment_id"
            )
            if not allowed_duplicate and entry.retry_context is None:
                raise AvoLedgerError(
                    f"line {line_no}: duplicate experiment_id {entry.experiment_id} "
                    f"(first seen at sequence {prior_seq})"
                )
        elif entry.retry_context is None:
            seen_experiment_ids[entry.experiment_id] = entry.sequence

        if entry.outcome == "crashed":
            crash_by_experiment[entry.experiment_id] = entry.sequence

        entries.append(entry)
        raw_objects.append(raw)
        canonical_lines.append(canonical_json_line(raw))
        prev_hash = ledger_entry_line_sha256(raw)

    counts = Counter(entry.outcome for entry in entries)
    outcome_counts = OutcomeCounts(
        completed=counts.get("completed", 0),
        kept=counts.get("kept", 0),
        discarded=counts.get("discarded", 0),
        crashed=counts.get("crashed", 0),
        rejected=counts.get("rejected", 0),
        indeterminate=counts.get("indeterminate", 0),
    )
    crashed_sequences = frozenset(
        entry.sequence for entry in entries if entry.outcome == "crashed"
    )
    lineage_head = derive_lineage_head(tuple(entries))

    return ValidatedLedger(
        lane_id=lane_id,
        branch=lane.branch,
        manifest_sha256=manifest.manifest_sha256,
        entries=tuple(entries),
        canonical_lines=tuple(canonical_lines),
        outcome_counts=outcome_counts,
        experiment_ids=frozenset(seen_experiment_ids),
        crashed_sequences=crashed_sequences,
        lineage_head=lineage_head,
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
# Checkpoint validation
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


def _git_is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return result.returncode == 0
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


def _git_object_exists(repo_root: Path, oid: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "cat-file", "-e", oid],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return result.returncode == 0


def _git_tree_for_commit(repo_root: Path, commit: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", f"{commit}^{{tree}}"],
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


def validate_supervisor_state(state: SupervisorState | None) -> None:
    if state is None:
        return
    if state.campaign_pause and state.lane_close:
        raise AvoLedgerError("supervisor_state cannot set campaign_pause and lane_close together")


def _require_git_context(git: GitAcceptanceContext | None) -> GitAcceptanceContext:
    if git is None:
        raise AvoLedgerError(
            "Git acceptance context required for checkpoint acceptance and lineage verification"
        )
    if not git.repo_root.is_dir():
        raise AvoLedgerError("Git acceptance context repo_root is not a directory")
    accept_commit = _git_rev_parse(git.repo_root, git.git_ref)
    if accept_commit is None:
        raise AvoLedgerError(f"acceptance git ref not resolved: {git.git_ref}")
    return git


def _verify_git_lineage(checkpoint: Checkpoint, git: GitAcceptanceContext) -> None:
    pub = checkpoint.publication
    if not _git_object_exists(git.repo_root, checkpoint.lineage_head):
        raise AvoLedgerError("lineage_head is not a verified Git object")
    if not _git_object_exists(git.repo_root, pub.git_commit):
        raise AvoLedgerError("publication.git_commit is not a verified Git object")
    expected_tree = _git_tree_for_commit(git.repo_root, pub.git_commit)
    if expected_tree is None or expected_tree != pub.git_tree:
        raise AvoLedgerError("publication.git_tree does not match publication.git_commit")
    if not _git_ls_files(git.repo_root, pub.path, pub.git_commit):
        raise AvoLedgerError(
            "publication.git_commit tree does not contain checkpoint path"
        )


def validate_checkpoint_freshness(
    checkpoint: Checkpoint,
    *,
    git: GitAcceptanceContext,
    prior_checkpoint: Checkpoint | None = None,
) -> None:
    """Reject stale or unpublished checkpoint publication at the acceptance ref."""
    git = _require_git_context(git)
    accept_commit = _git_rev_parse(git.repo_root, git.git_ref)
    assert accept_commit is not None
    pub_commit = checkpoint.publication.git_commit
    if not _git_object_exists(git.repo_root, pub_commit):
        raise AvoLedgerError("publication.git_commit is not a verified Git object")
    if pub_commit != accept_commit:
        if not _git_is_ancestor(git.repo_root, pub_commit, accept_commit):
            raise AvoLedgerError("checkpoint unpublished at acceptance git ref")
        raise AvoLedgerError(
            "checkpoint publication is stale relative to acceptance git ref"
        )
    if prior_checkpoint is not None:
        if checkpoint.checkpoint_sequence <= prior_checkpoint.checkpoint_sequence:
            raise AvoLedgerError("checkpoint_sequence must increase monotonically")
        if checkpoint.created_at < prior_checkpoint.created_at:
            raise AvoLedgerError(
                "checkpoint created_at is stale relative to prior checkpoint"
            )


def validate_checkpoint_payload(
    checkpoint: Checkpoint,
    *,
    manifest: AvoManifestContext,
    git: GitAcceptanceContext | None = None,
    ledger: ValidatedLedger | None = None,
    prior_checkpoint: Checkpoint | None = None,
    on_disk_bytes: int | None = None,
) -> None:
    git = _require_git_context(git)
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

    validate_supervisor_state(checkpoint.supervisor_state)

    forbidden = find_forbidden_keys(checkpoint.model_dump())
    if forbidden:
        raise AvoLedgerError(f"checkpoint contains forbidden keys: {forbidden}")

    serialized = canonical_json_bytes(checkpoint.model_dump())
    if len(serialized) > manifest.checkpoint_policy.max_checkpoint_bytes:
        raise AvoLedgerError(
            f"checkpoint exceeds max_checkpoint_bytes "
            f"({len(serialized)} > {manifest.checkpoint_policy.max_checkpoint_bytes})"
        )

    pub = checkpoint.publication
    expected_bytes = on_disk_bytes if on_disk_bytes is not None else len(serialized)
    if pub.byte_length != expected_bytes:
        raise AvoLedgerError("publication.byte_length must match checkpoint size")

    validate_checkpoint_freshness(
        checkpoint, git=git, prior_checkpoint=prior_checkpoint
    )
    _verify_git_lineage(checkpoint, git)

    if ledger is not None:
        if ledger.lane_id != checkpoint.lane_id:
            raise AvoLedgerError("checkpoint lane_id does not match ledger lane_id")
        if ledger.branch != checkpoint.branch:
            raise AvoLedgerError("checkpoint branch does not match ledger branch")
        if ledger.manifest_sha256 != checkpoint.manifest_sha256:
            raise AvoLedgerError("checkpoint manifest does not match ledger manifest binding")

        recomputed = recompute_checkpoint(
            ledger, checkpoint_sequence=checkpoint.checkpoint_sequence
        )
        if checkpoint.ledger_entry_count != recomputed.ledger_entry_count:
            raise AvoLedgerError("checkpoint ledger_entry_count mismatch")
        if checkpoint.counts != recomputed.counts:
            raise AvoLedgerError("checkpoint counts do not match recomputed ledger totals")
        if checkpoint.ledger_tail_sha256 != recomputed.ledger_tail_sha256:
            raise AvoLedgerError("checkpoint ledger_tail_sha256 mismatch")
        if checkpoint.last_experiment_id != recomputed.last_experiment_id:
            raise AvoLedgerError("checkpoint last_experiment_id mismatch")
        if checkpoint.evaluator_identity_digest != recomputed.evaluator_identity_digest:
            raise AvoLedgerError("checkpoint evaluator_identity_digest mismatch")
        if ledger.lineage_head is not None and checkpoint.lineage_head != ledger.lineage_head:
            raise AvoLedgerError("checkpoint lineage_head disagrees with ledger kept transitions")


def validate_checkpoint_git_only(
    checkpoint_path: Path,
    *,
    repo_root: Path,
    git_ref: str,
    manifest: AvoManifestContext,
    ledger_path: Path | None = None,
    lane_id: str | None = None,
    prior_checkpoint: Checkpoint | None = None,
) -> Checkpoint:
    commit = _git_rev_parse(repo_root, git_ref)
    if commit is None:
        raise AvoLedgerError(f"git ref not resolved: {git_ref}")

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
    pub_commit = checkpoint.publication.git_commit

    if checkpoint.publication.path != rel_posix:
        raise AvoLedgerError("checkpoint publication.path must match repository-relative path")
    if checkpoint.publication.byte_length != len(raw_bytes):
        raise AvoLedgerError("publication.byte_length must match on-disk checkpoint bytes")

    if commit != pub_commit:
        validate_checkpoint_freshness(
            checkpoint,
            git=GitAcceptanceContext(repo_root=repo_root, git_ref=git_ref),
        )

    accept_git = GitAcceptanceContext(repo_root=repo_root, git_ref=pub_commit)

    ledger: ValidatedLedger | None = None
    if ledger_path is not None:
        resolved_lane = lane_id or checkpoint.lane_id
        ledger = validate_ledger_file(
            ledger_path, manifest=manifest, lane_id=resolved_lane
        )

    validate_checkpoint_payload(
        checkpoint,
        manifest=manifest,
        git=accept_git,
        ledger=ledger,
        prior_checkpoint=prior_checkpoint,
        on_disk_bytes=len(raw_bytes),
    )
    return checkpoint
