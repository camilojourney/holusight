"""Incremental indexing regressions: empty-text handling, unchanged-chunk
retention during partial edits, and the indexer's privately owned store
lifetime.
"""

from __future__ import annotations

import gc
import hashlib
import sqlite3
import weakref
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from codesight import CodeSight, api, config, indexer, search
from codesight.chunker import chunk_file
from codesight.config import ServerConfig
from codesight.indexer import index_repo
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


# ---------------------------------------------------------------------------
# Indexer-owned store lifetime: close on every exit path.
# ---------------------------------------------------------------------------


@pytest.fixture
def indexing_session(tmp_path, monkeypatch):
    """Keep real stores alive so refcounting/GC cannot substitute for close()."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    source = corpus / "sample.txt"
    source.write_text("synthetic lifecycle needle\n", encoding="utf-8")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "derived")
    monkeypatch.setattr(indexer, "VOYAGE_API_KEY", None)
    embedder = SimpleNamespace(
        embed=Mock(side_effect=lambda texts: np.tile([1.0, 0.0], (len(texts), 1)))
    )
    monkeypatch.setattr(indexer, "get_embedder", lambda *a, **kw: embedder)
    monkeypatch.setattr(api, "get_embedder", lambda *a, **kw: embedder)
    clock = iter([100.0, 101.25] * 10)
    monkeypatch.setattr(indexer, "time", SimpleNamespace(time=lambda: next(clock)))

    held = []

    def new_store(*args, **kwargs):
        store = ChunkStore(*args, **kwargs)
        store.fts.close = Mock(wraps=store.fts.close)
        store.close = Mock(wraps=store.close)
        held.append(store)
        return store

    monkeypatch.setattr(indexer, "ChunkStore", new_store)
    engine = api.CodeSight(
        corpus,
        config.ServerConfig(
            embedding_model="synthetic", embedding_backend="local", embedding_dim=2,
            reranker=False, metadata_boost=False,
        ),
    )
    caller_store = engine.store
    caller_store.fts.close = Mock(wraps=caller_store.fts.close)
    session = SimpleNamespace(
        engine=engine, caller_store=caller_store, held=held, embedder=embedder,
        source=source, new_store=new_store,
    )
    try:
        yield session
    finally:
        # Bypass spies: test cleanup must not hide a missing production close.
        for store in held + [caller_store]:
            store.fts.conn.close()


def assert_closed_once(store):
    store.close.assert_called_once_with()
    store.fts.close.assert_called_once_with()
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        store.fts.conn.execute("SELECT 1")


def assert_caller_open(session):
    session.caller_store.fts.close.assert_not_called()
    assert session.caller_store.fts.conn.execute("SELECT 1").fetchone() == (1,)
    assert session.source.read_text(encoding="utf-8") == "synthetic lifecycle needle\n"


def test_index_repeated_calls_close_only_owned_store_and_preserve_stats(indexing_session):
    session = indexing_session
    for force, created, skipped in [(False, 1, 0), (False, 0, 1), (True, 1, 0)]:
        stats = session.engine.index(force_rebuild=force)
        assert stats.model_dump() == {
            "repo_path": str(session.engine.folder_path),
            "files_indexed": 1,
            "chunks_created": created,
            "chunks_skipped_unchanged": skipped,
            "chunks_deleted": 0,
            "total_chunks": 1,
            "elapsed_seconds": 1.25,
        }
        assert_closed_once(session.held[-1])
        assert_caller_open(session)
    # Even an explicit collection cannot mask leaks while these stores are held.
    gc.collect()
    assert len(session.held) == 3
    assert_caller_open(session)
    for store in session.held:
        assert_closed_once(store)
    assert session.embedder.embed.call_count == 2
    with ChunkStore(session.engine.folder_path, embedding_dim=2) as reopened:
        assert reopened.chunk_count == 1
        assert reopened.fts.get_meta("embedding_model") == "synthetic"
        hits = reopened.bm25_search("needle")
        assert len(hits) == 1
        assert reopened.get_chunk_metadata(hits)[hits[0]]["file_path"] == "sample.txt"


def test_index_empty_folder_closes_store(indexing_session):
    session = indexing_session
    # The fixture owner, never the indexing engine, removes its synthetic input.
    session.source.unlink()
    stats = session.engine.index()
    assert stats.files_indexed == stats.chunks_created == stats.total_chunks == 0
    assert_closed_once(session.held[0])
    session.caller_store.fts.close.assert_not_called()
    with ChunkStore(session.engine.folder_path, embedding_dim=2) as reopened:
        assert reopened.chunk_count == 0


@pytest.mark.parametrize("error_type", [RuntimeError, KeyboardInterrupt])
@pytest.mark.parametrize(
    "stage", ["metadata", "walk", "progress", "embed", "upsert", "touch", "stats"],
)
def test_index_closes_store_on_error_or_interrupt(
    indexing_session, monkeypatch, stage, error_type,
):
    session = indexing_session
    error = error_type(f"injected {stage} failure")

    def fail(*args, **kwargs):
        raise error

    def new_store(*args, **kwargs):
        store = session.new_store(*args, **kwargs)
        if stage == "metadata":
            monkeypatch.setattr(store.fts, "set_meta", fail)
        elif stage == "upsert":
            monkeypatch.setattr(store, "upsert_chunks", fail)
        elif stage == "touch":
            monkeypatch.setattr(store, "touch_indexed", fail)
        elif stage == "stats":
            monkeypatch.setattr(store.fts, "chunk_count", fail)
        return store

    monkeypatch.setattr(indexer, "ChunkStore", new_store)
    if stage == "walk":
        monkeypatch.setattr(indexer, "walk_repo_files", fail)
    elif stage == "embed":
        session.embedder.embed.side_effect = fail

    with pytest.raises(error_type) as raised:
        session.engine.index(progress_callback=fail if stage == "progress" else None)
    assert raised.value is error  # No suppression or exception replacement.
    gc.collect()
    assert len(session.held) == 1
    assert_caller_open(session)
    assert_closed_once(session.held[0])
    # Reopening and writing must still work after any failed/interrupted phase.
    with ChunkStore(session.engine.folder_path, embedding_dim=2) as reopened:
        reopened.fts.set_meta("lifecycle_probe", "reopened")
        assert reopened.fts.get_meta("lifecycle_probe") == "reopened"


@pytest.mark.parametrize("error_type", [None, RuntimeError, KeyboardInterrupt])
def test_direct_store_context_is_smallest_cleanup_counterfactual(indexing_session, error_type):
    session = indexing_session
    store = session.new_store(session.engine.folder_path, embedding_dim=2)
    if error_type is None:
        with store:
            assert store.chunk_count == 0
    else:
        error = error_type("context probe")
        with pytest.raises(error_type) as raised, store:
            raise error
        assert raised.value is error
    assert_closed_once(store)
    assert_caller_open(session)


def test_unretained_connections_can_be_collected_masking_missing_close(
    indexing_session, monkeypatch,
):
    session = indexing_session

    class WeakConnection(sqlite3.Connection):
        """Real SQLite connection with weak-reference support for the GC control."""

    connect = sqlite3.connect
    monkeypatch.setattr(
        sqlite3, "connect", lambda *a, **kw: connect(*a, factory=WeakConnection, **kw),
    )
    session.engine.index()
    connection = weakref.ref(session.held[0].fts.conn)
    gc.collect()
    assert connection() is not None  # Retained store prevents GC-based cleanup.
    session.held.clear()
    gc.collect()
    assert connection() is None  # Dropping stores hides the original leak.
    assert_caller_open(session)


# ---------------------------------------------------------------------------
# Incremental partial-file reindex: retain unchanged chunks and their rows.
# ---------------------------------------------------------------------------


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
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    server_config = ServerConfig(
        embedding_model="synthetic", embedding_dim=2,
        chunk_max_lines=2, chunk_overlap_lines=0,
    )
    return server_config, calls


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
