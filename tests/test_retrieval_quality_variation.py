"""Tests for the bounded retrieval variation v1 loop."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from codesight import config as config_module
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
        per_query = []
        for entry in base["per_query"]:
            normalized = dict(entry)
            normalized.setdefault("family", "unspecified")
            normalized.setdefault("diagnostic_only", False)
            normalized.setdefault(
                "evidence_completeness",
                base["metrics"].get("evidence_completeness", 0.0),
            )
            if normalized["diagnostic_only"]:
                normalized.update(hit=False, rank=None, rr=0.0, ndcg=0.0, evidence_completeness=0.0)
                normalized.setdefault("top_result_file", None)
                expected = "deny"
                observed = (
                    "deny" if normalized["top_result_file"] is None else "unsupported_evidence"
                )
            elif normalized["family"] == "ambiguity":
                expected = observed = "clarify"
            else:
                expected = "evidence"
                observed = "evidence" if normalized.get("hit", False) else "insufficient_evidence"
            if not normalized["diagnostic_only"]:
                if normalized.get("hit", False):
                    normalized["rank"] = round(1.0 / normalized["rr"])
                    normalized["ndcg"] = round(
                        1.0 / math.log2(normalized["rank"] + 1),
                        4,
                    )
                else:
                    normalized.update(rank=None, rr=0.0, ndcg=0.0)
            normalized["expected_routing_outcome"] = expected
            normalized["routing_outcome"] = observed
            normalized["routing_pass"] = expected == observed
            per_query.append(normalized)

        graded = [entry for entry in per_query if not entry["diagnostic_only"]]
        metrics = dict(base["metrics"])
        metrics.update(
            {
                "mrr_at_10": sum(entry["rr"] for entry in graded) / len(graded),
                "hit_rate": sum(entry["hit"] for entry in graded) / len(graded),
                "recall_at_10": sum(entry["hit"] for entry in graded) / len(graded),
                "ndcg_at_10": sum(entry["ndcg"] for entry in graded) / len(graded),
                "evidence_completeness": (
                    sum(entry["evidence_completeness"] for entry in graded) / len(graded)
                ),
            }
        )
        record = {
            "candidate_id": candidate.candidate_id,
            "version": candidate.version,
            "run_id": candidate.candidate_id,
            "config_overrides": dict(candidate.config_overrides),
            "controlled_variable": candidate.controlled_variable,
            "controlled_value": candidate.controlled_value,
            "label": candidate.label,
            "description": candidate.description,
            "metrics": metrics,
            "run_stats": base["run_stats"],
            "hit_sequence": [entry["hit"] for entry in graded],
            "per_query": per_query,
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
        record["run_id"] = rv._run_record_id(record, benchmark_path_hash)
        record["lineage"]["run_id"] = record["run_id"]
        record["run_digest"] = rv._run_record_digest(record)
        return record

    return _run_candidate


def _seal_run(run: dict, benchmark: rv.BenchmarkSpec, candidate: rv.CandidateDefinition) -> dict:
    sealed = dict(run)
    sealed.update(
        {
            "candidate_id": candidate.candidate_id,
            "version": candidate.version,
            "config_overrides": dict(candidate.config_overrides),
        }
    )
    sealed["run_stats"] = {
        "total_queries": len(sealed["per_query"]),
        "graded_queries": sealed["run_stats"]["graded_queries"],
        "diagnostic_queries": 0,
        "query_set_hash": benchmark.path_hash,
    }
    per_query = []
    for entry in sealed["per_query"]:
        normalized = {
            "family": "unspecified",
            "diagnostic_only": False,
            "evidence_completeness": sealed["metrics"].get("evidence_completeness", 0.0),
            **entry,
        }
        if normalized["diagnostic_only"]:
            normalized.update(hit=False, rank=None, rr=0.0, ndcg=0.0, evidence_completeness=0.0)
        else:
            normalized.setdefault("hit", normalized.get("rr", 0.0) > 0.0)
            if normalized["hit"]:
                normalized.setdefault("rank", round(1.0 / normalized["rr"]))
                normalized["ndcg"] = round(1.0 / math.log2(normalized["rank"] + 1), 4)
            else:
                normalized.setdefault("rank", None)
                normalized["ndcg"] = 0.0
        if normalized["diagnostic_only"]:
            normalized.setdefault("top_result_file", None)
            normalized["expected_routing_outcome"] = "deny"
            normalized["routing_outcome"] = (
                "deny" if normalized["top_result_file"] is None else "unsupported_evidence"
            )
        elif normalized["family"] == "ambiguity":
            normalized["expected_routing_outcome"] = "clarify"
            normalized["routing_outcome"] = "clarify"
        else:
            normalized["expected_routing_outcome"] = "evidence"
            normalized["routing_outcome"] = (
                "evidence" if normalized["hit"] else "insufficient_evidence"
            )
        normalized["routing_pass"] = (
            normalized["routing_outcome"] == normalized["expected_routing_outcome"]
        )
        per_query.append(normalized)
    sealed["per_query"] = per_query
    graded = [entry for entry in per_query if not entry["diagnostic_only"]]
    diagnostic = [entry for entry in per_query if entry["diagnostic_only"]]
    sealed["run_stats"].update(
        {
            "total_queries": len(per_query),
            "graded_queries": len(graded),
            "diagnostic_queries": len(diagnostic),
            "query_set_hash": benchmark.path_hash,
        }
    )
    sealed["hit_sequence"] = [entry["hit"] for entry in graded]
    sealed["metrics"].update(
        {
            "mrr_at_10": sum(entry["rr"] for entry in graded) / len(graded),
            "hit_rate": sum(entry["hit"] for entry in graded) / len(graded),
            "recall_at_10": sum(entry["hit"] for entry in graded) / len(graded),
            "ndcg_at_10": sum(entry["ndcg"] for entry in graded) / len(graded),
            "evidence_completeness": (
                sum(entry["evidence_completeness"] for entry in graded) / len(graded)
            ),
        }
    )
    sealed["lineage"] = {
        "candidate_id": candidate.candidate_id,
        "candidate_version": candidate.version,
        "registry_version": rv.DEFAULT_CANDIDATE_REGISTRY_VERSION,
        "run_id": sealed["run_id"],
        "query_set_hash": benchmark.path_hash,
        "benchmark_hash": benchmark.path_hash,
        "recorded_utc": "2026-01-01T00:00:00+00:00",
    }
    sealed["run_id"] = rv._run_record_id(sealed, benchmark.path_hash)
    sealed["lineage"]["run_id"] = sealed["run_id"]
    sealed["run_digest"] = rv._run_record_digest(sealed)
    return sealed


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
            [
                rv.EvalQuery(query=row["query"], expected_file=row["expected_file"])
                for row in _fixture_query_rows
            ],
            _fixture_query_rows,
            benchmark,
        )

    monkeypatch.setattr(rv, "_load_benchmark_queries", _load_stub)
    monkeypatch.setattr(rv, "FROZEN_BENCHMARK_HASH", "hash")

    payloads = {
        "baseline-hybrid": {
            "metrics": {
                "mrr_at_10": 0.5,
                "hit_rate": 0.5,
                "recall_at_10": 0.5,
                "ndcg_at_10": 0.5,
                "evidence_completeness": 0.5,
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
                "mrr_at_10": 0.0,
                "hit_rate": 0.0,
                "recall_at_10": 0.0,
                "ndcg_at_10": 0.0,
                "evidence_completeness": 0.0,
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
                {"query": "a", "hit": False, "rr": 0.0},
                {"query": "b", "hit": False, "rr": 0.0},
                {"query": "c", "diagnostic_only": True, "rr": 0.0},
            ],
        },
        "metadata-boost-off": {
            "metrics": {
                "mrr_at_10": 0.5,
                "hit_rate": 1.0,
                "recall_at_10": 1.0,
                "ndcg_at_10": 0.5,
                "evidence_completeness": 0.5,
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
                {"query": "a", "hit": True, "rr": 0.5},
                {"query": "b", "hit": True, "rr": 0.5},
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

    cnfb_comparison, metadata_comparison = report["comparisons"]
    assert cnfb_comparison["status"] == "reject"
    assert metadata_comparison["status"] == "inconclusive"
    assert metadata_comparison["decision"] == "retain_candidate"
    assert metadata_comparison["primary_p_value"] == 1.0


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
    queries = [rv.EvalQuery(query=f"q{index}", expected_file="expected") for index in range(15)]
    rows = [{"query": query.query, "expected_file": "expected"} for query in queries]
    monkeypatch.setattr(
        rv,
        "_load_benchmark_queries",
        lambda _path: (queries, rows, benchmark),
    )
    monkeypatch.setattr(rv, "_run_candidate", _fake_run_candidate_factory(payloads))
    monkeypatch.setattr(rv, "FROZEN_BENCHMARK_HASH", "hash")

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
            "hit_rate": 0.50,
            "recall_at_10": 0.50,
            "ndcg_at_10": 0.50,
            "evidence_completeness": 0.80,
        },
        "hit_sequence": [True, False],
        "per_query": [
            {"rr": 1.0, "ndcg": 1.0, "evidence_completeness": 0.8},
            {"rr": 0.0, "ndcg": 0.0, "evidence_completeness": 0.8},
        ],
    }
    candidate = {
        "candidate_id": "cnfb-alpha-0.25",
        "run_id": "cand",
        "run_stats": {"graded_queries": 2},
        "metrics": {
            "mrr_at_10": 0.55,
            "hit_rate": 1.0,
            "recall_at_10": 1.0,
            "ndcg_at_10": 0.49,
            "evidence_completeness": 0.79,
        },
        "hit_sequence": [True, True],
        "per_query": [
            {"rr": 1.0, "ndcg": 0.5, "evidence_completeness": 0.79},
            {"rr": 0.1, "ndcg": 0.48, "evidence_completeness": 0.79},
        ],
    }
    benchmark = rv.BenchmarkSpec("x", "h", 2, 2, {}, {})
    baseline = _seal_run(baseline, benchmark, rv.DEFAULT_CANDIDATES[0])
    candidate = _seal_run(candidate, benchmark, rv.DEFAULT_CANDIDATES[1])

    comparison = rv._compare_candidate(
        benchmark,
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
        "metrics": {
            "mrr_at_10": 0.5,
            "hit_rate": 0.5,
            "recall_at_10": 0.5,
            "ndcg_at_10": 0.5,
            "evidence_completeness": 0.5,
        },
        "per_query": [
            {"query": "a", "hit": True, "rr": 1.0, "ndcg": 1.0},
            {"query": "b", "hit": False, "rr": 0.0, "ndcg": 0.0},
        ],
    }
    candidate = {
        "candidate_id": "cnfb-alpha-0.25",
        "run_id": "cand",
        "run_stats": {"graded_queries": 1},
        "hit_sequence": [True],
        "metrics": {
            "mrr_at_10": 1.0,
            "hit_rate": 1.0,
            "recall_at_10": 1.0,
            "ndcg_at_10": 1.0,
            "evidence_completeness": 1.0,
        },
        "per_query": [{"query": "a", "hit": True, "rr": 1.0, "ndcg": 1.0}],
    }

    benchmark = rv.BenchmarkSpec("x", "h", 2, 2, {}, {})
    baseline = _seal_run(baseline, benchmark, rv.DEFAULT_CANDIDATES[0])
    candidate = _seal_run(candidate, benchmark, rv.DEFAULT_CANDIDATES[1])
    comparison = rv._compare_candidate(
        benchmark,
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


def test_cli_indexes_retrieves_and_persists_frozen_evidence(monkeypatch, tmp_path):
    benchmark_path = tmp_path / "frozen-benchmark.json"
    benchmark_rows = [
        {
            "id": "EX-01",
            "query": "Net 30 payment terms",
            "family": "exact_lookup",
            "split": "dev",
            "expected_file": "payment-terms.md",
        },
        {
            "id": "ADV-01",
            "query": "unsupported kubernetes deployment",
            "family": "adversarial",
            "split": "dev",
            "expected_file": "__NO_MATCH__",
        },
    ]
    benchmark_path.write_text(json.dumps(benchmark_rows), encoding="utf-8")
    benchmark_hash = rv._sha256_hex(rv._canonical_json(benchmark_rows))
    monkeypatch.setattr(rv, "DEFAULT_BENCHMARK", benchmark_path)
    monkeypatch.setattr(rv, "FROZEN_BENCHMARK_HASH", benchmark_hash)
    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "index-data")
    output = tmp_path / "evidence" / "report.json"
    repo = Path(__file__).parent / "fixtures" / "pilot_docs"

    assert (
        rv.main(
            [
                "--repo",
                str(repo),
                "--candidate",
                rv.BASELINE_CANDIDATE_ID,
                "--candidate",
                "cnfb-alpha-0.25",
                "--output",
                str(output),
            ]
        )
        == 0
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert len(report["runs"]) == 2
    assert report["benchmark"]["hash"] == benchmark_hash
    assert report["promotions"]["allowed"] is False
    assert all(run["run_digest"] == rv._run_record_digest(run) for run in report["runs"])
    assert report["runs"][0]["per_query"][1]["expected_routing_outcome"] == "deny"
    assert report["comparisons"][0]["status"] == "reject"


def test_registry_forbids_query_expansion_and_unregistered_definitions():
    assert all(
        candidate.config_overrides["query_enhancement"] is False
        for candidate in rv.DEFAULT_CANDIDATES
    )
    mutated = rv.CandidateDefinition(
        candidate_id=rv.BASELINE_CANDIDATE_ID,
        version="v999",
        label="mutated",
        config_overrides={"query_enhancement": True},
        controlled_variable="multiple",
        controlled_value="multiple",
        description="unregistered",
    )
    with pytest.raises(ValueError, match="immutable registry"):
        rv._normalize_candidate_selection((mutated,))


def test_run_variation_rejects_unregistered_benchmark(tmp_path):
    benchmark = tmp_path / "benchmark.json"
    benchmark.write_text(
        '[{"id":"Q1","query":"q","family":"exact_lookup","expected_file":"README.md"}]',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="immutable registered benchmark path"):
        rv.run_variation_suite(tmp_path, benchmark_path=benchmark)


def test_compare_rejects_malformed_evidence():
    benchmark = rv.BenchmarkSpec("x", "hash", 6, 6, {}, {})
    base = {
        "run_id": "base",
        "run_stats": {"graded_queries": 6},
        "metrics": {
            "mrr_at_10": 0.0,
            "hit_rate": 0.0,
            "recall_at_10": 0.0,
            "ndcg_at_10": 0.0,
            "evidence_completeness": 0.0,
        },
        "per_query": [{"query": f"q{i}", "rr": 0.0} for i in range(6)],
    }
    candidate = {
        "run_id": "candidate",
        "run_stats": {"graded_queries": 6},
        "metrics": {
            "mrr_at_10": 1.0,
            "hit_rate": 1.0,
            "recall_at_10": 1.0,
            "ndcg_at_10": 1.0,
            "evidence_completeness": 1.0,
        },
        "per_query": [{"query": f"q{i}", "rr": 1.0} for i in range(6)],
    }
    base = _seal_run(base, benchmark, rv.DEFAULT_CANDIDATES[0])
    candidate = _seal_run(candidate, benchmark, rv.DEFAULT_CANDIDATES[1])
    candidate["lineage"]["benchmark_hash"] = "forged"
    candidate["per_query"][0]["query"] = "altered identity"
    candidate["run_digest"] = "forged"

    comparison = rv._compare_candidate(benchmark, base, candidate)

    assert comparison["status"] == "invalid"
    assert comparison["promotion_relevant"] is False
    assert comparison["constraints"]["violations"]


def test_compare_rejects_self_consistent_impossible_rank_evidence():
    benchmark = rv.BenchmarkSpec("x", "hash", 6, 6, {}, {})
    baseline = _seal_run(
        {
            "run_id": "base",
            "run_stats": {"graded_queries": 6},
            "metrics": {
                "mrr_at_10": 0.0,
                "hit_rate": 0.0,
                "recall_at_10": 0.0,
                "ndcg_at_10": 0.0,
                "evidence_completeness": 0.0,
            },
            "per_query": [{"query": f"q{i}", "rr": 0.0} for i in range(6)],
        },
        benchmark,
        rv.DEFAULT_CANDIDATES[0],
    )
    candidate = _seal_run(
        {
            "run_id": "candidate",
            "run_stats": {"graded_queries": 6},
            "metrics": {
                "mrr_at_10": 1.0,
                "hit_rate": 1.0,
                "recall_at_10": 1.0,
                "ndcg_at_10": 1.0,
                "evidence_completeness": 1.0,
            },
            "per_query": [{"query": f"q{i}", "rr": 1.0} for i in range(6)],
        },
        benchmark,
        rv.DEFAULT_CANDIDATES[1],
    )
    valid_comparison = rv._compare_candidate(benchmark, baseline, candidate)
    assert valid_comparison["status"] == "promotable"
    assert valid_comparison["decision"] == "human_review_required"
    assert valid_comparison["promotion_relevant"] is True

    for entry in candidate["per_query"]:
        entry["rank"] = None
    candidate["run_id"] = rv._run_record_id(candidate, benchmark.path_hash)
    candidate["lineage"]["run_id"] = candidate["run_id"]
    candidate["run_digest"] = rv._run_record_digest(candidate)

    comparison = rv._compare_candidate(benchmark, baseline, candidate)

    assert comparison["status"] == "invalid"
    assert comparison["promotion_relevant"] is False
    assert any(
        violation["type"] == "retrieval_evidence_mismatch"
        for violation in comparison["constraints"]["violations"]
    )


def test_compare_rejects_swapped_diagnostic_identities():
    identities = (
        ("ADV-01", "unsupported", "adversarial", rv.NO_MATCH_SENTINEL),
        ("EX-01", "exact", "exact_lookup", "README.md"),
    )
    benchmark = rv.BenchmarkSpec("x", "hash", 2, 1, {}, {}, identities)
    rows = [
        {
            "id": identity[0],
            "query": identity[1],
            "family": identity[2],
            "expected_file": identity[3],
            "diagnostic_only": identity[3] == rv.NO_MATCH_SENTINEL,
            "rr": 0.0,
        }
        for identity in identities
    ]
    empty_metrics = {
        "mrr_at_10": 0.0,
        "hit_rate": 0.0,
        "recall_at_10": 0.0,
        "ndcg_at_10": 0.0,
        "evidence_completeness": 0.0,
    }
    baseline = _seal_run(
        {
            "run_id": "base",
            "run_stats": {"graded_queries": 1},
            "metrics": dict(empty_metrics),
            "per_query": rows,
        },
        benchmark,
        rv.DEFAULT_CANDIDATES[0],
    )
    candidate = _seal_run(
        {
            "run_id": "candidate",
            "run_stats": {"graded_queries": 1},
            "metrics": dict(empty_metrics),
            "per_query": rows,
        },
        benchmark,
        rv.DEFAULT_CANDIDATES[1],
    )
    candidate["per_query"][0].update(
        diagnostic_only=False,
        hit=True,
        rank=1,
        rr=1.0,
        ndcg=1.0,
        evidence_completeness=1.0,
        expected_routing_outcome="evidence",
        routing_outcome="evidence",
        routing_pass=True,
    )
    candidate["per_query"][1].update(
        diagnostic_only=True,
        hit=False,
        rank=None,
        rr=0.0,
        ndcg=0.0,
        evidence_completeness=0.0,
        top_result_file=None,
        expected_routing_outcome="deny",
        routing_outcome="deny",
        routing_pass=True,
    )
    candidate["metrics"].update(
        mrr_at_10=1.0,
        hit_rate=1.0,
        recall_at_10=1.0,
        ndcg_at_10=1.0,
        evidence_completeness=1.0,
    )
    candidate["hit_sequence"] = [True]
    candidate["run_id"] = rv._run_record_id(candidate, benchmark.path_hash)
    candidate["lineage"]["run_id"] = candidate["run_id"]
    candidate["run_digest"] = rv._run_record_digest(candidate)

    comparison = rv._compare_candidate(benchmark, baseline, candidate)

    assert comparison["status"] == "invalid"
    assert comparison["promotion_relevant"] is False
    assert any(
        violation["type"] == "diagnostic_identity_mismatch"
        for violation in comparison["constraints"]["violations"]
    )


def test_candidate_failure_is_retained(monkeypatch, tmp_path):
    benchmark = rv.BenchmarkSpec("x", "hash", 1, 1, {}, {})
    rows = [{"query": "q", "expected_file": "README.md"}]
    queries = [rv.EvalQuery("q", "README.md")]
    payloads = {
        rv.BASELINE_CANDIDATE_ID: {
            "metrics": {
                "mrr_at_10": 1.0,
                "hit_rate": 1.0,
                "recall_at_10": 1.0,
                "ndcg_at_10": 1.0,
                "evidence_completeness": 1.0,
            },
            "run_stats": {
                "total_queries": 1,
                "graded_queries": 1,
                "diagnostic_queries": 0,
                "query_set_hash": "hash",
            },
            "hit_sequence": [True],
            "per_query": [{"query": "q", "hit": True, "rr": 1.0}],
        }
    }
    baseline_runner = _fake_run_candidate_factory(payloads)

    def run_or_fail(*args, **kwargs):
        candidate = args[3]
        if candidate.candidate_id != rv.BASELINE_CANDIDATE_ID:
            raise RuntimeError("candidate execution failed")
        return baseline_runner(*args, **kwargs)

    monkeypatch.setattr(rv, "_load_benchmark_queries", lambda _path: (queries, rows, benchmark))
    monkeypatch.setattr(rv, "FROZEN_BENCHMARK_HASH", "hash")
    monkeypatch.setattr(rv, "_run_candidate", run_or_fail)

    report = rv.run_variation_suite(tmp_path, candidates=rv.DEFAULT_CANDIDATES[:2])

    assert report["runs"][1]["status"] == "failed"
    assert report["runs"][1]["decision"] == "retain_candidate"
    assert report["comparisons"][0]["status"] == "invalid"


def test_denial_routing_failure_blocks_promotion():
    benchmark = rv.BenchmarkSpec("x", "hash", 7, 6, {}, {})
    base_rows = [{"query": f"q{i}", "rr": 0.0} for i in range(6)]
    candidate_rows = [{"query": f"q{i}", "rr": 1.0} for i in range(6)]
    diagnostic = {
        "id": "ADV-01",
        "query": "unsupported",
        "family": "adversarial",
        "diagnostic_only": True,
        "top_result_file": "README.md",
        "rr": 0.0,
    }
    common_metrics = {
        "hit_rate": 0.0,
        "recall_at_10": 0.0,
        "mrr_at_10": 0.0,
        "ndcg_at_10": 0.0,
        "evidence_completeness": 0.0,
    }
    base = _seal_run(
        {
            "run_id": "base",
            "run_stats": {"graded_queries": 6},
            "metrics": common_metrics,
            "per_query": [*base_rows, diagnostic],
        },
        benchmark,
        rv.DEFAULT_CANDIDATES[0],
    )
    candidate = _seal_run(
        {
            "run_id": "candidate",
            "run_stats": {"graded_queries": 6},
            "metrics": {key: 1.0 for key in common_metrics},
            "per_query": [*candidate_rows, diagnostic],
        },
        benchmark,
        rv.DEFAULT_CANDIDATES[1],
    )
    for run in (base, candidate):
        denial = run["per_query"][-1]
        denial["expected_routing_outcome"] = "deny"
        denial["routing_outcome"] = "unsupported_evidence"
        denial["routing_pass"] = False
        run["run_id"] = rv._run_record_id(run, benchmark.path_hash)
        run["lineage"]["run_id"] = run["run_id"]
        run["run_digest"] = rv._run_record_digest(run)

    comparison = rv._compare_candidate(benchmark, base, candidate)

    assert comparison["status"] == "reject"
    assert comparison["promotion_relevant"] is False
    assert any(
        violation.get("type") == "evidence_routing_failure"
        for violation in comparison["constraints"]["violations"]
    )


def test_cli_rejects_output_inside_indexed_repository(monkeypatch, tmp_path):
    called = False

    def should_not_run(**_kwargs):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(rv, "run_variation_suite", should_not_run)
    with pytest.raises(SystemExit) as exc_info:
        rv.main(["--repo", str(tmp_path), "--output", str(tmp_path / "report.json")])

    assert exc_info.value.code == 2
    assert called is False
    assert not (tmp_path / "report.json").exists()
