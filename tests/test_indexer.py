"""Synthetic, offline API regressions for incremental missing-file reconciliation."""

import hashlib
from pathlib import Path

import numpy as np
import pytest

from codesight import CodeSight, api, config, indexer, search
from codesight.config import ServerConfig
from codesight.parsers import DocumentPage
from codesight.store import ChunkStore


class SyntheticEmbedder:
    def __init__(self, dim):
        self.dim = dim
        self.texts = []

    def embed_query(self, text):
        digest = hashlib.sha256(text.encode()).digest()
        return np.resize(np.frombuffer(digest, dtype=np.uint8), self.dim).astype(np.float32)

    def embed(self, texts):
        self.texts.extend(texts)
        return np.array([self.embed_query(text) for text in texts])


@pytest.fixture
def indexing_env(tmp_path, monkeypatch):
    """Real storage, private test DBs, and fake general/code/query embeddings."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "derived")
    general = SyntheticEmbedder(2)
    code = SyntheticEmbedder(1024)

    def fake_embedder(model, *args, **kwargs):
        return code if model == "voyage-code-3" else general

    for module in (api, indexer, search):
        monkeypatch.setattr(module, "get_embedder", fake_embedder)
    monkeypatch.setattr(indexer, "VOYAGE_API_KEY", "synthetic-not-a-key")
    monkeypatch.setattr(search, "VOYAGE_API_KEY", "synthetic-not-a-key")
    stores = []

    def tracked_store(*args, **kwargs):
        store = ChunkStore(*args, **kwargs)
        stores.append(store)
        return store

    monkeypatch.setattr(api, "ChunkStore", tracked_store)
    monkeypatch.setattr(indexer, "ChunkStore", tracked_store)
    settings = ServerConfig(
        embedding_model="synthetic", embedding_dim=2,
        reranker=False, metadata_boost=False, query_enhancement=False,
    )

    def engine_for(name):
        corpus = tmp_path / name
        corpus.mkdir()
        return CodeSight(corpus, settings)

    yield engine_for, general, code
    for store in stores:
        store.close()


def snapshot(engine):
    """Compare both raw vector tables and all shared metadata, not just rescued hits."""
    store = engine.store
    ids = [row[0] for row in store.fts.conn.execute("SELECT chunk_id FROM chunks")]
    vectors = {}
    for name, table in (("general", store.lance_table), ("code", store.code_lance_table)):
        vectors[name] = (
            sorted(table.to_arrow().to_pylist(), key=lambda row: row["chunk_id"])
            if table is not None else []
        )
    return store.get_chunk_metadata(ids), vectors


@pytest.mark.parametrize("suffix", [".txt", ".py"])
def test_removed_file_reindex_matches_fresh_final_corpus(indexing_env, suffix):
    engine_for, general, code = indexing_env
    engine = engine_for("incremental")
    removed = engine.folder_path / ("removed" + suffix)
    survivor = engine.folder_path / ("survivor" + suffix)
    removed.write_text("removedneedle = 1\n")
    survivor.write_text("survivorneedle = 2\n")
    assert engine.index().total_chunks == 2
    assert removed.name in {r.file_path for r in engine.search("removedneedle")}
    survivor_hashes = engine.store.fts.get_chunk_hashes(survivor.name)
    embedded = len(general.texts), len(code.texts)
    unchanged = snapshot(engine)
    assert engine.index().chunks_created == 0
    assert snapshot(engine) == unchanged
    assert (len(general.texts), len(code.texts)) == embedded

    # The synthetic fixture owner removes an input. The engine must only read inputs.
    removed.unlink()
    stats = engine.index()
    assert removed.name not in {r.file_path for r in engine.search("removedneedle")}
    assert engine.store.bm25_search("removedneedle") == []
    assert stats.total_chunks == engine.status().chunk_count == 1
    assert stats.chunks_deleted == 1
    assert engine.status().files_indexed == 1
    assert stats.chunks_created == 0
    assert stats.chunks_skipped_unchanged == 1
    assert (len(general.texts), len(code.texts)) == embedded
    assert engine.store.fts.get_chunk_hashes(survivor.name) == survivor_hashes
    assert survivor.read_text() == "survivorneedle = 2\n"
    assert list(engine.folder_path.iterdir()) == [survivor]
    for ids in (
        engine.store.vector_search(general.embed_query("removedneedle")),
        engine.store.vector_search_code(code.embed_query("removedneedle")),
    ):
        assert all(not cid.startswith(removed.name + ":") for cid in ids)

    final = snapshot(engine)
    repeated = engine.index()
    assert repeated.chunks_created == repeated.chunks_deleted == 0
    assert snapshot(engine) == final
    assert (len(general.texts), len(code.texts)) == embedded

    fresh = engine_for("fresh")
    (fresh.folder_path / survivor.name).write_text(survivor.read_text())
    fresh.index()
    assert snapshot(fresh) == final
    assert {r.chunk_id for r in fresh.search("survivorneedle")} == {
        r.chunk_id for r in engine.search("survivorneedle")
    }


def test_removed_subdirectory_loses_every_file_chunk(indexing_env):
    engine_for, general, _ = indexing_env
    engine = engine_for("nested")
    engine.config.chunk_max_lines = 2
    engine.config.chunk_overlap_lines = 0
    nested = engine.folder_path / "nested"
    nested.mkdir()
    removed = nested / "removed.txt"
    removed.write_text("removedneedle\nfirst\nremovedneedle\nsecond")
    (engine.folder_path / "survivor.txt").write_text("survivorneedle")
    assert engine.index().total_chunks == 3
    removed.unlink()
    nested.rmdir()
    stats = engine.index()
    assert stats.total_chunks == 1
    assert stats.chunks_deleted == 2
    assert engine.store.bm25_search("removedneedle") == []
    assert len(engine.store.vector_search(general.embed_query("removedneedle"))) == 1


def test_rename_and_empty_corpus_are_idempotent(indexing_env):
    engine_for, general, code = indexing_env
    engine = engine_for("renamed")
    original = engine.folder_path / "original.txt"
    original.write_text("renameneedle\n")
    engine.index()
    renamed = original.rename(engine.folder_path / "renamed.txt")
    stats = engine.index()
    assert stats.chunks_created == stats.total_chunks == 1
    assert {r.file_path for r in engine.search("renameneedle")} == {renamed.name}
    fresh = engine_for("fresh")
    (fresh.folder_path / renamed.name).write_text(renamed.read_text())
    fresh.index()
    assert snapshot(engine) == snapshot(fresh)
    before = len(general.texts), len(code.texts)
    assert engine.index().chunks_created == 0
    assert (len(general.texts), len(code.texts)) == before

    renamed.unlink()
    for _ in range(2):
        assert engine.index().total_chunks == 0
        assert engine.search("renameneedle") == []
        assert engine.store.bm25_search("renameneedle") == []
        assert engine.store.vector_search(general.embed_query("renameneedle")) == []
        assert engine.status().files_indexed == 0
    assert (len(general.texts), len(code.texts)) == before


@pytest.mark.parametrize(
    "failure", ["walk", "walk_late", "stat", "gitignore", "missing_root", "embedding"]
)
def test_incomplete_scan_or_failed_index_never_prunes(indexing_env, monkeypatch, failure):
    engine_for, general, _ = indexing_env
    engine = engine_for("incomplete")
    removed = engine.folder_path / "removed.txt"
    survivor = engine.folder_path / "survivor.txt"
    removed.write_text("removedneedle\n")
    survivor.write_text("survivorneedle\n")
    engine.index()
    before = snapshot(engine)
    removed.unlink()

    with monkeypatch.context() as patch:
        if failure in {"walk", "walk_late"}:
            def failed_walk(root, **kwargs):
                # Exercise os.walk's error callback, including failure after yielding entries.
                if failure == "walk_late":
                    yield str(root), [], [survivor.name]
                if kwargs.get("onerror"):
                    kwargs["onerror"](PermissionError("synthetic inaccessible directory"))
            patch.setattr(indexer.os, "walk", failed_walk)
        elif failure == "stat":
            original_stat = Path.stat

            def failed_stat(path, *args, **kwargs):
                if path == survivor:
                    raise PermissionError("synthetic unreadable stat")
                return original_stat(path, *args, **kwargs)
            patch.setattr(Path, "stat", failed_stat)
        elif failure == "gitignore":
            def failed_open(*args, **kwargs):
                raise PermissionError("synthetic unreadable gitignore")
            patch.setattr(indexer, "open", failed_open, raising=False)
        elif failure == "missing_root":
            original_walk = indexer.os.walk

            def vanished_root(root, **kwargs):
                yield from original_walk(root, **kwargs)
                Path(root).rename(Path(root).with_name("temporarily-away"))
            patch.setattr(indexer.os, "walk", vanished_root)
        else:
            (engine.folder_path / "new.txt").write_text("newneedle\n")

            def failed_embed(texts):
                raise RuntimeError("synthetic embedding failure")
            patch.setattr(general, "embed", failed_embed)
        with pytest.raises((OSError, RuntimeError)):
            engine.index()
        assert snapshot(engine) == before

    if failure == "missing_root":
        engine.folder_path.with_name("temporarily-away").rename(engine.folder_path)
    # Same fixture with the failure removed converges; absence alone wasn't the error.
    assert engine.index().total_chunks == (2 if failure == "embedding" else 1)
    assert engine.store.bm25_search("removedneedle") == []


@pytest.mark.parametrize("unseen_reason", ["gitignore", "oversize", "omitted", "symlink"])
def test_unseen_but_existing_paths_are_not_removals(indexing_env, monkeypatch, unseen_reason):
    engine_for, general, _ = indexing_env
    engine = engine_for("excluded")
    path = engine.folder_path / "retained.txt"
    path.write_text("retainedneedle\n")
    engine.index()
    before = snapshot(engine)
    embedded = len(general.texts)
    if unseen_reason == "gitignore":
        (engine.folder_path / ".gitignore").write_text("retained.txt\n")
    elif unseen_reason == "oversize":
        monkeypatch.setattr(indexer, "MAX_FILE_SIZE_BYTES", 1)
    elif unseen_reason == "omitted":
        monkeypatch.setattr(indexer, "walk_repo_files", lambda root: [])
    else:
        target_dir = engine.folder_path / ".hidden"
        target_dir.mkdir()
        target = path.rename(target_dir / path.name)
        path.symlink_to(target)
        monkeypatch.setattr(indexer, "walk_repo_files", lambda root: [])
    assert engine.index().chunks_created == 0
    assert snapshot(engine) == before
    assert len(general.texts) == embedded


@pytest.mark.parametrize("failure", ["read", "parse", "parse_empty"])
def test_read_and_parse_failures_preserve_seen_file_records(indexing_env, monkeypatch, failure):
    engine_for, _, _ = indexing_env
    engine = engine_for("unreadable")
    retained = engine.folder_path / ("retained.txt" if failure == "read" else "retained.pdf")
    retained.write_text("synthetic input\n")
    removed = engine.folder_path / "removed.txt"
    removed.write_text("removedneedle\n")
    monkeypatch.setattr(indexer, "extract_text", lambda _: [DocumentPage("retainedneedle", 1)])
    engine.index()
    retained_ids = engine.store.fts.get_chunk_hashes(retained.name)
    retained_metadata = engine.store.get_chunk_metadata(list(retained_ids))
    removed.unlink()

    def fail(*args, **kwargs):
        raise PermissionError("synthetic read/parse failure")

    if failure == "read":
        monkeypatch.setattr(Path, "read_text", fail)
    elif failure == "parse":
        monkeypatch.setattr(indexer, "extract_text", fail)
    else:
        monkeypatch.setattr(indexer, "extract_text", lambda _: [])
    assert engine.index().total_chunks == len(retained_ids)
    assert engine.store.get_chunk_metadata(list(retained_ids)) == retained_metadata
    assert engine.store.bm25_search("removedneedle") == []


def test_lineage_namespace_is_not_owned_by_file_scan(indexing_env):
    engine_for, general, _ = indexing_env
    engine = engine_for("lineage-preservation")
    ordinary = engine.folder_path / "ordinary.txt"
    ordinary.write_text("ordinaryneedle\n")
    engine.index()
    # Seed inert synthetic storage records directly. No lineage import or external data.
    lineage_ids = ["holus:synthetic:node", "holus:synthetic:collision"]
    engine.store.upsert_chunks(
        lineage_ids, general.embed(["lineageneedle"] * 2),
        [dict(file_path=path, start_line=1, end_line=1, scope="Holus lineage",
              language="holus-lineage", content_hash="synthetic", content="lineageneedle")
         for path in ("holus-lineage/synthetic.json", "collision.txt")],
    )
    engine.store.fts.set_lineage_metadata(lineage_ids[0], {"synthetic": True})
    lineage_before = engine.store.get_chunk_metadata(lineage_ids)
    ordinary.unlink()
    for _ in range(2):
        assert engine.index().total_chunks == 2
        assert engine.store.get_chunk_metadata(lineage_ids) == lineage_before
        assert set(engine.store.bm25_search("lineageneedle")) == set(lineage_ids)
        assert set(engine.store.vector_search(general.embed_query("lineageneedle"))) == set(
            lineage_ids
        )
        assert engine.store.fts.get_lineage_metadata(lineage_ids[0]) == {"synthetic": True}


def test_absence_check_error_does_not_partially_prune(indexing_env, monkeypatch):
    engine_for, _, _ = indexing_env
    engine = engine_for("absence-error")
    files = [engine.folder_path / name for name in ("a.txt", "b.txt")]
    for path in files:
        path.write_text("absenceneedle\n")
    engine.index()
    before = snapshot(engine)
    for path in files:
        path.unlink()
    original_lstat = Path.lstat

    def failed_lstat(path, *args, **kwargs):
        if path == files[1]:
            raise PermissionError("synthetic absence check error")
        return original_lstat(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "lstat", failed_lstat)
        with pytest.raises(PermissionError):
            engine.index()
        assert snapshot(engine) == before
    assert engine.index().total_chunks == 0
