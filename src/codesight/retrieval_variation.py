"""Controlled, local evidence-routing variation program.

This is a narrow extension of the existing ``holus improve-*`` control plane,
not a second workflow engine.  It evaluates two fixed display strategies over a
frozen, synthetic benchmark.  Candidate definitions, the legacy baseline,
and every input fixture are content-addressed.  It never calls a model, opens a
network connection, changes production routing, or promotes a candidate.

Only privacy-safe aggregate counts and stable fixture identifiers are persisted
when an operator explicitly requests a derived record.  Canonical truth remains
reviewed source, fixtures, and improvement-control manifests.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .control_storage import HISTORY_ROOT, UnsafeStoragePath, safe_atomic_write

SCHEMA_BENCHMARK = "holusight-retrieval-variation-benchmark/v1"
SCHEMA_RUN = "holusight-retrieval-variation-run/v1"
SCHEMA_RECORD = "holusight-retrieval-variation-record/v1"
BENCHMARK_PATH = Path("tests/fixtures/holusight_retrieval_variation_benchmark.json")
PROGRAM_HISTORY_ROOT = HISTORY_ROOT / "retrieval-variation"
PROVIDERS = ("exact", "structural", "consistency", "semantic")
MINIMUM_PRACTICAL_DELTA = 0.05
MAX_SIGN_TEST_P_VALUE = 0.05
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")


@dataclass(frozen=True)
class Strategy:
    """An immutable candidate definition, never executable user input."""

    candidate_id: str
    variable: str
    description: str
    select: Callable[[dict[str, int], int], list[str]]


def _legacy_concatenate(counts: dict[str, int], cap: int) -> list[str]:
    return [provider for provider in PROVIDERS for _ in range(counts.get(provider, 0))][:cap]


def _round_robin(counts: dict[str, int], cap: int) -> list[str]:
    remaining = {provider: counts.get(provider, 0) for provider in PROVIDERS}
    selected: list[str] = []
    while len(selected) < cap and any(remaining.values()):
        for provider in PROVIDERS:
            if remaining[provider] <= 0:
                continue
            selected.append(provider)
            remaining[provider] -= 1
            if len(selected) == cap:
                break
    return selected


def _equal_quota_without_redistribution(counts: dict[str, int], cap: int) -> list[str]:
    """A deliberately bounded alternate: only redistribution is disabled.

    It is a real controlled candidate, retained even though the benchmark can
    reject it for leaving capacity unused.  It never becomes production code.
    """
    active = [provider for provider in PROVIDERS if counts.get(provider, 0)]
    if not active:
        return []
    quota = max(1, cap // len(active))
    return [
        provider
        for provider in PROVIDERS
        for _ in range(min(counts.get(provider, 0), quota))
    ][:cap]


BASELINE = Strategy(
    "baseline-legacy-concatenate-v1",
    "none",
    "Frozen pre-fix concatenate-then-slice control from the existing eval pilot.",
    _legacy_concatenate,
)
CANDIDATES = (
    Strategy(
        "candidate-round-robin-v1",
        "display-selection=round-robin",
        "One item per available provider per fixed-order round.",
        _round_robin,
    ),
    Strategy(
        "candidate-equal-quota-no-redistribution-v1",
        "display-selection=equal-quota-without-redistribution",
        "Equal initial quota but intentionally no unused-capacity redistribution.",
        _equal_quota_without_redistribution,
    ),
)


def _hash_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_hash(value: Any) -> str:
    return _hash_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _repo_path(repo_root: Path, path: Path) -> Path:
    candidate = (repo_root / path).resolve()
    try:
        candidate.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError("benchmark path must stay inside the repository") from exc
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError("benchmark path must be a regular file")
    return candidate


def _strategy_identity(strategy: Strategy) -> dict[str, str]:
    definition = {
        "candidate_id": strategy.candidate_id,
        "variable": strategy.variable,
        "description": strategy.description,
        "implementation": strategy.select.__name__,
    }
    return {**definition, "definition_hash": _canonical_hash(definition)}


def _evaluator_digest() -> str:
    # This module is the evaluator. Pinning its bytes makes a result from a
    # changed evaluator inapplicable rather than silently comparable.
    return _hash_bytes(Path(__file__).read_bytes())


def load_benchmark(repo_root: Path, path: Path = BENCHMARK_PATH) -> tuple[dict[str, Any], str]:
    """Load a strict, frozen benchmark. Unknown or partial input is rejected."""
    benchmark_path = _repo_path(repo_root, path)
    try:
        benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("benchmark must be valid JSON") from exc
    if set(benchmark) != {"schema_version", "behavior", "source_fixtures", "cases"}:
        raise ValueError("benchmark must use the closed v1 schema")
    if benchmark["schema_version"] != SCHEMA_BENCHMARK:
        raise ValueError("unsupported benchmark schema")
    if benchmark["behavior"] != "evidence_display_provider_coverage":
        raise ValueError("unsupported benchmark behavior")
    sources = benchmark["source_fixtures"]
    if not isinstance(sources, list) or not sources:
        raise ValueError("benchmark must declare reviewed source fixtures")
    for raw in sources:
        if not isinstance(raw, str) or not raw.startswith("tests/fixtures/"):
            raise ValueError("source fixtures must be repository test fixtures")
        _repo_path(repo_root, Path(raw))
    cases = benchmark["cases"]
    required_families = {
        "exact", "hybrid", "graph_impact", "ambiguity", "no_evidence", "adversarial"
    }
    observed_families = {
        case.get("family") for case in cases if isinstance(case, dict)
    } if isinstance(cases, list) else set()
    if observed_families != required_families:
        raise ValueError(
            "benchmark must cover exact, hybrid, graph/impact, ambiguity, "
            "no-evidence, and adversarial cases"
        )
    case_ids: set[str] = set()
    for case in cases:
        if set(case) != {"case_id", "family", "cap", "provider_item_counts", "required_providers"}:
            raise ValueError("benchmark case must use the closed v1 schema")
        case_id = case["case_id"]
        if not isinstance(case_id, str) or not _SAFE_ID.fullmatch(case_id) or case_id in case_ids:
            raise ValueError("benchmark case ids must be unique stable identifiers")
        case_ids.add(case_id)
        if not isinstance(case["cap"], int) or not 1 <= case["cap"] <= 100:
            raise ValueError("benchmark case cap must be between 1 and 100")
        counts = case["provider_item_counts"]
        required = case["required_providers"]
        if (
            not isinstance(counts, dict)
            or set(counts) - set(PROVIDERS)
            or not all(isinstance(value, int) and value >= 0 for value in counts.values())
            or not isinstance(required, list)
            or set(required) - set(PROVIDERS)
            or any(counts.get(provider, 0) <= 0 for provider in required)
        ):
            raise ValueError("benchmark provider declarations are invalid")
        if case["family"] == "no_evidence" and (counts or required):
            raise ValueError("no-evidence case must have no providers")
    benchmark_hash = _hash_bytes(benchmark_path.read_bytes())
    return benchmark, benchmark_hash


def _grade_case(strategy: Strategy, case: dict[str, Any]) -> dict[str, Any]:
    counts = case["provider_item_counts"]
    cap = case["cap"]
    selected = strategy.select(counts, cap)
    selected_counts = {provider: selected.count(provider) for provider in PROVIDERS}
    available = sum(counts.values())
    required = set(case["required_providers"])
    selected_set = set(selected)
    hard_constraints: list[str] = []
    if len(selected) > cap:
        hard_constraints.append("cap_exceeded")
    if any(selected_counts[p] > counts.get(p, 0) for p in PROVIDERS):
        hard_constraints.append("invented_evidence")
    if required - selected_set:
        hard_constraints.append("required_provider_hidden")
    if available and len(selected) != min(cap, available):
        hard_constraints.append("available_capacity_unused")
    if not available and selected:
        hard_constraints.append("no_evidence_misrepresented")
    coverage = 1.0 if not required else len(required & selected_set) / len(required)
    return {
        "case_id": case["case_id"],
        "family": case["family"],
        "hard_constraints": hard_constraints,
        "required_provider_coverage": coverage,
        "selected_total": len(selected),
        "selected_by_provider": selected_counts,
    }


def _evaluate(strategy: Strategy, benchmark: dict[str, Any]) -> dict[str, Any]:
    grades = [_grade_case(strategy, case) for case in benchmark["cases"]]
    protected_failures = sum(bool(grade["hard_constraints"]) for grade in grades)
    comparable = [grade for grade in grades if grade["family"] != "no_evidence"]
    return {
        "candidate": _strategy_identity(strategy),
        "case_grades": grades,
        "hard_constraints": {
            "protected_case_failures": protected_failures,
            "all_protected_cases_pass": protected_failures == 0,
        },
        "reward": {
            "primary_metric": "mean_required_provider_coverage",
            "primary_value": round(
                sum(grade["required_provider_coverage"] for grade in comparable)
                / len(comparable),
                6,
            ),
        },
    }


def _public_evaluation(evaluation: dict[str, Any]) -> dict[str, Any]:
    """Remove fixture counts and selected ordering before a persisted record."""
    return {
        "candidate": evaluation["candidate"],
        "case_outcomes": [
            {
                "case_id": grade["case_id"],
                "family": grade["family"],
                "hard_constraints": grade["hard_constraints"],
                "required_provider_coverage": grade["required_provider_coverage"],
            }
            for grade in evaluation["case_grades"]
        ],
        "hard_constraints": evaluation["hard_constraints"],
        "reward": evaluation["reward"],
    }


def _paired_sign_test_p_value(wins: int, losses: int) -> float:
    """Two-sided exact sign test over non-tied frozen-case outcomes."""
    trials = wins + losses
    if not trials:
        return 1.0
    lower_tail = sum(math.comb(trials, value) for value in range(0, min(wins, losses) + 1))
    return min(1.0, round(2 * lower_tail / 2**trials, 8))


def _candidate_verdict(
    baseline: dict[str, Any], candidate: dict[str, Any], replay: dict[str, Any]
) -> dict[str, Any]:
    baseline_value = baseline["reward"]["primary_value"]
    candidate_value = candidate["reward"]["primary_value"]
    delta = round(candidate_value - baseline_value, 6)
    paired_wins = sum(
        one["required_provider_coverage"] > two["required_provider_coverage"]
        for one, two in zip(candidate["case_grades"], baseline["case_grades"], strict=True)
    )
    paired_losses = sum(
        one["required_provider_coverage"] < two["required_provider_coverage"]
        for one, two in zip(candidate["case_grades"], baseline["case_grades"], strict=True)
    )
    p_value = _paired_sign_test_p_value(paired_wins, paired_losses)
    hard_pass = candidate["hard_constraints"]["all_protected_cases_pass"]
    reproducible = _public_evaluation(candidate) == _public_evaluation(replay)
    practically_meaningful = delta >= MINIMUM_PRACTICAL_DELTA
    statistically_meaningful = p_value < MAX_SIGN_TEST_P_VALUE
    reasons: list[str] = []
    if not hard_pass:
        reasons.append("protected_metric_regression")
    if not reproducible:
        reasons.append("non_reproducible_rerun")
    if not practically_meaningful:
        reasons.append("primary_reward_not_practically_meaningful")
    if not statistically_meaningful:
        reasons.append("insufficient_paired_statistical_evidence")
    status = "inconclusive" if reasons else "eligible_for_independent_review"
    return {
        "status": status,
        "baseline_primary_value": baseline_value,
        "candidate_primary_value": candidate_value,
        "primary_delta": delta,
        "paired_wins": paired_wins,
        "paired_losses": paired_losses,
        "paired_sign_test_p_value": p_value,
        "hard_constraints_pass": hard_pass,
        "reproducible": reproducible,
        "practically_meaningful": practically_meaningful,
        "statistically_meaningful": statistically_meaningful,
        "reasons": reasons,
        "promotion": {
            "allowed": False,
            "status": "human_review_required",
            "independent_verification_required": True,
            "candidate_self_promotion": "denied",
        },
    }


def run_program(repo_root: Path, benchmark_path: Path = BENCHMARK_PATH) -> dict[str, Any]:
    """Run the fixed baseline and both controlled candidates without side effects."""
    benchmark, benchmark_hash = load_benchmark(repo_root, benchmark_path)
    baseline = _evaluate(BASELINE, benchmark)
    candidates = []
    for strategy in CANDIDATES:
        candidate = _evaluate(strategy, benchmark)
        replay = _evaluate(strategy, benchmark)
        candidates.append(
            {"evaluation": candidate, "verdict": _candidate_verdict(baseline, candidate, replay)}
        )
    result: dict[str, Any] = {
        "schema_version": SCHEMA_RUN,
        "program": {
            "behavior": benchmark["behavior"],
            "benchmark": str(benchmark_path),
            "benchmark_hash": benchmark_hash,
            "source_fixture_hashes": {
                source: _hash_bytes(_repo_path(repo_root, Path(source)).read_bytes())
                for source in benchmark["source_fixtures"]
            },
            "evaluator_digest": _evaluator_digest(),
            "evidence_mode": "declared_deterministic",
            "external_egress": "denied",
            "model_judging": "not_used",
        },
        "baseline": _public_evaluation(baseline),
        "candidates": [
            {"evaluation": _public_evaluation(item["evaluation"]), "verdict": item["verdict"]}
            for item in candidates
        ],
        "promotion": {
            "allowed": False,
            "authority": "independent_human_review_via_holus_improve_review",
            "requirements": [
                "declared practical primary improvement",
                "paired statistical evidence",
                "no protected-metric regression",
                "reproducible rerun",
                "independent verified manifest review",
            ],
        },
    }
    result["result_digest"] = _canonical_hash(result)
    return result


def validate_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Fail closed before a persisted result can be inspected or reused."""
    required_fields = {
        "schema_version", "program", "baseline", "candidates", "promotion", "result_digest"
    }
    if not isinstance(payload, dict) or set(payload) != required_fields:
        raise ValueError("variation result has an unsupported or partial schema")
    if payload.get("schema_version") != SCHEMA_RUN:
        raise ValueError("unsupported variation result schema")
    digest = payload.get("result_digest")
    if not isinstance(digest, str):
        raise ValueError("variation result lacks a digest")
    unsealed = dict(payload)
    unsealed.pop("result_digest", None)
    if digest != _canonical_hash(unsealed):
        raise ValueError("variation result digest does not match its bytes")
    program = payload.get("program")
    expected_program_fields = {
        "behavior", "benchmark", "benchmark_hash", "source_fixture_hashes", "evaluator_digest",
        "evidence_mode", "external_egress", "model_judging"
    }
    if not isinstance(program, dict) or set(program) != expected_program_fields:
        raise ValueError("variation result has incomplete program lineage")
    if payload.get("promotion", {}).get("allowed") is not False:
        raise ValueError("variation result may never authorize promotion")
    candidates = payload.get("candidates")
    expected_ids = {strategy.candidate_id for strategy in CANDIDATES}
    if not isinstance(candidates, list) or len(candidates) != len(CANDIDATES):
        raise ValueError("variation result is partial or has unsupported candidates")
    observed_ids: set[str] = set()
    required_families = {
        "exact", "hybrid", "graph_impact", "ambiguity", "no_evidence", "adversarial"
    }
    for candidate in candidates:
        if not isinstance(candidate, dict) or set(candidate) != {"evaluation", "verdict"}:
            raise ValueError("variation result has unsupported candidate fields")
        evaluation = candidate["evaluation"]
        verdict = candidate["verdict"]
        if not isinstance(evaluation, dict) or set(evaluation) != {
            "candidate", "case_outcomes", "hard_constraints", "reward"
        }:
            raise ValueError("variation result has incomplete candidate evidence")
        identity = evaluation["candidate"]
        grades = evaluation["case_outcomes"]
        grade_families = (
            {grade.get("family") for grade in grades if isinstance(grade, dict)}
            if isinstance(grades, list)
            else set()
        )
        if (
            not isinstance(identity, dict)
            or identity.get("candidate_id") not in expected_ids
            or not isinstance(grades, list)
            or grade_families != required_families
            or not isinstance(verdict, dict)
            or not isinstance(verdict.get("reasons"), list)
        ):
            raise ValueError("variation result has incomplete candidate evidence")
        observed_ids.add(identity["candidate_id"])
        if verdict.get("promotion", {}).get("allowed") is not False:
            raise ValueError("candidate result may never authorize promotion")
    if observed_ids != expected_ids:
        raise ValueError("variation result is partial or has duplicate candidates")
    return payload


