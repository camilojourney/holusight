"""Offline public-API regressions for incremental empty-text handling."""

from pathlib import Path

import numpy as np
import pytest

from codesight import CodeSight, api, config, indexer, search
from codesight.config import ServerConfig
from codesight.store import ChunkStore


class _DeterministicEmbedder:
    def __init__(self):
        self.embedded = []

    def embed(self, texts):
        self.embedded.extend(texts)
        return np.tile(np.array([1.0, 0.0], dtype=np.float32), (len(texts), 1))

    def embed_query(self, text):
        return np.array([1.0, 0.0], dtype=np.float32)


@pytest.fixture
def offline_index(tmp_path, monkeypatch):
    """Use real local stores, but never models, providers, or shared data."""
    embedder = _DeterministicEmbedder()
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "derived")
    monkeypatch.setattr(indexer, "VOYAGE_API_KEY", None)
    monkeypatch.setattr(search, "VOYAGE_API_KEY", None)
    monkeypatch.setattr(indexer, "get_embedder", lambda *a, **kw: embedder)
    monkeypatch.setattr(api, "get_embedder", lambda *a, **kw: embedder)
    stores = []

    def make_store(*args, **kwargs):
        store = ChunkStore(*args, **kwargs)
        stores.append(store)
        return store

    monkeypatch.setattr(api, "ChunkStore", make_store)
    monkeypatch.setattr(indexer, "ChunkStore", make_store)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    engine = CodeSight(corpus, ServerConfig(
        embedding_model="synthetic",
        embedding_backend="local",
        embedding_dim=2,
        chunk_max_lines=2,
        chunk_overlap_lines=0,
        reranker=False,
        metadata_boost=False,
        query_enhancement=False,
    ))
    yield engine, embedder
    for store in stores:
        store.close()


def _input_snapshot(corpus):
    return {str(p.relative_to(corpus)): p.read_bytes() for p in corpus.rglob("*") if p.is_file()}


def _index_read_only(engine):
    before = _input_snapshot(engine.folder_path)
    try:
        return engine.index()
    finally:
        assert _input_snapshot(engine.folder_path) == before


def _stored_snapshot(engine):
    ids = engine.store.vector_search(np.array([1.0, 0.0], dtype=np.float32), top_k=100)
    ids = sorted(ids)
    return (
        engine.status().chunk_count,
        engine.status().files_indexed,
        engine.store.get_chunk_metadata(ids),
        [v.tolist() for v in engine.store.get_chunk_vectors(ids)],
        [r.model_dump() for r in engine.search("needle", top_k=100)],
    )


def _assert_matches_fresh(engine, tmp_path, monkeypatch):
    incremental = _stored_snapshot(engine)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "fresh-derived")
    fresh = CodeSight(engine.folder_path, engine.config)
    _index_read_only(fresh)
    assert _stored_snapshot(fresh) == incremental


@pytest.mark.parametrize("replacement", ["", " \n\t\n  "])
@pytest.mark.parametrize("keep_other", [False, True])
def test_successfully_emptied_text_clears_old_chunks(
    offline_index, tmp_path, monkeypatch, replacement, keep_other,
):
    engine, embedder = offline_index
    target = engine.folder_path / "erased.txt"
    target.write_text("needle erased\nfirst chunk\nneedle obsolete\nsecond chunk")
    if keep_other:
        (engine.folder_path / "retained.txt").write_text("needle retained")
    initial = _index_read_only(engine)
    assert initial.total_chunks == 2 + keep_other
    assert len(engine.search("needle", file_glob="erased.txt")) == 2
    retained = engine.store.fts.get_chunk_hashes("retained.txt")
    embedded = list(embedder.embedded)

    # Mask/control: an entirely unchanged reindex must retain all chunks.
    unchanged = _index_read_only(engine)
    assert unchanged.chunks_created == 0
    assert unchanged.chunks_skipped_unchanged == initial.total_chunks
    assert embedder.embedded == embedded

    # The fixture owner, not the engine, successfully truncates the input.
    target.write_text(replacement)
    emptied = _index_read_only(engine)
    assert engine.search("needle", file_glob="erased.txt") == []
    assert emptied.total_chunks == keep_other
    assert engine.status().chunk_count == keep_other
    assert engine.store.bm25_search("erased") == []
    assert len(engine.store.vector_search(embedder.embed_query("needle"))) == keep_other
    assert engine.store.fts.get_chunk_hashes("erased.txt") == {}
    assert engine.store.fts.get_chunk_hashes("retained.txt") == retained
    if keep_other:
        assert engine.search("retained")[0].file_path == "retained.txt"
    assert embedder.embedded == embedded

    repeated = _index_read_only(engine)
    assert repeated.total_chunks == keep_other
    assert repeated.chunks_created == 0
    assert embedder.embedded == embedded
    _assert_matches_fresh(engine, tmp_path, monkeypatch)


