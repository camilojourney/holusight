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
from typing import Annotated, Any, Callable, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, ValidationError

from .control_storage import (
    HISTORY_ROOT,
    RESULTS_ROOT,
    UnsafeStoragePath,
    is_clean_tracked_file,
    safe_atomic_write,
    validate_output_path,
)

SCHEMA_BENCHMARK = "holusight-retrieval-variation-benchmark/v1"
SCHEMA_RUN = "holusight-retrieval-variation-run/v1"
SCHEMA_RECORD = "holusight-retrieval-variation-record/v1"
BENCHMARK_PATH = Path("tests/fixtures/holusight_retrieval_variation_benchmark.json")
PROGRAM_HISTORY_ROOT = HISTORY_ROOT / "retrieval-variation"
PROGRAM_RESULTS_ROOT = RESULTS_ROOT / "retrieval-variation"
RETRIEVAL_SOURCE_PATH = Path("src/codesight/retrieval_variation.py")
PRODUCTION_SELECTOR_SOURCE_PATH = Path("src/codesight/cli_axi.py")
PROVIDER_MODELS_SOURCE_PATH = Path("src/codesight/axi_providers.py")
CONTROL_STORAGE_SOURCE_PATH = Path("src/codesight/control_storage.py")
PROVIDERS = ("exact", "structural", "consistency", "semantic")
MAX_PROVIDER_ITEMS = 100
MAX_FEEDBACK_COUNT = 1_000_000
MINIMUM_PRACTICAL_DELTA = 0.05
MAX_SIGN_TEST_P_VALUE = 0.05
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")


def _require_exact_float(value: Any) -> Any:
    if type(value) is not float:
        raise ValueError("value must be a JSON floating-point number")
    return value


_ExactFloat = Annotated[float, BeforeValidator(_require_exact_float)]
_Family = Literal[
    "exact", "hybrid", "graph_impact", "ambiguity", "no_evidence", "adversarial"
]


class _ClosedVariationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _StrategyIdentityModel(_ClosedVariationModel):
    candidate_id: str
    variable: str
    description: str
    implementation: str
    implementation_hashes: dict[str, str]
    definition_hash: str


class _CaseOutcomeModel(_ClosedVariationModel):
    case_id: str
    family: _Family
    hard_constraints: list[str]
    required_provider_coverage: _ExactFloat


class _HardConstraintsModel(_ClosedVariationModel):
    protected_case_failures: int
    all_protected_cases_pass: bool


class _RewardModel(_ClosedVariationModel):
    primary_metric: Literal["mean_required_provider_coverage"]
    primary_value: _ExactFloat


class _EvaluationModel(_ClosedVariationModel):
    candidate: _StrategyIdentityModel
    case_outcomes: list[_CaseOutcomeModel]
    hard_constraints: _HardConstraintsModel
    reward: _RewardModel


class _CandidatePromotionModel(_ClosedVariationModel):
    allowed: Literal[False]
    status: Literal["human_review_required"]
    independent_verification_required: Literal[True]
    candidate_self_promotion: Literal["denied"]


class _VerdictModel(_ClosedVariationModel):
    status: Literal["failed", "inconclusive", "eligible_for_independent_review"]
    baseline_primary_value: _ExactFloat
    candidate_primary_value: _ExactFloat
    primary_delta: _ExactFloat
    paired_wins: int
    paired_losses: int
    paired_sign_test_p_value: _ExactFloat
    hard_constraints_pass: bool
    reproducible: bool
    practically_meaningful: bool
    statistically_meaningful: bool
    reasons: list[str]
    promotion: _CandidatePromotionModel


class _CandidateResultModel(_ClosedVariationModel):
    evaluation: _EvaluationModel
    verdict: _VerdictModel


class _ProgramModel(_ClosedVariationModel):
    behavior: Literal["evidence_display_provider_coverage"]
    benchmark: Literal["tests/fixtures/holusight_retrieval_variation_benchmark.json"]
    benchmark_hash: str
    source_fixture_hashes: dict[str, str]
    evaluator_digest: str
    implementation_hashes: dict[str, str]
    evidence_mode: Literal["declared_deterministic"]
    external_egress: Literal["denied"]
    model_judging: Literal["not_used"]


