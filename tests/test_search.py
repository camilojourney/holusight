"""Tests for the search module (RRF merging + reranker routing)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from codesight.search import _rerank, rrf_merge
from codesight.types import SearchResult


class TestRRFMerge:
    def test_single_list(self):
        """Single ranked list preserves order."""
        result = rrf_merge([["a", "b", "c"]])
        ids = [cid for cid, _ in result]
        assert ids == ["a", "b", "c"]

    def test_two_identical_lists(self):
        """Two identical lists: items appear once with doubled scores."""
        result = rrf_merge([["a", "b", "c"], ["a", "b", "c"]])
        ids = [cid for cid, _ in result]
        assert ids[0] == "a"  # top item stays top

    def test_disjoint_lists(self):
        """Disjoint lists merge all items."""
        result = rrf_merge([["a", "b"], ["c", "d"]])
        ids = {cid for cid, _ in result}
        assert ids == {"a", "b", "c", "d"}

    def test_overlapping_lists_boost_shared(self):
        """Items appearing in both lists get higher scores."""
        result = rrf_merge([["shared", "only_a"], ["shared", "only_b"]])
        ids = [cid for cid, _ in result]
        # "shared" appears in both lists, should be ranked first
        assert ids[0] == "shared"

    def test_empty_lists(self):
        result = rrf_merge([[], []])
        assert result == []

    def test_k_constant_affects_scores(self):
        """Higher k flattens score differences."""
        result_low_k = rrf_merge([["a", "b"]], k=1)
        result_high_k = rrf_merge([["a", "b"]], k=100)

        # With low k, score difference between rank 0 and 1 is larger
        diff_low = result_low_k[0][1] - result_low_k[1][1]
        diff_high = result_high_k[0][1] - result_high_k[1][1]
        assert diff_low > diff_high


def _make_result(snippet: str, score: float = 0.5) -> SearchResult:
    return SearchResult(
        file_path="test.py",
        start_line=1,
        end_line=10,
        snippet=snippet,
        score=score,
        scope="module",
        chunk_id=snippet[:8],
    )


class TestVoyageReranker:
    """Tests for voyage API reranker routing and fallback."""

    def test_rerank_routes_to_voyage_when_backend_voyage(self):
        """_rerank() calls _rerank_voyage when backend='voyage'."""
        results = [_make_result("def foo(): pass"), _make_result("class Bar: pass")]

        mock_item_0 = MagicMock()
        mock_item_0.index = 1
        mock_item_0.relevance_score = 0.95

        mock_item_1 = MagicMock()
        mock_item_1.index = 0
        mock_item_1.relevance_score = 0.42

        mock_response = MagicMock()
        mock_response.results = [mock_item_0, mock_item_1]

        mock_client = MagicMock()
        mock_client.rerank.return_value = mock_response

        with patch("codesight.search._get_voyage_client", return_value=mock_client):
            reranked = _rerank("foo bar", results, top_k=2, model_name="rerank-2", backend="voyage")

        mock_client.rerank.assert_called_once_with(
            query="foo bar",
            documents=["def foo(): pass", "class Bar: pass"],
            model="rerank-2",
            top_k=2,
        )
        # index=1 (class Bar) should be first since it got higher relevance
        assert reranked[0].snippet == "class Bar: pass"
        assert reranked[0].score == 0.95
        assert reranked[1].snippet == "def foo(): pass"
        assert reranked[1].score == 0.42

    def test_rerank_routes_to_local_when_backend_local(self):
        """_rerank() calls local cross-encoder when backend='local'."""
        results = [_make_result("def alpha(): pass"), _make_result("def beta(): pass")]

        with patch("codesight.search._rerank_local") as mock_local:
            mock_local.return_value = results[:1]
            out = _rerank(
                "alpha",
                results,
                top_k=1,
                model_name="cross-encoder/ms-marco-MiniLM-L-6-v2",
                backend="local",
            )

        mock_local.assert_called_once()
        assert out == results[:1]

    def test_voyage_reranker_falls_back_on_api_error(self):
        """_rerank_voyage falls back to RRF order when API throws."""
        from codesight.search import _rerank_voyage

        results = [_make_result("snippet_a"), _make_result("snippet_b")]
        mock_client = MagicMock()
        mock_client.rerank.side_effect = RuntimeError("API timeout")

        with patch("codesight.search._get_voyage_client", return_value=mock_client):
            out = _rerank_voyage("query", results, top_k=2, model_name="rerank-2")

        # Falls back to original RRF order, truncated to top_k
        assert len(out) == 2
        assert out[0].snippet == "snippet_a"

    def test_voyage_reranker_empty_results(self):
        """_rerank_voyage returns empty list when no results provided."""
        from codesight.search import _rerank_voyage

        out = _rerank_voyage("query", [], top_k=5, model_name="rerank-2")
        assert out == []
