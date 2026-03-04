"""Statistical comparison and reporting utilities for benchmark runs."""

from __future__ import annotations

import math
from statistics import mean, median
from typing import Any

from .storage import BenchmarkStore

METRICS = [
    "precision_at_k",
    "recall_at_k",
    "ndcg_at_10",
    "faithfulness",
    "hallucination_rate",
    "answer_relevancy",
]


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = (len(ordered) - 1) * p
    low = int(math.floor(idx))
    high = int(math.ceil(idx))
    if low == high:
        return ordered[low]
    weight = idx - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _wilcoxon_signed_rank(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 1.0
    if all(x == y for x, y in zip(a, b)):
        return 1.0
    try:
        from scipy.stats import wilcoxon

        _, pvalue = wilcoxon(a, b, zero_method="wilcox", correction=False)
        return float(pvalue)
    except Exception:
        return 1.0


def compare_runs(
    store: BenchmarkStore,
    run_a: str,
    run_b: str,
) -> dict[str, Any]:
    meta_a = store.get_run(run_a)
    meta_b = store.get_run(run_b)
    if meta_a is None or meta_b is None:
        raise ValueError("One or both run IDs were not found.")
    if meta_a["question_bank_hash"] != meta_b["question_bank_hash"]:
        raise ValueError("Runs used different question banks and cannot be compared.")

    scores_a = {row["query_id"]: row for row in store.get_scores(run_a) if not row["excluded"]}
    scores_b = {row["query_id"]: row for row in store.get_scores(run_b) if not row["excluded"]}
    shared_ids = sorted(set(scores_a) & set(scores_b))

    warnings: list[str] = []
    if len(shared_ids) < 30:
        # EDGE-009-004: Warning when sample size is below Wilcoxon guidance.
        warnings.append(
            f"WARNING: Only {len(shared_ids)} paired observations - "
            "Wilcoxon test requires n>=30 for reliable results"
        )

    rows: list[dict[str, Any]] = []
    # SPEC-009-006: Wilcoxon signed-rank comparison per metric.
    for metric in METRICS:
        paired_a: list[float] = []
        paired_b: list[float] = []
        for query_id in shared_ids:
            val_a = scores_a[query_id].get(metric)
            val_b = scores_b[query_id].get(metric)
            if val_a is None or val_b is None:
                continue
            paired_a.append(float(val_a))
            paired_b.append(float(val_b))

        if not paired_a:
            continue
        p_value = _wilcoxon_signed_rank(paired_a, paired_b)
        rows.append(
            {
                "metric": metric,
                "run_a_mean": round(mean(paired_a), 6),
                "run_b_mean": round(mean(paired_b), 6),
                "difference": round(mean(paired_b) - mean(paired_a), 6),
                "p_value": round(p_value, 6),
                "significant": p_value < 0.05,
                "n": len(paired_a),
            }
        )

    return {"rows": rows, "warnings": warnings}


def build_report(store: BenchmarkStore, run_id: str) -> list[dict[str, Any]]:
    scores = [row for row in store.get_scores(run_id) if not row["excluded"]]
    rows: list[dict[str, Any]] = []
    for metric in METRICS:
        values = [float(row[metric]) for row in scores if row.get(metric) is not None]
        if not values:
            continue
        rows.append(
            {
                "metric": metric,
                "mean": round(mean(values), 6),
                "median": round(median(values), 6),
                "p5": round(_percentile(values, 0.05), 6),
                "p95": round(_percentile(values, 0.95), 6),
            }
        )
    return rows
