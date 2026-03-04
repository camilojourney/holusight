from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from codesight import __main__ as cli
from codesight.benchmark import compare, configs, metrics, runner, storage
from codesight.types import Answer, SearchResult


def _mk_result(
    *,
    file_path: str = "src/codesight/chunker.py",
    start_line: int = 10,
    end_line: int = 12,
    chunk_id: str = "chunk-1",
) -> SearchResult:
    return SearchResult(
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        snippet="snippet",
        score=1.0,
        scope="function x",
        chunk_id=chunk_id,
    )


class StubEngine:
    def __init__(self, _path: str | Path) -> None:
        self._result = _mk_result()

    def search(self, _query: str, top_k: int = 10):
        return [self._result][:top_k]

    def ask(self, _question: str, top_k: int = 5) -> Answer:
        return Answer(text="answer", sources=[self._result][:top_k], model="stub")


def _mk_corpus(tmp_path: Path) -> Path:
    target = tmp_path / "src" / "codesight"
    target.mkdir(parents=True)
    (target / "chunker.py").write_text("# demo\n", encoding="utf-8")
    return tmp_path


def _mk_question_bank(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "questions.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


def test_spec_009_001_question_bank_distribution():
    """SPEC-009-001: Question bank has required categories and counts."""
    rows = json.loads(Path("tests/benchmarks/questions.json").read_text(encoding="utf-8"))
    assert 75 <= len(rows) <= 85
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["category"]] = counts.get(row["category"], 0) + 1
    assert counts["factoid"] == 20
    assert counts["code"] == 20
    assert counts["multi-hop"] == 15
    assert counts["jit"] == 10
    assert counts["negative"] == 10
    assert counts["adversarial"] == 5


def test_spec_009_002_retrieval_metrics_computation():
    """SPEC-009-002: Precision/Recall/NDCG are computed."""
    results = [_mk_result(), _mk_result(chunk_id="chunk-2", start_line=30, end_line=32)]
    truth = [{"file_path": "src/codesight/chunker.py", "start_line": 10, "end_line": 12}]
    values = metrics.compute_retrieval_metrics(results, truth)
    assert values["precision_at_k"] is not None
    assert values["recall_at_k"] is not None
    assert values["ndcg_at_10"] is not None


def test_spec_009_003_llm_metrics_skipped_without_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """SPEC-009-003: LLM metrics are None in retrieval-only runs."""
    corpus = _mk_corpus(tmp_path)
    qb = _mk_question_bank(
        tmp_path,
        [
            {
                "id": "q-1",
                "question": "q",
                "category": "factoid",
                "difficulty": "easy",
                "ground_truth": [
                    {"file_path": "src/codesight/chunker.py", "start_line": 1, "end_line": 1}
                ],
            }
        ],
    )
    db_path = tmp_path / "results.db"
    monkeypatch.setattr(runner, "CodeSight", StubEngine)

    out = runner.run_benchmark(
        config_name="B",
        corpus_path=corpus,
        include_llm=False,
        question_bank_path=qb,
        results_db_path=db_path,
    )
    db = storage.BenchmarkStore(db_path)
    scores = db.get_scores(out["run_id"])
    assert scores[0]["faithfulness"] is None
    assert scores[0]["hallucination_rate"] is None
    assert scores[0]["answer_relevancy"] is None


def test_spec_009_004_profiles_and_feature_requirements():
    """SPEC-009-004: Profile selection supports A-H and rejects unmet deps."""
    assert configs.get_profile("A").retrieval == "vector_only"
    assert configs.get_profile("B").retrieval == "hybrid"
    assert configs.get_profile("C").reranker == "minilm"
    assert configs.get_profile("D").reranker == "qwen3"
    assert configs.get_profile("E").chunking == "1024_overlap_15"
    assert configs.get_profile("F").requires_ast is True
    with pytest.raises(ValueError):
        configs.get_profile("G")
    with pytest.raises(ValueError):
        configs.get_profile("H")


def test_spec_009_005_sqlite_results_storage(tmp_path: Path):
    """SPEC-009-005: Run + score rows persist in SQLite."""
    db_path = tmp_path / "results.db"
    db = storage.BenchmarkStore(db_path)
    run_id = db.create_run(
        config_name="B",
        corpus_path="/tmp/corpus",
        question_bank_hash="abc123",
        include_llm=False,
    )
    db.insert_score(
        run_id=run_id,
        query_id="q1",
        category="factoid",
        excluded=False,
        precision_at_k=1.0,
        recall_at_k=1.0,
        ndcg_at_10=1.0,
        faithfulness=None,
        hallucination_rate=None,
        answer_relevancy=None,
        latency_ms=10.0,
    )
    db.finalize_run(run_id, {"precision_at_k": 1.0})

    db2 = storage.BenchmarkStore(db_path)
    run = db2.get_run(run_id)
    assert run is not None
    assert run["aggregate_metrics"]["precision_at_k"] == 1.0
    assert len(db2.get_scores(run_id)) == 1


