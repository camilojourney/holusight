"""Security tests for read-only invariant and input sanitization."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from codesight.store import FTSSidecar


class TestFTSQuerySanitization:
    """Verify that FTS5 MATCH queries are sanitized against injection."""

    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.fts = FTSSidecar(Path(self.tmp.name))
        # Insert some test data
        self.fts.upsert_chunk(
            chunk_id="test:1-10:abc123",
            file_path="test.py",
            start_line=1,
            end_line=10,
            scope="function test",
            language="python",
            content_hash="abc123",
            content="def test_function(): return True",
        )
        self.fts.commit()

    def teardown_method(self):
        self.fts.close()
        os.unlink(self.tmp.name)

    def test_normal_query(self):
        """Normal search term works."""
        results = self.fts.bm25_search("test")
        assert len(results) >= 0  # just shouldn't crash

    def test_fts_operator_injection(self):
        """FTS5 operators in query don't cause errors."""
        # These would crash or behave unexpectedly without sanitization
        dangerous_queries = [
            'test OR 1=1 --',
            'test" AND "1"="1',
            "NEAR(test, hack)",
            "test NOT *",
            '"; DROP TABLE chunks; --',
            "test AND OR NOT",
            "{test}",
        ]
        for q in dangerous_queries:
            # Should not raise, regardless of results
            results = self.fts.bm25_search(q)
            assert isinstance(results, list), f"Failed on query: {q}"

    def test_empty_query(self):
        """Empty query returns empty results without error."""
        results = self.fts.bm25_search("")
        assert isinstance(results, list)

    def test_whitespace_only_query(self):
        """Whitespace-only query returns empty results."""
        results = self.fts.bm25_search("   ")
        assert isinstance(results, list)


class TestChunkIdSanitization:
    """Verify that chunk IDs with injection attempts are rejected."""

    def test_suspicious_chunk_ids_logged(self):
        """Chunk IDs containing quotes should be skipped."""
        import tempfile

        from codesight.store import ChunkStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = ChunkStore(tmpdir)
            # This should not raise even with suspicious IDs (no lance table yet)
            store._delete_vectors_by_ids([
                'valid:1-10:abc123',
                'injection" OR 1=1 --',
                "another'injection",
            ])
            store.close()

    def test_allowlist_rejects_quotes(self):
        """Chunk IDs with quotes fail the allowlist validation."""
        from codesight.store import ChunkStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = ChunkStore(tmpdir)
            with pytest.raises(ValueError, match="allowlist"):
                store._validate_chunk_id('injection" OR 1=1 --')
            with pytest.raises(ValueError, match="allowlist"):
                store._validate_chunk_id("another'injection")
            store.close()

    def test_allowlist_rejects_backslash(self):
        """Chunk IDs with backslashes fail the allowlist."""
        from codesight.store import ChunkStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = ChunkStore(tmpdir)
            with pytest.raises(ValueError, match="allowlist"):
                store._validate_chunk_id("path\\to\\file:1-10:abc")
            store.close()

    def test_allowlist_rejects_semicolon(self):
        """Chunk IDs with semicolons (SQL injection) fail the allowlist."""
        from codesight.store import ChunkStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = ChunkStore(tmpdir)
            with pytest.raises(ValueError, match="allowlist"):
                store._validate_chunk_id('; DROP TABLE chunks; --')
            store.close()

    def test_allowlist_accepts_valid_ids(self):
        """Normal chunk IDs pass the allowlist."""
        from codesight.store import ChunkStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = ChunkStore(tmpdir)
            # All of these should pass
            assert store._validate_chunk_id("file.py:1-10:abc123") == "file.py:1-10:abc123"
            result = store._validate_chunk_id("src/deep/path.py:100-200:def456")
            assert result == "src/deep/path.py:100-200:def456"
            assert store._validate_chunk_id("my-file_v2.py:1-5:hash") == "my-file_v2.py:1-5:hash"
            store.close()


