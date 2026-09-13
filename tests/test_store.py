"""Real storage regressions: BM25 glob membership plus vector search glob
pagination, using only synthetic metadata and vectors.
"""

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
    # separate bug (see the vector-glob pagination tests below). This test
    # measures exact membership in both real backends.
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


# ---------------------------------------------------------------------------
# Vector search: apply the file glob before the result limit, not after.
# ---------------------------------------------------------------------------


@pytest.fixture(params=["general", "code"])
def vector_store(request, tmp_path, monkeypatch):
    monkeypatch.setattr("codesight.config.DATA_DIR", tmp_path / "data")
    dimension = CODE_EMBEDDING_DIM if request.param == "code" else 2
    with ChunkStore(tmp_path / "corpus", embedding_dim=dimension) as store:
        upsert = store.upsert_code_chunks if request.param == "code" else store.upsert_chunks
        search = store.vector_search_code if request.param == "code" else store.vector_search

        def insert(ids, paths):
            vectors = np.zeros((len(ids), dimension), dtype=np.float32)
            vectors[:, 0] = np.arange(1, len(ids) + 1)
            upsert(ids, vectors, [
                dict(file_path=path, start_line=1, end_line=2, scope="module",
                     language="text", content_hash="synthetic", content="fixture content")
                for path in paths
            ])

        yield store, search, insert, np.zeros(dimension, dtype=np.float32)


def test_vector_glob_empty_table(vector_store):
    _, search, _, query = vector_store
    assert search(query, top_k=1, file_glob="*.py") == []
    assert search(query, top_k=1) == []


@pytest.mark.parametrize("top_k", [0, -1])
def test_vector_glob_nonpositive_limit(vector_store, top_k):
    _, search, insert, query = vector_store
    insert(["target"], ["target.py"])
    assert search(query, top_k=top_k, file_glob="*.py") == []
    assert search(query, top_k=top_k) == []


def test_vector_glob_exact_page_exhaustion(vector_store):
    _, search, insert, query = vector_store
    ids = [f"chunk-{i}" for i in range(256)]
    insert(ids, [f"decoy-{i}.txt" for i in range(256)])
    assert search(query, top_k=1, file_glob="*.py") == []


def test_vector_glob_limit_larger_than_page(vector_store):
    _, search, insert, query = vector_store
    ids = [f"chunk-{i}" for i in range(513)]
    insert(ids, [f"target-{i}.py" for i in range(513)])
    assert search(query, top_k=300, file_glob="*.py") == ids[:300]


@pytest.mark.parametrize("top_k", [1, 3, 10])
def test_vector_glob_limits_matching_records(vector_store, top_k):
    store, search, insert, query = vector_store
    paths = [f"decoy-{i}.txt" for i in range(513)] + [f"src/target-{i}.py" for i in range(4)]
    ids = [f"chunk-{i}" for i in range(len(paths))]
    insert(ids, paths)
    expected = ids[513:][:top_k]
    assert search(query, top_k=top_k, file_glob="*.py") == expected
    assert search(query, top_k=top_k) == ids[:top_k]
    assert search(query, top_k=top_k, file_glob="") == ids[:top_k]
    assert search(query, top_k=top_k, file_glob="*.missing") == []
    assert store.chunk_count == len(ids)


@pytest.mark.parametrize("pattern", [
    "*.py", "src/file_[ab].py", "src/file_?.py", "src/file_a.py",
    "rate%.md", "*.PY", "src/*", "src/file_[!a].py",
])
def test_vector_glob_retains_fnmatch_contract(vector_store, pattern):
    _, search, insert, query = vector_store
    paths = ["src/file_a.py", "src/fileXa.py", "src/file_b.py", "rate%.md",
             "rateX.md", "src/nested/file_a.py", "src/file_A.PY"]
    ids = [f"chunk-{i}" for i in range(len(paths))]
    insert(ids, paths)
    expected = [cid for cid, path in zip(ids, paths) if fnmatch.fnmatch(path, pattern)]
    assert search(query, top_k=10, file_glob=pattern) == expected


def test_vector_glob_pages_ids_without_materializing_vectors(vector_store, monkeypatch):
    from lancedb.query import LanceVectorQueryBuilder

    _, search, insert, query = vector_store
    paths = [f"decoy-{i}.txt" for i in range(513)] + ["target.py"]
    ids = [f"chunk-{i}" for i in range(len(paths))]
    insert(ids, paths)
    page_sizes = []
    original = LanceVectorQueryBuilder.to_pandas

    def bounded_page(builder, *args, **kwargs):
        page = original(builder, *args, **kwargs)
        assert "vector" not in page.columns
        assert len(page) <= 256
        page_sizes.append(len(page))
        return page

    monkeypatch.setattr(LanceVectorQueryBuilder, "to_pandas", bounded_page)
    assert search(query, top_k=1, file_glob="*.py") == [ids[-1]]
    assert len(page_sizes) >= 3
    assert sum(page_sizes) == len(ids)


def test_vector_glob_skips_missing_metadata(vector_store):
    store, search, insert, query = vector_store
    insert(["orphan", "target"], ["orphan.py", "target.py"])
    store.fts.delete_chunks_for_file("orphan.py")
    store.fts.commit()
    assert search(query, top_k=1, file_glob="*.py") == ["target"]


def test_vector_glob_preserves_source_filter(tmp_path, monkeypatch):
    monkeypatch.setattr("codesight.config.DATA_DIR", tmp_path / "data")
    with ChunkStore(tmp_path / "corpus", embedding_dim=2) as store:
        ids = ["ordinary", "holus:decoy", "holus:target"]
        paths = ["ordinary.py", "decoy.txt", "target.py"]
        store.upsert_chunks(ids, np.array([[0, 0], [1, 0], [2, 0]], dtype=np.float32), [
            dict(file_path=path, start_line=1, end_line=2, scope="module",
                 language="text", content_hash="synthetic", content="fixture content")
            for path in paths
        ])
        query = np.zeros(2, dtype=np.float32)
        assert store.vector_search(query, top_k=1, source="holus") == ["holus:decoy"]
        assert store.vector_search(query, top_k=1, file_glob="*.py", source="holus") == [
            "holus:target",
        ]
