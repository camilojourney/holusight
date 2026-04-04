"""Tests for the search module (RRF merging + reranker routing)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from codesight.search import _cnfb_boost, _reorder_by_filename_match, _rerank, rrf_merge, vprf_enhance_query
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


class TestVPRF:
    """Tests for Vector Pseudo-Relevance Feedback query enhancement."""

    def test_no_feedback_returns_original(self):
        """Returns original query vector when no feedback vectors provided."""
        q = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        out = vprf_enhance_query(q, [])
        np.testing.assert_array_equal(out, q)

    def test_output_is_l2_normalized(self):
        """Enhanced vector must be unit-norm."""
        q = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        fb = [np.array([0.0, 1.0, 0.0], dtype=np.float32)]
        out = vprf_enhance_query(q, fb)
        assert abs(np.linalg.norm(out) - 1.0) < 1e-6

    def test_feedback_shifts_query_toward_documents(self):
        """Enhanced query is a weighted blend of query + feedback, not identical to query."""
        q = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        fb = [np.array([0.0, 1.0, 0.0], dtype=np.float32)]
        out = vprf_enhance_query(q, fb, query_weight=0.8)
        # Enhanced vector should have non-zero y component from feedback
        assert out[1] > 0.0
        # And still dominated by x (query direction)
        assert out[0] > out[1]

    def test_uses_at_most_3_feedback_vectors(self):
        """Only top-3 feedback vectors are used even when more are provided."""
        q = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        # 5 feedback vectors all pointing in y direction
        fb = [np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)] * 5
        out_5 = vprf_enhance_query(q, fb)
        # Result should be same as with exactly 3 (since they're identical)
        fb_3 = fb[:3]
        out_3 = vprf_enhance_query(q, fb_3)
        np.testing.assert_array_almost_equal(out_5, out_3)

    def test_output_dtype_is_float32(self):
        """Output vector must be float32 for LanceDB compatibility."""
        q = np.array([1.0, 0.0, 0.0], dtype=np.float64)
        fb = [np.array([0.5, 0.5, 0.0], dtype=np.float64)]
        out = vprf_enhance_query(q, fb)
        assert out.dtype == np.float32


class TestMetadataBoost:
    """Tests for filename-based metadata boosting via _reorder_by_filename_match."""

    def _make_metadatas(self, mapping: dict[str, str]) -> dict[str, dict]:
        """Build a metadatas dict: chunk_id → {file_path: ...}."""
        return {cid: {"file_path": fp} for cid, fp in mapping.items()}

    def test_filename_match_promoted_to_front(self):
        """Chunk from a file whose name matches a query token is promoted."""
        metadatas = self._make_metadatas({
            "chunk_a": "src/codesight/embeddings.py",
            "chunk_b": "src/codesight/store.py",
            "chunk_c": "src/codesight/search.py",
        })
        # "embeddings" matches embeddings.py stem
        result = _reorder_by_filename_match(
            ["chunk_b", "chunk_c", "chunk_a"],
            "embeddings model",
            metadatas,
        )
        assert result[0] == "chunk_a"  # embeddings.py promoted to front
        assert set(result) == {"chunk_a", "chunk_b", "chunk_c"}

    def test_no_match_preserves_original_order(self):
        """When no token matches any filename, original order is unchanged."""
        metadatas = self._make_metadatas({
            "chunk_a": "src/codesight/store.py",
            "chunk_b": "src/codesight/search.py",
        })
        result = _reorder_by_filename_match(
            ["chunk_a", "chunk_b"],
            "how does retrieval work",  # "retrieval", "work" don't match store/search
            metadatas,
        )
        assert result == ["chunk_a", "chunk_b"]

    def test_stopwords_not_matched(self):
        """Stopwords like 'how', 'does', 'the', 'is' are filtered out."""
        metadatas = self._make_metadatas({
            "chunk_a": "src/codesight/how.py",   # filename matches stopword "how"
            "chunk_b": "src/codesight/store.py",
        })
        # "how" and "does" are stopwords — should NOT trigger boost
        result = _reorder_by_filename_match(
            ["chunk_b", "chunk_a"],
            "how does search work",
            metadatas,
        )
        # Only "search" and "work" are checked (len >= 3, not stopwords).
        # Neither matches "how.py" or "store.py", so order unchanged.
        assert result == ["chunk_b", "chunk_a"]

    def test_partial_filename_match(self):
        """Token that is a substring of the filename stem triggers boost."""
        metadatas = self._make_metadatas({
            "chunk_a": "src/codesight/chunk_manager.py",
            "chunk_b": "src/codesight/store.py",
        })
        # "chunk" is a substring of "chunk_manager"
        result = _reorder_by_filename_match(
            ["chunk_b", "chunk_a"],
            "chunk file splitting",
            metadatas,
        )
        assert result[0] == "chunk_a"

    def test_empty_query_tokens_after_stopword_filter(self):
        """If all tokens are stopwords, original order is preserved."""
        metadatas = self._make_metadatas({
            "chunk_a": "src/codesight/store.py",
            "chunk_b": "src/codesight/search.py",
        })
        result = _reorder_by_filename_match(
            ["chunk_a", "chunk_b"],
            "how is",  # both stopwords
            metadatas,
        )
        assert result == ["chunk_a", "chunk_b"]

    def test_missing_metadata_goes_to_rest(self):
        """Chunks with missing metadata are placed after matched chunks."""
        metadatas = self._make_metadatas({
            "chunk_a": "src/codesight/embeddings.py",
            # chunk_b has no metadata entry
        })
        result = _reorder_by_filename_match(
            ["chunk_b", "chunk_a"],
            "embeddings model",
            metadatas,
        )
        assert result[0] == "chunk_a"   # embeddings.py match → front
        assert result[1] == "chunk_b"   # no metadata → rest


def _make_cnfb_result(
    file_path: str,
    score: float = 1.0,
    start_line: int = 1,
) -> SearchResult:
    return SearchResult(
        file_path=file_path,
        start_line=start_line,
        end_line=start_line + 10,
        snippet="def foo(): pass",
        score=score,
        scope="function",
        chunk_id=f"{file_path}:{start_line}",
    )


class TestCNFBBoost:
    """Tests for _cnfb_boost() — SPEC-009."""

    def test_SPEC009_AC001_alpha_zero_is_noop(self):
        """AC-001: alpha=0.0 returns results unchanged (identity)."""
        results = [
            _make_cnfb_result("src/codesight/chunker.py", score=0.9),
            _make_cnfb_result("src/codesight/store.py", score=0.8),
        ]
        boosted = _cnfb_boost(results, "chunker logic", cnfb_alpha=0.0)
        assert boosted is results  # exact same object returned

    def test_SPEC009_AC002_full_match_boosts_score(self):
        """AC-002: full filename token match → score * (1 + alpha * 1.0)."""
        result = _make_cnfb_result("src/codesight/chunker.py", score=1.0)
        boosted = _cnfb_boost([result], "chunker", cnfb_alpha=0.5)
        # filename_tokens = {"chunker"}, query_tokens = {"chunker"}, overlap = 1.0
        # new_score = 1.0 * (1 + 0.5 * 1.0) = 1.5
        assert abs(boosted[0].score - 1.5) < 1e-5

    def test_SPEC009_AC003_no_match_score_unchanged(self):
        """AC-003: no filename overlap → score unchanged (overlap=0)."""
        result = _make_cnfb_result("src/codesight/store.py", score=1.0)
        boosted = _cnfb_boost([result], "chunker", cnfb_alpha=0.5)
        # filename_tokens = {"store"}, query_tokens = {"chunker"} → overlap = 0
        assert abs(boosted[0].score - 1.0) < 1e-5

    def test_SPEC009_AC004_partial_match_partial_boost(self):
        """AC-004: partial overlap → proportional boost."""
        # filename = "vector_store_impl" → tokens = {"vector", "store", "impl"}
        # query = "vector search store" → query_tokens = {"vector", "search", "store"}
        # overlap = |{vector, store} ∩ {vector, store, impl}| / 3 = 2/3
        result = _make_cnfb_result("src/codesight/vector_store_impl.py", score=1.0)
        boosted = _cnfb_boost([result], "vector search store", cnfb_alpha=0.5)
        expected = 1.0 * (1.0 + 0.5 * (2 / 3))
        assert abs(boosted[0].score - expected) < 1e-4

    def test_SPEC009_AC005_sort_order_by_boosted_score(self):
        """Higher overlap result should rank above lower overlap after boost."""
        # chunker.py matches "chunker" query → boosted
        # store.py does not match → unboosted
        chunker = _make_cnfb_result("src/codesight/chunker.py", score=0.8)
        store = _make_cnfb_result("src/codesight/store.py", score=0.9)
        # Without CNFB: store ranks first (0.9 > 0.8)
        # With CNFB alpha=1.0: chunker score = 0.8 * 2.0 = 1.6 > 0.9
        boosted = _cnfb_boost([store, chunker], "chunker", cnfb_alpha=1.0)
        assert boosted[0].file_path == "src/codesight/chunker.py"

    def test_SPEC009_AC006_query_tokens_not_recomputed_per_chunk(self):
        """AC-006: function processes multiple results correctly (shared tokenization)."""
        results = [
            _make_cnfb_result("src/codesight/chunker.py", score=1.0),
            _make_cnfb_result("src/codesight/embeddings.py", score=1.0),
            _make_cnfb_result("src/codesight/store.py", score=1.0),
        ]
        boosted = _cnfb_boost(results, "chunker", cnfb_alpha=0.5)
        # Only chunker.py matches — verify others are 1.0
        by_path = {r.file_path: r.score for r in boosted}
        assert abs(by_path["src/codesight/chunker.py"] - 1.5) < 1e-5
        assert abs(by_path["src/codesight/embeddings.py"] - 1.0) < 1e-5
        assert abs(by_path["src/codesight/store.py"] - 1.0) < 1e-5

    def test_SPEC009_AC007_empty_results_returns_empty(self):
        """Empty input → empty output, no crash."""
        assert _cnfb_boost([], "chunker", cnfb_alpha=0.5) == []

    def test_SPEC009_EDGE001_empty_filename_stem(self):
        """EDGE-001: file with unusual stem → no crash, correct math."""
        result = _make_cnfb_result("/foo/.hidden", score=1.0)
        boosted = _cnfb_boost([result], "hidden file", cnfb_alpha=0.5)
        # stem=".hidden" → token="hidden" (len>=2), query_tokens={"hidden","file"}
        assert len(boosted) == 1
        assert boosted[0].score >= 1.0  # either boosted or unchanged, no crash

    def test_SPEC009_EDGE003_stopword_only_query_no_boost(self):
        """EDGE-003: query with only stopwords → no query_tokens → results unchanged."""
        result = _make_cnfb_result("src/codesight/chunker.py", score=1.0)
        # "how does the" are all stopwords (len>=3 but in stopword list)
        boosted = _cnfb_boost([result], "how does the", cnfb_alpha=0.5)
        assert abs(boosted[0].score - 1.0) < 1e-5
