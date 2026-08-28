#!/usr/bin/env python3
"""Read-only pre-launch checker for Mini's advisory experiment setup.

This intentionally has no lane-launch or trial-execution command. A separate,
independently reviewed tracked change must replace the pre-launch blockers.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

CONFIG_PATH = Path("autoresearch/mini-program-v1.json")
MINIMUM_FREE_DISK_BYTES = 2 * 1024**3
LAPTOP_CHECKPOINT_PREFIX = "refs/remotes/origin/fm/holusight-avo-laptop-"
LAPTOP_PHASE_A_REFS = [
    f"{LAPTOP_CHECKPOINT_PREFIX}calibration-0001-0013",
    f"{LAPTOP_CHECKPOINT_PREFIX}calibration-0014-0026",
    f"{LAPTOP_CHECKPOINT_PREFIX}calibration-0027-0038",
    f"{LAPTOP_CHECKPOINT_PREFIX}calibration-0039-0050",
]
LAPTOP_PHASE_B_REFS = [
    f"{LAPTOP_CHECKPOINT_PREFIX}product-0051-0107",
    f"{LAPTOP_CHECKPOINT_PREFIX}product-0108-0164",
    f"{LAPTOP_CHECKPOINT_PREFIX}product-0165-0220",
    f"{LAPTOP_CHECKPOINT_PREFIX}product-0221-0276",
    f"{LAPTOP_CHECKPOINT_PREFIX}product-0277-0332",
    f"{LAPTOP_CHECKPOINT_PREFIX}product-0333-0388",
    f"{LAPTOP_CHECKPOINT_PREFIX}product-0389-0444",
    f"{LAPTOP_CHECKPOINT_PREFIX}product-0445-0500",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _repo_file(path: Path, repo_root: Path) -> Path:
    """Resolve a user-supplied read path without permitting repository escape."""
    resolved = path.resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError("input path must remain inside the repository") from exc
    return resolved


def _completed_ids(results_path: Path | None, repo_root: Path) -> set[str]:
    if results_path is None:
        return set()
    resolved = _repo_file(results_path, repo_root)
    if not resolved.is_file():
        raise ValueError("results.tsv must be a regular file")
    with resolved.open(newline="", encoding="utf-8") as results_file:
        return {row["trial_id"] for row in csv.DictReader(results_file) if row.get("trial_id")}


def validate_trial(
    record_path: Path, results_path: Path | None, config: dict[str, Any], repo_root: Path
) -> list[str]:
    """Return reasons a proposed trial must not become a counted row."""
    record_file = _repo_file(record_path, repo_root)
    if not record_file.is_file():
        raise ValueError("trial record must be a regular file")
    record = json.loads(record_file.read_text(encoding="utf-8"))
    errors = [
        f"missing_{field}"
        for field in config["trial_record"]["required_fields"]
        if record.get(field) in (None, "", [], {})
    ]
    trial_id = record.get("trial_id")
    if not isinstance(trial_id, str) or not re.fullmatch(r"\d{4}", trial_id):
        errors.append("trial_id_must_be_four_digits")
    elif not 501 <= int(trial_id) <= 1000:
        errors.append("trial_id_out_of_mini_range")
    elif trial_id in _completed_ids(results_path, repo_root):
        errors.append("duplicate_completed_trial_id")
    if record.get("phase") != "B":
        errors.append("mini_trials_must_be_phase_B")
    intervention = record.get("intervention")
    if not isinstance(intervention, str) or not intervention.strip():
        errors.append("exactly_one_nonempty_intervention_required")
    for field in ("subject_sha256", "evaluator_sha256", "manifest_sha256"):
        value = record.get(field)
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            errors.append(f"invalid_{field}")
    if not isinstance(record.get("seed"), int) or isinstance(record.get("seed"), bool):
        errors.append("seed_must_be_an_integer")
    wall_time = record.get("wall_time_seconds")
    if not isinstance(wall_time, (int, float)) or wall_time < 0:
        errors.append("wall_time_seconds_must_be_nonnegative")
    if not isinstance(record.get("metrics"), dict):
        errors.append("metrics_must_be_an_object")
    if record.get("status") != config["trial_record"]["counting_status"]:
        errors.append("status_must_be_recorded_to_count")
    if record.get("outcome") not in config["trial_record"]["outcomes"]:
        errors.append("invalid_outcome")
    return errors


def check(config_path: Path, repo_root: Path) -> dict[str, Any]:
    """Validate only frozen, visible setup material; never create lane state."""
    config = json.loads(config_path.read_text(encoding="utf-8"))
    blockers = [
        item["input_id"]
        for item in config["prelaunch_blockers"]
        if item["state"].startswith("blocked_") or not item["immutable_hash"]
    ]
    errors: list[str] = []
    if config["review_gate"] != "approved_independent_read_only_review":
        errors.append("independent_read_only_review_required")
    if config["machine"]["owned_trial_id_range"] != [501, 1000]:
        errors.append("mini_must_own_only_0501_1000")
    if config["local_storage"]["max_lanes"] > 4:
        errors.append("lane_limit_exceeds_four")
    if config["local_storage"]["minimum_free_disk_bytes"] < MINIMUM_FREE_DISK_BYTES:
        errors.append("free_disk_floor_below_2_gib")
    if config["local_storage"]["run_log"]["mode"] != "overwrite":
        errors.append("run_logs_must_be_overwritten")
    if not config["local_storage"]["run_log"]["tee_forbidden"]:
        errors.append("tee_must_be_forbidden")
    disk_free = shutil.disk_usage(repo_root).free
    if disk_free < MINIMUM_FREE_DISK_BYTES:
        errors.append("local_disk_below_2_gib_floor")

    phase_a = config["phases"]["A"]
    phase_b = config["phases"]["B"]
    phase_a_bucket_count = sum(
        item["count"] for item in phase_a["metaevaluation_buckets"]
    )
    if phase_a["trial_count"] != 100 or phase_a_bucket_count != 100:
        errors.append("phase_a_must_be_exactly_100_trials")
    phase_b_ranges = [item["trial_id_range"] for item in phase_b["partitions"]]
    if (
        phase_b["trial_count"] != 900
        or [item["count"] for item in phase_b["partitions"]] != [225] * 4
        or phase_b_ranges != [[101, 325], [326, 550], [551, 775], [776, 1000]]
    ):
        errors.append("phase_b_must_be_four_deterministic_partitions_of_225")
    if len(config["trial_record"]["required_fields"]) < 21:
        errors.append("trial_record_schema_incomplete")

    laptop_checkpoints = config["cross_machine"]["laptop_checkpoints"]
    if (
        laptop_checkpoints["transport"] != "ordinary-git-only"
        or laptop_checkpoints["namespace_prefix"] != LAPTOP_CHECKPOINT_PREFIX
        or laptop_checkpoints["poll_interval_minutes"] != 15
        or laptop_checkpoints["phase_A_refs"] != LAPTOP_PHASE_A_REFS
        or laptop_checkpoints["phase_B_refs"] != LAPTOP_PHASE_B_REFS
    ):
        errors.append("captain_laptop_checkpoint_contract_mismatch")
    missing_ref = laptop_checkpoints["missing_ref_before_first_ten_trial_checkpoint"]
    if (
        missing_ref["meaning"] != "not-yet-published"
        or missing_ref["completed_ids"] != 0
        or missing_ref["duplicate_id_authority"] != "none"
    ):
        errors.append("missing_laptop_ref_must_not_grant_duplicate_authority")

    return {
        "schema_version": "holusight-advisory-prelaunch-check-v1",
        "mode": "read-only-prelaunch-check",
        "config_sha256": _sha256(config_path),
        "disk_free_bytes": disk_free,
        "launch_authorized": not blockers and not errors,
        "hard_blockers": blockers,
        "validation_errors": errors,
        "next_step": "independent read-only review; do not launch a lane",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Mini's frozen local-only setup.")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument(
        "--validate-trial",
        type=Path,
        help="read and reject/accept a proposed row without writing or launching",
    )
    parser.add_argument(
        "--results",
        type=Path,
        help="optional untracked append-only results.tsv used only to reject duplicates",
    )
    args = parser.parse_args()
    repo_root = Path.cwd().resolve()
    config_path = _repo_file(args.config, repo_root)
    result = check(config_path, repo_root)
    if args.validate_trial:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        result["trial_validation_errors"] = validate_trial(
            args.validate_trial, args.results, config, repo_root
        )
        result["counting_allowed"] = (
            result["launch_authorized"] and not result["trial_validation_errors"]
        )
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["launch_authorized"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
