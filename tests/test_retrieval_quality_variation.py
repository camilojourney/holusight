"""Tests for the bounded retrieval variation v1 loop."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests import retrieval_variation as rv


@pytest.fixture
def _fixture_query_rows() -> list[dict]:
    return [
        {
            "id": "Q1",
            "query": "how does hybrid search work",
            "family": "conceptual_localization",
            "expected_file": "src/codesight/search.py",
            "split": "dev",
        },
        {
            "id": "Q2",
            "query": "def rrf_merge",
            "family": "exact_lookup",
            "expected_file": "src/codesight/search.py",
            "split": "dev",
        },
        {
            "id": "Q3",
            "query": "unsupported query",
            "family": "contradiction_no_answer",
            "expected_file": "__NO_MATCH__",
            "split": "dev",
        },
    ]


def _fake_run_candidate_factory(payloads: dict[str, dict]):
    def _run_candidate(
        repo_root: Path,
        queries,
        rows,
        candidate,
        benchmark_path_hash,
        top_k,
        force_rebuild,
    ):
        if candidate.candidate_id not in payloads:
            raise KeyError(candidate.candidate_id)
        base = payloads[candidate.candidate_id]
        return {
            "candidate_id": candidate.candidate_id,
            "version": candidate.version,
            "run_id": candidate.candidate_id,
            "config_overrides": dict(candidate.config_overrides),
            "controlled_variable": candidate.controlled_variable,
            "controlled_value": candidate.controlled_value,
            "label": candidate.label,
            "description": candidate.description,
            "metrics": base["metrics"],
            "run_stats": base["run_stats"],
            "hit_sequence": base["hit_sequence"],
            "per_query": base["per_query"],
            "run_digest": "sha256:placeholder",
            "index_stats": {
                "files_indexed": 1,
                "chunks_created": 1,
                "forced_rebuild": force_rebuild,
                "index_warmed": True,
            },
            "lineage": {
                "candidate_id": candidate.candidate_id,
                "candidate_version": candidate.version,
                "registry_version": rv.DEFAULT_CANDIDATE_REGISTRY_VERSION,
                "run_id": candidate.candidate_id,
                "query_set_hash": benchmark_path_hash,
                "benchmark_hash": benchmark_path_hash,
                "recorded_utc": "2026-01-01T00:00:00+00:00",
            },
            "family_breakdown": {},
        }

    return _run_candidate


def test_variant_loop_records_rejected_and_promotable_candidates(
    monkeypatch, _fixture_query_rows, tmp_path
):
    benchmark = rv.BenchmarkSpec(
        path="tests/fixtures/holusight_retrieval_quality_variation_benchmark.json",
        path_hash="hash",
        query_count=3,
        graded_query_count=2,
        family_counts={
            "conceptual_localization": 1,
            "exact_lookup": 1,
            "contradiction_no_answer": 1,
        },
        family_counts_graded={"conceptual_localization": 1, "exact_lookup": 1},
    )

    def _load_stub(_path):
        return (
            [rv.EvalQuery(query=row["query"], expected_file=row["expected_file"]) for row in _fixture_query_rows],
            _fixture_query_rows,
            benchmark,
        )

    monkeypatch.setattr(rv, "_load_benchmark_queries", _load_stub)

    payloads = {
        "baseline-hybrid": {
            "metrics": {
                "mrr_at_10": 0.45,
                "hit_rate": 0.5,
                "recall_at_10": 0.5,
                "ndcg_at_10": 0.45,
                "evidence_completeness": 0.25,
                "avg_latency_ms": 10.0,
                "tokens_per_correct_answer": 11.0,
                "num_queries": 3,
                "num_graded": 2,
                "num_diagnostic_probes": 1,
                "total_tokens": 100,
            },
            "run_stats": {
                "total_queries": 3,
                "graded_queries": 2,
                "diagnostic_queries": 1,
                "query_set_hash": "hash",
            },
            "hit_sequence": [True, False],
            "per_query": [
                {"query": "a", "hit": True},
                {"query": "b", "hit": False},
                {"query": "c", "diagnostic_only": True},
            ],
        },
        "cnfb-alpha-0.25": {
            "metrics": {
                "mrr_at_10": 0.40,
                "hit_rate": 0.25,
                "recall_at_10": 0.25,
                "ndcg_at_10": 0.45,
                "evidence_completeness": 0.40,
                "avg_latency_ms": 10.0,
                "tokens_per_correct_answer": 12.0,
                "num_queries": 3,
                "num_graded": 2,
                "num_diagnostic_probes": 1,
                "total_tokens": 100,
            },
            "run_stats": {
                "total_queries": 3,
                "graded_queries": 2,
                "diagnostic_queries": 1,
                "query_set_hash": "hash",
            },
            "hit_sequence": [True, False],
            "per_query": [
                {"query": "a", "hit": True},
                {"query": "b", "hit": False},
                {"query": "c", "diagnostic_only": True},
            ],
        },
        "query-enhancement-on": {
            "metrics": {
                "mrr_at_10": 0.65,
                "hit_rate": 0.75,
                "recall_at_10": 0.75,
                "ndcg_at_10": 0.60,
                "evidence_completeness": 0.50,
                "avg_latency_ms": 10.0,
                "tokens_per_correct_answer": 12.0,
                "num_queries": 3,
                "num_graded": 2,
                "num_diagnostic_probes": 1,
                "total_tokens": 100,
            },
            "run_stats": {
                "total_queries": 3,
                "graded_queries": 2,
                "diagnostic_queries": 1,
                "query_set_hash": "hash",
            },
            "hit_sequence": [True, True],
            "per_query": [
                {"query": "a", "hit": True},
                {"query": "b", "hit": True},
                {"query": "c", "diagnostic_only": True},
            ],
        },
    }

    monkeypatch.setattr(rv, "_run_candidate", _fake_run_candidate_factory(payloads))

    report = rv.run_variation_suite(
        repo_root=tmp_path,
        candidates=rv.DEFAULT_CANDIDATES,
    )

    assert report["program"]["candidate_count"] == 3
    assert report["promotions"]["allowed"] is False

    cnfb_comparison, query_enhanced_comparison = report["comparisons"]
    assert cnfb_comparison["status"] == "reject"
    assert query_enhanced_comparison["status"] == "promotable"
    assert query_enhanced_comparison["decision"] == "human_review_required"


def test_compare_candidate_blocks_regression():
    baseline = {
        "candidate_id": "baseline-hybrid",
        "run_id": "base",
        "run_stats": {"graded_queries": 2},
        "metrics": {
            "mrr_at_10": 0.50,
            "hit_rate": 0.75,
            "recall_at_10": 0.75,
            "ndcg_at_10": 0.50,
            "evidence_completeness": 0.80,
        },
        "hit_sequence": [True, False],
    }
    candidate = {
        "candidate_id": "cnfb-alpha-0.25",
        "run_id": "cand",
        "run_stats": {"graded_queries": 2},
        "metrics": {
            "mrr_at_10": 0.55,
            "hit_rate": 0.74,
            "recall_at_10": 0.75,
            "ndcg_at_10": 0.50,
            "evidence_completeness": 0.80,
        },
        "hit_sequence": [True, True],
    }

    comparison = rv._compare_candidate(
        rv.BenchmarkSpec("x", "h", 2, 2, {}, {}),
        baseline,
        candidate,
    )

    assert comparison["status"] == "reject"
    assert comparison["constraints"]["violations"]


def test_compare_candidate_requires_matching_graded_counts():
    baseline = {
        "candidate_id": "baseline-hybrid",
        "run_id": "base",
        "run_stats": {"graded_queries": 2},
        "hit_sequence": [True, False],
        "metrics": {},
    }
    candidate = {
        "candidate_id": "cnfb-alpha-0.25",
        "run_id": "cand",
        "run_stats": {"graded_queries": 1},
        "hit_sequence": [True],
        "metrics": {},
    }

    comparison = rv._compare_candidate(
        rv.BenchmarkSpec("x", "h", 2, 2, {}, {}),
        baseline,
        candidate,
    )

    assert comparison["status"] == "invalid"
    assert comparison["decision"] == "invalid_comparison"


def test_run_variation_requires_baseline_candidate():
    with pytest.raises(ValueError, match="baseline-hybrid"):
        rv.run_variation_suite(Path("."), candidates=(rv.DEFAULT_CANDIDATES[1],))


def test_parse_benchmark_requires_rows(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty"):
        rv._load_benchmark_queries(bad)
