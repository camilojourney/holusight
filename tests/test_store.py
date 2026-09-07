"""Vector filtering regressions using isolated, deterministic LanceDB tables."""

import fnmatch

import numpy as np
import pytest

from codesight.store import CODE_EMBEDDING_DIM, ChunkStore


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
