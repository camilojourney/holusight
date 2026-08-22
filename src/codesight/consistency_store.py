"""SQLite storage for the Holusight-AXI consistency cache.

One atomic SQLite database at ``.holusight/consistency.db``. See
``specs/013-holusight-axi-consistency-architecture.md`` and
``docs/decisions/0011-single-sqlite-consistency-store.md`` for the storage
design rationale.

``.holusight/`` is gitignored derived state, never canonical truth. It is
safe to delete; the next ``consistency.refresh()`` rebuilds it from the
canonical repository inputs (git history, tracked specs/decisions/source,
and the tracked ``graphify-out/graph.json``).

This module is intentionally dict-in/dict-out — the ``consistency`` module
owns the typed (pydantic) model layer, mirroring the existing separation
between ``store.py`` (raw SQLite/LanceDB rows) and ``types.py`` (typed
models) elsewhere in this package.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = "1"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS repo_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    head_commit TEXT,
    dirty INTEGER NOT NULL DEFAULT 0,
    last_refreshed_at TEXT NOT NULL,
    structural_graph_stale INTEGER NOT NULL DEFAULT 1,
    structural_graph_commit TEXT
);

CREATE TABLE IF NOT EXISTS artifacts (
    path TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    authority TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    classified_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS concepts (
    concept_id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    canonical_path TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_ref TEXT NOT NULL,
    to_ref TEXT NOT NULL,
    relation TEXT NOT NULL,
    provider TEXT NOT NULL,
    confidence REAL NOT NULL,
    evidence TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(from_ref, to_ref, relation, provider)
);

CREATE TABLE IF NOT EXISTS claims (
    name TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    doc_path TEXT NOT NULL,
    doc_value TEXT,
    code_path TEXT NOT NULL,
    code_value TEXT,
    status TEXT NOT NULL,
    evaluated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS health_flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    flag_type TEXT NOT NULL,
    concept_id TEXT,
    detail TEXT NOT NULL,
    severity TEXT NOT NULL,
    detected_at TEXT NOT NULL
);
"""


class ConsistencyStore:
    """Thin dict-based CRUD layer over the ``.holusight/consistency.db`` file."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(_SCHEMA)
        self.conn.execute(
            "INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('schema_version', ?)",
            (SCHEMA_VERSION,),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "ConsistencyStore":
        return self

    def __exit__(self, *_exc_info) -> None:
        self.close()

    # -- repo_state -----------------------------------------------------

    def get_repo_state(self) -> dict | None:
        row = self.conn.execute("SELECT * FROM repo_state WHERE id = 1").fetchone()
        return dict(row) if row else None

    def set_repo_state(
        self,
        head_commit: str | None,
        dirty: bool,
        refreshed_at: str,
        structural_graph_stale: bool,
        structural_graph_commit: str | None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO repo_state
                (id, head_commit, dirty, last_refreshed_at,
                 structural_graph_stale, structural_graph_commit)
            VALUES (1, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                head_commit = excluded.head_commit,
                dirty = excluded.dirty,
                last_refreshed_at = excluded.last_refreshed_at,
                structural_graph_stale = excluded.structural_graph_stale,
                structural_graph_commit = excluded.structural_graph_commit
            """,
            (
                head_commit,
                int(dirty),
                refreshed_at,
                int(structural_graph_stale),
                structural_graph_commit,
            ),
        )

    # -- artifacts --------------------------------------------------------

    def get_artifact(self, path: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM artifacts WHERE path = ?", (path,)).fetchone()
        return dict(row) if row else None

    def all_artifacts(self) -> dict[str, dict]:
        rows = self.conn.execute("SELECT * FROM artifacts").fetchall()
        return {row["path"]: dict(row) for row in rows}

    def upsert_artifact(
        self, path: str, kind: str, authority: str, content_hash: str, classified_at: str
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO artifacts (path, kind, authority, content_hash, classified_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                kind = excluded.kind,
                authority = excluded.authority,
                content_hash = excluded.content_hash,
                classified_at = excluded.classified_at
            """,
            (path, kind, authority, content_hash, classified_at),
        )

    def delete_artifacts_not_in(self, keep_paths: set[str]) -> int:
        """Remove cached artifacts for files no longer discovered on disk."""
        existing = {row["path"] for row in self.conn.execute("SELECT path FROM artifacts")}
        stale = existing - keep_paths
        if stale:
            self.conn.executemany("DELETE FROM artifacts WHERE path = ?", [(p,) for p in stale])
        return len(stale)

    # -- concepts -----------------------------------------------------

    def replace_concepts(self, concepts: list[dict]) -> None:
        self.conn.execute("DELETE FROM concepts")
        if concepts:
            self.conn.executemany(
                """
                INSERT INTO concepts (concept_id, scope, canonical_path, source_kind, status)
                VALUES (:concept_id, :scope, :canonical_path, :source_kind, :status)
                """,
                concepts,
            )

    def get_concept(self, concept_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM concepts WHERE concept_id = ?", (concept_id,)
        ).fetchone()
        return dict(row) if row else None

    def all_concepts(self) -> list[dict]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM concepts")]

    # -- edges ------------------------------------------------------------

    def replace_edges(self, edges: list[dict]) -> None:
        self.conn.execute("DELETE FROM edges")
        if edges:
            self.conn.executemany(
                """
                INSERT OR IGNORE INTO edges
                    (from_ref, to_ref, relation, provider, confidence, evidence, created_at)
                VALUES
                    (:from_ref, :to_ref, :relation, :provider, :confidence, :evidence, :created_at)
                """,
                edges,
            )

    def edges_for_ref(self, ref: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM edges WHERE from_ref = ? OR to_ref = ?", (ref, ref)
        ).fetchall()
        return [dict(row) for row in rows]

    def all_edges(self) -> list[dict]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM edges")]

    # -- claims -------------------------------------------------------

    def replace_claims(self, claims: list[dict]) -> None:
        self.conn.execute("DELETE FROM claims")
        if claims:
            self.conn.executemany(
                """
                INSERT INTO claims
                    (name, description, doc_path, doc_value, code_path, code_value,
                     status, evaluated_at)
                VALUES
                    (:name, :description, :doc_path, :doc_value, :code_path, :code_value,
                     :status, :evaluated_at)
                """,
                claims,
            )

    def all_claims(self) -> list[dict]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM claims")]

    def claims_for_doc_path(self, doc_path: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM claims WHERE doc_path = ?", (doc_path,)
        ).fetchall()
        return [dict(row) for row in rows]

    # -- health flags -----------------------------------------------------

    def replace_health_flags(self, flags: list[dict]) -> None:
        self.conn.execute("DELETE FROM health_flags")
        if flags:
            self.conn.executemany(
                """
                INSERT INTO health_flags (flag_type, concept_id, detail, severity, detected_at)
                VALUES (:flag_type, :concept_id, :detail, :severity, :detected_at)
                """,
                flags,
            )

    def all_health_flags(self) -> list[dict]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM health_flags")]

    def health_flags_for_concept(self, concept_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM health_flags WHERE concept_id = ?", (concept_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def commit(self) -> None:
        self.conn.commit()
