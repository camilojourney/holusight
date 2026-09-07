"""End-to-end tests: index → hybrid search → API citations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

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


@pytest.mark.parametrize("edit_second_chunk", [False, True], ids=["unchanged", "partial-edit"])
def test_incremental_partial_file_matches_fresh_index(tmp_path, monkeypatch, edit_second_chunk):
    """An edit must not erase a sibling chunk that hash deduplication skips."""
    import numpy as np

    embedded = []

    class SyntheticEmbedder:
        def embed(self, texts):
            embedded.extend(texts)
            return np.array([[1.0, float("changed" in text)] for text in texts], dtype=np.float32)

        def embed_query(self, text):
            return np.array([1.0, 0.0], dtype=np.float32)

    embedder = SyntheticEmbedder()
    monkeypatch.setattr("codesight.indexer.get_embedder", lambda *a, **kw: embedder)
    monkeypatch.setattr("codesight.api.get_embedder", lambda *a, **kw: embedder)
    monkeypatch.setattr("codesight.indexer.VOYAGE_API_KEY", None)
    monkeypatch.setattr("codesight.search.VOYAGE_API_KEY", None)
    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "data")
    config = ServerConfig(
        embedding_model="synthetic", embedding_dim=2,
        chunk_max_lines=2, chunk_overlap_lines=0,
        reranker=False, query_enhancement=False, metadata_boost=False, cnfb_alpha=0,
    )
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    source = corpus / "sample.txt"
    original = "alpha\none\nbeta\ntwo"
    source.write_text(original)
    engine = CodeSight(corpus, config=config)
    initial = engine.index()
    assert initial.total_chunks == initial.chunks_created == 2
    before = engine.search("alpha", top_k=10)
    retained = next(result for result in before if "alpha" in result.snippet)
    retained_metadata = engine.store.get_chunk_metadata([retained.chunk_id])
    retained_vectors = engine.store.get_chunk_vectors([retained.chunk_id])
    assert len(retained_vectors) == 1
    assert len(embedded) == 2
    engine.store.close()

    edited = original.replace("two", "changed") if edit_second_chunk else original
    source.write_text(edited)
    embedded.clear()
    incremental = engine.index()
    actual = engine.search("alpha", top_k=10)
    incremental_texts = list(embedded)

    # Counterfactual: an independent fresh index of the identical edited corpus.
    fresh_corpus = tmp_path / "fresh-corpus"
    fresh_corpus.mkdir()
    (fresh_corpus / "sample.txt").write_text(edited)
    fresh_engine = CodeSight(fresh_corpus, config=config)
    try:
        fresh = fresh_engine.index()
        expected = fresh_engine.search("alpha", top_k=10)
        assert fresh.total_chunks == 2
        assert {(r.start_line, r.end_line) for r in expected} == {(1, 2), (3, 4)}
        assert len(expected) == 2
        assert incremental.chunks_created == int(edit_second_chunk)
        assert incremental.chunks_skipped_unchanged == 2 - int(edit_second_chunk)
        assert len(incremental_texts) == int(edit_second_chunk)
        assert all("changed" in text and "alpha" not in text for text in incremental_texts)
        assert len(actual) == len(expected), "Partial edit lost a searchable unchanged chunk"
        assert incremental.total_chunks == fresh.total_chunks
        assert {r.chunk_id for r in actual} == {r.chunk_id for r in expected}
        assert {(r.file_path, r.start_line, r.end_line, r.snippet) for r in actual} == {
            (r.file_path, r.start_line, r.end_line, r.snippet) for r in expected
        }
        assert engine.store.get_chunk_metadata([retained.chunk_id]) == retained_metadata
        np.testing.assert_array_equal(
            engine.store.get_chunk_vectors([retained.chunk_id]), retained_vectors,
        )
        assert engine.store.bm25_search("alpha") == [retained.chunk_id]
        assert source.read_text() == edited

        engine.store.close()
        embedded.clear()
        repeat = engine.index()
        assert repeat.total_chunks == repeat.chunks_skipped_unchanged == 2
        assert repeat.chunks_created == 0
        assert embedded == []
    finally:
        engine.store.close()
        fresh_engine.store.close()


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
