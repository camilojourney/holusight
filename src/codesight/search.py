"""Hybrid search: BM25 + vector + RRF + optional cross-encoder reranking.

Pipeline:
  query → BM25 top N → ┐
                        ├→ RRF merge → top N → [reranker] → top K
  query → Vector top N → ┘
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from .config import (
    BM25_CANDIDATE_MULTIPLIER,
    DEFAULT_QUERY_ENHANCEMENT,
    DEFAULT_RERANKER_BACKEND,
    DEFAULT_RERANKER_ENABLED,
    DEFAULT_RERANKER_MODEL,
    DEFAULT_RERANKER_TOP_N,
    DEFAULT_TOP_K,
    VOYAGE_API_KEY,
    ServerConfig,
)
from .embeddings import Embedder, get_embedder
from .store import ChunkStore
from .types import SearchResult

logger = logging.getLogger(__name__)


def vprf_enhance_query(
    query_vector: np.ndarray,
    feedback_vectors: list[np.ndarray],
    query_weight: float = 0.8,
) -> np.ndarray:
    """Vector Pseudo-Relevance Feedback: blend query with top-retrieved document vectors.

    Improves recall by ~1-2% nDCG@10 with <5ms overhead and no hallucination risk.
    Formula: enhanced = 0.8 * query + 0.2 * mean(top_3_feedback), then L2-normalize.
    """
    if not feedback_vectors:
        return query_vector.astype(np.float32)
    top_k = min(3, len(feedback_vectors))
    feedback = np.mean(np.stack(feedback_vectors[:top_k]), axis=0)
    enhanced = query_weight * query_vector + (1.0 - query_weight) * feedback
    norm = np.linalg.norm(enhanced)
    if norm > 0:
        enhanced = enhanced / norm
    return enhanced.astype(np.float32)


def rrf_merge(
    ranked_lists: list[list[str]],
    k: int = 60,
) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion across multiple ranked ID lists.

    Returns [(chunk_id, rrf_score)] sorted by score descending.
    The constant k controls how much we penalize low-ranked items.
    k=60 is the standard value from the original RRF paper.
    """
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


# ---------------------------------------------------------------------------
# Voyage reranker (API — preferred when VOYAGE_API_KEY is set)
# ---------------------------------------------------------------------------

_voyage_reranker_client = None


def _get_voyage_client():
    """Lazy-load the Voyage AI client (cached for process lifetime)."""
    global _voyage_reranker_client
    if _voyage_reranker_client is None:
        import voyageai
        _voyage_reranker_client = voyageai.Client(api_key=VOYAGE_API_KEY)
    return _voyage_reranker_client


def _rerank_voyage(
    query: str,
    results: list[SearchResult],
    top_k: int,
    model_name: str,
) -> list[SearchResult]:
    """Rerank results using the Voyage AI reranker API.

    Sends (query, documents) to voyage rerank-2, maps scores back to
    original SearchResult objects, and returns the top K sorted by score.
    """
    if not results:
        return results

    client = _get_voyage_client()
    documents = [r.snippet for r in results]

    try:
        response = client.rerank(
            query=query,
            documents=documents,
            model=model_name,
            top_k=min(top_k, len(results)),
        )
    except Exception:
        logger.exception("Voyage reranker failed — falling back to RRF order")
        return results[:top_k]

    reranked: list[SearchResult] = []
    for item in response.results:
        if item.index >= len(results):
            logger.warning("Voyage reranker returned invalid index %d", item.index)
            continue
        result = results[item.index]
        result.score = round(float(item.relevance_score), 6)
        reranked.append(result)

    return reranked


# ---------------------------------------------------------------------------
# Cross-encoder reranker (local fallback — no API key required)
# ---------------------------------------------------------------------------

_reranker_model = None


