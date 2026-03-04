"""Metric functions for retrieval and answer-quality benchmarking."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from typing import Any

from ..types import SearchResult


def _overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return max(a_start, b_start) <= min(a_end, b_end)


def _is_relevant(result: SearchResult, ground_truth: Sequence[dict[str, Any]]) -> bool:
    for truth in ground_truth:
        truth_chunk = truth.get("chunk_id")
        if truth_chunk and truth_chunk == result.chunk_id:
            return True
        truth_path = truth.get("file_path")
        if not truth_path or truth_path != result.file_path:
            continue
        t_start = int(truth.get("start_line", result.start_line))
        t_end = int(truth.get("end_line", result.end_line))
        if _overlaps(result.start_line, result.end_line, t_start, t_end):
            return True
    return False


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9_]+", text.lower()) if t}


def _jaccard(a: str, b: str) -> float:
    ta = _tokenize(a)
    tb = _tokenize(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def precision_at_k(
    results: Sequence[SearchResult],
    ground_truth: Sequence[dict[str, Any]],
    k: int = 5,
) -> float:
    if not ground_truth:
        return 0.0
    top = list(results[:k])
    if not top:
        return 0.0
    hits = sum(1 for item in top if _is_relevant(item, ground_truth))
    return hits / len(top)


def recall_at_k(
    results: Sequence[SearchResult],
    ground_truth: Sequence[dict[str, Any]],
    k: int = 10,
) -> float:
    if not ground_truth:
        return 0.0
    top = list(results[:k])
    if not top:
        return 0.0
    hits = sum(1 for item in top if _is_relevant(item, ground_truth))
    return hits / len(ground_truth)


def ndcg_at_k(
    results: Sequence[SearchResult],
    ground_truth: Sequence[dict[str, Any]],
    k: int = 10,
) -> float:
    if not ground_truth:
        return 0.0
    top = list(results[:k])
    if not top:
        return 0.0

    rels = [1.0 if _is_relevant(item, ground_truth) else 0.0 for item in top]
    dcg = sum(rel / math.log2(idx + 2) for idx, rel in enumerate(rels))
    ideal_hits = min(len(ground_truth), k)
    idcg = sum(1.0 / math.log2(idx + 2) for idx in range(ideal_hits))
    if idcg == 0:
        return 0.0
    return dcg / idcg


# SPEC-009-002: Compute retrieval metrics for each benchmark query.
def compute_retrieval_metrics(
    results: Sequence[SearchResult],
    ground_truth: Sequence[dict[str, Any]],
    *,
    precision_k: int = 5,
    recall_k: int = 10,
) -> dict[str, float | None]:
    if not ground_truth:
        # EDGE-009-001: Missing ground truth treated as negative query scoring.
        return {
            "precision_at_k": None,
            "recall_at_k": None,
            "ndcg_at_10": None,
            "false_positive_rate": 1.0 if results else 0.0,
        }
    return {
        "precision_at_k": round(precision_at_k(results, ground_truth, precision_k), 6),
        "recall_at_k": round(recall_at_k(results, ground_truth, recall_k), 6),
        "ndcg_at_10": round(ndcg_at_k(results, ground_truth, 10), 6),
        "false_positive_rate": None,
    }


# SPEC-009-003: LLM answer quality metrics for include-llm benchmark runs.
def compute_answer_metrics(
    *,
    question: str,
    answer_text: str,
    contexts: Sequence[str],
) -> dict[str, float]:
    """Compute answer quality metrics.

    Tries DeepEval/RAGAS first (pip install codesight[benchmark]).
    Falls back to lexical Jaccard heuristics if not installed.
    """
    try:
        return _compute_with_deepeval_ragas(question, answer_text, list(contexts))
    except ImportError:
        pass

    # Fallback: lexical heuristics (deterministic, no external deps)
    context_text = "\n".join(contexts)
    faithfulness = _jaccard(answer_text, context_text)
    answer_relevancy = _jaccard(question, answer_text)
    hallucination_rate = max(0.0, 1.0 - faithfulness)
    return {
        "faithfulness": round(faithfulness, 6),
        "hallucination_rate": round(hallucination_rate, 6),
        "answer_relevancy": round(answer_relevancy, 6),
    }


def _compute_with_deepeval_ragas(
    question: str,
    answer_text: str,
    contexts: list[str],
) -> dict[str, float]:
    """Use DeepEval + RAGAS for real answer quality metrics. Raises ImportError if unavailable."""
    from deepeval.metrics import FaithfulnessMetric, HallucinationMetric
    from deepeval.test_case import LLMTestCase

    test_case = LLMTestCase(
        input=question,
        actual_output=answer_text,
        retrieval_context=contexts,
    )

    faith_metric = FaithfulnessMetric(threshold=0.5)
    faith_metric.measure(test_case)
    faithfulness = faith_metric.score or 0.0

    halluc_metric = HallucinationMetric(threshold=0.5)
    halluc_metric.measure(test_case)
    hallucination_rate = halluc_metric.score or 0.0

    # Answer relevancy via RAGAS
    try:
        from datasets import Dataset
        from ragas import evaluate as ragas_evaluate
        from ragas.metrics import answer_relevancy as ragas_relevancy

        ds = Dataset.from_dict({
            "question": [question],
            "answer": [answer_text],
            "contexts": [contexts],
        })
        result = ragas_evaluate(ds, metrics=[ragas_relevancy])
        relevancy = result["answer_relevancy"] or 0.0
    except Exception:
        relevancy = _jaccard(question, answer_text)

    return {
        "faithfulness": round(float(faithfulness), 6),
        "hallucination_rate": round(float(hallucination_rate), 6),
        "answer_relevancy": round(float(relevancy), 6),
    }
