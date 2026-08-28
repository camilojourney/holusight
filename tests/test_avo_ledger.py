"""Tests for AVO ledger/checkpoint executable validation (remediation slice)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from codesight import avo_ledger

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "avo"

MANIFEST = avo_ledger.load_default_manifest_context(REPO_ROOT)
LANE = MANIFEST.lane_for_id("laptop-calibration-0001-0013")

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
LINEAGE = "d" * 40


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
        "lineage_parent": LINEAGE,
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
    prev_hash: str | None = None,
) -> dict:
    payload = {
        "schema_version": "holusight-avo-ledger/v1",
        "campaign_id": "holusight-avo-v1",
        "lane_id": LANE.lane_id,
        "sequence": sequence,
        "recorded_at": "2026-08-28T06:00:00Z",
        "experiment_id": experiment_id,
        "outcome": outcome,
        "trial": trial or _trial(experiment_id=experiment_id),
    }
    if crash is not None:
        payload["crash"] = crash
    if rejection is not None:
        payload["rejection"] = rejection
    if prev_hash is not None or sequence > 1:
        payload["ledger_chain"] = {
            "prev_entry_sha256": prev_hash or avo_ledger._GENESIS_PREV,
        }
    return payload


def _ledger_line(entry: dict) -> str:
    return json.dumps(entry, separators=(",", ":"))


def _write_git_file(repo: Path, relative: str, content: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _init_repo(repo: Path) -> None:
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "avo-ledger@example.test")
    _git(repo, "config", "user.name", "AVO Ledger Test")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def test_manifest_self_hash_verifies():
    loaded = avo_ledger.load_default_manifest_context(REPO_ROOT)
    assert loaded.manifest_sha256.startswith("sha256:")
    assert loaded.deterministic_seeds.global_seed == 926223


def test_derive_trial_seed_is_deterministic():
    seed_a = avo_ledger.derive_trial_seed("0001", 926223)
    seed_b = avo_ledger.derive_trial_seed("0001", 926223)
    seed_other = avo_ledger.derive_trial_seed("0002", 926223)
    assert seed_a == seed_b
    assert seed_a != seed_other


def test_ledger_entry_requires_canonical_trial_fields():
    entry = _entry()
    validated = avo_ledger.validate_ledger_text(
        _ledger_line(entry) + "\n",
        manifest=MANIFEST,
        lane_id=LANE.lane_id,
    )
    assert validated.outcome_counts.completed == 1
    assert validated.experiment_ids == frozenset({"0001"})


def test_ledger_rejects_wrong_seed_allocation():
    bad = _entry(trial=_trial(experiment_id="0001", seed=12345))
    with pytest.raises(avo_ledger.AvoLedgerError, match="deterministic allocation"):
        avo_ledger.validate_ledger_text(
            _ledger_line(bad) + "\n",
            manifest=MANIFEST,
            lane_id=LANE.lane_id,
        )


def test_ledger_rejects_experiment_id_outside_lane_range():
    bad = _entry(experiment_id="9999")
    with pytest.raises(avo_ledger.AvoLedgerError, match="outside lane range"):
        avo_ledger.validate_ledger_text(
            _ledger_line(bad) + "\n",
            manifest=MANIFEST,
            lane_id=LANE.lane_id,
        )


def test_ledger_rejects_missing_protected_gates():
    trial = _trial()
    trial["protected_gates"] = ["gate.g2.blocked"]
    bad = _entry(trial=trial)
    with pytest.raises(avo_ledger.AvoLedgerError, match="missing manifest protected_gates"):
        avo_ledger.validate_ledger_text(
            _ledger_line(bad) + "\n",
            manifest=MANIFEST,
            lane_id=LANE.lane_id,
        )


def test_ledger_duplicate_prevention_allows_explicit_rejection():
    first = _entry(sequence=1, experiment_id="0001", outcome="completed")
    first_hash = avo_ledger.ledger_entry_line_sha256(first)
    duplicate = _entry(
        sequence=2,
        experiment_id="0001",
        outcome="rejected",
        rejection={"reason_code": "duplicate_experiment_id"},
        prev_hash=first_hash,
    )
    text = _ledger_line(first) + "\n" + _ledger_line(duplicate) + "\n"
    validated = avo_ledger.validate_ledger_text(
        text, manifest=MANIFEST, lane_id=LANE.lane_id
    )
    assert validated.outcome_counts.rejected == 1
    assert validated.outcome_counts.completed == 1


def test_ledger_duplicate_prevention_blocks_silent_reuse():
    first = _entry(sequence=1, experiment_id="0002", outcome="completed")
    first_hash = avo_ledger.ledger_entry_line_sha256(first)
    second = _entry(
        sequence=2,
        experiment_id="0002",
        outcome="discarded",
        prev_hash=first_hash,
    )
    text = _ledger_line(first) + "\n" + _ledger_line(second) + "\n"
    with pytest.raises(avo_ledger.AvoLedgerError, match="duplicate experiment_id"):
        avo_ledger.validate_ledger_text(
            text, manifest=MANIFEST, lane_id=LANE.lane_id
        )


def test_ledger_crash_retention_requires_crash_block():
    bad = _entry(outcome="crashed")
    with pytest.raises(ValidationError):
        avo_ledger.LedgerEntry.model_validate(bad)


def test_ledger_retains_crashed_outcome_in_counts():
    crashed = _entry(
        outcome="crashed",
        crash={"phase": "evaluate", "error_class": "TimeoutError"},
    )
    validated = avo_ledger.validate_ledger_text(
        _ledger_line(crashed) + "\n",
        manifest=MANIFEST,
        lane_id=LANE.lane_id,
    )
    assert validated.outcome_counts.crashed == 1
    assert validated.crashed_experiment_ids == frozenset({"0001"})


def test_ledger_rejects_self_referencing_matched_control():
    trial = _trial(experiment_id="0003")
    trial["control"] = {"kind": "parent_lineage", "digest": DIGEST_B}
    trial["lineage_parent"] = "0003"
    bad = _entry(experiment_id="0003", trial=trial)
    with pytest.raises(avo_ledger.AvoLedgerError, match="self-reference"):
        avo_ledger.validate_ledger_text(
            _ledger_line(bad) + "\n",
            manifest=MANIFEST,
            lane_id=LANE.lane_id,
        )


def test_checkpoint_payload_matches_ledger_tail_and_counts():
    entry = _entry(experiment_id="0004", outcome="kept")
    ledger_text = _ledger_line(entry)
    ledger = avo_ledger.validate_ledger_text(
        ledger_text + "\n",
        manifest=MANIFEST,
        lane_id=LANE.lane_id,
    )
    checkpoint = {
        "schema_version": "holusight-avo-checkpoint/v1",
        "campaign_id": "holusight-avo-v1",
        "lane_id": LANE.lane_id,
        "branch": LANE.branch,
        "checkpoint_sequence": 1,
        "created_at": "2026-08-28T06:10:00Z",
        "manifest_sha256": MANIFEST.manifest_sha256,
        "last_experiment_id": "0004",
        "lineage_head": LINEAGE,
        "evaluator_identity_digest": DIGEST_C,
        "counts": ledger.outcome_counts.model_dump(),
        "ledger_tail_sha256": avo_ledger.ledger_entry_sha256_from_line(ledger_text),
    }
    parsed = avo_ledger.parse_checkpoint(checkpoint)
    avo_ledger.validate_checkpoint_payload(
        parsed, manifest=MANIFEST, ledger=ledger
    )


def test_checkpoint_rejects_forbidden_keys():
    entry = _entry(experiment_id="0005")
    ledger = avo_ledger.validate_ledger_text(
        _ledger_line(entry) + "\n",
        manifest=MANIFEST,
        lane_id=LANE.lane_id,
    )
    checkpoint = {
        "schema_version": "holusight-avo-checkpoint/v1",
        "campaign_id": "holusight-avo-v1",
        "lane_id": LANE.lane_id,
        "branch": LANE.branch,
        "checkpoint_sequence": 1,
        "created_at": "2026-08-28T06:10:00Z",
        "manifest_sha256": MANIFEST.manifest_sha256,
        "last_experiment_id": "0005",
        "lineage_head": LINEAGE,
        "evaluator_identity_digest": DIGEST_C,
        "counts": ledger.outcome_counts.model_dump(),
        "ledger_tail_sha256": avo_ledger.ledger_entry_line_sha256(entry),
        "telemetry": {"tokens": 1},
    }
    with pytest.raises(avo_ledger.AvoLedgerError, match="schema invalid"):
        avo_ledger.parse_checkpoint(checkpoint)


def test_checkpoint_git_only_requires_tracked_file(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    manifest_rel = "docs/avo/trial-manifest.v1.json"
    _write_git_file(repo, manifest_rel, (REPO_ROOT / manifest_rel).read_text())
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "manifest")

    lane_id = "laptop-calibration-0001-0013"
    entry = _entry(experiment_id="0001")
    ledger_line = _ledger_line(entry)
    ledger_rel = f"docs/avo/lanes/{lane_id}/ledger.jsonl"
    _write_git_file(repo, ledger_rel, ledger_line + "\n")

    checkpoint_rel = f"docs/avo/lanes/{lane_id}/checkpoints/cp-0001.json"
    ledger_line = _ledger_line(entry)
    ledger = avo_ledger.validate_ledger_text(
        ledger_line + "\n",
        manifest=avo_ledger.load_manifest_context(repo / manifest_rel),
        lane_id=lane_id,
    )
    checkpoint_body = {
        "schema_version": "holusight-avo-checkpoint/v1",
        "campaign_id": "holusight-avo-v1",
        "lane_id": lane_id,
        "branch": LANE.branch,
        "checkpoint_sequence": 1,
        "created_at": "2026-08-28T06:10:00Z",
        "manifest_sha256": MANIFEST.manifest_sha256,
        "last_experiment_id": "0001",
        "lineage_head": LINEAGE,
        "evaluator_identity_digest": DIGEST_C,
        "counts": ledger.outcome_counts.model_dump(),
        "ledger_tail_sha256": avo_ledger.ledger_entry_sha256_from_line(ledger_line),
    }
    _write_git_file(
        repo,
        checkpoint_rel,
        json.dumps(checkpoint_body, separators=(",", ":")),
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "checkpoint")

    manifest = avo_ledger.load_manifest_context(repo / manifest_rel)
    accepted = avo_ledger.validate_checkpoint_git_only(
        repo / checkpoint_rel,
        repo_root=repo,
        git_ref="HEAD",
        manifest=manifest,
        ledger_path=repo / ledger_rel,
    )
    assert accepted.lane_id == lane_id


def test_checkpoint_git_only_rejects_untracked_file(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    manifest_rel = "docs/avo/trial-manifest.v1.json"
    _write_git_file(repo, manifest_rel, (REPO_ROOT / manifest_rel).read_text())
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "manifest")

    checkpoint_rel = "docs/avo/lanes/laptop-calibration-0001-0013/checkpoints/cp-0001.json"
    entry = _entry()
    ledger = avo_ledger.validate_ledger_text(
        _ledger_line(entry) + "\n",
        manifest=MANIFEST,
        lane_id=LANE.lane_id,
    )
    checkpoint_body = {
        "schema_version": "holusight-avo-checkpoint/v1",
        "campaign_id": "holusight-avo-v1",
        "lane_id": LANE.lane_id,
        "branch": LANE.branch,
        "checkpoint_sequence": 1,
        "created_at": "2026-08-28T06:10:00Z",
        "manifest_sha256": MANIFEST.manifest_sha256,
        "last_experiment_id": "0001",
        "lineage_head": LINEAGE,
        "evaluator_identity_digest": DIGEST_C,
        "counts": ledger.outcome_counts.model_dump(),
        "ledger_tail_sha256": avo_ledger.ledger_entry_line_sha256(entry),
    }
    _write_git_file(
        repo,
        checkpoint_rel,
        json.dumps(checkpoint_body, separators=(",", ":")),
    )

    with pytest.raises(avo_ledger.AvoLedgerError, match="not tracked in Git"):
        avo_ledger.validate_checkpoint_git_only(
            repo / checkpoint_rel,
            repo_root=repo,
            git_ref="HEAD",
            manifest=MANIFEST,
        )


def test_fixture_ledger_sample_if_present():
    sample = FIXTURES / "sample-ledger.jsonl"
    if not sample.exists():
        pytest.skip("fixture not written")
    avo_ledger.validate_ledger_file(
        sample, manifest=MANIFEST, lane_id=LANE.lane_id
    )