def _get_reranker(model_name: str):
    """Lazy-load the cross-encoder model (cached for process lifetime)."""
    global _reranker_model
    if _reranker_model is None:
        logger.info("Loading reranker model: %s", model_name)
        from sentence_transformers import CrossEncoder
        _reranker_model = CrossEncoder(model_name)
    return _reranker_model


def _rerank_local(
    query: str,
    results: list[SearchResult],
    top_k: int,
    model_name: str,
) -> list[SearchResult]:
    """Rerank results using a local cross-encoder model.

    Scores each (query, chunk_content) pair, re-sorts by score,
    and returns the top K.
    """
    if not results:
        return results

    reranker = _get_reranker(model_name)
    pairs = [(query, r.snippet) for r in results]
    scores = reranker.predict(pairs)

    for result, score in zip(results, scores):
        result.score = round(float(score), 6)

    reranked = sorted(results, key=lambda r: r.score, reverse=True)
    return reranked[:top_k]


def _rerank(
    query: str,
    results: list[SearchResult],
    top_k: int,
    model_name: str,
    backend: str = "local",
) -> list[SearchResult]:
    """Route reranking to voyage API or local cross-encoder based on backend."""
    if backend == "voyage":
        logger.debug("Reranking with Voyage API: %s", model_name)
        return _rerank_voyage(query, results, top_k, model_name)
    logger.debug("Reranking with local cross-encoder: %s", model_name)
    return _rerank_local(query, results, top_k, model_name)


# ---------------------------------------------------------------------------
# Metadata boosting
# ---------------------------------------------------------------------------

_METADATA_BOOST_STOPWORDS: frozenset[str] = frozenset({
    "how", "does", "what", "the", "is", "in", "for", "of", "a", "an", "to",
    "do", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "it", "its", "this", "that", "and", "or", "not", "with", "from", "by",
    "on", "at", "as", "i", "we", "you", "he", "she", "they", "my", "our",
    "can", "could", "would", "should", "may", "might", "will", "shall",
})


def _reorder_by_filename_match(
    chunk_ids: list[str],
    query: str,
    metadatas: dict[str, dict],
) -> list[str]:
    """Promote chunks from filename-matching files to the top of the list.

    Extracts non-stopword query tokens (>= 3 chars), then checks if any token
    is a substring of the filename stem or immediate parent directory. Matching
    chunks are moved to the front; order within each group is preserved.

    This is a stable re-ordering (not a score change), so the cross-encoder
    reranker can still override it when enabled.
    """
    tokens = {
        t.lower() for t in query.split()
        if t.lower() not in _METADATA_BOOST_STOPWORDS and len(t) >= 3
    }
    if not tokens:
        return chunk_ids

    boosted: list[str] = []
    rest: list[str] = []

    for cid in chunk_ids:
        meta = metadatas.get(cid)
        if meta is None:
            rest.append(cid)
            continue
        file_path = meta.get("file_path", "")
        p = Path(file_path)
        stem = p.stem.lower()
        parent = p.parent.name.lower()

        if any(token in stem or token in parent for token in tokens):
            boosted.append(cid)
        else:
            rest.append(cid)

    return boosted + rest


# ---------------------------------------------------------------------------
# Main search function
# ---------------------------------------------------------------------------