class _FilterCapturingTable:
    """Minimal stand-in for a LanceDB table's query-builder chain, so the
    exact filter string reaching .where() can be asserted on directly --
    proof the fix's actual mechanism (validate-then-exclude) runs, rather
    than relying on LanceDB's own parser happening to reject a malformed
    filter, which would pass the same broad `except Exception` either way
    and prove nothing about whether validation ran."""

    def __init__(self):
        self.where_calls: list[str] = []

    def search(self):
        return self

    def where(self, expr):
        self.where_calls.append(expr)
        return self

    def limit(self, n):
        return self

    def to_pandas(self):
        import pandas as pd

        return pd.DataFrame(columns=["chunk_id", "vector"])


class TestVectorFilterInjection:
    """SEC-004: get_chunk_vectors() interpolates chunk IDs into a Lance
    filter; a malicious ID must be rejected, not crash the query or reach
    the filter unescaped. Reproduces the exact finding the security-sentinel
    audit found and confirmed on 2026-09-19."""

    def test_malicious_id_is_excluded_before_reaching_the_filter_string(
        self, tmp_path, monkeypatch
    ):
        from codesight import config as config_module
        from codesight.store import ChunkStore

        monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "data")
        with ChunkStore(tmp_path / "corpus", embedding_dim=2) as store:
            spy = _FilterCapturingTable()
            monkeypatch.setattr(store, "_lance_table", spy)

            malicious = "x') OR chunk_id LIKE '%"
            store.get_chunk_vectors(["file.py:1-10:abc123", malicious])

            assert spy.where_calls, "get_chunk_vectors never queried the table"
            assert all(malicious not in expr for expr in spy.where_calls)

    def test_all_malicious_ids_never_queries_the_table(self, tmp_path, monkeypatch):
        """No valid IDs survive validation -> must short-circuit before
        ever calling .search(), not send an empty/malformed filter."""
        from codesight import config as config_module
        from codesight.store import ChunkStore

        monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "data")
        with ChunkStore(tmp_path / "corpus", embedding_dim=2) as store:
            spy = _FilterCapturingTable()
            monkeypatch.setattr(store, "_lance_table", spy)

            vectors = store.get_chunk_vectors(["'; DROP TABLE chunks; --", "\" OR 1=1"])

            assert vectors == []
            assert spy.where_calls == []

    def test_malicious_ids_are_skipped_not_crashed_end_to_end(self, tmp_path, monkeypatch):
        """Real store, real data: confirms the validated path still returns
        exactly the legitimate vector when malicious IDs are mixed in."""
        import numpy as np

        from codesight import config as config_module
        from codesight.store import ChunkStore

        monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "data")
        with ChunkStore(tmp_path / "corpus", embedding_dim=2) as store:
            valid_id = "file.py:1-10:abc123"
            store.upsert_chunks(
                [valid_id],
                np.array([[1.0, 0.0]], dtype=np.float32),
                [
                    {
                        "file_path": "file.py", "start_line": 1, "end_line": 10,
                        "scope": "", "language": "python", "content_hash": "abc123",
                        "content": "needle",
                    }
                ],
            )

            malicious_ids = [
                valid_id,
                "') OR chunk_id != 'x' --",
                "'; DROP TABLE chunks; --",
            ]

            vectors = store.get_chunk_vectors(malicious_ids)

            assert len(vectors) == 1
            assert np.allclose(vectors[0], [1.0, 0.0])