class _RunPromotionModel(_ClosedVariationModel):
    allowed: Literal[False]
    authority: Literal["independent_human_review_via_holus_improve_review"]
    requirements: list[str]


class _VariationRunModel(_ClosedVariationModel):
    schema_version: Literal["holusight-retrieval-variation-run/v1"]
    program: _ProgramModel
    baseline: _EvaluationModel
    candidates: list[_CandidateResultModel]
    promotion: _RunPromotionModel
    result_digest: str


@dataclass(frozen=True)
class Strategy:
    """An immutable candidate definition, never executable user input."""

    candidate_id: str
    variable: str
    description: str
    select: Callable[[dict[str, int], int], list[str]]
    implementation_paths: tuple[Path, ...]


def _legacy_concatenate(counts: dict[str, int], cap: int) -> list[str]:
    selected: list[str] = []
    for provider in PROVIDERS:
        remaining = cap - len(selected)
        if remaining <= 0:
            break
        selected.extend([provider] * min(counts.get(provider, 0), remaining))
    return selected


def _production_round_robin(counts: dict[str, int], cap: int) -> list[str]:
    from . import axi_providers, cli_axi

    results = []
    for provider in PROVIDERS:
        items = [
            axi_providers.EvidenceItem(
                provider=provider,
                source=f"fixture:{provider}:{index}",
                location="synthetic",
                excerpt="synthetic",
            )
            for index in range(counts.get(provider, 0))
        ]
        results.append(
            axi_providers.ProviderResult(
                provider=provider,
                state=(
                    axi_providers.ProviderState.OK
                    if items
                    else axi_providers.ProviderState.NO_EVIDENCE
                ),
                detail="synthetic variation fixture",
                route_reason="frozen variation benchmark",
                items=items,
            )
        )
    return [item.provider for item in cli_axi._select_display_items(results, cap)]


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
    (RETRIEVAL_SOURCE_PATH, CONTROL_STORAGE_SOURCE_PATH),
)
CANDIDATES = (
    Strategy(
        "candidate-round-robin-v1",
        "display-selection=round-robin",
        "One item per available provider per fixed-order round.",
        _production_round_robin,
        (
            RETRIEVAL_SOURCE_PATH,
            PRODUCTION_SELECTOR_SOURCE_PATH,
            PROVIDER_MODELS_SOURCE_PATH,
            CONTROL_STORAGE_SOURCE_PATH,
        ),
    ),
    Strategy(
        "candidate-equal-quota-no-redistribution-v1",
        "display-selection=equal-quota-without-redistribution",
        "Equal initial quota but intentionally no unused-capacity redistribution.",
        _equal_quota_without_redistribution,
        (RETRIEVAL_SOURCE_PATH, CONTROL_STORAGE_SOURCE_PATH),
    ),
)


def _hash_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_hash(value: Any) -> str:
    return _hash_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _repo_path(repo_root: Path, path: Path) -> Path:
    unresolved = repo_root / path
    if unresolved.is_symlink():
        raise ValueError("repository input must be a regular no-follow file")
    candidate = unresolved.resolve()
    try:
        candidate.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError("repository input must stay inside the repository") from exc
    if not candidate.is_file():
        raise ValueError("repository input must be a regular file")
    return candidate


def _source_hashes(repo_root: Path) -> dict[str, str]:
    from . import axi_providers, cli_axi, control_storage

    paths = {
        path
        for strategy in (BASELINE, *CANDIDATES)
        for path in strategy.implementation_paths
    }
    executed = {
        RETRIEVAL_SOURCE_PATH: Path(__file__),
        PRODUCTION_SELECTOR_SOURCE_PATH: Path(cli_axi.__file__),
        PROVIDER_MODELS_SOURCE_PATH: Path(axi_providers.__file__),
        CONTROL_STORAGE_SOURCE_PATH: Path(control_storage.__file__),
    }
    hashes: dict[str, str] = {}
    for relative in sorted(paths):
        full_path = _repo_path(repo_root, relative)
        if not is_clean_tracked_file(repo_root, full_path):
            raise ValueError("variation implementations must be clean and tracked at HEAD")
        repo_bytes = full_path.read_bytes()
        if repo_bytes != executed[relative].read_bytes():
            raise ValueError("executed variation implementation differs from repository bytes")
        hashes[relative.as_posix()] = _hash_bytes(repo_bytes)
    return hashes


