"""Storage layer: LanceDB for vectors + SQLite FTS5 sidecar for BM25.

This module handles all persistence: inserting chunks, querying vectors,
querying full-text, and managing repo metadata.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import lancedb
import numpy as np
import pyarrow as pa

from .config import DEFAULT_EMBEDDING_DIM, repo_data_dir, repo_fts_db_path

logger = logging.getLogger(__name__)

LANCE_TABLE_NAME = "chunks"


# ---------------------------------------------------------------------------
# SQLite FTS5 sidecar (for BM25 keyword search + metadata)
# ---------------------------------------------------------------------------


class FTSSidecar:
    """Lightweight SQLite database for BM25 search and repo metadata."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_tables()

    def _init_tables(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                file_path TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                scope TEXT NOT NULL,
                language TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                content TEXT NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                chunk_id,
                file_path,
                scope,
                content,
                content='chunks',
                content_rowid='rowid',
                tokenize='porter unicode61'
            );

            -- Triggers to keep FTS in sync
            CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
                INSERT INTO chunks_fts(rowid, chunk_id, file_path, scope, content)
                VALUES (new.rowid, new.chunk_id, new.file_path, new.scope, new.content);
            END;

            CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
                INSERT INTO chunks_fts(chunks_fts, rowid, chunk_id, file_path, scope, content)
                VALUES ('delete', old.rowid, old.chunk_id, old.file_path, old.scope, old.content);
            END;

            CREATE TABLE IF NOT EXISTS repo_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        self.conn.commit()

    def upsert_chunk(
        self,
        chunk_id: str,
        file_path: str,
        start_line: int,
        end_line: int,
        scope: str,
        language: str,
        content_hash: str,
        content: str,
    ) -> None:
        """Insert or replace a chunk in the metadata store."""
        # Delete first to trigger FTS cleanup
        self.conn.execute("DELETE FROM chunks WHERE chunk_id = ?", (chunk_id,))
        self.conn.execute(
            """INSERT INTO chunks
               (chunk_id, file_path, start_line, end_line,
                scope, language, content_hash, content)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (chunk_id, file_path, start_line, end_line, scope, language, content_hash, content),
        )

    def delete_chunks_for_file(self, file_path: str) -> int:
        """Delete all chunks belonging to a file. Returns count deleted."""
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE file_path = ?", (file_path,)
        )
        count = cursor.fetchone()[0]
        self.conn.execute("DELETE FROM chunks WHERE file_path = ?", (file_path,))
        return count

    def get_chunk_hashes(self, file_path: str) -> dict[str, str]:
        """Return {chunk_id: content_hash} for all chunks of a file."""
        cursor = self.conn.execute(
            "SELECT chunk_id, content_hash FROM chunks WHERE file_path = ?", (file_path,)
        )
        return dict(cursor.fetchall())

    @staticmethod
    def _sanitize_fts_query(query: str) -> str:
        """Sanitize a query for FTS5 MATCH to prevent injection.

        FTS5 MATCH has its own syntax (AND, OR, NOT, NEAR, quotes, etc.).
        We escape special characters so user input is treated as literal terms.
        """
        if not query or not query.strip():
            return '""'  # empty match
        # Remove FTS5 operators and special chars; keep only words and spaces
        import re
        # Strip characters that have special meaning in FTS5
        sanitized = re.sub(r'[^\w\s]', ' ', query, flags=re.UNICODE)
        # Collapse whitespace
        sanitized = ' '.join(sanitized.split())
        if not sanitized:
            return '""'
        # Quote each term to prevent FTS5 operator interpretation
        terms = sanitized.split()
        return ' '.join(f'"{t}"' for t in terms)

    def bm25_search(self, query: str, top_k: int = 20, file_glob: str | None = None) -> list[str]:
        """Run BM25 search, returning chunk_ids ranked by relevance."""
        safe_query = self._sanitize_fts_query(query)
        if file_glob:
            # Convert glob to SQL LIKE pattern
            like_pattern = file_glob.replace("*", "%").replace("?", "_")
            cursor = self.conn.execute(
                """SELECT chunk_id FROM chunks_fts
                   WHERE chunks_fts MATCH ?
                   AND chunk_id IN (SELECT chunk_id FROM chunks WHERE file_path LIKE ?)
                   ORDER BY rank
                   LIMIT ?""",
                (safe_query, like_pattern, top_k),
            )
        else:
            cursor = self.conn.execute(
                """SELECT chunk_id FROM chunks_fts
                   WHERE chunks_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (safe_query, top_k),
            )
        return [row[0] for row in cursor.fetchall()]

    def get_chunk_by_id(self, chunk_id: str) -> dict | None:
        """Return full chunk metadata by ID."""
        cursor = self.conn.execute(
            "SELECT chunk_id, file_path, start_line, end_line, "
            "scope, language, content_hash, content "
            "FROM chunks WHERE chunk_id = ?",
            (chunk_id,),
        )
        row = cursor.fetchone()
        if row:
            return {
                "chunk_id": row[0],
                "file_path": row[1],
                "start_line": row[2],
                "end_line": row[3],
                "scope": row[4],
                "language": row[5],
                "content_hash": row[6],
                "content": row[7],
            }
        return None

    def get_chunks_by_ids(self, chunk_ids: list[str]) -> dict[str, dict]:
        """Return {chunk_id: metadata} for a batch of IDs."""
        if not chunk_ids:
            return {}
        placeholders = ",".join("?" for _ in chunk_ids)
        cursor = self.conn.execute(
            "SELECT chunk_id, file_path, start_line, end_line, "
            "scope, language, content_hash, content "
            f"FROM chunks WHERE chunk_id IN ({placeholders})",
            chunk_ids,
        )
        result = {}
        for row in cursor.fetchall():
            result[row[0]] = {
                "chunk_id": row[0],
                "file_path": row[1],
                "start_line": row[2],
                "end_line": row[3],
                "scope": row[4],
                "language": row[5],
                "content_hash": row[6],
                "content": row[7],
            }
        return result

    def chunk_count(self) -> int:
        cursor = self.conn.execute("SELECT COUNT(*) FROM chunks")
        return cursor.fetchone()[0]

    def file_count(self) -> int:
        cursor = self.conn.execute("SELECT COUNT(DISTINCT file_path) FROM chunks")
        return cursor.fetchone()[0]

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO repo_meta (key, value) VALUES (?, ?)", (key, value)
        )
        self.conn.commit()

    def get_meta(self, key: str) -> str | None:
        cursor = self.conn.execute("SELECT value FROM repo_meta WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else None

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# ---------------------------------------------------------------------------
# Combined store (LanceDB + FTS sidecar)
# ---------------------------------------------------------------------------


class ChunkStore:
    """Unified store: LanceDB for vectors, SQLite for BM25 + metadata."""

    def __init__(self, repo_path: str | Path, embedding_dim: int = DEFAULT_EMBEDDING_DIM) -> None:
        self.repo_path = str(repo_path)
        self.embedding_dim = embedding_dim
        self.data_dir = repo_data_dir(repo_path)

        # LanceDB (vectors)
        self.lance_db = lancedb.connect(str(self.data_dir / "lance"))
        self._lance_table = None

        # SQLite FTS5 sidecar
        self.fts = FTSSidecar(repo_fts_db_path(repo_path))

    @property
    def lance_table(self):
        """Lazy access to LanceDB table, creating if needed."""
        if self._lance_table is None:
            try:
                self._lance_table = self.lance_db.open_table(LANCE_TABLE_NAME)
            except (FileNotFoundError, ValueError) as e:
                # Table doesn't exist yet — will be created on first insert
                logger.debug("LanceDB table %r not found yet, will create on first insert: %s", LANCE_TABLE_NAME, e)
            except Exception as e:
                logger.error("Failed to open LanceDB table %r: %s", LANCE_TABLE_NAME, e)
                raise
        return self._lance_table

    def _ensure_lance_table(self, vectors: np.ndarray, chunk_ids: list[str]) -> None:
        """Create or append to the LanceDB table."""
        data = pa.table({
            "chunk_id": chunk_ids,
            "vector": [v.tolist() for v in vectors],
        })

        if self._lance_table is None:
            try:
                self._lance_table = self.lance_db.open_table(LANCE_TABLE_NAME)
            except (FileNotFoundError, ValueError) as e:
                logger.debug("LanceDB table %r not found, will create: %s", LANCE_TABLE_NAME, e)
            except Exception as e:
                logger.error("Failed to open LanceDB table %r: %s", LANCE_TABLE_NAME, e)
                raise

        if self._lance_table is None:
            self._lance_table = self.lance_db.create_table(LANCE_TABLE_NAME, data)
        else:
            self._lance_table.add(data)

    def upsert_chunks(
        self,
        chunk_ids: list[str],
        vectors: np.ndarray,
        metadatas: list[dict],
    ) -> None:
        """Upsert chunks into both LanceDB and the FTS sidecar."""
        if not chunk_ids:
            return

        # Delete old vectors for these chunk_ids if they exist
        if self.lance_table is not None:
            try:
                self._delete_vectors_by_ids(chunk_ids)
            except ValueError as e:
                logger.warning("Chunk ID validation failed during upsert: %s", e)
                raise
            except Exception as e:
                logger.warning("Could not delete old vectors (may be expected on first insert): %s", e)

        # Insert new vectors
        self._ensure_lance_table(vectors, chunk_ids)

        # Upsert into FTS sidecar
        for cid, meta in zip(chunk_ids, metadatas):
            self.fts.upsert_chunk(
                chunk_id=cid,
                file_path=meta["file_path"],
                start_line=meta["start_line"],
                end_line=meta["end_line"],
                scope=meta["scope"],
                language=meta["language"],
                content_hash=meta["content_hash"],
                content=meta["content"],
            )
        self.fts.commit()

    # Strict allowlist for chunk IDs: word chars, colons, hyphens, slashes, dots, spaces
    _SAFE_CHUNK_ID_RE = re.compile(r'^[\w:./ -]+$', re.UNICODE)

    def _validate_chunk_id(self, cid: str) -> str:
        """Validate a chunk_id against the allowlist regex.

        Returns the chunk_id if valid, raises ValueError otherwise.
        This prevents filter injection via LanceDB's SQL-like filter syntax.
        """
        if not isinstance(cid, str) or not self._SAFE_CHUNK_ID_RE.match(cid):
            raise ValueError(f"Invalid chunk_id rejected by allowlist: {cid!r}")
        return cid

    def _delete_vectors_by_ids(self, chunk_ids: list[str]) -> None:
        """Delete vectors from LanceDB using validated chunk IDs.

        Each chunk_id is validated against a strict allowlist regex before
        being interpolated into the filter string. Invalid IDs raise ValueError.
        """
        if not chunk_ids or self.lance_table is None:
            return
        safe_ids = []
        for cid in chunk_ids:
            try:
                safe_ids.append(self._validate_chunk_id(cid))
            except ValueError:
                logger.warning("Skipping chunk_id that failed allowlist validation: %r", cid)
                continue
        if not safe_ids:
            return
        id_filter = " OR ".join(f'chunk_id = "{cid}"' for cid in safe_ids)
        self.lance_table.delete(id_filter)

    def delete_file_chunks(self, file_path: str) -> int:
        """Remove all chunks for a file from both stores."""
        # Get chunk IDs before deleting from FTS
        hashes = self.fts.get_chunk_hashes(file_path)
        chunk_ids = list(hashes.keys())

        # Delete from LanceDB
        if chunk_ids and self.lance_table is not None:
            try:
                self._delete_vectors_by_ids(chunk_ids)
            except Exception as e:
                logger.warning("Could not delete vectors for %s: %s", file_path, e)
                raise

        # Delete from FTS
        count = self.fts.delete_chunks_for_file(file_path)
        self.fts.commit()
        return count

    def vector_search(
        self, query_vector: np.ndarray, top_k: int = 20, file_glob: str | None = None
    ) -> list[str]:
        """Search LanceDB by vector similarity, returning ranked chunk_ids."""
        if self.lance_table is None:
            return []

        results = (
            self.lance_table
            .search(query_vector.tolist())
            .limit(top_k)
            .to_pandas()
        )

        if results.empty:
            return []

        chunk_ids = results["chunk_id"].tolist()

        # Post-filter by file glob if specified
        if file_glob:
            import fnmatch
            filtered = []
            for cid in chunk_ids:
                meta = self.fts.get_chunk_by_id(cid)
                if meta and fnmatch.fnmatch(meta["file_path"], file_glob):
                    filtered.append(cid)
            return filtered

        return chunk_ids

    def bm25_search(self, query: str, top_k: int = 20, file_glob: str | None = None) -> list[str]:
        """BM25 search via FTS sidecar."""
        return self.fts.bm25_search(query, top_k, file_glob)

    def get_chunk_metadata(self, chunk_ids: list[str]) -> dict[str, dict]:
        """Get full metadata for a batch of chunk IDs."""
        return self.fts.get_chunks_by_ids(chunk_ids)

    @property
    def chunk_count(self) -> int:
        return self.fts.chunk_count()

    @property
    def file_count(self) -> int:
        return self.fts.file_count()

    @property
    def is_indexed(self) -> bool:
        return self.chunk_count > 0

    @property
    def last_commit(self) -> str | None:
        return self.fts.get_meta("last_commit")

    @last_commit.setter
    def last_commit(self, value: str) -> None:
        self.fts.set_meta("last_commit", value)

    @property
    def last_indexed_at(self) -> str | None:
        return self.fts.get_meta("last_indexed_at")

    @last_indexed_at.setter
    def last_indexed_at(self, value: str) -> None:
        self.fts.set_meta("last_indexed_at", value)

    @property
    def repo_canonical_path(self) -> str | None:
        return self.fts.get_meta("repo_canonical_path")

    @repo_canonical_path.setter
    def repo_canonical_path(self, value: str) -> None:
        self.fts.set_meta("repo_canonical_path", value)

    def touch_indexed(self) -> None:
        """Update the last_indexed_at timestamp."""
        self.last_indexed_at = datetime.now(timezone.utc).isoformat()

    def close(self) -> None:
        self.fts.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
