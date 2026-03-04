"""Benchmark runner for query bank execution and metric aggregation."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from ..api import CodeSight
from ..types import SearchResult
from .configs import BenchmarkProfile, get_profile, load_profile_from_file
from .metrics import compute_answer_metrics, compute_retrieval_metrics
from .storage import BenchmarkStore

logger = logging.getLogger(__name__)

DEFAULT_QUESTION_BANK_PATH = Path("tests/benchmarks/questions.json")
DEFAULT_RESULTS_DB_PATH = Path("tests/benchmarks/results.db")
QUESTION_CATEGORIES = {"factoid", "code", "multi-hop", "jit", "negative", "adversarial"}


@dataclass(frozen=True)
class BenchmarkQuery:
    query_id: str
    question: str
    category: str
    difficulty: str
    ground_truth: list[dict[str, Any]]


def _question_bank_hash(path: Path) -> str:
    payload = path.read_bytes()
    return hashlib.sha256(payload).hexdigest()[:16]


# SPEC-009-001: Load validated benchmark query bank from JSON.
def load_question_bank(path: str | Path) -> list[BenchmarkQuery]:
    bank_path = Path(path)
    raw = json.loads(bank_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Question bank must be a JSON array.")

    queries: list[BenchmarkQuery] = []
    for row in raw:
        query_id = str(row["id"])
        category = str(row["category"])
        ground_truth = list(row.get("ground_truth", []))

        if category not in QUESTION_CATEGORIES:
            raise ValueError(f"Query {query_id} has invalid category '{category}'.")
        if category != "negative" and not ground_truth:
            raise ValueError(f"Query {query_id} must include at least one ground-truth entry.")

        queries.append(
            BenchmarkQuery(
                query_id=query_id,
                question=str(row["question"]),
                category=category,
                difficulty=str(row.get("difficulty", "medium")),
                ground_truth=ground_truth,
            )
        )
    return queries


def _progress(current: int, total: int) -> None:
    width = 24
    done = int((current / total) * width)
    bar = "#" * done + "-" * (width - done)
    print(f"\r[{bar}] {current}/{total}", end="", flush=True)
    if current == total:
        print()


def _vector_only_search(engine: CodeSight, query: str, top_k: int = 10) -> list[SearchResult]:
    engine._ensure_indexed()
    query_vector = engine.embedder.embed_query(query)
    chunk_ids = engine.store.vector_search(query_vector, top_k=top_k)
    metadata = engine.store.get_chunk_metadata(chunk_ids)
    results: list[SearchResult] = []
    for rank, chunk_id in enumerate(chunk_ids, start=1):
        meta = metadata.get(chunk_id)
        if meta is None:
            continue
        results.append(
            SearchResult(
                file_path=meta["file_path"],
                start_line=meta["start_line"],
                end_line=meta["end_line"],
                snippet=meta["content"],
                score=round(1.0 / rank, 6),
                scope=meta["scope"],
                chunk_id=chunk_id,
            )
        )
    return results


def _run_query(engine: CodeSight, profile: BenchmarkProfile, question: str) -> list[SearchResult]:
    if profile.retrieval == "vector_only":
        return _vector_only_search(engine, question)
    return engine.search(question, top_k=10)


def _aggregate(scores: list[dict[str, Any]]) -> dict[str, float]:
    metrics = [
        "precision_at_k",
        "recall_at_k",
        "ndcg_at_10",
        "faithfulness",
        "hallucination_rate",
        "answer_relevancy",
        "latency_ms",
    ]
    aggregates: dict[str, float] = {}
    for metric in metrics:
        values = [
            float(row[metric])
            for row in scores
            if row.get(metric) is not None and not row["excluded"]
        ]
        if not values:
            continue
        aggregates[metric] = round(mean(values), 6)
    return aggregates


# SPEC-009-007: Benchmark CLI run operation entrypoint.
def run_benchmark(
    *,
    config_name: str,
    corpus_path: str | Path,
    include_llm: bool = False,
    question_bank_path: str | Path = DEFAULT_QUESTION_BANK_PATH,
    results_db_path: str | Path = DEFAULT_RESULTS_DB_PATH,
    config_file: str | Path | None = None,
) -> dict[str, Any]:
    if config_file:
        profile = load_profile_from_file(config_file)
    else:
        profile = get_profile(config_name)

    bank_path = Path(question_bank_path)
    queries = load_question_bank(bank_path)
    store = BenchmarkStore(results_db_path)

    run_id = store.create_run(
        config_name=profile.name,
        corpus_path=str(Path(corpus_path).resolve()),
        question_bank_hash=_question_bank_hash(bank_path),
        include_llm=include_llm,
    )

    engine = CodeSight(corpus_path)
    llm_warning_emitted = False
    excluded_queries = 0

    for idx, query in enumerate(queries, start=1):
        _progress(idx, len(queries))
        start_time = time.perf_counter()

        missing_ground_truth_file = False
        for gt in query.ground_truth:
            gt_path = gt.get("file_path")
            if gt_path and not (Path(corpus_path) / gt_path).exists():
                # EDGE-009-002: Corpus mismatch excludes query and logs warning.
                logger.warning(
                    "WARNING: Ground truth file %s not found in corpus - "
                    "excluding query %s from metrics",
                    gt_path,
                    query.query_id,
                )
                missing_ground_truth_file = True
                excluded_queries += 1
                break
        if missing_ground_truth_file:
            store.insert_score(
                run_id=run_id,
                query_id=query.query_id,
                category=query.category,
                excluded=True,
                precision_at_k=None,
                recall_at_k=None,
                ndcg_at_10=None,
                faithfulness=None,
                hallucination_rate=None,
                answer_relevancy=None,
                latency_ms=round((time.perf_counter() - start_time) * 1000, 3),
            )
            continue

        results = _run_query(engine, profile, query.question)
        retrieval = compute_retrieval_metrics(results, query.ground_truth)

        faithfulness = None
        hallucination_rate = None
        answer_relevancy = None

        if include_llm:
            try:
                answer = engine.ask(query.question, top_k=5)
                answer_metrics = compute_answer_metrics(
                    question=query.question,
                    answer_text=answer.text,
                    contexts=[result.snippet for result in answer.sources],
                )
                faithfulness = answer_metrics["faithfulness"]
                hallucination_rate = answer_metrics["hallucination_rate"]
                answer_relevancy = answer_metrics["answer_relevancy"]
            except Exception:
                # EDGE-009-003: LLM unavailability keeps retrieval run valid.
                if not llm_warning_emitted:
                    logger.warning(
                        "LLM backend unavailable - retrieval metrics computed, "
                        "LLM metrics skipped for this run"
                    )
                    llm_warning_emitted = True
        # SPEC-009-003: Retrieval-only is default when include-llm is not set.

        latency_ms = round((time.perf_counter() - start_time) * 1000, 3)
        store.insert_score(
            run_id=run_id,
            query_id=query.query_id,
            category=query.category,
            excluded=False,
            precision_at_k=retrieval["precision_at_k"],
            recall_at_k=retrieval["recall_at_k"],
            ndcg_at_10=retrieval["ndcg_at_10"],
            faithfulness=faithfulness,
            hallucination_rate=hallucination_rate,
            answer_relevancy=answer_relevancy,
            latency_ms=latency_ms,
        )

    all_scores = store.get_scores(run_id)
    aggregates = _aggregate(all_scores)
    store.finalize_run(run_id, aggregates)

    return {
        "run_id": run_id,
        "config_name": profile.name,
        "query_count": len(queries),
        "excluded_queries": excluded_queries,
        "aggregate_metrics": aggregates,
    }
