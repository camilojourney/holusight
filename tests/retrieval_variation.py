"""Bounded retrieval variation program with immutable baseline and review-ready lineage.

This module implements a tiny, production-safe local loop for candidate retrieval
configuration variation. It is intentionally narrow: one fixed frozen benchmark,
three candidate arms (baseline + two controlled variable variants), no automatic
promotion, and complete, content-minimized evidence for every run.

The loop has five required properties:
- immutable baseline definition and benchmark hash
- versioned candidate definitions
- per-run and per-query replay fingerprints
- explicit hard-constraint checks separated from optimization reward
- failed or inconclusive outcomes remain retained for traceability
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codesight import CodeSight
from codesight.config import ServerConfig
from tests.eval_harness import EvalQuery, run_eval

DEFAULT_REPO_PATH = Path(__file__).resolve().parents[1]
DEFAULT_BENCHMARK = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "holusight_retrieval_quality_variation_benchmark.json"
)
DEFAULT_TOP_K = 10
SCHEMA_VERSION = "holus-retrieval-variation/v1"
PROGRAM_VERSION = "v1"
DEFAULT_CANDIDATE_REGISTRY_VERSION = "v1"
BASELINE_CANDIDATE_ID = "baseline-hybrid"
PRIMARY_METRIC = "mrr_at_10"
PRIMARY_DELTA_MIN = 0.02
SIGNIFICANCE_ALPHA = 0.05
PROTECTED_METRICS = {
    "hit_rate": 0.0,
    "recall_at_10": 0.0,
    "evidence_completeness": 0.0,
    "ndcg_at_10": 0.0,
}


@dataclass(frozen=True)
class CandidateDefinition:
    candidate_id: str
    version: str
    label: str
    config_overrides: dict[str, Any]
    controlled_variable: str
    controlled_value: str
    description: str


DEFAULT_CANDIDATES: tuple[CandidateDefinition, ...] = (
    CandidateDefinition(
        candidate_id="baseline-hybrid",
        version="v1",
        label="hybrid-search-baseline",
        config_overrides={},
        controlled_variable="none",
        controlled_value="default",
        description="Production default hybrid retrieval configuration.",
    ),
    CandidateDefinition(
        candidate_id="cnfb-alpha-0.25",
        version="v1",
        label="hybrid-cnfb-alpha",
        config_overrides={"cnfb_alpha": 0.25},
        controlled_variable="cnfb_alpha",
        controlled_value="0.25",
        description="Single controlled retrieval boost variable.",
    ),
    CandidateDefinition(
        candidate_id="query-enhancement-on",
        version="v1",
        label="hybrid-query-enhancement",
        config_overrides={"query_enhancement": True},
        controlled_variable="query_enhancement",
        controlled_value="true",
        description="Single controlled query expansion variable.",
    ),
)


@dataclass(frozen=True)
class BenchmarkSpec:
    path: str
    path_hash: str
    query_count: int
    graded_query_count: int
    family_counts: dict[str, int]
    family_counts_graded: dict[str, int]


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _candidate_id_set(candidates: tuple[CandidateDefinition, ...]) -> set[str]:
    return {candidate.candidate_id for candidate in candidates}


def _candidate_definition_digest(candidates: tuple[CandidateDefinition, ...]) -> str:
    payload = [
        {
            "candidate_id": c.candidate_id,
            "version": c.version,
            "controlled_variable": c.controlled_variable,
            "controlled_value": c.controlled_value,
            "config_overrides": dict(c.config_overrides),
        }
        for c in candidates
    ]
    return _sha256_hex(_canonical_json(payload) + DEFAULT_CANDIDATE_REGISTRY_VERSION)


def _run_record_digest(run_payload: dict[str, Any]) -> str:
    sanitized = dict(run_payload)
    sanitized.pop("run_id", None)
    sanitized.pop("run_digest", None)
    return _sha256_hex(_canonical_json(sanitized))


def _query_row_to_eval_query(row: dict[str, Any], *, index: int) -> EvalQuery:
    family = row.get("family", "unspecified") or "unspecified"
    split = row.get("split", "dev") or "dev"
    expected_file = row.get("expected_file")
    if not isinstance(expected_file, str) or not expected_file.strip():
        raise ValueError(f"row {index}: expected_file must be a non-empty string")
    return EvalQuery(
        query=row["query"],
        expected_file=expected_file,
        expected_start_line=row.get("expected_start_line"),
        family=family,
        split=split,
        expected_evidence=row.get("expected_evidence"),
    )


def _load_benchmark_queries(path: Path) -> tuple[list[EvalQuery], list[dict[str, Any]], BenchmarkSpec]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"benchmark must be a non-empty JSON array: {path}")

    rows: list[dict[str, Any]] = []
    queries: list[EvalQuery] = []
    family_counts: dict[str, int] = {}
    family_counts_graded: dict[str, int] = {}

    for idx, row in enumerate(raw, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"row {idx}: benchmark rows must be objects")
        query = row.get("query")
        expected_file = row.get("expected_file")
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"row {idx}: query must be a non-empty string")
        if not isinstance(expected_file, str) or not expected_file.strip():
            raise ValueError(f"row {idx}: expected_file must be a non-empty string")

        normalized = dict(row)
        normalized.setdefault("family", "unspecified")
        normalized.setdefault("split", "dev")

        rows.append(normalized)
        eval_query = _query_row_to_eval_query(normalized, index=idx)
        queries.append(eval_query)

        family = eval_query.family
        family_counts[family] = family_counts.get(family, 0) + 1
        if not eval_query.is_diagnostic_probe:
            family_counts_graded[family] = family_counts_graded.get(family, 0) + 1

    spec = BenchmarkSpec(
        path=str(path),
        path_hash=_sha256_hex(_canonical_json(rows)),
        query_count=len(queries),
        graded_query_count=sum(1 for q in queries if not q.is_diagnostic_probe),
        family_counts=family_counts,
        family_counts_graded=family_counts_graded,
    )
    return queries, rows, spec


def _family_breakdown(per_query: list[dict[str, Any]], *, include_diagnostic: bool = True) -> dict[str, dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for entry in per_query:
        family = entry.get("family", "unspecified")
        bucket = buckets.setdefault(family, {"total": 0, "hits": 0, "diagnostic": 0})
        bucket["total"] += 1
        if entry.get("diagnostic_only", False):
            bucket["diagnostic"] += 1
            continue
        if bool(entry.get("hit", False)):
            bucket["hits"] += 1
    return buckets


def _run_candidate(
    repo_root: Path,
    queries: list[EvalQuery],
    rows: list[dict[str, Any]],
    candidate: CandidateDefinition,
    benchmark_path_hash: str,
    top_k: int,
    force_rebuild: bool,
) -> dict[str, Any]:
    config = ServerConfig(**candidate.config_overrides)
    engine = CodeSight(repo_root, config=config)
    index_stats = engine.index(force_rebuild=force_rebuild)

    result = run_eval(queries, engine.store, engine.embedder, top_k=top_k, config=config)

    run_payload: dict[str, Any] = {
        "candidate_id": candidate.candidate_id,
        "version": candidate.version,
        "label": candidate.label,
        "controlled_variable": candidate.controlled_variable,
        "controlled_value": candidate.controlled_value,
        "description": candidate.description,
        "config_overrides": dict(candidate.config_overrides),
        "index_stats": {
            "files_indexed": index_stats.files_indexed,
            "chunks_created": index_stats.chunks_created,
            "forced_rebuild": force_rebuild,
            "index_warmed": engine.store.is_indexed,
        },
        "metrics": {
            "hit_rate": round(result.hit_rate, 6),
            "mrr_at_10": round(result.mrr_at_10, 6),
            "ndcg_at_10": round(result.ndcg_at_10, 6),
            "evidence_completeness": round(result.evidence_completeness, 6),
            "recall_at_10": round(result.recall_at_k.get(10, 0.0), 6),
            "avg_latency_ms": round(result.avg_latency_ms, 3),
            "tokens_per_correct_answer": round(result.tokens_per_correct_answer, 3),
            "num_queries": result.num_queries,
            "num_graded": result.num_graded,
            "num_diagnostic_probes": result.num_diagnostic_probes,
            "total_tokens": result.total_tokens,
        },
        "run_stats": {
            "total_queries": len(rows),
            "graded_queries": result.num_graded,
            "diagnostic_queries": result.num_diagnostic_probes,
            "query_set_hash": _sha256_hex(_canonical_json(rows)),
        },
    }

    per_query: list[dict[str, Any]] = []
    hit_sequence: list[bool] = []
    for entry in result.per_query:
        q = {
            "query": entry["query"],
            "family": entry.get("family"),
            "split": entry.get("split"),
            "expected_file": entry.get("expected_file"),
            "diagnostic_only": bool(entry.get("diagnostic_only", False)),
            "hit": bool(entry.get("hit", False)),
            "rank": entry.get("rank"),
            "rr": entry.get("rr", 0.0),
            "ndcg": entry.get("ndcg", 0.0),
            "evidence_completeness": entry.get("evidence_completeness", 0.0),
            "latency_ms": entry.get("latency_ms"),
            "query_tokens": entry.get("query_tokens"),
        }
        per_query.append(q)
        if not q["diagnostic_only"]:
            hit_sequence.append(bool(q["hit"]))

    run_payload["per_query"] = per_query
    run_payload["family_breakdown"] = _family_breakdown(per_query)
    run_payload["hit_sequence"] = hit_sequence
    run_payload["run_id"] = _sha256_hex(_canonical_json({
        "candidate_id": candidate.candidate_id,
        "query_set_hash": run_payload["run_stats"]["query_set_hash"],
        "config_overrides": candidate.config_overrides,
        "benchmark_hash": benchmark_path_hash,
        "metrics": run_payload["metrics"],
    }))[:20]
    run_payload["run_digest"] = _run_record_digest(run_payload)
    run_payload["lineage"] = {
        "candidate_id": candidate.candidate_id,
        "candidate_version": candidate.version,
        "registry_version": DEFAULT_CANDIDATE_REGISTRY_VERSION,
        "run_id": run_payload["run_id"],
        "query_set_hash": run_payload["run_stats"]["query_set_hash"],
        "benchmark_hash": benchmark_path_hash,
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
    }
    return run_payload


def _paired_sign_two_sided_p_value(
    baseline_reciprocal_ranks: list[float],
    candidate_reciprocal_ranks: list[float],
) -> float:
    if len(baseline_reciprocal_ranks) != len(candidate_reciprocal_ranks):
        raise ValueError("reciprocal-rank sequences must have equal length")

    wins = losses = 0
    for baseline_rr, candidate_rr in zip(
        baseline_reciprocal_ranks,
        candidate_reciprocal_ranks,
    ):
        if candidate_rr > baseline_rr:
            wins += 1
        elif candidate_rr < baseline_rr:
            losses += 1

    paired = wins + losses
    if paired == 0:
        return 1.0

    minority = min(wins, losses)
    lower_tail_count = sum(math.comb(paired, successes) for successes in range(minority + 1))
    return min(1.0, 2.0 * lower_tail_count / (2**paired))


def _compare_candidate(
    benchmark: BenchmarkSpec,
    baseline: dict[str, Any],
    candidate_run: dict[str, Any],
) -> dict[str, Any]:
    candidate_id = candidate_run.get("candidate_id")
    candidate_run_id = candidate_run.get("run_id")
    baseline_run_id = baseline.get("run_id")

    if candidate_id is None:
        candidate_id = candidate_run.get("lineage", {}).get("candidate_id")
    if candidate_run_id is None:
        candidate_run_id = candidate_run.get("lineage", {}).get("run_id")
    if baseline_run_id is None:
        baseline_run_id = baseline.get("lineage", {}).get("run_id")

    comparison: dict[str, Any] = {
        "candidate_id": candidate_id,
        "candidate_run_id": candidate_run_id,
        "baseline_run_id": baseline_run_id,
        "benchmark_hash": benchmark.path_hash,
        "query_set_hash": benchmark.path_hash,
        "primary_metric": PRIMARY_METRIC,
        "status": "inconclusive",
        "decision": "retain_candidate",
        "reason": "no statistically practical primary improvement",
        "promotion_relevant": False,
        "primary_delta": 0.0,
        "primary_p_value": None,
        "constraints": {
            "name": "no-regression",
            "violations": [],
        },
        "optimization_signal": {
            "practical_delta_min": PRIMARY_DELTA_MIN,
            "significance_alpha": SIGNIFICANCE_ALPHA,
            "statistically_significant": False,
        },
        "metrics": {
            "baseline": {},
            "candidate": {},
            "delta": {},
        },
    }

    if candidate_id is None or candidate_run_id is None or baseline_run_id is None:
        comparison["status"] = "invalid"
        comparison["decision"] = "invalid_comparison"
        comparison["reason"] = "missing required run identifiers"
        comparison["constraints"]["violations"].append(
            {"type": "missing_run_identifier", "message": "run must include candidate_id and run_id"}
        )
        return comparison

    if baseline["run_stats"]["graded_queries"] != candidate_run["run_stats"]["graded_queries"]:
        comparison["status"] = "invalid"
        comparison["decision"] = "invalid_comparison"
        comparison["reason"] = "graded-query count mismatch"
        return comparison

    baseline_reciprocal_ranks = [
        float(entry["rr"])
        for entry in baseline["per_query"]
        if not entry.get("diagnostic_only", False)
    ]
    candidate_reciprocal_ranks = [
        float(entry["rr"])
        for entry in candidate_run["per_query"]
        if not entry.get("diagnostic_only", False)
    ]
    if len(baseline_reciprocal_ranks) != len(candidate_reciprocal_ranks):
        comparison["status"] = "invalid"
        comparison["decision"] = "invalid_comparison"
        comparison["reason"] = "reciprocal-rank sequence length mismatch"
        return comparison

    baseline_metrics = baseline["metrics"]
    candidate_metrics = candidate_run["metrics"]
    comparison["metrics"]["baseline"] = baseline_metrics
    comparison["metrics"]["candidate"] = candidate_metrics

    for metric_name, tolerance in PROTECTED_METRICS.items():
        delta = round(candidate_metrics[metric_name] - baseline_metrics[metric_name], 6)
        comparison["metrics"]["delta"][metric_name] = delta
        if delta + tolerance < 0.0:
            comparison["constraints"]["violations"].append(
                {
                    "metric": metric_name,
                    "baseline": baseline_metrics[metric_name],
                    "candidate": candidate_metrics[metric_name],
                    "minimum_allowed": round(-tolerance, 6),
                    "observed_delta": delta,
                }
            )

    p_value = _paired_sign_two_sided_p_value(
        baseline_reciprocal_ranks,
        candidate_reciprocal_ranks,
    )
    comparison["primary_p_value"] = round(p_value, 6)

    primary_delta = round(candidate_metrics[PRIMARY_METRIC] - baseline_metrics[PRIMARY_METRIC], 6)
    comparison["primary_delta"] = primary_delta
    comparison["optimization_signal"]["observed_delta"] = primary_delta

    comparison["optimization_signal"]["statistically_significant"] = p_value < SIGNIFICANCE_ALPHA

    if comparison["constraints"]["violations"]:
        comparison["status"] = "reject"
        comparison["decision"] = "human_review_required"
        comparison["reason"] = "protected-metric regression"
        comparison["promotion_relevant"] = False
        return comparison

    if comparison["optimization_signal"]["statistically_significant"] and primary_delta >= PRIMARY_DELTA_MIN:
        comparison["status"] = "promotable"
        comparison["decision"] = "human_review_required"
        comparison["reason"] = "meets statistical and practical gates"
        comparison["promotion_relevant"] = True
        return comparison

    return comparison


def _normalize_candidate_selection(candidates: tuple[CandidateDefinition, ...] | None = None) -> tuple[CandidateDefinition, ...]:
    selected = tuple(candidates) if candidates else DEFAULT_CANDIDATES
    if not selected:
        raise ValueError("at least one candidate is required")

    if len(_candidate_id_set(selected)) != len(selected):
        duplicates = sorted({
            candidate_id
            for candidate_id in _candidate_id_set(selected)
            if [c.candidate_id for c in selected].count(candidate_id) > 1
        })
        raise ValueError(f"duplicate candidate_id values: {duplicates}")

    if BASELINE_CANDIDATE_ID not in _candidate_id_set(selected):
        raise ValueError(
            f"benchmark run must include immutable baseline candidate '{BASELINE_CANDIDATE_ID}'"
        )

    selected_sorted = sorted(selected, key=lambda c: 0 if c.candidate_id == BASELINE_CANDIDATE_ID else 1)
    return selected_sorted


def run_variation_suite(
    repo_root: str | Path,
    benchmark_path: str | Path | None = None,
    top_k: int = DEFAULT_TOP_K,
    candidates: tuple[CandidateDefinition, ...] | None = None,
    force_rebuild: bool = False,
) -> dict[str, Any]:
    if top_k < 1:
        raise ValueError("top_k must be >= 1")

    benchmark_file = Path(benchmark_path or DEFAULT_BENCHMARK)
    if not benchmark_file.exists():
        raise FileNotFoundError(f"benchmark file not found: {benchmark_file}")

    queries, rows, spec = _load_benchmark_queries(benchmark_file)
    selected_candidates = _normalize_candidate_selection(candidates)

    run_records = [
        _run_candidate(
            Path(repo_root),
            queries,
            rows,
            candidate,
            benchmark_path_hash=spec.path_hash,
            top_k=top_k,
            force_rebuild=force_rebuild,
        )
        for candidate in selected_candidates
    ]

    baseline = run_records[0]
    if baseline["candidate_id"] != BASELINE_CANDIDATE_ID:
        raise RuntimeError("baseline candidate must be first in run order")

    comparisons = [
        _compare_candidate(spec, baseline, candidate_run) for candidate_run in run_records[1:]
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "program": {
            "version": PROGRAM_VERSION,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "top_k": top_k,
            "registry_version": DEFAULT_CANDIDATE_REGISTRY_VERSION,
            "candidate_definition_digest": _candidate_definition_digest(selected_candidates),
            "candidate_count": len(selected_candidates),
        },
        "repository": {
            "root": str(Path(repo_root).resolve()),
            "root_hash": _sha256_hex(str(Path(repo_root).resolve())),
            "force_rebuild": bool(force_rebuild),
        },
        "benchmark": {
            "path": spec.path,
            "hash": spec.path_hash,
            "query_count": spec.query_count,
            "graded_query_count": spec.graded_query_count,
            "families": spec.family_counts,
            "families_graded": spec.family_counts_graded,
            "rows": rows,
        },
        "promotions": {
            "allowed": False,
            "status": "human_review_required",
            "reason": "This loop is review-only by design",
            "evidence_required": "No candidate is auto-promoted",
        },
        "runs": run_records,
        "comparisons": comparisons,
        "constraints": {
            "name": "no protected regression",
            "metrics": {
                k: {"min_delta": v}
                for k, v in PROTECTED_METRICS.items()
            },
            "practical_gate": {
                "metric": PRIMARY_METRIC,
                "alpha": SIGNIFICANCE_ALPHA,
                "minimum_delta": PRIMARY_DELTA_MIN,
            },
            "lineage_immutable": True,
        },
        "query_set_hash": spec.path_hash,
        "run_id": _sha256_hex(_canonical_json({
            "benchmark": spec.path_hash,
            "candidate_ids": [c.candidate_id for c in selected_candidates],
            "candidate_definition_digest": _candidate_definition_digest(selected_candidates),
            "candidate_definition_version": DEFAULT_CANDIDATE_REGISTRY_VERSION,
            "top_k": top_k,
            "program_version": PROGRAM_VERSION,
        }))[:20],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run bounded retrieval variation candidates against a frozen benchmark.",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=DEFAULT_REPO_PATH,
        help="Repository root to evaluate.",
    )
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=DEFAULT_BENCHMARK,
        help="Frozen benchmark path.",
    )
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Per-query result cap.")
    parser.add_argument(
        "--candidate",
        action="append",
        default=None,
        help="Candidate IDs to run. Repeatable. Defaults to all known candidates.",
    )
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Rebuild index before each candidate run.",
    )
    parser.add_argument("--output", type=Path, default=None, help="Write JSON output to this file.")

    args = parser.parse_args(argv)

    selected_candidates: tuple[CandidateDefinition, ...] = DEFAULT_CANDIDATES
    if args.candidate:
        selected = [
            candidate
            for candidate in DEFAULT_CANDIDATES
            if candidate.candidate_id in set(args.candidate)
        ]
        if not selected:
            parser.error("no matching candidate ids")
        selected_candidates = tuple(selected)

    payload = run_variation_suite(
        repo_root=args.repo,
        benchmark_path=args.benchmark,
        top_k=args.top_k,
        candidates=selected_candidates,
        force_rebuild=args.force_rebuild,
    )

    text = json.dumps(payload, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