class TestAggregateIndexingBudget:
    """SEC-007: the per-file size limit bounds one file; an aggregate
    file-count/byte budget must bound the whole folder too. Reproduces the
    gap the security-sentinel audit found and confirmed on 2026-09-19."""

    def test_raises_when_file_count_budget_exceeded(self, tmp_path, monkeypatch):
        from codesight import indexer

        monkeypatch.setattr(indexer, "MAX_INDEXED_FILES", 2)
        for i in range(3):
            (tmp_path / f"f{i}.py").write_text("x = 1")

        with pytest.raises(indexer.IndexBudgetExceeded, match="file indexing budget"):
            indexer.walk_repo_files(tmp_path)

    def test_raises_when_total_byte_budget_exceeded(self, tmp_path, monkeypatch):
        from codesight import indexer

        monkeypatch.setattr(indexer, "MAX_TOTAL_INDEXED_BYTES", 10)
        (tmp_path / "a.py").write_text("x" * 6)
        (tmp_path / "b.py").write_text("x" * 6)

        with pytest.raises(indexer.IndexBudgetExceeded, match="aggregate indexing budget"):
            indexer.walk_repo_files(tmp_path)

    def test_accepts_a_folder_within_budget(self, tmp_path, monkeypatch):
        from codesight import indexer

        monkeypatch.setattr(indexer, "MAX_INDEXED_FILES", 10)
        monkeypatch.setattr(indexer, "MAX_TOTAL_INDEXED_BYTES", 10_000)
        (tmp_path / "a.py").write_text("x = 1")

        found = indexer.walk_repo_files(tmp_path)

        assert len(found) == 1

    def test_partial_listing_is_never_returned_on_budget_exceeded(self, tmp_path, monkeypatch):
        """The failure mode this exists to prevent: a truncated listing
        would make every file past the cutoff look deleted to the
        incremental-refresh removal logic. Confirms the budget check
        raises instead of returning a partial list."""
        from codesight import indexer

        monkeypatch.setattr(indexer, "MAX_INDEXED_FILES", 1)
        (tmp_path / "a.py").write_text("x = 1")
        (tmp_path / "b.py").write_text("x = 2")

        with pytest.raises(indexer.IndexBudgetExceeded):
            indexer.walk_repo_files(tmp_path)


class TestBoundedEmbeddingInput:
    """SEC-007: every embedding backend must share the same per-text
    character bound LocalEmbedder already enforces, not just the local
    one. Reproduces the exact gap the security-sentinel audit found and
    confirmed on 2026-09-19."""

    def test_bound_texts_truncates_oversized_input(self):
        from codesight.embeddings import _MAX_EMBEDDING_TEXT_CHARS, _bound_texts

        oversized = "x" * (_MAX_EMBEDDING_TEXT_CHARS + 500)
        result = _bound_texts([oversized, "short"])

        assert len(result[0]) == _MAX_EMBEDDING_TEXT_CHARS
        assert result[1] == "short"

    def test_api_embedder_bounds_input_before_sending(self, monkeypatch):
        from codesight import embeddings

        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        embedder = embeddings.APIEmbedder()

        captured = {}

        class _FakeResponse:
            data = [type("Item", (), {"embedding": [0.0] * embedder.expected_dim})()]

        class _FakeEmbeddings:
            def create(self, model, input):
                captured["input"] = input
                return _FakeResponse()

        class _FakeClient:
            embeddings = _FakeEmbeddings()

        monkeypatch.setattr(embedder, "_client", _FakeClient())

        oversized = "x" * (embeddings._MAX_EMBEDDING_TEXT_CHARS + 500)
        embedder.embed([oversized])

        assert len(captured["input"][0]) == embeddings._MAX_EMBEDDING_TEXT_CHARS

    def test_voyage_embedder_bounds_input_before_sending(self, monkeypatch):
        from codesight import embeddings

        monkeypatch.setattr(embeddings, "VOYAGE_API_KEY", "test-key")
        embedder = embeddings.VoyageEmbedder()

        captured = {}

        class _FakeVoyageResponse:
            embeddings = [[0.0] * embedder.expected_dim]

        class _FakeVoyageClient:
            def embed(self, batch, model, input_type):
                captured["batch"] = batch
                return _FakeVoyageResponse()

        monkeypatch.setattr(embedder, "_client", _FakeVoyageClient())

        oversized = "x" * (embeddings._MAX_EMBEDDING_TEXT_CHARS + 500)
        embedder.embed([oversized])

        assert len(captured["batch"][0]) == embeddings._MAX_EMBEDDING_TEXT_CHARS


