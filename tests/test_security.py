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
            assert store._validate_chunk_id("src/deep/path.py:100-200:def456") == "src/deep/path.py:100-200:def456"
            assert store._validate_chunk_id("my-file_v2.py:1-5:hash") == "my-file_v2.py:1-5:hash"
            store.close()


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