def record_run(repo_root: Path, result: dict[str, Any]) -> str:
    """Opt in to an append-only, no-follow derived record for every outcome."""
    validate_result(result)
    record = {
        "schema_version": SCHEMA_RECORD,
        "record_id": uuid.uuid4().hex,
        "result_digest": result["result_digest"],
        "benchmark_hash": result["program"]["benchmark_hash"],
        "evaluator_digest": result["program"]["evaluator_digest"],
        "candidate_outcomes": [
            {
                "candidate_id": item["evaluation"]["candidate"]["candidate_id"],
                "status": item["verdict"]["status"],
                "reasons": item["verdict"]["reasons"],
            }
            for item in result["candidates"]
        ],
    }
    path = PROGRAM_HISTORY_ROOT / f"{record['record_id']}.json"
    try:
        written = safe_atomic_write(
            repo_root,
            path,
            (json.dumps(record, sort_keys=True) + "\n").encode("utf-8"),
            allowed_repo_root=HISTORY_ROOT,
        )
    except UnsafeStoragePath as exc:
        raise ValueError("unsafe variation record path") from exc
    return str(written.relative_to(repo_root))


def build_feedback_proposal(signal: str, count: int) -> dict[str, Any]:
    """Queue only a bounded aggregate signal for human case-admission review."""
    if (
        signal not in {"failure_case", "aggregate_outcome"}
        or not isinstance(count, int)
        or count < 1
    ):
        raise ValueError("feedback requires a known signal and a positive aggregate count")
    return {
        "review_queue": {
            "signal": signal,
            "count": count,
            "raw_prompt_retained": False,
            "canonical_truth_changed": False,
            "next_step": "use holus improve-intake then an ordinary reviewed fixture PR",
        },
        "privacy": {"external_egress": "denied", "personal_data": "not_collected"},
    }


def main(argv: list[str] | None = None) -> int:
    """Small direct runner for local operator and E2E use; the holus CLI wraps it."""
    repo_root = Path.cwd().resolve()
    result = run_program(repo_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