def _strategy_identity(
    strategy: Strategy, implementation_hashes: dict[str, str]
) -> dict[str, Any]:
    definition = {
        "candidate_id": strategy.candidate_id,
        "variable": strategy.variable,
        "description": strategy.description,
        "implementation": strategy.select.__name__,
        "implementation_hashes": {
            path.as_posix(): implementation_hashes[path.as_posix()]
            for path in strategy.implementation_paths
        },
    }
    return {**definition, "definition_hash": _canonical_hash(definition)}


def _evaluator_digest(implementation_hashes: dict[str, str]) -> str:
    return implementation_hashes[RETRIEVAL_SOURCE_PATH.as_posix()]


def _validate_fixture_backing(
    repo_root: Path, sources: list[str], cases: list[dict[str, Any]]
) -> None:
    adversarial = next(case for case in cases if case["family"] == "adversarial")
    for source in sources:
        source_path = _repo_path(repo_root, Path(source))
        try:
            entries = [
                json.loads(line)
                for line in source_path.read_text(encoding="utf-8").splitlines()
                if line
            ]
        except json.JSONDecodeError as exc:
            raise ValueError("source fixture must be valid JSONL") from exc
        for entry in entries:
            fixture = entry.get("fixture", {}) if isinstance(entry, dict) else {}
            if (
                fixture.get("provider_item_counts") == adversarial["provider_item_counts"]
                and fixture.get("cap") == adversarial["cap"]
                and entry.get("grader") == "grade_display_quota_case"
            ):
                return
    raise ValueError("benchmark adversarial case must match its reviewed source fixture")


def load_benchmark(repo_root: Path, path: Path = BENCHMARK_PATH) -> tuple[dict[str, Any], str]:
    """Load a strict, frozen benchmark. Unknown or partial input is rejected."""
    if path != BENCHMARK_PATH:
        raise ValueError("only the canonical frozen benchmark is supported")
    benchmark_path = _repo_path(repo_root, path)
    canonical_path = _repo_path(repo_root, BENCHMARK_PATH)
    if benchmark_path != canonical_path:
        raise ValueError("only the canonical frozen benchmark is supported")
    if not is_clean_tracked_file(repo_root, benchmark_path):
        raise ValueError("canonical benchmark must be clean and tracked at HEAD")
    try:
        benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("benchmark must be valid JSON") from exc
    if not isinstance(benchmark, dict) or set(benchmark) != {
        "schema_version",
        "behavior",
        "source_fixtures",
        "cases",
    }:
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
        source_path = _repo_path(repo_root, Path(raw))
        if not is_clean_tracked_file(repo_root, source_path):
            raise ValueError("source fixtures must be clean and tracked at HEAD")
    cases = benchmark["cases"]
    required_families = {
        "exact", "hybrid", "graph_impact", "ambiguity", "no_evidence", "adversarial"
    }
    if not isinstance(cases, list) or not cases or not all(
        isinstance(case, dict) for case in cases
    ):
        raise ValueError("benchmark cases must be a non-empty object list")
    observed_families = {case.get("family") for case in cases}
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
        if type(case["cap"]) is not int or not 1 <= case["cap"] <= 100:
            raise ValueError("benchmark case cap must be between 1 and 100")
        counts = case["provider_item_counts"]
        required = case["required_providers"]
        if (
            not isinstance(counts, dict)
            or set(counts) - set(PROVIDERS)
            or not all(
                type(value) is int and 0 <= value <= MAX_PROVIDER_ITEMS
                for value in counts.values()
            )
            or sum(counts.values()) > MAX_PROVIDER_ITEMS * len(PROVIDERS)
            or not isinstance(required, list)
            or not all(isinstance(provider, str) for provider in required)
            or len(required) != len(set(required))
            or set(required) - set(PROVIDERS)
            or any(counts.get(provider, 0) <= 0 for provider in required)
        ):
            raise ValueError("benchmark provider declarations are invalid")
        if case["family"] == "no_evidence" and (counts or required):
            raise ValueError("no-evidence case must have no providers")
    _validate_fixture_backing(repo_root, sources, cases)
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


