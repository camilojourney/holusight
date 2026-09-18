"""Local/advisory named-suite orchestration (ADR-0019).

Loads the versioned suite identity (spec 022), binds an EvaluationSubject
(spec 021), and runs the *visible* offline surfaces already on master
(fleet-smoke + eval-pilot). Hidden-holdout payloads are never read.

This is **not** the G2 trusted-sandbox evaluator. Suite manifests may still
say ``runner: not_implemented`` / ``blocked_until_g2_trusted_sandbox`` for
that path. This module is the advisory finish-line runner captains can run
today with promotion always denied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from . import eval_suite
from .eval_pilot import (
    CandidateLineage,
    PilotRunResult,
    _current_subject,  # subject binding; not a public judge knobs
    run_pilot,
)
from .fleet_scorecard import _run_smoke_suite

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "holusight-proper-eval-result/v1"
JUDGE_ID = "codesight.proper_eval/advisory-v1"
Verdict = Literal["pass", "block", "indeterminate"]


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class SurfaceResult:
    name: str
    verdict: Verdict
    detail: str
    counts: dict[str, int] | None = None


def _pilot_verdict(result: PilotRunResult) -> SurfaceResult:
    if result.counts.errored or result.counts.failed:
        return SurfaceResult(
            name="eval-pilot",
            verdict="block",
            detail=(
                f"pilot failed_or_errored "
                f"passed={result.counts.passed} failed={result.counts.failed} "
                f"errored={result.counts.errored}"
            ),
            counts=result.counts.model_dump(),
        )
    return SurfaceResult(
        name="eval-pilot",
        verdict="pass",
        detail=f"pilot all passed total={result.counts.total}",
        counts=result.counts.model_dump(),
    )


def _smoke_verdict(returncode: int, counts: dict[str, int]) -> SurfaceResult:
    if returncode != 0 or counts.get("failed", 0) or counts.get("errors", 0):
        return SurfaceResult(
            name="fleet-smoke",
            verdict="block",
            detail=f"smoke exit={returncode} counts={counts}",
            counts=counts,
        )
    return SurfaceResult(
        name="fleet-smoke",
        verdict="pass",
        detail=f"smoke passed counts={counts}",
        counts=counts,
    )


def _aggregate(
    *,
    suite_ok: bool,
    suite_detail: str,
    subject_clean: bool,
    surfaces: list[SurfaceResult],
) -> tuple[Verdict, str]:
    if not suite_ok:
        return "block", suite_detail
    if any(s.verdict == "block" for s in surfaces):
        blocked = [s.name for s in surfaces if s.verdict == "block"]
        return "block", "blocked_surfaces=" + ",".join(blocked)
    if not subject_clean:
        return (
            "indeterminate",
            "visible surfaces passed but EvaluationSubject is dirty or unbound; "
            "advisory only — promotion denied",
        )
    return "pass", "advisory_named_suite_surfaces_passed"


def run_proper_eval(
    repo_root: Path,
    *,
    suite_id: str = eval_suite.DEFAULT_SUITE_ID,
    skip_smoke: bool = False,
) -> dict[str, Any]:
    """Run advisory proper-eval. Never reads hidden-holdout payloads."""
    judge_path = Path(__file__).resolve()
    judge_digest = _sha256_file(judge_path)

    suite_ok = True
    suite_detail = "suite_loaded"
    loaded: eval_suite.LoadedSuite | None = None
    try:
        loaded = eval_suite.load_suite(repo_root, suite_id)
    except eval_suite.SuiteError as exc:
        suite_ok = False
        suite_detail = f"suite_load_failed: {exc}"

    subject = _current_subject(repo_root)
    surfaces: list[SurfaceResult] = []

    if suite_ok and loaded is not None:
        if skip_smoke:
            surfaces.append(
                SurfaceResult(
                    name="fleet-smoke",
                    verdict="indeterminate",
                    detail="skipped_by_flag",
                )
            )
        else:
            code, counts = _run_smoke_suite()
            surfaces.append(_smoke_verdict(code, counts))

        lineage = CandidateLineage(
            candidate_id="proper-eval-advisory",
            repo_commit=subject.commit,
            workflow="proper-eval",
            tool=JUDGE_ID,
            model=None,
            repo_dirty=not subject.clean,
            evaluator_digest=judge_digest,
        )
        pilot = run_pilot(
            repo_root,
            lineage=lineage,
            allow_egress=False,
            allow_semantic=False,
        )
        surfaces.append(_pilot_verdict(pilot))

    # If smoke was skipped, treat that surface as non-blocking for aggregate
    # only when other surfaces exist — skip_smoke is for fast unit tests.
    effective = [
        s for s in surfaces if not (s.name == "fleet-smoke" and s.detail == "skipped_by_flag")
    ]
    if not effective and surfaces:
        effective = surfaces

    verdict, reason = _aggregate(
        suite_ok=suite_ok,
        suite_detail=suite_detail,
        subject_clean=bool(subject.clean and subject.commit and subject.tree),
        surfaces=effective,
    )

    payload: dict[str, Any] = {
        "schema_version": SCHEMA,
        "recorded_at": _now(),
        "suite_id": suite_id,
        "verdict": verdict,
        "reason": reason,
        "promotion": {
            "allowed": False,
            "status": "denied",
            "reason": "ADR-0019 local/advisory evaluator; no autonomous promote/merge/deploy",
        },
        "judge": {
            "id": JUDGE_ID,
            "digest": judge_digest,
            "selectable_by_candidate": False,
            "kind": "local_advisory",
            "g2_trusted_sandbox": False,
        },
        "subject": subject.model_dump(mode="json"),
        "suite": None
        if loaded is None
        else {
            "suite_sha256": loaded.suite_sha256,
            "method_sha256": loaded.method_sha256,
            "holdout_manifest_sha256": loaded.holdout_manifest_sha256,
            "development_sha256": loaded.development_sha256,
            "manifest_status": loaded.suite.status,
            "manifest_runner": loaded.suite.runner,
            "manifest_evaluator_execution": loaded.suite.evaluator_execution,
            "manifest_promotion": loaded.suite.promotion,
        },
        "surfaces": [
            {
                "name": s.name,
                "verdict": s.verdict,
                "detail": s.detail,
                "counts": s.counts,
            }
            for s in surfaces
        ],
        "hidden_holdout": {
            "scored": False,
            "status": "deferred",
            "reason": "payload absent; G2 trusted sandbox still blocked (spec 022)",
        },
    }
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Holusight advisory proper-eval runner")
    parser.add_argument("--suite-id", default=eval_suite.DEFAULT_SUITE_ID)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Skip fleet-smoke (tests / fast path only)",
    )
    parser.add_argument("--format", choices=("json",), default="json")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    payload = run_proper_eval(
        args.repo_root.resolve(),
        suite_id=args.suite_id,
        skip_smoke=args.skip_smoke,
    )
    print(json.dumps(payload, sort_keys=True, indent=2))
    verdict = payload["verdict"]
    if verdict == "pass":
        return 0
    if verdict == "indeterminate":
        return 3
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
