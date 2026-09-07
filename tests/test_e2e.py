"""End-to-end tests: index → hybrid search → API citations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from codesight import config as config_module
from codesight.api import CodeSight
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


@pytest.mark.parametrize("mode", ["ast-preamble", "ast-no-preamble", "regex-preamble"])
def test_index_search_emits_each_python_chunk_once(tmp_path, monkeypatch, mode):
    """Preamble chunks must not be embedded/stored twice or re-embedded unchanged."""
    if mode.startswith("ast"):
        pytest.importorskip("tree_sitter")
        pytest.importorskip("tree_sitter_python")
    else:
        def unavailable_parser(_language):
            raise ImportError("synthetic unavailable tree-sitter")

        monkeypatch.setattr("codesight.chunker._get_ts_parser", unavailable_parser)

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    preamble = "" if mode == "ast-no-preamble" else "import os\nimport sys\n\n"
    content = preamble + "def main():\n    return 'needle'\n"
    source = corpus / "main.py"
    source.write_text(content, encoding="utf-8")
    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "index-data")

    class RecordingEmbedder:
        def __init__(self):
            self.texts = []

        def embed(self, texts):
            self.texts.extend(texts)
            return np.tile(np.array([1.0, 0.0], dtype=np.float32), (len(texts), 1))

        def embed_query(self, _query):
            return np.array([1.0, 0.0], dtype=np.float32)

    embedder = RecordingEmbedder()
    monkeypatch.setattr("codesight.indexer.get_embedder", lambda *a, **kw: embedder)
    monkeypatch.setattr("codesight.api.get_embedder", lambda *a, **kw: embedder)
    monkeypatch.setattr("codesight.indexer.VOYAGE_API_KEY", None)
    monkeypatch.setattr("codesight.search.VOYAGE_API_KEY", None)
    engine = CodeSight(
        corpus,
        config=ServerConfig(
            embedding_model="synthetic",
            embedding_backend="local",
            embedding_dim=2,
            stale_threshold_seconds=3600,
            reranker=False,
            metadata_boost=False,
            query_enhancement=False,
            cnfb_alpha=0.0,
        ),
    )
    stores = []
    try:
        first = engine.index()
        results = engine.search("needle", top_k=8)
        stores.append(engine.store)
        vector_ids = engine.store.lance_table.to_arrow().column("chunk_id").to_pylist()
        expected_count = 1 if not preamble else 2

        assert results
        assert any("needle" in result.snippet for result in results)
        assert all(result.file_path == "main.py" for result in results)
        assert len(vector_ids) == len(set(vector_ids)) == expected_count
        assert first.chunks_created == first.total_chunks == expected_count
        assert len(embedder.texts) == len(set(embedder.texts)) == expected_count
        assert {result.chunk_id for result in results} == set(vector_ids)
        assert source.read_text(encoding="utf-8") == content
        assert list(corpus.iterdir()) == [source]

        original_embedding_texts = list(embedder.texts)
        second = engine.index()
        stores.append(engine.store)
        repeated = engine.search("needle", top_k=8)
        repeated_ids = engine.store.lance_table.to_arrow().column("chunk_id").to_pylist()
        assert second.chunks_created == 0
        assert second.chunks_skipped_unchanged == expected_count
        assert second.total_chunks == expected_count
        assert embedder.texts == original_embedding_texts
        assert repeated_ids == vector_ids
        assert {result.chunk_id for result in repeated} == set(vector_ids)
        assert source.read_text(encoding="utf-8") == content
    finally:
        for store in stores:
            store.close()
