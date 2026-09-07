"""Offline API regressions for the indexer's privately owned store lifetime."""

import gc
import sqlite3
import weakref
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from codesight import api, config, indexer
from codesight.store import ChunkStore


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