def hybrid_search(
    store: ChunkStore,
    embedder: Embedder,
    query: str,
    top_k: int = DEFAULT_TOP_K,
    file_glob: str | None = None,
    code_embedder: Embedder | None = None,
    config: ServerConfig | None = None,
) -> list[SearchResult]:
    """Run hybrid BM25 + vector search with RRF merging.

    Steps:
    1. Embed the query
    2. Run vector search (top candidates)
    3. Run BM25 search (top candidates)
    4. Merge with RRF
    5. (Optional) Rerank with cross-encoder
    6. Fetch metadata and build SearchResult objects
    """
    reranker_enabled = config.reranker if config else DEFAULT_RERANKER_ENABLED
    reranker_top_n = config.reranker_top_n if config else DEFAULT_RERANKER_TOP_N
    reranker_model = (
        config.reranker_model if config
        else DEFAULT_RERANKER_MODEL
    )
    reranker_backend = config.reranker_backend if config else DEFAULT_RERANKER_BACKEND
    query_enhancement = config.query_enhancement if config else DEFAULT_QUERY_ENHANCEMENT
    metadata_boost = config.metadata_boost if config else True

    candidate_count = top_k * BM25_CANDIDATE_MULTIPLIER

    # If reranker is on, fetch more candidates for RRF so the reranker
    # has a richer pool to re-sort.
    rrf_top = reranker_top_n if reranker_enabled else top_k

    # 1. Embed query
    query_vector = embedder.embed_query(query)

    # 2. Vector search
    vec_ids = store.vector_search(
        query_vector, top_k=candidate_count, file_glob=file_glob,
    )
    logger.debug("Vector search returned %d candidates", len(vec_ids))

    # 2a. VPRF: refine query vector using top retrieved document vectors
    if query_enhancement and vec_ids:
        feedback_vecs = store.get_chunk_vectors(vec_ids[:3])
        if feedback_vecs:
            query_vector = vprf_enhance_query(query_vector, feedback_vecs)
            vec_ids = store.vector_search(
                query_vector, top_k=candidate_count, file_glob=file_glob,
            )
            logger.debug("VPRF re-search returned %d candidates", len(vec_ids))

    code_vec_ids: list[str] = []
    if code_embedder is None and VOYAGE_API_KEY and store.code_lance_table is not None:
        code_embedder = get_embedder("voyage-code-3", 1024, backend="voyage")

    if code_embedder is not None and store.code_lance_table is not None:
        code_query_vector = code_embedder.embed_query(query)
        code_vec_ids = store.vector_search_code(
            code_query_vector,
            top_k=candidate_count,
            file_glob=file_glob,
        )
        logger.debug("Code vector search returned %d candidates", len(code_vec_ids))

    # 3. BM25 search
    bm25_ids = store.bm25_search(
        query, top_k=candidate_count, file_glob=file_glob,
    )
    logger.debug("BM25 search returned %d candidates", len(bm25_ids))

    # 4. RRF merge
    ranked_lists = [ranked for ranked in [vec_ids, bm25_ids, code_vec_ids] if ranked]
    if not ranked_lists:
        return []

    merged = rrf_merge(ranked_lists)
    top_chunk_ids = [cid for cid, _ in merged[:rrf_top]]
    score_map = dict(merged[:rrf_top])

    # 5. Fetch metadata and build results
    metadatas = store.get_chunk_metadata(top_chunk_ids)

    # 5a. Metadata boost: re-order top_chunk_ids so that chunks from files whose
    # name matches a query token are promoted to the front of the list. This
    # affects the final order when the reranker is off, and gives the reranker
    # better-ranked input when it is on.
    if metadata_boost:
        top_chunk_ids = _reorder_by_filename_match(top_chunk_ids, query, metadatas)

    results: list[SearchResult] = []
    for cid in top_chunk_ids:
        meta = metadatas.get(cid)
        if meta is None:
            continue
        snippet = meta["content"]
        if len(snippet) > 1500:
            snippet = snippet[:1500] + "\n... (truncated)"

        results.append(SearchResult(
            file_path=meta["file_path"],
            start_line=meta["start_line"],
            end_line=meta["end_line"],
            snippet=snippet,
            score=round(score_map.get(cid, 0.0), 6),
            scope=meta["scope"],
            chunk_id=cid,
            tokens_used=len(snippet) // 4,
        ))

    # 6. Rerank (optional)
    if reranker_enabled and len(results) > 1:
        logger.debug(
            "Reranking %d results with %s (backend=%s)",
            len(results), reranker_model, reranker_backend,
        )
        results = _rerank(query, results, top_k, reranker_model, backend=reranker_backend)
    else:
        results = results[:top_k]

    return results
