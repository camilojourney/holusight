"""Real storage membership checks using only synthetic metadata and vectors."""

from __future__ import annotations

import fnmatch

import numpy as np
import pytest

import codesight.config as config_module
from codesight.store import CODE_EMBEDDING_DIM, ChunkStore, FTSSidecar

GLOB_PATHS = [
    "file_a.py", "fileXa.py", "rate%.md", "rateX.md", "filea.py", "fileb.py",
    "file[ab].py", "Case.py", "lower.py", "src/nested.py", "src/deep/leaf.py",
    r"src\windows.py", "plain.txt", "quote'file.py", "file[.py",
    "x' OR 1=1 --.py",
]
GLOB_PATTERNS = [
    "file_a.py", "rate%.md", "file[ab].py", "file[!X]a.py", "file[a-b].py",
    "file[[]ab].py", "file[.py", "case.py", "Case.py", "src/*.py", "src/?ested.py",
    r"src\*.py", "*.py", "file?a.py", "quote'file.py", "x' OR 1=1 --.py",
    "' OR 1=1 --", "missing*", None, "",
]


def _metadata(path, content="needle"):
    return {
        "file_path": path, "start_line": 1, "end_line": 1, "scope": "",
        "language": "text", "content_hash": "synthetic", "content": content,
    }


@pytest.fixture
def glob_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "data")
    with ChunkStore(tmp_path / "corpus", embedding_dim=2) as store:
        # Synthetic IDs exercise the existing source predicate, not lineage import.
        ids = [f"{prefix}{i}" for prefix in ("file:", "holus:") for i in range(len(GLOB_PATHS))]
        metadata = [_metadata(path) for _ in range(2) for path in GLOB_PATHS]
        code_vectors = np.zeros((len(ids), CODE_EMBEDDING_DIM), dtype=np.float32)
        code_vectors[:, 0] = 1
        store.upsert_code_chunks(ids, code_vectors, metadata)
        store.upsert_chunks(ids, np.tile([1.0, 0.0], (len(ids), 1)), metadata)
        yield store


@pytest.mark.parametrize("pattern", GLOB_PATTERNS)
@pytest.mark.parametrize("source", [None, "holus"])
def test_bm25_glob_membership_matches_fnmatch_and_vector(glob_store, pattern, source):
    store = glob_store
    all_ids = store.bm25_search("needle", top_k=100, source=source)
    metadata = store.get_chunk_metadata(all_ids)
    expected = {
        cid for cid, meta in metadata.items()
        if not pattern or fnmatch.fnmatch(meta["file_path"], pattern)
    }
    if source == "holus":
        assert len(all_ids) == len(GLOB_PATHS)
        assert all(cid.startswith("holus:") for cid in all_ids)
    else:
        assert len(all_ids) == 2 * len(GLOB_PATHS)

    # Include the whole fixture in vector candidates: pre-limit starvation is a
    # separate bug. This test measures exact membership in both real backends.
    vector_ids = store.vector_search(np.array([1.0, 0.0]), 100, pattern, source)
    assert set(vector_ids) == expected
    if source is None:
        code_query = np.zeros(CODE_EMBEDDING_DIM, dtype=np.float32)
        code_query[0] = 1
        assert set(store.vector_search_code(code_query, 100, pattern)) == expected
    assert set(store.fts.bm25_search("needle", 100, pattern, source)) == expected
    assert set(store.bm25_search("needle", 100, pattern, source)) == expected


@pytest.mark.parametrize("source", [None, "holus"])
def test_bm25_filters_before_top_k_and_preserves_rank(tmp_path, source):
    with FTSSidecar(tmp_path / "fts.db") as fts:
        for i in range(40):
            fts.upsert_chunk(f"holus:decoy:{i}", f"fileX{i}.py", 1, 1, "", "text",
                             "synthetic", "needle " * 20)
        for i in range(3):
            fts.upsert_chunk(f"holus:match:{i}", f"file_{i}.py", 1, 1, "", "text",
                             "synthetic", "needle " + "padding " * (20 + i))
        fts.upsert_chunk("file:ordinary", "file_ordinary.py", 1, 1, "", "text",
                         "synthetic", "needle " * 30)
        fts.commit()
        unfiltered = fts.bm25_search("needle", top_k=100, source=source)
        expected = [
            cid for cid in unfiltered
            if fnmatch.fnmatch(fts.get_chunk_by_id(cid)["file_path"], "file_*.py")
        ]
        assert len(expected) >= 3
        # A globally limited result cannot fill the filtered top two.
        assert len(set(unfiltered[:2]) & set(expected)) < 2
        assert fts.bm25_search("needle", 2, "file_*.py", source) == expected[:2]
        assert fts.bm25_search("needle", 0, "file_*.py", source) == []


def test_bm25_glob_is_parameterized_and_available_after_reopen(tmp_path):
    db = tmp_path / "fts.db"
    path = "x' OR 1=1 --.py"
    with FTSSidecar(db) as fts:
        fts.upsert_chunk("literal", path, 1, 1, "", "text", "synthetic", "needle")
        fts.upsert_chunk("decoy", "decoy.py", 1, 1, "", "text", "synthetic", "needle")
        fts.commit()
    with FTSSidecar(db) as fts:
        assert fts.bm25_search("needle", file_glob=path) == ["literal"]
        assert fts.bm25_search("needle", file_glob="' OR 1=1 --") == []
        assert fts.chunk_count() == 2
        assert set(fts.bm25_search("needle")) == {"literal", "decoy"}
