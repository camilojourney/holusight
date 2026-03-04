"""SQLite persistence for benchmark runs and per-query scores."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class BenchmarkStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        # SPEC-009-005: Persist benchmark runs + per-query scores in SQLite.
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS benchmark_runs (
                run_id TEXT PRIMARY KEY,
                config_name TEXT NOT NULL,
                corpus_path TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                question_bank_hash TEXT NOT NULL,
                include_llm INTEGER NOT NULL,
                aggregate_metrics TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS benchmark_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                query_id TEXT NOT NULL,
                category TEXT NOT NULL,
                excluded INTEGER NOT NULL DEFAULT 0,
                precision_at_k REAL,
                recall_at_k REAL,
                ndcg_at_10 REAL,
                faithfulness REAL,
                hallucination_rate REAL,
                answer_relevancy REAL,
                latency_ms REAL,
                FOREIGN KEY(run_id) REFERENCES benchmark_runs(run_id)
            );

            CREATE INDEX IF NOT EXISTS idx_benchmark_scores_run
            ON benchmark_scores(run_id);
            """
        )
        self.conn.commit()

    def create_run(
        self,
        *,
        config_name: str,
        corpus_path: str,
        question_bank_hash: str,
        include_llm: bool,
    ) -> str:
        run_id = uuid.uuid4().hex[:12]
        timestamp = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """
            INSERT INTO benchmark_runs
            (run_id, config_name, corpus_path, timestamp, question_bank_hash, include_llm)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, config_name, corpus_path, timestamp, question_bank_hash, int(include_llm)),
        )
        self.conn.commit()
        return run_id

    def insert_score(
        self,
        *,
        run_id: str,
        query_id: str,
        category: str,
        excluded: bool,
        precision_at_k: float | None,
        recall_at_k: float | None,
        ndcg_at_10: float | None,
        faithfulness: float | None,
        hallucination_rate: float | None,
        answer_relevancy: float | None,
        latency_ms: float,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO benchmark_scores
            (run_id, query_id, category, excluded, precision_at_k, recall_at_k, ndcg_at_10,
             faithfulness, hallucination_rate, answer_relevancy, latency_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                query_id,
                category,
                int(excluded),
                precision_at_k,
                recall_at_k,
                ndcg_at_10,
                faithfulness,
                hallucination_rate,
                answer_relevancy,
                latency_ms,
            ),
        )
        self.conn.commit()

    def finalize_run(self, run_id: str, aggregate_metrics: dict[str, Any]) -> None:
        self.conn.execute(
            "UPDATE benchmark_runs SET aggregate_metrics = ? WHERE run_id = ?",
            (json.dumps(aggregate_metrics, sort_keys=True), run_id),
        )
        self.conn.commit()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM benchmark_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload["aggregate_metrics"] = json.loads(payload["aggregate_metrics"])
        return payload

    def get_scores(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM benchmark_scores WHERE run_id = ? ORDER BY id ASC",
            (run_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        self.conn.close()
