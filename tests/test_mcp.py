"""Tests for the CodeSight API surface that replaces the former MCP tools.

The original FastMCP server exposed three tools: index, search, status.
CodeSight.index/search/status/ask are the Python API equivalents — these
tests lock that contract so future MCP re-exposure stays compatible.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import codesight.config as config_module
from codesight.api import CodeSight
from codesight.config import ServerConfig
from codesight.types import Answer, IndexStats, RepoStatus, SearchResult

# Keys returned by the original MCP tools via model_dump().
MCP_INDEX_KEYS = {
    "repo_path",
    "files_indexed",
    "chunks_created",
    "chunks_skipped_unchanged",
    "chunks_deleted",
    "total_chunks",
    "elapsed_seconds",
}
MCP_STATUS_KEYS = {
    "repo_path",
    "indexed",
    "chunk_count",
    "files_indexed",
    "last_commit",
    "last_indexed_at",
    "stale",
}
MCP_SEARCH_RESULT_KEYS = {
    "file_path",
    "start_line",
    "end_line",
    "snippet",
    "score",
    "scope",
    "chunk_id",
}


@pytest.fixture
def doc_folder(tmp_path):
    """Minimal document folder with one searchable Python file."""
    source = tmp_path / "docs"
    source.mkdir()
    (source / "payments.py").write_text(
        "def calculate_payment_terms():\n"
        "    '''Return net-30 payment terms for vendor contracts.'''\n"
        "    return 'net-30'\n"
    )
    return source


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    """Route index storage to a temp dir (config.DATA_DIR is import-time bound)."""
    data_dir = tmp_path / "codesight-data"
    data_dir.mkdir()
    monkeypatch.setattr(config_module, "DATA_DIR", data_dir)
    return data_dir


@pytest.fixture
def engine(doc_folder, isolated_data_dir):
    """CodeSight instance with local embeddings and isolated storage."""
    config = ServerConfig(
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        embedding_backend="local",
    )
    return CodeSight(doc_folder, config=config)


class TestMCPIndexTool:
    """CodeSight.index() ↔ former MCP index tool."""

    def test_index_returns_index_stats(self, engine, doc_folder):
        stats = engine.index()

        assert isinstance(stats, IndexStats)
        assert stats.repo_path == str(doc_folder)
        assert stats.files_indexed >= 1
        assert stats.total_chunks >= 1
        assert stats.elapsed_seconds >= 0.0

    def test_index_model_dump_matches_mcp_contract(self, engine):
        payload = engine.index().model_dump()

        assert MCP_INDEX_KEYS.issubset(payload.keys())
        assert payload["files_indexed"] >= 1
        assert payload["total_chunks"] >= 1

    def test_force_rebuild_still_returns_stats(self, engine):
        engine.index()
        rebuilt = engine.index(force_rebuild=True)

        assert isinstance(rebuilt, IndexStats)
        assert rebuilt.total_chunks >= 1


class TestMCPSearchTool:
    """CodeSight.search() ↔ former MCP search tool."""

    def test_search_auto_indexes_when_empty(self, engine):
        """MCP search auto-indexed on first call; API must do the same."""
        assert not engine.status().indexed

        results = engine.search("payment terms", top_k=5)

        assert engine.status().indexed
        assert isinstance(results, list)

    def test_search_results_match_mcp_shape(self, engine):
        engine.index()
        results = engine.search("payment terms", top_k=3)

        assert len(results) >= 1
        for result in results:
            assert isinstance(result, SearchResult)
            dumped = result.model_dump()
            assert MCP_SEARCH_RESULT_KEYS.issubset(dumped.keys())
            assert dumped["file_path"].endswith("payments.py")
            assert dumped["snippet"]

    def test_search_respects_top_k(self, engine):
        engine.index()
        results = engine.search("payment", top_k=1)

        assert len(results) <= 1

    def test_search_with_file_glob_filter(self, engine, doc_folder):
        (doc_folder / "notes.txt").write_text("payment terms in plain text")
        engine.index()

        py_only = engine.search("payment", file_glob="*.py", top_k=5)

        assert all(r.file_path.endswith(".py") for r in py_only)

    def test_search_empty_query_returns_list(self, engine):
        engine.index()
        results = engine.search("", top_k=5)

        assert isinstance(results, list)


class TestMCPStatusTool:
    """CodeSight.status() ↔ former MCP status tool."""

    def test_status_before_index_reports_not_indexed(self, engine, doc_folder):
        status = engine.status()

        assert isinstance(status, RepoStatus)
        assert status.repo_path == str(doc_folder)
        assert status.indexed is False
        assert status.chunk_count == 0

    def test_status_after_index_reports_health(self, engine):
        engine.index()
        status = engine.status()

        assert status.indexed is True
        assert status.chunk_count >= 1
        assert status.files_indexed >= 1
        assert status.last_indexed_at is not None
        assert status.stale is False

    def test_status_model_dump_matches_mcp_contract(self, engine):
        engine.index()
        payload = engine.status().model_dump()

        assert MCP_STATUS_KEYS.issubset(payload.keys())
        assert payload["indexed"] is True


class TestMCPAskExtension:
    """CodeSight.ask() — API extension beyond the original three MCP tools."""

    def test_ask_with_no_index_returns_helpful_message(self, engine):
        mock_llm = MagicMock()
        mock_llm.model_id = "test-model"
        engine._llm = mock_llm

        with patch.object(engine, "search", return_value=[]):
            answer = engine.ask("What are the payment terms?")

        assert isinstance(answer, Answer)
        assert "No relevant documents found" in answer.text
        assert answer.sources == []
        assert answer.model == "test-model"

    def test_ask_synthesizes_answer_from_search_results(self, engine):
        engine.index()
        fake_results = [
            SearchResult(
                file_path="payments.py",
                start_line=1,
                end_line=5,
                snippet="net-30 payment terms",
                score=0.95,
                scope="function calculate_payment_terms",
                chunk_id="payments.py:1-5:abc",
            )
        ]
        mock_llm = MagicMock()
        mock_llm.model_id = "mock-backend"
        mock_llm.generate.return_value = "Payment terms are net-30."
        engine._llm = mock_llm

        with patch.object(engine, "search", return_value=fake_results):
            answer = engine.ask("What are the payment terms?")

        assert answer.text == "Payment terms are net-30."
        assert answer.model == "mock-backend"
        assert len(answer.sources) == 1
        mock_llm.generate.assert_called_once()


class TestMCPPathResolution:
    """Path validation shared by all former MCP tools."""

    def test_nonexistent_folder_raises(self):
        with pytest.raises(ValueError, match="Not a directory"):
            CodeSight("/nonexistent/holusight/path")

    def test_tilde_expands_to_real_directory(self, tmp_path, isolated_data_dir):
        link = tmp_path / "linked"
        link.mkdir()
        engine = CodeSight(link)
        assert engine.folder_path == link.resolve()
