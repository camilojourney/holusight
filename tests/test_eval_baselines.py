"""Tests for eval_baselines.py — exact, BM25-only, and Graphify structural
retrieval baselines used by the eval harness."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from tests.eval_baselines import (
    BASELINE_BM25,
    BASELINE_EXACT,
    BASELINE_GRAPHIFY,
    bm25_search_fn,
    exact_search_fn_factory,
    graphify_availability,
    graphify_structural_search_fn_factory,
)


@pytest.fixture
def tiny_repo(tmp_path):
    """A minimal repo with a couple of Python files and no .gitignore surprises."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "search.py").write_text(
        "def rrf_merge(ranked_lists, k=60):\n    return []\n\n\ndef other():\n    pass\n"
    )
    (tmp_path / "src" / "store.py").write_text(
        "def bm25_search(query):\n    return []\n"
    )
    return tmp_path


class TestExactSearchFn:
    def test_finds_literal_match(self, tiny_repo):
        fn = exact_search_fn_factory(tiny_repo)
        results = fn(None, None, "def rrf_merge", top_k=5)
        assert len(results) == 1
        assert results[0].file_path == "src/search.py"
        assert results[0].source == BASELINE_EXACT

    def test_no_match_returns_empty(self, tiny_repo):
        fn = exact_search_fn_factory(tiny_repo)
        results = fn(None, None, "this string does not exist anywhere", top_k=5)
        assert results == []

    def test_empty_query_returns_empty(self, tiny_repo):
        fn = exact_search_fn_factory(tiny_repo)
        assert fn(None, None, "   ", top_k=5) == []

    def test_case_insensitive(self, tiny_repo):
        fn = exact_search_fn_factory(tiny_repo)
        results = fn(None, None, "RRF_MERGE", top_k=5)
        assert len(results) == 1
        assert results[0].file_path == "src/search.py"

    def test_respects_top_k(self, tiny_repo):
        # Every line in both files contains "def", so top_k should cap results.
        fn = exact_search_fn_factory(tiny_repo)
        results = fn(None, None, "def", top_k=1)
        assert len(results) <= 1


class TestBm25SearchFn:
    def test_calls_store_bm25_search_and_builds_results(self):
        store = MagicMock()
        store.bm25_search.return_value = ["chunk-1", "chunk-2"]
        store.get_chunk_metadata.return_value = {
            "chunk-1": {
                "file_path": "src/search.py", "start_line": 10, "end_line": 20,
                "scope": "function", "content": "def rrf_merge(): pass",
            },
            "chunk-2": {
                "file_path": "src/store.py", "start_line": 1, "end_line": 5,
                "scope": "module", "content": "import sqlite3",
            },
        }

        results = bm25_search_fn(store, None, "rrf merge", top_k=10)

        store.bm25_search.assert_called_once_with("rrf merge", top_k=10)
        assert len(results) == 2
        assert results[0].file_path == "src/search.py"
        assert results[0].source == BASELINE_BM25
        # Rank-derived scores are strictly descending.
        assert results[0].score > results[1].score

    def test_no_results_returns_empty(self):
        store = MagicMock()
        store.bm25_search.return_value = []
        assert bm25_search_fn(store, None, "nothing", top_k=10) == []


class TestGraphifyStructuralBaseline:
    def _write_graph(self, tmp_path, built_at_commit="abc123"):
        graphify_dir = tmp_path / "graphify-out"
        graphify_dir.mkdir()
        graph = {
            "nodes": [
                {"id": "src_search_rrf_merge", "source_file": "src/search.py"},
                {"id": "src_store_bm25_search", "source_file": "src/store.py"},
            ],
            "links": [],
            "built_at_commit": built_at_commit,
        }
        (graphify_dir / "graph.json").write_text(json.dumps(graph))

    def test_unavailable_when_no_graph(self, tmp_path):
        avail = graphify_availability(tmp_path)
        assert avail.available is False

        fn = graphify_structural_search_fn_factory(tmp_path)
        assert fn(None, None, "rrf merge", top_k=5) == []

    def test_available_and_matches_node_id_tokens(self, tiny_repo):
        self._write_graph(tiny_repo)
        avail = graphify_availability(tiny_repo)
        assert avail.available is True

        fn = graphify_structural_search_fn_factory(tiny_repo)
        results = fn(None, None, "rrf merge", top_k=5)
        assert len(results) == 1
        assert results[0].file_path == "src/search.py"
        assert results[0].source == BASELINE_GRAPHIFY

    def test_no_token_overlap_returns_empty(self, tiny_repo):
        self._write_graph(tiny_repo)
        fn = graphify_structural_search_fn_factory(tiny_repo)
        results = fn(None, None, "completely unrelated topic zzz", top_k=5)
        assert results == []

    def test_staleness_reported_relative_to_head(self, tiny_repo):
        self._write_graph(tiny_repo, built_at_commit="not-a-real-commit")
        avail = graphify_availability(tiny_repo)
        # tiny_repo is not a git repo at all, so current_commit is None and
        # staleness must be conservative (stale=True), never silently "fresh".
        assert avail.stale is True