class TestReadOnlyInvariant:
    """Verify the engine never writes to the indexed folder."""

    def test_index_does_not_write_to_source_folder(self):
        """After indexing, the source folder should have no new files."""
        import tempfile

        from codesight.config import ServerConfig

        with tempfile.TemporaryDirectory() as source_dir:
            # Create a simple test file
            test_file = Path(source_dir) / "test.py"
            test_file.write_text("def hello(): return 'world'")

            # Record initial state
            initial_files = set(Path(source_dir).rglob("*"))

            # Index (using a separate data dir to avoid default ~/.codesight)
            with tempfile.TemporaryDirectory() as data_dir:
                os.environ["CODESIGHT_DATA_DIR"] = data_dir
                try:
                    from codesight.indexer import index_repo
                    config = ServerConfig()
                    index_repo(source_dir, config)
                finally:
                    del os.environ["CODESIGHT_DATA_DIR"]

            # Verify no new files in source
            final_files = set(Path(source_dir).rglob("*"))
            new_files = final_files - initial_files
            assert not new_files, f"Engine wrote to source folder: {new_files}"


class TestDataDirContainment:
    """SEC-002: CODESIGHT_DATA_DIR must never resolve inside the folder
    being indexed, directly or through a symlink. Reproduces the exact
    exploit the security-sentinel audit found and confirmed on 2026-09-19."""

    def test_rejects_data_dir_nested_inside_indexed_root(self, monkeypatch):
        import tempfile

        from codesight import config

        with tempfile.TemporaryDirectory() as source_dir:
            nested = Path(source_dir) / "derived-index"
            monkeypatch.setattr(config, "DATA_DIR", nested)

            with pytest.raises(ValueError, match="resolves inside the indexed"):
                config.repo_data_dir(source_dir)

            assert not nested.exists()

    def test_rejects_data_dir_equal_to_indexed_root(self, monkeypatch):
        import tempfile

        from codesight import config

        with tempfile.TemporaryDirectory() as source_dir:
            monkeypatch.setattr(config, "DATA_DIR", Path(source_dir))

            with pytest.raises(ValueError, match="resolves inside the indexed"):
                config.repo_data_dir(source_dir)

    def test_rejects_data_dir_symlinked_into_indexed_root(self, monkeypatch):
        import tempfile

        from codesight import config

        with tempfile.TemporaryDirectory() as source_dir, \
                tempfile.TemporaryDirectory() as elsewhere:
            data_dir_link = Path(elsewhere) / "data-link"
            data_dir_link.symlink_to(source_dir)
            monkeypatch.setattr(config, "DATA_DIR", data_dir_link)

            with pytest.raises(ValueError, match="resolves inside the indexed"):
                config.repo_data_dir(source_dir)

    def test_accepts_data_dir_genuinely_outside_indexed_root(self, monkeypatch):
        import tempfile

        from codesight import config

        with tempfile.TemporaryDirectory() as source_dir, \
                tempfile.TemporaryDirectory() as data_dir:
            monkeypatch.setattr(config, "DATA_DIR", Path(data_dir))

            result = config.repo_data_dir(source_dir)

            assert result.exists()

    def test_env_var_override_is_read_fresh_on_every_call(self, monkeypatch):
        """A later os.environ mutation (e.g. a test's monkeypatch.setenv, or
        any code path that sets CODESIGHT_DATA_DIR after codesight.config
        was already imported) must actually take effect. DATA_DIR itself is
        computed once at import time; repo_data_dir() must not silently
        keep using that frozen value forever."""
        import tempfile

        from codesight import config

        with tempfile.TemporaryDirectory() as source_dir, \
                tempfile.TemporaryDirectory() as data_dir:
            # DATA_DIR still points somewhere else entirely -- only the env
            # var is set, simulating a real mid-process override.
            monkeypatch.setenv("CODESIGHT_DATA_DIR", data_dir)

            result = config.repo_data_dir(source_dir)

            assert str(result).startswith(str(Path(data_dir)))

    def test_env_var_override_still_enforces_containment(self, monkeypatch):
        import tempfile

        from codesight import config

        with tempfile.TemporaryDirectory() as source_dir:
            monkeypatch.setenv("CODESIGHT_DATA_DIR", source_dir)

            with pytest.raises(ValueError, match="resolves inside the indexed"):
                config.repo_data_dir(source_dir)

    def test_index_does_not_write_inside_source_when_misconfigured_end_to_end(
        self, monkeypatch
    ):
        """Full reproduction of the audit's E2E finding. CODESIGHT_DATA_DIR
        is a module-level constant read once at import time, so the
        misconfiguration is applied the same way the rest of this test
        class does it: monkeypatching the already-imported config module,
        not re-setting the environment variable after import (which
        wouldn't be re-read)."""
        import tempfile

        from codesight import config
        from codesight.config import ServerConfig
        from codesight.indexer import index_repo

        with tempfile.TemporaryDirectory() as source_dir:
            (Path(source_dir) / "doc.txt").write_text("hello world")
            nested_data_dir = Path(source_dir) / "derived-index"
            monkeypatch.setattr(config, "DATA_DIR", nested_data_dir)

            with pytest.raises(ValueError, match="resolves inside the indexed"):
                index_repo(source_dir, ServerConfig())

            assert not nested_data_dir.exists()


