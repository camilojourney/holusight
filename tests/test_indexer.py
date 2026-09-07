"""Incremental indexing regressions using real stores and synthetic embeddings."""

from __future__ import annotations

import hashlib
from collections import Counter

import numpy as np
import pytest

from codesight import config as config_module
from codesight.chunker import chunk_file
from codesight.config import ServerConfig
from codesight.indexer import index_repo
from codesight.store import ChunkStore


@pytest.fixture
def synthetic_indexing(tmp_path, monkeypatch):
    calls = []

    class SyntheticEmbedder:
        def __init__(self, model, dim):
            self.model = model
            self.dim = dim

        def embed(self, texts):
            calls.extend((self.model, text) for text in texts)
            vectors = np.zeros((len(texts), self.dim), dtype=np.float32)
            for i, text in enumerate(texts):
                vectors[i, 0] = 1
                vectors[i, 1] = hashlib.sha256(text.encode()).digest()[0] / 255
            return vectors

    monkeypatch.setattr("codesight.indexer.get_embedder", lambda model, dim, **kw: (
        SyntheticEmbedder(model, dim)
    ))
    monkeypatch.setattr("codesight.indexer.VOYAGE_API_KEY", None)
    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "data")
    config = ServerConfig(
        embedding_model="synthetic", embedding_dim=2,
        chunk_max_lines=2, chunk_overlap_lines=0,
    )
    return config, calls


@pytest.mark.parametrize("code_vectors", [False, True], ids=["general", "code"])
def test_partial_edit_retains_rows_and_embeds_only_changed_chunk(
    tmp_path, monkeypatch, synthetic_indexing, code_vectors,
):
    config, calls = synthetic_indexing
    if code_vectors:
        # Enable only the route; the factory above returns a deterministic fake.
        monkeypatch.setattr("codesight.indexer.VOYAGE_API_KEY", True)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    source = corpus / "sample.py"
    original = "def alpha():\n    return 'stable'\ndef beta():\n    return 'old'"
    source.write_text(original)
    chunks = chunk_file(original, source.name, max_lines=2, overlap_lines=0)
    assert len(chunks) == 2
    retained, obsolete = chunks
    assert index_repo(corpus, config).total_chunks == 2

    def vector_rows(store):
        table = store.code_lance_table if code_vectors else store.lance_table
        return {r["chunk_id"]: r["vector"] for r in table.search().limit(10).to_list()}

    with ChunkStore(corpus, embedding_dim=2) as store:
        before_metadata = store.get_chunk_metadata([retained.chunk_id])
        before_vectors = vector_rows(store)
        before_rowid = store.fts.conn.execute(
            "SELECT rowid FROM chunks WHERE chunk_id = ?", (retained.chunk_id,),
        ).fetchone()
    calls.clear()
    stored_ids = []
    original_upsert = ChunkStore._upsert_metadata

    def track_upsert(store, chunk_ids, metadata):
        stored_ids.extend(chunk_ids)
        original_upsert(store, chunk_ids, metadata)

    monkeypatch.setattr(ChunkStore, "_upsert_metadata", track_upsert)
    edited = original.replace("'old'", "'changed'")
    source.write_text(edited)
    new_chunks = chunk_file(edited, source.name, max_lines=2, overlap_lines=0)
    changed = new_chunks[1]
    stats = index_repo(corpus, config)
    assert stats.total_chunks == 2
    assert stats.files_indexed == stats.chunks_created == stats.chunks_skipped_unchanged == 1
    model = "voyage-code-3" if code_vectors else "synthetic"
    assert calls == [(model, changed.embedding_text)]
    assert stored_ids == [changed.chunk_id], "Retained metadata must not be rewritten"

    with ChunkStore(corpus, embedding_dim=2) as store:
        after_vectors = vector_rows(store)
        assert set(after_vectors) == {c.chunk_id for c in new_chunks}
        assert after_vectors[retained.chunk_id] == before_vectors[retained.chunk_id]
        assert store.get_chunk_metadata([retained.chunk_id]) == before_metadata
        assert store.get_chunk_metadata([obsolete.chunk_id]) == {}
        assert store.fts.conn.execute(
            "SELECT rowid FROM chunks WHERE chunk_id = ?", (retained.chunk_id,),
        ).fetchone() == before_rowid
        assert store.bm25_search("stable") == [retained.chunk_id]
        assert store.bm25_search("changed") == [changed.chunk_id]
        assert store.bm25_search("old") == []
        # The existing full-file deletion contract still clears both surfaces.
        assert store.delete_file_chunks(source.name) == 2
        assert store.chunk_count == 0
        assert vector_rows(store) == {}
    assert source.read_text() == edited


@pytest.mark.parametrize("edited, created", [
    ("alpha\none\nalpha\none", 1),  # Same hash, new ID at a second anchor.
    ("beta\ntwo\nalpha\none", 2),  # Same hashes, both anchors move.
])
def test_partial_replacement_matches_chunk_identity_not_any_old_hash(
    tmp_path, synthetic_indexing, edited, created,
):
    config, calls = synthetic_indexing
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    source = corpus / "sample.txt"
    source.write_text("alpha\none\nbeta\ntwo")
    assert index_repo(corpus, config).total_chunks == 2
    calls.clear()
    source.write_text(edited)
    expected = chunk_file(edited, source.name, max_lines=2, overlap_lines=0)
    stats = index_repo(corpus, config)
    assert stats.total_chunks == 2
    assert stats.chunks_created == created
    assert stats.chunks_skipped_unchanged == 2 - created
    assert len(calls) == created
    assert all(count == 1 for count in Counter(calls).values())
    with ChunkStore(corpus, embedding_dim=2) as store:
        metadata = store.get_chunk_metadata([c.chunk_id for c in expected])
        assert set(metadata) == {c.chunk_id for c in expected}
        assert store.lance_table.count_rows() == 2
        for chunk in expected:
            row = metadata[chunk.chunk_id]
            assert (row["start_line"], row["end_line"], row["content"]) == (
                chunk.start_line, chunk.end_line, chunk.content,
            )
    calls.clear()
    repeated = index_repo(corpus, config)
    assert repeated.chunks_created == 0
    assert repeated.chunks_skipped_unchanged == repeated.total_chunks == 2
    assert calls == []