def test_spec_009_006_wilcoxon_comparison(tmp_path: Path):
    """SPEC-009-006: Comparison outputs p-values and significance columns."""
    db = storage.BenchmarkStore(tmp_path / "results.db")
    run_a = db.create_run(
        config_name="A",
        corpus_path="/tmp/a",
        question_bank_hash="same-bank",
        include_llm=False,
    )
    run_b = db.create_run(
        config_name="B",
        corpus_path="/tmp/a",
        question_bank_hash="same-bank",
        include_llm=False,
    )
    for idx in range(35):
        db.insert_score(
            run_id=run_a,
            query_id=f"q-{idx}",
            category="factoid",
            excluded=False,
            precision_at_k=0.2,
            recall_at_k=0.2,
            ndcg_at_10=0.2,
            faithfulness=None,
            hallucination_rate=None,
            answer_relevancy=None,
            latency_ms=1.0,
        )
        db.insert_score(
            run_id=run_b,
            query_id=f"q-{idx}",
            category="factoid",
            excluded=False,
            precision_at_k=0.9,
            recall_at_k=0.9,
            ndcg_at_10=0.9,
            faithfulness=None,
            hallucination_rate=None,
            answer_relevancy=None,
            latency_ms=1.0,
        )
    output = compare.compare_runs(db, run_a, run_b)
    assert output["rows"]
    assert {"metric", "difference", "p_value", "significant"} <= set(output["rows"][0])


def test_spec_009_007_cli_benchmark_subcommands(monkeypatch: pytest.MonkeyPatch):
    """SPEC-009-007: benchmark run|compare|report are parsed by CLI."""
    calls: list[str] = []

    def fake_run(args):
        calls.append(args.benchmark_command)

    monkeypatch.setattr(cli, "_run_benchmark_cli", fake_run)

    monkeypatch.setattr(
        sys,
        "argv",
        ["codesight", "benchmark", "run", "--config", "B", "--corpus", "."],
    )
    cli.main()
    monkeypatch.setattr(
        sys, "argv", ["codesight", "benchmark", "compare", "--run-a", "a", "--run-b", "b"]
    )
    cli.main()
    monkeypatch.setattr(sys, "argv", ["codesight", "benchmark", "report", "--run", "a"])
    cli.main()
    assert calls == ["run", "compare", "report"]


def test_edge_009_001_missing_ground_truth_scored_as_negative():
    values = metrics.compute_retrieval_metrics([_mk_result()], [])
    assert values["precision_at_k"] is None
    assert values["false_positive_rate"] == 1.0


def test_edge_009_002_corpus_mismatch_excludes_queries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    corpus = _mk_corpus(tmp_path / "corpus")
    qb = _mk_question_bank(
        tmp_path,
        [
            {
                "id": "q-missing",
                "question": "q",
                "category": "factoid",
                "difficulty": "easy",
                "ground_truth": [
                    {"file_path": "src/does/not/exist.py", "start_line": 1, "end_line": 1}
                ],
            }
        ],
    )
    monkeypatch.setattr(runner, "CodeSight", StubEngine)
    out = runner.run_benchmark(
        config_name="B",
        corpus_path=corpus,
        question_bank_path=qb,
        results_db_path=tmp_path / "db.sqlite",
    )
    assert out["excluded_queries"] == 1
    assert "excluding query q-missing from metrics" in caplog.text


def test_edge_009_003_llm_backend_unavailable_sets_null_llm_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    class FailingLLMEngine(StubEngine):
        def ask(self, _question: str, top_k: int = 5) -> Answer:
            raise RuntimeError("offline")

    corpus = _mk_corpus(tmp_path / "corpus")
    qb = _mk_question_bank(
        tmp_path,
        [
            {
                "id": "q-1",
                "question": "q",
                "category": "factoid",
                "difficulty": "easy",
                "ground_truth": [
                    {"file_path": "src/codesight/chunker.py", "start_line": 1, "end_line": 1}
                ],
            }
        ],
    )
    db_path = tmp_path / "results.db"
    monkeypatch.setattr(runner, "CodeSight", FailingLLMEngine)
    out = runner.run_benchmark(
        config_name="B",
        corpus_path=corpus,
        include_llm=True,
        question_bank_path=qb,
        results_db_path=db_path,
    )
    db = storage.BenchmarkStore(db_path)
    score = db.get_scores(out["run_id"])[0]
    assert score["faithfulness"] is None
    assert "LLM backend unavailable" in caplog.text


def test_edge_009_004_warning_for_insufficient_paired_observations(tmp_path: Path):
    db = storage.BenchmarkStore(tmp_path / "results.db")
    run_a = db.create_run(
        config_name="A",
        corpus_path="/tmp/a",
        question_bank_hash="same-bank",
        include_llm=False,
    )
    run_b = db.create_run(
        config_name="B",
        corpus_path="/tmp/a",
        question_bank_hash="same-bank",
        include_llm=False,
    )
    for idx in range(5):
        kwargs = dict(
            query_id=f"q-{idx}",
            category="factoid",
            excluded=False,
            precision_at_k=0.5,
            recall_at_k=0.5,
            ndcg_at_10=0.5,
            faithfulness=None,
            hallucination_rate=None,
            answer_relevancy=None,
            latency_ms=1.0,
        )
        db.insert_score(run_id=run_a, **kwargs)
        db.insert_score(run_id=run_b, **kwargs)
    out = compare.compare_runs(db, run_a, run_b)
    assert out["warnings"]
    assert "n>=30" in out["warnings"][0]


def test_edge_009_005_config_requires_unimplemented_feature():
    with pytest.raises(ValueError, match="requires JIT retrieval"):
        configs.get_profile("G")
