"""Tests for eval_harness.py — hit_rate, MRR, token efficiency metrics."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from codesight.types import SearchResult
from tests.eval_harness import EvalQuery, _count_tokens, run_eval


def _make_result(
    file_path: str,
    start_line: int = 1,
    snippet: str = "def foo(): pass",
    score: float = 0.9,
) -> SearchResult:
    return SearchResult(
        file_path=file_path,
        start_line=start_line,
        end_line=start_line + 10,
        snippet=snippet,
        score=score,
        scope="function",
        chunk_id=f"{file_path}:{start_line}",
        tokens_used=len(snippet) // 4,
    )


class TestCountTokens:
    def test_fallback_short_text(self):
        result = _count_tokens("hello")
        assert result >= 1

    def test_fallback_longer_text(self):
        text = "a" * 400
        result = _count_tokens(text)
        assert result == 100  # 400 // 4

    def test_minimum_is_one(self):
        # Even empty-ish strings return at least 1
        result = _count_tokens("x")
        assert result >= 1


class TestTokensUsedField:
    def test_tokens_used_populated(self):
        """SearchResult.tokens_used should be set."""
        r = _make_result("src/foo.py", snippet="def foo(): pass  # 16 chars")
        assert r.tokens_used is not None
        assert r.tokens_used >= 1

    def test_tokens_used_optional_default_none(self):
        """tokens_used defaults to None when not provided."""
        r = SearchResult(
            file_path="f.py",
            start_line=1,
            end_line=5,
            snippet="short",
            score=0.5,
            scope="module",
            chunk_id="f.py:1",
        )
        assert r.tokens_used is None


class TestRunEval:
    """Tests for run_eval() using mocked hybrid_search."""

    def _make_store_embedder(self):
        store = MagicMock()
        embedder = MagicMock()
        return store, embedder

    def test_perfect_hit_rate(self):
        """All queries hit → hit_rate=1.0, mrr=1.0."""
        store, embedder = self._make_store_embedder()
        results = [
            _make_result("src/codesight/search.py", start_line=10),
            _make_result("src/other.py", start_line=50),
        ]

        with patch("codesight.search.hybrid_search", return_value=results):
            eq = EvalQuery(query="how does rrf work", expected_file="search.py")
            out = run_eval([eq], store, embedder, top_k=5)

        assert out.hit_rate == 1.0
        assert out.mrr_at_10 == 1.0  # rank 1
        assert out.num_hits == 1

    def test_miss(self):
        """Query with no matching file → hit_rate=0, mrr=0."""
        store, embedder = self._make_store_embedder()
        results = [_make_result("src/other.py", start_line=5)]

        with patch("codesight.search.hybrid_search", return_value=results):
            eq = EvalQuery(query="embedding model", expected_file="embeddings.py")
            out = run_eval([eq], store, embedder, top_k=5)

        assert out.hit_rate == 0.0
        assert out.mrr_at_10 == 0.0
        assert out.num_hits == 0

    def test_mrr_rank_2(self):
        """Correct answer at rank 2 → MRR=0.5."""
        store, embedder = self._make_store_embedder()
        results = [
            _make_result("src/other.py"),  # rank 1 — not matching
            _make_result("src/chunker.py"),  # rank 2 — matches
        ]

        with patch("codesight.search.hybrid_search", return_value=results):
            eq = EvalQuery(query="chunking", expected_file="chunker.py")
            out = run_eval([eq], store, embedder, top_k=5)

        assert out.hit_rate == 1.0
        assert abs(out.mrr_at_10 - 0.5) < 1e-9

    def test_multiple_queries_mixed(self):
        """2 queries: 1 hit, 1 miss → hit_rate=0.5."""
        store, embedder = self._make_store_embedder()
        hit_results = [_make_result("src/search.py")]
        miss_results = [_make_result("src/other.py")]

        call_count = [0]

        def fake_search(*args, **kwargs):
            call_count[0] += 1
            return hit_results if call_count[0] == 1 else miss_results

        with patch("codesight.search.hybrid_search", side_effect=fake_search):
            queries = [
                EvalQuery("rrf merge", expected_file="search.py"),
                EvalQuery("not found query", expected_file="missing.py"),
            ]
            out = run_eval(queries, store, embedder, top_k=5)

        assert out.hit_rate == 0.5
        assert out.num_queries == 2
        assert out.num_hits == 1

    def test_total_tokens_counted(self):
        """total_tokens sums snippet tokens across all queries."""
        store, embedder = self._make_store_embedder()
        snippet = "a" * 100  # 100 chars → 25 tokens via fallback
        results = [_make_result("src/x.py", snippet=snippet)]

        with patch("codesight.search.hybrid_search", return_value=results):
            eq = EvalQuery("query", expected_file="x.py")
            out = run_eval([eq], store, embedder, top_k=5)

        assert out.total_tokens > 0
        assert out.tokens_per_correct_answer > 0

    def test_empty_queries_returns_zero_metrics(self):
        """No queries → all metrics zero."""
        store, embedder = self._make_store_embedder()
        out = run_eval([], store, embedder, top_k=5)
        assert out.hit_rate == 0.0
        assert out.mrr_at_10 == 0.0
        assert out.total_tokens == 0
        assert out.num_queries == 0

    def test_tokens_per_correct_answer_zero_on_all_miss(self):
        """No hits → tokens_per_correct_answer is 0.0 (no division by zero)."""
        store, embedder = self._make_store_embedder()
        results = [_make_result("src/other.py")]

        with patch("codesight.search.hybrid_search", return_value=results):
            eq = EvalQuery("query", expected_file="nonexistent.py")
            out = run_eval([eq], store, embedder, top_k=5)

        assert out.tokens_per_correct_answer == 0.0

    def test_per_query_list_populated(self):
        """per_query list has one entry per query with required keys."""
        store, embedder = self._make_store_embedder()
        results = [_make_result("src/store.py")]

        with patch("codesight.search.hybrid_search", return_value=results):
            eq = EvalQuery("lancedb storage", expected_file="store.py")
            out = run_eval([eq], store, embedder, top_k=5)

        assert len(out.per_query) == 1
        entry = out.per_query[0]
        assert "query" in entry
        assert "hit" in entry
        assert "rr" in entry
        assert "query_tokens" in entry