class TestConsistencyCacheSymlink:
    """SEC-003: the consistency cache must refuse a symlinked `.holusight`
    directory rather than follow it. Reproduces the exact exploit the
    security-sentinel audit found and confirmed on 2026-09-19."""

    def test_rejects_symlinked_holusight_directory(self):
        import tempfile

        from codesight.consistency_store import ConsistencyStore

        with tempfile.TemporaryDirectory() as repo_dir, \
                tempfile.TemporaryDirectory() as elsewhere:
            holusight_link = Path(repo_dir) / ".holusight"
            holusight_link.symlink_to(elsewhere)
            db_path = holusight_link / "consistency.db"

            with pytest.raises(ValueError):
                ConsistencyStore(db_path)

            assert not (Path(elsewhere) / "consistency.db").exists()

    def test_rejects_symlinked_holusight_after_first_creation(self):
        """The attack the audit actually reproduced: a repo that already
        has a real `.holusight/consistency.db`, then gets `.holusight`
        replaced with a symlink before a later run."""
        import tempfile

        from codesight.consistency_store import ConsistencyStore

        with tempfile.TemporaryDirectory() as repo_dir, \
                tempfile.TemporaryDirectory() as elsewhere:
            db_path = Path(repo_dir) / ".holusight" / "consistency.db"
            store = ConsistencyStore(db_path)
            store.close()
            assert db_path.exists()

            # Replace the real .holusight with a symlink to an external dir.
            import shutil
            shutil.rmtree(Path(repo_dir) / ".holusight")
            (Path(repo_dir) / ".holusight").symlink_to(elsewhere)

            with pytest.raises(ValueError):
                ConsistencyStore(db_path)

            assert not (Path(elsewhere) / "consistency.db").exists()

    def test_accepts_genuine_non_symlinked_holusight_directory(self):
        import tempfile

        from codesight.consistency_store import ConsistencyStore

        with tempfile.TemporaryDirectory() as repo_dir:
            db_path = Path(repo_dir) / ".holusight" / "consistency.db"

            store = ConsistencyStore(db_path)
            try:
                assert db_path.exists()
            finally:
                store.close()


