"""Tests for AVO ledger/checkpoint executable validation (remediation slice).

Covers adversarial vectors from the Mini ledger/checkpoint audit and integration
matrix: duplicate IDs, lane identity mismatch, crash/replay ambiguity, stale
publication, lineage disagreement, hash-not-content, schema rejection, and
supervisor pause/close/resume schema validity.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from codesight import avo_ledger

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = avo_ledger.load_default_manifest_context(REPO_ROOT)
LANE = MANIFEST.lane_for_id("laptop-calibration-0001-0013")

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
DIGEST_D = "sha256:" + "d" * 64
LINEAGE_A = "a" * 40
LINEAGE_B = "b" * 40
TREE_OID = "c" * 40


def _trial(*, experiment_id: str = "0001", seed: int | None = None) -> dict:
    if seed is None:
        seed = avo_ledger.derive_trial_seed(
            experiment_id, MANIFEST.deterministic_seeds.global_seed
        )
    return {
        "purpose_id": "evaluator_method_calibration",
        "hypothesis": "bounded intervention improves coverage",
        "target_failure_mode": "missing required provider in display list",
        "intervention": {
            "kind": "display_selection",
            "summary": "prefer exact signal for provider lookup",
            "digest": DIGEST_A,
        },
        "expected_effect": "required_provider_coverage_mean increases",
        "falsifier": "coverage does not improve versus matched control",
        "control": {"kind": "parent_lineage", "digest": DIGEST_B},
        "protected_gates": list(MANIFEST.protected_gates),
        "lineage_parent": LINEAGE_A,
        "decision_informed": "calibration",
        "seed": seed,
        "evaluator_identity": {
            "digest": DIGEST_C,
            "method_config_sha256": DIGEST_B,
        },
    }


def _entry(
    *,
    sequence: int = 1,
    experiment_id: str = "0001",
    outcome: str = "completed",
    trial: dict | None = None,
    crash: dict | None = None,
    rejection: dict | None = None,
    retry_context: dict | None = None,
    prev_hash: str | None = None,
    branch: str | None = None,
) -> dict:
    payload = {
        "schema_version": "holusight-avo-ledger/v1",
        "campaign_id": "holusight-avo-v1",
        "lane_id": LANE.lane_id,
        "branch": branch or LANE.branch,
        "manifest_sha256": MANIFEST.manifest_sha256,
        "sequence": sequence,
        "recorded_at": "2026-08-28T06:00:00Z",
        "experiment_id": experiment_id,
        "outcome": outcome,
        "trial": trial or _trial(experiment_id=experiment_id),
        "ledger_chain": {
            "prev_entry_sha256": prev_hash
            if prev_hash is not None
            else avo_ledger._GENESIS_PREV,
        },
    }
    if crash is not None:
        payload["crash"] = crash
    if rejection is not None:
        payload["rejection"] = rejection
    if retry_context is not None:
        payload["retry_context"] = retry_context
    return payload


def _canonical_line(entry: dict) -> str:
    return avo_ledger.canonical_json_line(entry)


def _validate_lines(*lines: str) -> avo_ledger.ValidatedLedger:
    text = "\n".join(lines) + ("\n" if lines else "")
    return avo_ledger.validate_ledger_text(
        text, manifest=MANIFEST, lane_id=LANE.lane_id
    )


def _checkpoint_body(
    *,
    ledger: avo_ledger.ValidatedLedger,
    git_commit: str,
    git_tree: str,
    path: str,
    byte_length: int,
    checkpoint_sequence: int = 1,
    lineage_head: str | None = None,
    supervisor_state: dict | None = None,
) -> dict:
    recomputed = avo_ledger.recompute_checkpoint(
        ledger, checkpoint_sequence=checkpoint_sequence
    )
    body = {
        "schema_version": "holusight-avo-checkpoint/v1",
        "campaign_id": "holusight-avo-v1",
        "lane_id": LANE.lane_id,
        "branch": LANE.branch,
        "checkpoint_sequence": checkpoint_sequence,
        "created_at": "2026-08-28T06:10:00Z",
        "manifest_sha256": MANIFEST.manifest_sha256,
        "last_experiment_id": recomputed.last_experiment_id,
        "ledger_entry_count": recomputed.ledger_entry_count,
        "lineage_head": lineage_head or git_commit,
        "evaluator_identity_digest": recomputed.evaluator_identity_digest,
        "counts": recomputed.counts.model_dump(),
        "ledger_tail_sha256": recomputed.ledger_tail_sha256,
        "publication": {
            "git_commit": git_commit,
            "git_tree": git_tree,
            "path": path,
            "byte_length": byte_length,
        },
    }
    if supervisor_state is not None:
        body["supervisor_state"] = supervisor_state
    return body


def _finalize_checkpoint_bytes(body: dict) -> bytes:
    body["publication"]["byte_length"] = 1
    for _ in range(5):
        serialized = avo_ledger.canonical_json_bytes(body)
        if body["publication"]["byte_length"] == len(serialized):
            return serialized
        body["publication"]["byte_length"] = len(serialized)
    return avo_ledger.canonical_json_bytes(body)


def _write_git_file(repo: Path, relative: str, content: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _init_repo(repo: Path) -> None:
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "avo-ledger@example.test")
    _git(repo, "config", "user.name", "AVO Ledger Test")


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _commit_checkpoint_at_ref(
    repo: Path, body: dict, *, checkpoint_rel: str
) -> str:
    """Commit checkpoint JSON; return the publication commit oid."""
    parent = _git(repo, "rev-parse", "HEAD")
    parent_tree = _git(repo, "rev-parse", "HEAD^{tree}")
    body["publication"]["git_commit"] = parent
    body["publication"]["git_tree"] = parent_tree
    body["lineage_head"] = parent
    serialized = _finalize_checkpoint_bytes(body)
    _write_git_file(repo, checkpoint_rel, serialized.decode())
    _git(repo, "add", checkpoint_rel)
    _git(repo, "commit", "-q", "-m", "checkpoint draft")
    publish_commit = _git(repo, "rev-parse", "HEAD")
    publish_tree = _git(repo, "rev-parse", "HEAD^{tree}")
    body["publication"]["git_commit"] = publish_commit
    body["publication"]["git_tree"] = publish_tree
    body["lineage_head"] = publish_commit
    serialized = _finalize_checkpoint_bytes(body)
    _write_git_file(repo, checkpoint_rel, serialized.decode())
    _git(repo, "add", checkpoint_rel)
    _git(repo, "commit", "-q", "-m", "checkpoint provenance")
    committed = json.loads((repo / checkpoint_rel).read_text(encoding="utf-8"))
    return committed["publication"]["git_commit"]


def test_manifest_self_hash_verifies():
    loaded = avo_ledger.load_default_manifest_context(REPO_ROOT)
    assert loaded.manifest_sha256.startswith("sha256:")
    assert loaded.deterministic_seeds.global_seed == 926223


def test_derive_trial_seed_is_deterministic():
    assert avo_ledger.derive_trial_seed("0001", 926223) == avo_ledger.derive_trial_seed(
        "0001", 926223
    )
    assert avo_ledger.derive_trial_seed("0001", 926223) != avo_ledger.derive_trial_seed(
        "0002", 926223
    )


def test_ledger_requires_canonical_encoding():
    entry = _entry()
    noncanonical = json.dumps(entry, separators=(", ", ": "))
    with pytest.raises(avo_ledger.AvoLedgerError, match="not canonical JSON"):
        avo_ledger.validate_ledger_text(
            noncanonical + "\n", manifest=MANIFEST, lane_id=LANE.lane_id
        )


def test_ledger_requires_mandatory_hash_chain():
    entry = _entry()
    entry["ledger_chain"] = {"prev_entry_sha256": "sha256:" + "f" * 64}
    with pytest.raises(avo_ledger.AvoLedgerError, match="hash chain"):
        _validate_lines(_canonical_line(entry))


def test_ledger_enforces_contiguous_sequence_and_manifest_branch_binding():
    first = _entry(sequence=1, experiment_id="0001")
    first_hash = avo_ledger.ledger_entry_line_sha256(first)
    second = _entry(sequence=2, experiment_id="0002", prev_hash=first_hash)
    ledger = _validate_lines(_canonical_line(first), _canonical_line(second))
    assert ledger.outcome_counts.completed == 2
    assert ledger.branch == LANE.branch
    assert ledger.manifest_sha256 == MANIFEST.manifest_sha256


def test_adversarial_duplicate_id_rejected():
    first = _entry(sequence=1, experiment_id="0001")
    first_hash = avo_ledger.ledger_entry_line_sha256(first)
    second = _entry(sequence=2, experiment_id="0001", prev_hash=first_hash)
    with pytest.raises(avo_ledger.AvoLedgerError, match="duplicate experiment_id"):
        _validate_lines(_canonical_line(first), _canonical_line(second))


def test_duplicate_id_allowed_for_atomic_rejection():
    first = _entry(sequence=1, experiment_id="0001")
    first_hash = avo_ledger.ledger_entry_line_sha256(first)
    second = _entry(
        sequence=2,
        experiment_id="0001",
        outcome="rejected",
        rejection={"reason_code": "duplicate_experiment_id", "atomic": True},
        prev_hash=first_hash,
    )
    ledger = _validate_lines(_canonical_line(first), _canonical_line(second))
    assert ledger.outcome_counts.rejected == 1


def test_crash_retention_and_replay_ambiguity():
    crashed = _entry(
        outcome="crashed",
        crash={
            "phase": "evaluate",
            "error_class": "TimeoutError",
            "retry_state": "retained",
        },
    )
    crash_hash = avo_ledger.ledger_entry_line_sha256(crashed)
    completion = _entry(
        sequence=2,
        experiment_id="0001",
        outcome="completed",
        prev_hash=crash_hash,
    )
    with pytest.raises(avo_ledger.AvoLedgerError, match="crash-retained"):
        _validate_lines(_canonical_line(crashed), _canonical_line(completion))


def test_crash_retry_with_retry_context():
    crashed = _entry(
        outcome="crashed",
        crash={
            "phase": "evaluate",
            "error_class": "TimeoutError",
            "retry_state": "retained",
        },
    )
    crash_hash = avo_ledger.ledger_entry_line_sha256(crashed)
    retry = _entry(
        sequence=2,
        experiment_id="0001",
        outcome="completed",
        prev_hash=crash_hash,
        retry_context={
            "prior_sequence": 1,
            "restart_generation": 1,
            "frozen_input_digest": DIGEST_D,
        },
    )
    ledger = _validate_lines(_canonical_line(crashed), _canonical_line(retry))
    assert ledger.outcome_counts.crashed == 1
    assert ledger.outcome_counts.completed == 1


def test_semantic_rejection_requires_atomic_flag():
    bad = _entry(
        outcome="rejected",
        rejection={"reason_code": "gate_violation", "atomic": True},
    )
    ledger = _validate_lines(_canonical_line(bad))
    assert ledger.outcome_counts.rejected == 1
    with pytest.raises(ValidationError):
        avo_ledger.LedgerEntry.model_validate(
            {
                **_entry(outcome="rejected"),
                "rejection": {"reason_code": "gate_violation", "atomic": False},
            }
        )


def test_recomputed_checkpoint_counters_match_ledger():
    kept = _entry(experiment_id="0003", outcome="kept")
    kept["trial"]["lineage_parent"] = LINEAGE_B
    ledger = _validate_lines(_canonical_line(kept))
    recomputed = avo_ledger.recompute_checkpoint(ledger, checkpoint_sequence=1)
    assert recomputed.counts == ledger.outcome_counts
    assert recomputed.ledger_entry_count == 1
    assert recomputed.last_experiment_id == "0003"
    assert recomputed.ledger_tail_sha256 == avo_ledger.ledger_entry_sha256_from_line(
        _canonical_line(kept)
    )


def test_adversarial_hash_not_content_rejected(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _write_git_file(repo, "README.md", "init\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")

    entry = _entry(experiment_id="0004", outcome="kept")
    entry["trial"]["lineage_parent"] = LINEAGE_B
    ledger = _validate_lines(_canonical_line(entry))
    checkpoint_rel = f"docs/avo/lanes/{LANE.lane_id}/checkpoints/cp-hash.json"
    head = _git(repo, "rev-parse", "HEAD")
    head_tree = _git(repo, "rev-parse", "HEAD^{tree}")
    body = _checkpoint_body(
        ledger=ledger,
        git_commit=head,
        git_tree=head_tree,
        path=checkpoint_rel,
        byte_length=1,
    )
    body["counts"] = {
        "completed": 999,
        "kept": 999,
        "discarded": 999,
        "crashed": 999,
        "rejected": 999,
        "indeterminate": 999,
    }
    body["ledger_tail_sha256"] = "sha256:" + "c" * 64
    publish = _commit_checkpoint_at_ref(repo, body, checkpoint_rel=checkpoint_rel)
    checkpoint = avo_ledger.parse_checkpoint(
        json.loads((repo / checkpoint_rel).read_text(encoding="utf-8"))
    )
    git = avo_ledger.GitAcceptanceContext(repo_root=repo, git_ref=publish)
    with pytest.raises(avo_ledger.AvoLedgerError, match="counts do not match"):
        avo_ledger.validate_checkpoint_payload(
            checkpoint,
            manifest=MANIFEST,
            git=git,
            ledger=ledger,
            on_disk_bytes=checkpoint.publication.byte_length,
        )


def test_supervisor_pause_close_resume_schema_valid():
    entry = _entry()
    ledger = _validate_lines(_canonical_line(entry))
    body = _checkpoint_body(
        ledger=ledger,
        git_commit=LINEAGE_A,
        git_tree=TREE_OID,
        path=f"docs/avo/lanes/{LANE.lane_id}/checkpoints/cp-supervisor.json",
        byte_length=1,
        supervisor_state={"campaign_pause": True, "resume_generation": 0},
    )
    parsed = avo_ledger.parse_checkpoint(body)
    avo_ledger.validate_supervisor_state(parsed.supervisor_state)
    body_bad = dict(body)
    body_bad["supervisor_state"] = {"campaign_pause": True, "lane_close": True}
    bad = avo_ledger.parse_checkpoint(body_bad)
    with pytest.raises(avo_ledger.AvoLedgerError, match="campaign_pause and lane_close"):
        avo_ledger.validate_supervisor_state(bad.supervisor_state)


def test_checkpoint_git_only_requires_tracked_provenance(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    manifest_rel = "docs/avo/trial-manifest.v1.json"
    _write_git_file(repo, manifest_rel, (REPO_ROOT / manifest_rel).read_text())
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "manifest")

    entry = _entry(experiment_id="0001")
    ledger_line = _canonical_line(entry)
    ledger_rel = f"docs/avo/lanes/{LANE.lane_id}/ledger.jsonl"
    _write_git_file(repo, ledger_rel, ledger_line + "\n")
    _git(repo, "add", ledger_rel)
    _git(repo, "commit", "-q", "-m", "ledger")

    manifest = avo_ledger.load_manifest_context(repo / manifest_rel)
    ledger = avo_ledger.validate_ledger_text(
        ledger_line + "\n", manifest=manifest, lane_id=LANE.lane_id
    )
    checkpoint_rel = f"docs/avo/lanes/{LANE.lane_id}/checkpoints/cp-0001.json"
    head = _git(repo, "rev-parse", "HEAD")
    head_tree = _git(repo, "rev-parse", "HEAD^{tree}")
    body = _checkpoint_body(
        ledger=ledger,
        git_commit=head,
        git_tree=head_tree,
        path=checkpoint_rel,
        byte_length=1,
    )
    publish_commit = _commit_checkpoint_at_ref(
        repo, body, checkpoint_rel=checkpoint_rel
    )

    accepted = avo_ledger.validate_checkpoint_git_only(
        repo / checkpoint_rel,
        repo_root=repo,
        git_ref=publish_commit,
        manifest=manifest,
        ledger_path=repo / ledger_rel,
    )
    assert accepted.lane_id == LANE.lane_id
    assert accepted.publication.git_commit == publish_commit


def test_adversarial_lane_identity_mismatch():
    entry = _entry(branch="fm/holusight-avo-mini-supervisor")
    with pytest.raises(avo_ledger.AvoLedgerError, match="branch"):
        _validate_lines(_canonical_line(entry))


def test_adversarial_schema_rejected_extra_property():
    entry = _entry()
    entry["telemetry"] = {"tokens": 1}
    with pytest.raises(ValidationError):
        avo_ledger.LedgerEntry.model_validate(entry)


def test_lineage_disagreement_rejected(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _write_git_file(repo, "README.md", "init\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")

    kept = _entry(experiment_id="0005", outcome="kept")
    kept["trial"]["lineage_parent"] = LINEAGE_B
    ledger = _validate_lines(_canonical_line(kept))
    checkpoint_rel = f"docs/avo/lanes/{LANE.lane_id}/checkpoints/cp-lineage.json"
    head = _git(repo, "rev-parse", "HEAD")
    head_tree = _git(repo, "rev-parse", "HEAD^{tree}")
    body = _checkpoint_body(
        ledger=ledger,
        git_commit=head,
        git_tree=head_tree,
        path=checkpoint_rel,
        byte_length=1,
        lineage_head=LINEAGE_A,
    )
    publish = _commit_checkpoint_at_ref(repo, body, checkpoint_rel=checkpoint_rel)
    checkpoint = avo_ledger.parse_checkpoint(
        json.loads((repo / checkpoint_rel).read_text(encoding="utf-8"))
    )
    git = avo_ledger.GitAcceptanceContext(repo_root=repo, git_ref=publish)
    with pytest.raises(avo_ledger.AvoLedgerError, match="lineage_head disagrees"):
        avo_ledger.validate_checkpoint_payload(
            checkpoint,
            manifest=MANIFEST,
            git=git,
            ledger=ledger,
            on_disk_bytes=checkpoint.publication.byte_length,
        )


def test_checkpoint_acceptance_fails_closed_without_git_context():
    entry = _entry()
    ledger = _validate_lines(_canonical_line(entry))
    body = _checkpoint_body(
        ledger=ledger,
        git_commit=LINEAGE_A,
        git_tree=TREE_OID,
        path=f"docs/avo/lanes/{LANE.lane_id}/checkpoints/cp-failclosed.json",
        byte_length=1,
    )
    body["publication"]["byte_length"] = len(avo_ledger.canonical_json_bytes(body))
    checkpoint = avo_ledger.parse_checkpoint(body)
    with pytest.raises(avo_ledger.AvoLedgerError, match="Git acceptance context required"):
        avo_ledger.validate_checkpoint_payload(
            checkpoint, manifest=MANIFEST, git=None
        )


def test_adversarial_stale_unpublished_rejected(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _write_git_file(repo, "README.md", "init\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")

    entry = _entry(experiment_id="0001")
    ledger = _validate_lines(_canonical_line(entry))
    checkpoint_rel = f"docs/avo/lanes/{LANE.lane_id}/checkpoints/cp-stale.json"
    head = _git(repo, "rev-parse", "HEAD")
    head_tree = _git(repo, "rev-parse", "HEAD^{tree}")
    body = _checkpoint_body(
        ledger=ledger,
        git_commit=head,
        git_tree=head_tree,
        path=checkpoint_rel,
        byte_length=1,
    )
    body["created_at"] = "2020-01-01T00:00:00Z"
    publish_commit = _commit_checkpoint_at_ref(
        repo, body, checkpoint_rel=checkpoint_rel
    )
    _write_git_file(repo, "README.md", "advance\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "advance tip")
    lane_tip = _git(repo, "rev-parse", "HEAD")

    stale = avo_ledger.parse_checkpoint(
        json.loads((repo / checkpoint_rel).read_text(encoding="utf-8"))
    )
    git_tip = avo_ledger.GitAcceptanceContext(repo_root=repo, git_ref=lane_tip)
    with pytest.raises(
        avo_ledger.AvoLedgerError, match="stale relative to acceptance git ref"
    ):
        avo_ledger.validate_checkpoint_freshness(stale, git=git_tip)

    with pytest.raises(
        avo_ledger.AvoLedgerError, match="stale relative to acceptance git ref"
    ):
        avo_ledger.validate_checkpoint_git_only(
            repo / checkpoint_rel,
            repo_root=repo,
            git_ref=lane_tip,
            manifest=MANIFEST,
        )

    git_publish = avo_ledger.GitAcceptanceContext(
        repo_root=repo, git_ref=publish_commit
    )
    avo_ledger.validate_checkpoint_freshness(stale, git=git_publish)


def test_adversarial_evaluator_digest_mismatch_rejected(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _write_git_file(repo, "README.md", "init\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")

    entry = _entry(experiment_id="0002")
    ledger_line = _canonical_line(entry)
    ledger_rel = f"docs/avo/lanes/{LANE.lane_id}/ledger.jsonl"
    _write_git_file(repo, ledger_rel, ledger_line + "\n")
    ledger = avo_ledger.validate_ledger_text(
        ledger_line + "\n", manifest=MANIFEST, lane_id=LANE.lane_id
    )
    checkpoint_rel = f"docs/avo/lanes/{LANE.lane_id}/checkpoints/cp-eval.json"
    head = _git(repo, "rev-parse", "HEAD")
    head_tree = _git(repo, "rev-parse", "HEAD^{tree}")
    body = _checkpoint_body(
        ledger=ledger,
        git_commit=head,
        git_tree=head_tree,
        path=checkpoint_rel,
        byte_length=1,
    )
    body["evaluator_identity_digest"] = "sha256:" + "e" * 64
    publish = _commit_checkpoint_at_ref(repo, body, checkpoint_rel=checkpoint_rel)
    checkpoint = avo_ledger.parse_checkpoint(
        json.loads((repo / checkpoint_rel).read_text(encoding="utf-8"))
    )
    git = avo_ledger.GitAcceptanceContext(repo_root=repo, git_ref=publish)
    with pytest.raises(
        avo_ledger.AvoLedgerError, match="evaluator_identity_digest mismatch"
    ):
        avo_ledger.validate_checkpoint_payload(
            checkpoint,
            manifest=MANIFEST,
            git=git,
            ledger=ledger,
            on_disk_bytes=checkpoint.publication.byte_length,
        )