def _evaluate(
    strategy: Strategy,
    benchmark: dict[str, Any],
    implementation_hashes: dict[str, str],
) -> dict[str, Any]:
    grades = [_grade_case(strategy, case) for case in benchmark["cases"]]
    protected_failures = sum(bool(grade["hard_constraints"]) for grade in grades)
    comparable = [grade for grade in grades if grade["family"] != "no_evidence"]
    return {
        "candidate": _strategy_identity(strategy, implementation_hashes),
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
    if not hard_pass or not reproducible:
        status = "failed"
    elif reasons:
        status = "inconclusive"
    else:
        status = "eligible_for_independent_review"
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
    implementation_hashes = _source_hashes(repo_root)
    baseline = _evaluate(BASELINE, benchmark, implementation_hashes)
    candidates = []
    for strategy in CANDIDATES:
        candidate = _evaluate(strategy, benchmark, implementation_hashes)
        replay = _evaluate(strategy, benchmark, implementation_hashes)
        candidates.append(
            {"evaluation": candidate, "verdict": _candidate_verdict(baseline, candidate, replay)}
        )
    result: dict[str, Any] = {
        "schema_version": SCHEMA_RUN,
        "program": {
            "behavior": benchmark["behavior"],
            "benchmark": BENCHMARK_PATH.as_posix(),
            "benchmark_hash": benchmark_hash,
            "source_fixture_hashes": {
                source: _hash_bytes(_repo_path(repo_root, Path(source)).read_bytes())
                for source in benchmark["source_fixtures"]
            },
            "evaluator_digest": _evaluator_digest(implementation_hashes),
            "implementation_hashes": implementation_hashes,
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


def validate_result(
    payload: dict[str, Any], *, repo_root: Path | None = None
) -> dict[str, Any]:
    """Fail closed before a persisted result can be inspected or reused."""
    try:
        _VariationRunModel.model_validate(payload)
    except ValidationError as exc:
        raise ValueError("variation result has an unsupported or partial strict schema") from exc

    digest = payload["result_digest"]
    unsealed = dict(payload)
    unsealed.pop("result_digest")
    if digest != _canonical_hash(unsealed):
        raise ValueError("variation result digest does not match its bytes")

    candidates = payload["candidates"]
    expected_ids = {strategy.candidate_id for strategy in CANDIDATES}
    observed_ids = {
        candidate["evaluation"]["candidate"]["candidate_id"] for candidate in candidates
    }
    if len(candidates) != len(CANDIDATES) or observed_ids != expected_ids:
        raise ValueError("variation result is partial or has duplicate candidates")

    root = repo_root.resolve() if repo_root is not None else Path(__file__).resolve().parents[2]
    if payload != run_program(root):
        raise ValueError("variation result does not match independently recomputed frozen evidence")
    return payload


def persist_result(repo_root: Path, result: dict[str, Any]) -> str:
    """Persist the complete typed result for independently anchored review."""
    validate_result(result, repo_root=repo_root)
    digest = result["result_digest"].removeprefix("sha256:")
    path = PROGRAM_RESULTS_ROOT / f"{digest}.json"
    try:
        written = safe_atomic_write(
            repo_root,
            path,
            (json.dumps(result, sort_keys=True) + "\n").encode("utf-8"),
            allowed_repo_root=RESULTS_ROOT,
        )
    except UnsafeStoragePath as exc:
        raise ValueError("unsafe variation result path") from exc
    return str(written.relative_to(repo_root))


def load_result(repo_root: Path, path: Path) -> dict[str, Any]:
    """Load and independently recompute a persisted typed result."""
    try:
        validate_output_path(repo_root, path, allowed_repo_root=RESULTS_ROOT)
    except UnsafeStoragePath as exc:
        raise ValueError("unsafe variation result path") from exc
    full_path = _repo_path(repo_root, path)
    relative = full_path.relative_to(repo_root.resolve())
    if PROGRAM_RESULTS_ROOT not in (relative, *relative.parents):
        raise ValueError("variation result must be under improvement-results")
    try:
        payload = json.loads(full_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("variation result must be valid JSON") from exc
    return validate_result(payload, repo_root=repo_root)


def record_run(repo_root: Path, result: dict[str, Any]) -> str:
    """Opt in to an append-only, no-follow derived record for every outcome."""
    validate_result(result, repo_root=repo_root)
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
        or type(count) is not int
        or not 1 <= count <= MAX_FEEDBACK_COUNT
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