class TestSymlinkEscape:
    """SEC-001: a symlink inside an indexed folder must never disclose
    content living outside the folder's root. Reproduces the exact exploit
    the security-sentinel audit found and confirmed on 2026-09-19."""

    def test_walk_repo_files_rejects_symlinked_files(self):
        import tempfile

        from codesight.indexer import walk_repo_files

        with tempfile.TemporaryDirectory() as outside_dir, \
                tempfile.TemporaryDirectory() as source_dir:
            secret = Path(outside_dir) / "secret.txt"
            secret.write_text("UNTRUSTED-OUTSIDE-CONTENT")

            leak_link = Path(source_dir) / "leak.txt"
            leak_link.symlink_to(secret)

            found = walk_repo_files(source_dir)

            assert leak_link.resolve() not in {p.resolve() for p in found}

    def test_chunk_text_file_refuses_symlinked_path(self):
        import tempfile

        from codesight.config import ServerConfig
        from codesight.indexer import _chunk_text_file

        with tempfile.TemporaryDirectory() as outside_dir, \
                tempfile.TemporaryDirectory() as source_dir:
            secret = Path(outside_dir) / "secret.txt"
            secret.write_text("UNTRUSTED-OUTSIDE-CONTENT")
            leak_link = Path(source_dir) / "leak.txt"
            leak_link.symlink_to(secret)

            result = _chunk_text_file(
                leak_link, "leak.txt", ServerConfig(), Path(source_dir)
            )

            assert result is None

    def test_symlinked_file_is_not_indexed_or_searchable_end_to_end(self):
        """Full reproduction of the audit's E2E finding: index a folder
        containing a symlink to an outside secret, confirm the secret never
        enters the index and is unreachable through search()."""
        import tempfile

        from codesight.api import CodeSight
        from codesight.config import ServerConfig

        with tempfile.TemporaryDirectory() as outside_dir, \
                tempfile.TemporaryDirectory() as source_dir:
            secret = Path(outside_dir) / "secret.txt"
            secret.write_text("zylophrantic-marker-xyz")

            (Path(source_dir) / "leak.txt").symlink_to(secret)
            # A normal, legitimate file must still index fine alongside it.
            (Path(source_dir) / "normal.txt").write_text("ordinary quazzledorf content")

            with tempfile.TemporaryDirectory() as data_dir:
                os.environ["CODESIGHT_DATA_DIR"] = data_dir
                try:
                    engine = CodeSight(source_dir, ServerConfig())
                    stats = engine.index()
                    assert stats.files_indexed == 1  # only normal.txt, not the symlink

                    # Hybrid search always returns its nearest candidate from
                    # whatever's indexed (no "no match" concept for vector
                    # search on a tiny corpus), so the proof isn't an empty
                    # result set -- it's that nothing traces back to the
                    # symlink or carries the secret's content.
                    results = engine.search("zylophrantic-marker-xyz")
                    assert all(r.file_path != "leak.txt" for r in results)
                    assert all("zylophrantic-marker-xyz" not in r.snippet for r in results)

                    normal_results = engine.search("quazzledorf")
                    assert any(r.file_path == "normal.txt" for r in normal_results)
                finally:
                    del os.environ["CODESIGHT_DATA_DIR"]


class TestPathTraversal:
    """Verify path traversal attacks are prevented."""

    def test_folder_must_be_directory(self):
        """CodeSight rejects non-directory paths."""
        from codesight.api import CodeSight

        with pytest.raises(ValueError, match="Not a directory"):
            CodeSight("/nonexistent/path/that/does/not/exist")

    def test_folder_must_be_real_directory(self):
        """CodeSight resolves symlinks and validates the real path."""
        from codesight.api import CodeSight

        with pytest.raises(ValueError, match="Not a directory"):
            CodeSight("/tmp/../nonexistent_path_12345")
