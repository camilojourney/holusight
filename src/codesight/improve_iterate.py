"""Iterative advisory improve loop over proper-eval (ADR-0019).

Each call:
1. Runs ``proper_eval.run_proper_eval`` (visible surfaces only).
2. Compares against the previous local iteration receipt (if any).
3. Writes a new receipt under ``.holusight/improvement-runs/proper-eval-iterations/``.
4. Emits ``progress`` + ``next_action`` for a human or agent to act on.

Promotion is always denied. This loop does not edit source, admit cases,
merge PRs, or launch research — it measures and directs the next human/
agent iteration.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from .control_storage import HISTORY_ROOT, UnsafeStoragePath, safe_atomic_write
from .proper_eval import REPO_ROOT, run_proper_eval

SCHEMA = "holusight-improve-iterate-result/v1"
ITERATE_DIR = HISTORY_ROOT / "proper-eval-iterations"
LATEST_NAME = "latest.json"
Progress = Literal["baseline", "improved", "stagnated", "regressed", "blocked", "indeterminate"]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _surface_passed(payload: dict[str, Any], name: str) -> int | None:
    for surface in payload.get("surfaces") or []:
        if surface.get("name") == name:
            counts = surface.get("counts") or {}
            if "passed" in counts and "total" in counts:
                return int(counts["passed"])
            if name == "fleet-smoke":
                return int(counts.get("passed", 0))
            return int(counts.get("passed", 0))
    return None


def _pilot_rate(payload: dict[str, Any]) -> float | None:
    for surface in payload.get("surfaces") or []:
        if surface.get("name") != "eval-pilot":
            continue
        counts = surface.get("counts") or {}
        total = int(counts.get("total") or 0)
        if total <= 0:
            return None
        return int(counts.get("passed") or 0) / total
    return None


def compare_iterations(current: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    """Advisory comparison of two proper-eval payloads."""
    if previous is None:
        return {
            "progress": "baseline",
            "reason": "no prior iteration receipt",
            "next_action": "implement_candidate_then_rerun",
            "research_needed": False,
        }

    cur_v = current.get("verdict")
    prev_v = previous.get("verdict")
    cur_rate = _pilot_rate(current)
    prev_rate = _pilot_rate(previous)

    if cur_v == "block":
        return {
            "progress": "blocked",
            "reason": current.get("reason") or "current proper-eval blocked",
            "next_action": "fix_failing_surface_then_rerun",
            "research_needed": True,
        }
    if cur_v == "indeterminate":
        return {
            "progress": "indeterminate",
            "reason": current.get("reason") or "current subject dirty/unbound",
            "next_action": "commit_or_clean_tree_then_rerun",
            "research_needed": False,
        }
    if prev_v == "block" and cur_v == "pass":
        return {
            "progress": "improved",
            "reason": "recovered from blocked to pass",
            "next_action": "admit_regression_case_if_gap_found",
            "research_needed": False,
        }
    if cur_rate is not None and prev_rate is not None:
        if cur_rate > prev_rate:
            return {
                "progress": "improved",
                "reason": f"pilot pass rate {prev_rate:.3f} -> {cur_rate:.3f}",
                "next_action": "human_review_candidate_then_continue",
                "research_needed": False,
            }
        if cur_rate < prev_rate:
            return {
                "progress": "regressed",
                "reason": f"pilot pass rate {prev_rate:.3f} -> {cur_rate:.3f}",
                "next_action": "rollback_or_isolate_regression",
                "research_needed": True,
            }
    if cur_v == prev_v == "pass":
        return {
            "progress": "stagnated",
            "reason": "pass rate unchanged on visible surfaces",
            "next_action": "improve_intake_new_case_or_research",
            "research_needed": True,
        }
    return {
        "progress": "indeterminate",
        "reason": "insufficient comparable surface metrics",
        "next_action": "rerun_with_clean_subject",
        "research_needed": False,
    }


def _load_latest(repo_root: Path) -> dict[str, Any] | None:
    path = repo_root / ITERATE_DIR / LATEST_NAME
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    eval_payload = payload.get("proper_eval")
    return eval_payload if isinstance(eval_payload, dict) else None


def run_improve_iterate(
    repo_root: Path,
    *,
    skip_smoke: bool = False,
    record: bool = True,
) -> dict[str, Any]:
    previous_eval = _load_latest(repo_root)
    current_eval = run_proper_eval(repo_root, skip_smoke=skip_smoke)
    comparison = compare_iterations(current_eval, previous_eval)
    iteration_id = (
        f"iter-{current_eval.get('subject', {}).get('commit', 'unknown')[:12]}-"
        f"{_now().replace(':', '').replace('-', '')}"
    )
    result: dict[str, Any] = {
        "schema_version": SCHEMA,
        "iteration_id": iteration_id,
        "recorded_at": _now(),
        "promotion": {
            "allowed": False,
            "status": "denied",
            "reason": "ADR-0019 — iterative loop is advisory; humans own promotion",
        },
        "progress": comparison["progress"],
        "reason": comparison["reason"],
        "next_action": comparison["next_action"],
        "research_needed": comparison["research_needed"],
        "proper_eval": current_eval,
        "had_prior_iteration": previous_eval is not None,
        "loop": {
            "measures": ["suite_bind", "fleet-smoke", "eval-pilot"],
            "auto_edits_source": False,
            "auto_admits_cases": False,
            "auto_merges": False,
            "hidden_holdout_scored": False,
        },
    }

    if record:
        body = json.dumps(result, sort_keys=True, indent=2).encode("utf-8")
        stamped = ITERATE_DIR / f"{iteration_id}.json"
        latest = ITERATE_DIR / LATEST_NAME
        try:
            safe_atomic_write(repo_root, stamped, body, allowed_repo_root=HISTORY_ROOT)
            safe_atomic_write(repo_root, latest, body, allowed_repo_root=HISTORY_ROOT)
            result["receipts"] = {
                "iteration": str(stamped.as_posix()),
                "latest": str(latest.as_posix()),
            }
        except UnsafeStoragePath as exc:
            result["receipts"] = {"error": str(exc)}

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Holusight advisory improve-iterate loop")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--skip-smoke", action="store_true")
    parser.add_argument("--no-record", action="store_true")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    payload = run_improve_iterate(
        args.repo_root.resolve(),
        skip_smoke=args.skip_smoke,
        record=not args.no_record,
    )
    print(json.dumps(payload, sort_keys=True, indent=2))
    progress = payload["progress"]
    if progress in {"blocked", "regressed"}:
        return 1
    if progress == "indeterminate":
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