@pytest.mark.parametrize("read_error", [PermissionError, OSError])
def test_failed_text_read_preserves_last_good_chunks_until_successful_retry(
    offline_index, tmp_path, monkeypatch, read_error,
):
    engine, embedder = offline_index
    target = engine.folder_path / "erased.txt"
    target.write_text("needle erased")
    (engine.folder_path / "retained.txt").write_text("needle retained")
    _index_read_only(engine)
    before = _stored_snapshot(engine)
    embedded = list(embedder.embedded)
    target.write_text("")
    real_read_text = Path.read_text

    def unreadable(path, *args, **kwargs):
        if path == target:
            raise read_error("synthetic read failure")
        return real_read_text(path, *args, **kwargs)

    with monkeypatch.context() as failure:
        failure.setattr(Path, "read_text", unreadable)
        failed = _index_read_only(engine)
        assert failed.total_chunks == 2
        assert failed.chunks_created == 0
        assert _stored_snapshot(engine) == before
        assert engine.search("erased", file_glob="erased.txt")
        assert embedder.embedded == embedded

    retry = _index_read_only(engine)
    assert retry.total_chunks == 1
    assert engine.search("erased", file_glob="erased.txt") == []
    assert engine.search("retained")[0].file_path == "retained.txt"
    assert embedder.embedded == embedded
    _assert_matches_fresh(engine, tmp_path, monkeypatch)


def test_text_chunking_error_preserves_last_good_chunks(
    offline_index, tmp_path, monkeypatch,
):
    engine, embedder = offline_index
    target = engine.folder_path / "erased.txt"
    target.write_text("needle erased")
    (engine.folder_path / "retained.txt").write_text("needle retained")
    _index_read_only(engine)
    before = _stored_snapshot(engine)
    embedded = list(embedder.embedded)

    def chunk_error(*args, **kwargs):
        raise ValueError("synthetic text parse failure")

    with monkeypatch.context() as failure:
        failure.setattr(indexer, "chunk_file", chunk_error)
        with pytest.raises(ValueError, match="synthetic text parse failure"):
            _index_read_only(engine)
        assert _stored_snapshot(engine) == before
        assert embedder.embedded == embedded

    # A successful nonempty replacement still follows the existing path.
    target.write_text("needle replacement")
    retry = _index_read_only(engine)
    assert retry.total_chunks == 2
    assert retry.chunks_created == 1
    assert len(embedder.embedded) == len(embedded) + 1
    assert engine.search("replacement", file_glob="erased.txt")[0].snippet == "needle replacement"
    _assert_matches_fresh(engine, tmp_path, monkeypatch)


@pytest.mark.parametrize("failure_mode", ["raised", "swallowed"])
def test_document_parse_failure_is_not_successful_empty_text(
    offline_index, tmp_path, monkeypatch, failure_mode,
):
    from docx import Document

    engine, embedder = offline_index
    target = engine.folder_path / "document.docx"
    doc = Document()
    doc.add_paragraph("needle document")
    doc.save(target)
    good_document = target.read_bytes()
    (engine.folder_path / "retained.txt").write_text("needle retained")
    _index_read_only(engine)
    before = _stored_snapshot(engine)
    embedded = list(embedder.embedded)

    with monkeypatch.context() as failure:
        if failure_mode == "raised":
            def parse_error(path):
                raise ValueError("synthetic parse failure")

            failure.setattr(indexer, "extract_text", parse_error)
        else:
            # Real document parsers can swallow errors and return [], so only
            # successful text reads authorize empty-file deletion in this fix.
            target.write_bytes(b"synthetic invalid docx")
        failed = _index_read_only(engine)
        assert failed.total_chunks == 2
        assert _stored_snapshot(engine) == before
        assert engine.search("document", file_glob="document.docx")
        assert embedder.embedded == embedded

    target.write_bytes(good_document)
    retry = _index_read_only(engine)
    assert retry.chunks_created == 0
    assert _stored_snapshot(engine) == before
    assert embedder.embedded == embedded
    _assert_matches_fresh(engine, tmp_path, monkeypatch)
