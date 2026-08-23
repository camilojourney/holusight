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


class TestRecallNdcgEvidenceLatency:
    """Tests for the generalized metrics added alongside hit_rate/MRR."""

    def _make_store_embedder(self):
        return MagicMock(), MagicMock()

    def test_recall_at_k_reflects_hit_rank(self):
        """Hit at rank 3 counts toward recall@5 and recall@10 but not recall@1."""
        store, embedder = self._make_store_embedder()
        results = [
            _make_result("src/other.py"),
            _make_result("src/other2.py"),
            _make_result("src/search.py"),  # rank 3
        ]
        with patch("codesight.search.hybrid_search", return_value=results):
            eq = EvalQuery("rrf", expected_file="search.py")
            out = run_eval([eq], store, embedder, top_k=5, k_values=(1, 5, 10))

        assert out.recall_at_k[1] == 0.0
        assert out.recall_at_k[5] == 1.0
        assert out.recall_at_k[10] == 1.0

    def test_ndcg_rank_1_is_perfect(self):
        store, embedder = self._make_store_embedder()
        results = [_make_result("src/search.py")]
        with patch("codesight.search.hybrid_search", return_value=results):
            eq = EvalQuery("rrf", expected_file="search.py")
            out = run_eval([eq], store, embedder, top_k=5)
        assert out.ndcg_at_10 == 1.0

    def test_ndcg_zero_on_miss(self):
        store, embedder = self._make_store_embedder()
        results = [_make_result("src/other.py")]
        with patch("codesight.search.hybrid_search", return_value=results):
            eq = EvalQuery("rrf", expected_file="missing.py")
            out = run_eval([eq], store, embedder, top_k=5)
        assert out.ndcg_at_10 == 0.0

    def test_evidence_completeness_multi_file_gold(self):
        """Partial evidence coverage yields a fractional completeness score."""
        store, embedder = self._make_store_embedder()
        results = [_make_result("src/a.py"), _make_result("src/c.py")]
        with patch("codesight.search.hybrid_search", return_value=results):
            eq = EvalQuery(
                "impact of X", expected_file="a.py",
                expected_evidence=["a.py", "b.py", "c.py"],
            )
            out = run_eval([eq], store, embedder, top_k=5)
        assert abs(out.evidence_completeness - (2 / 3)) < 1e-9

    def test_evidence_completeness_defaults_to_expected_file(self):
        store, embedder = self._make_store_embedder()
        results = [_make_result("src/search.py")]
        with patch("codesight.search.hybrid_search", return_value=results):
            eq = EvalQuery("rrf", expected_file="search.py")
            out = run_eval([eq], store, embedder, top_k=5)
        assert out.evidence_completeness == 1.0

    def test_latency_recorded_per_query(self):
        store, embedder = self._make_store_embedder()
        results = [_make_result("src/search.py")]
        with patch("codesight.search.hybrid_search", return_value=results):
            eq = EvalQuery("rrf", expected_file="search.py")
            out = run_eval([eq], store, embedder, top_k=5)
        assert out.avg_latency_ms >= 0.0
        assert "latency_ms" in out.per_query[0]

    def test_diagnostic_probe_excluded_from_aggregates(self):
        """NO_MATCH_SENTINEL queries are diagnostic-only: they don't count
        toward hit_rate/recall/mrr/ndcg/evidence_completeness."""
        from tests.eval_harness import NO_MATCH_SENTINEL

        store, embedder = self._make_store_embedder()
        graded_hit = [_make_result("src/search.py")]
        probe_results = [_make_result("src/random.py")]

        call_count = [0]

        def fake_search(*args, **kwargs):
            call_count[0] += 1
            return graded_hit if call_count[0] == 1 else probe_results

        with patch("codesight.search.hybrid_search", side_effect=fake_search):
            queries = [
                EvalQuery("rrf", expected_file="search.py"),
                EvalQuery("kubernetes helm chart", expected_file=NO_MATCH_SENTINEL),
            ]
            out = run_eval(queries, store, embedder, top_k=5)

        assert out.num_graded == 1
        assert out.num_diagnostic_probes == 1
        assert out.hit_rate == 1.0  # only the graded query counts
        diag_entry = [e for e in out.per_query if e.get("diagnostic_only")][0]
        assert diag_entry["top_result_file"] == "src/random.py"
        assert "hit" not in diag_entry


class TestPluggableSearchFn:
    """Tests that run_eval() can score an arbitrary retriever, not just
    the production hybrid_search."""

    def _make_store_embedder(self):
        return MagicMock(), MagicMock()

    def test_custom_search_fn_is_used_instead_of_hybrid_search(self):
        store, embedder = self._make_store_embedder()
        custom_results = [_make_result("src/custom.py")]

        def fake_baseline(store_, embedder_, query, top_k, config):
            return custom_results

        with patch("codesight.search.hybrid_search") as mock_hybrid:
            eq = EvalQuery("anything", expected_file="custom.py")
            out = run_eval([eq], store, embedder, top_k=5, search_fn=fake_baseline)

        mock_hybrid.assert_not_called()
        assert out.hit_rate == 1.0

    def test_search_fn_receives_positional_args(self):
        store, embedder = self._make_store_embedder()
        received = {}

        def capturing_fn(store_, embedder_, query, top_k, config):
            received["store"] = store_
            received["embedder"] = embedder_
            received["query"] = query
            received["top_k"] = top_k
            received["config"] = config
            return []

        eq = EvalQuery("some query", expected_file="x.py")
        run_eval([eq], store, embedder, top_k=7, config="cfg-sentinel", search_fn=capturing_fn)

        assert received["store"] is store
        assert received["embedder"] is embedder
        assert received["query"] == "some query"
        assert received["top_k"] == 7
        assert received["config"] == "cfg-sentinel"
