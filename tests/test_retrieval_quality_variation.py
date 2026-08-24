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


def test_variant_loop_records_rejected_and_inconclusive_candidates(
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
                {"query": "a", "hit": True, "rr": 1.0},
                {"query": "b", "hit": False, "rr": 0.0},
                {"query": "c", "diagnostic_only": True, "rr": 0.0},
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
                {"query": "a", "hit": True, "rr": 1.0},
                {"query": "b", "hit": False, "rr": 0.0},
                {"query": "c", "diagnostic_only": True, "rr": 0.0},
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
                {"query": "a", "hit": True, "rr": 1.0},
                {"query": "b", "hit": True, "rr": 1.0},
                {"query": "c", "diagnostic_only": True, "rr": 0.0},
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
    assert query_enhanced_comparison["status"] == "inconclusive"
    assert query_enhanced_comparison["decision"] == "retain_candidate"
    assert query_enhanced_comparison["primary_p_value"] == 1.0


def test_predominantly_worse_candidate_is_not_promotable(monkeypatch, tmp_path):
    reciprocal_ranks = {
        "baseline-hybrid": [0.0] + [1.0 / 9.0] * 10 + [0.0] * 4,
        "cnfb-alpha-0.25": [1.0] + [1.0 / 10.0] * 10 + [0.0] * 4,
    }
    metrics = {
        "baseline-hybrid": {
            "mrr_at_10": sum(reciprocal_ranks["baseline-hybrid"]) / 15,
            "hit_rate": 10 / 15,
            "recall_at_10": 10 / 15,
            "ndcg_at_10": 0.20,
            "evidence_completeness": 0.50,
        },
        "cnfb-alpha-0.25": {
            "mrr_at_10": sum(reciprocal_ranks["cnfb-alpha-0.25"]) / 15,
            "hit_rate": 11 / 15,
            "recall_at_10": 11 / 15,
            "ndcg_at_10": 0.25,
            "evidence_completeness": 0.50,
        },
    }
    payloads = {}
    for candidate_id, ranks in reciprocal_ranks.items():
        payloads[candidate_id] = {
            "metrics": metrics[candidate_id],
            "run_stats": {
                "total_queries": 15,
                "graded_queries": 15,
                "diagnostic_queries": 0,
                "query_set_hash": "hash",
            },
            "hit_sequence": [rank > 0.0 for rank in ranks],
            "per_query": [
                {"query": f"q{index}", "hit": rank > 0.0, "rr": rank}
                for index, rank in enumerate(ranks)
            ],
        }

    benchmark = rv.BenchmarkSpec("benchmark", "hash", 15, 15, {}, {})
    queries = [
        rv.EvalQuery(query=f"q{index}", expected_file="expected")
        for index in range(15)
    ]
    rows = [{"query": query.query, "expected_file": "expected"} for query in queries]
    monkeypatch.setattr(
        rv,
        "_load_benchmark_queries",
        lambda _path: (queries, rows, benchmark),
    )
    monkeypatch.setattr(rv, "_run_candidate", _fake_run_candidate_factory(payloads))

    report = rv.run_variation_suite(
        repo_root=tmp_path,
        candidates=rv.DEFAULT_CANDIDATES[:2],
    )

    comparison = report["comparisons"][0]
    assert comparison["primary_p_value"] == 0.011719
    assert comparison["primary_delta"] > rv.PRIMARY_DELTA_MIN
    assert comparison["optimization_signal"]["candidate_wins"] == 1
    assert comparison["optimization_signal"]["candidate_losses"] == 10
    assert comparison["optimization_signal"]["candidate_direction_favorable"] is False
    assert comparison["status"] == "inconclusive"
    assert comparison["promotion_relevant"] is False


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
        "per_query": [{"rr": 1.0}, {"rr": 0.0}],
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
        "per_query": [{"rr": 1.0}, {"rr": 1.0}],
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


def test_run_variation_rejects_non_mrr_at_10_cutoff():
    with pytest.raises(ValueError, match="top_k must be 10 for mrr_at_10"):
        rv.run_variation_suite(Path("."), top_k=20)


def test_cli_rejects_every_unknown_candidate_id(capsys):
    with pytest.raises(SystemExit) as exc_info:
        rv.main(
            [
                "--candidate",
                rv.BASELINE_CANDIDATE_ID,
                "--candidate",
                "cnfb-alpha-typo",
            ]
        )

    assert exc_info.value.code == 2
    assert "unknown candidate ids: cnfb-alpha-typo" in capsys.readouterr().err


def test_parse_benchmark_requires_rows(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty"):
        rv._load_benchmark_queries(bad)
