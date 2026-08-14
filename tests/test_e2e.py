"""End-to-end tests: index → hybrid search → API citations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codesight.api import CodeSight
from codesight import config as config_module
from codesight.config import ServerConfig
from codesight.search import rrf_merge

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pilot_docs"


@pytest.fixture
def indexed_engine(tmp_path, monkeypatch):
    """Index pilot fixtures into an isolated data directory."""
    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "data")
    engine = CodeSight(FIXTURES, config=ServerConfig())
    stats = engine.index(force_rebuild=True)
    assert stats.files_indexed >= 2
    assert stats.total_chunks >= 2
    return engine


class TestE2ERetrieval:
    def test_bm25_finds_exact_payment_terms(self, indexed_engine):
        results = indexed_engine.search("Net 30 payment terms")
        assert results, "BM25 should match exact phrase in payment-terms.md"
        paths = {r.file_path for r in results}
        assert any("payment-terms" in p for p in paths)

    def test_semantic_search_finds_auth_topic(self, indexed_engine):
        results = indexed_engine.search("validate bearer tokens")
        assert results, "Vector search should find auth_utils.py"
        assert any("auth_utils" in r.file_path for r in results)

    def test_rrf_merges_keyword_and_semantic(self, indexed_engine):
        vector_ids = ["shared", "vector-only"]
        bm25_ids = ["bm25-only", "shared"]
        merged = rrf_merge([vector_ids, bm25_ids])
        assert [chunk_id for chunk_id, _ in merged] == ["shared", "bm25-only", "vector-only"]
        assert merged[0][1] == (1 / 61) + (1 / 62)
        assert merged[0][1] > merged[1][1]

        results = indexed_engine.search("payment billing invoice")
        assert results
        top = results[0]
        assert top.file_path
        assert top.start_line >= 1
        assert top.end_line >= top.start_line
        assert top.snippet
        assert top.chunk_id

    def test_citation_metadata_for_markdown(self, indexed_engine):
        results = indexed_engine.search("Net 30", file_glob="*.md")
        assert results
        r = results[0]
        assert r.file_path.endswith(".md")
        assert r.scope == "#"
        assert r.start_line >= 1
        assert r.end_line >= r.start_line

    def test_citation_metadata_for_code(self, indexed_engine):
        results = indexed_engine.search("verify_api_token", file_glob="*.py")
        assert results
        r = results[0]
        assert r.file_path.endswith(".py")
        assert r.start_line >= 1

    def test_empty_collection_returns_no_results(self, tmp_path, monkeypatch):
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "data")
        engine = CodeSight(empty, config=ServerConfig())
        engine.index()
        results = engine.search("anything")
        assert results == []

    def test_ask_without_llm_returns_graceful_or_mocked(self, indexed_engine):
        with patch("codesight.api.get_backend") as mock_get:
            backend = MagicMock()
            backend.model_id = "test:mock"
            backend.generate.return_value = "Net 30 applies. [Source 1]"
            mock_get.return_value = backend
            answer = indexed_engine.ask("What are the payment terms?")
        assert "Net 30" in answer.text or answer.sources
        assert answer.sources
        assert any("payment" in s.file_path for s in answer.sources)

    def test_index_persists_across_engine_restart(self, tmp_path, monkeypatch):
        data_dir = tmp_path / "data"
        monkeypatch.setattr(config_module, "DATA_DIR", data_dir)
        e1 = CodeSight(FIXTURES, config=ServerConfig())
        e1.index(force_rebuild=True)
        count = e1.store.chunk_count
        e2 = CodeSight(FIXTURES, config=ServerConfig())
        assert e2.store.is_indexed
        assert e2.store.chunk_count == count
