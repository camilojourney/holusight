"""Embedding model wrapper — local (sentence-transformers), or API (OpenAI
or Voyage AI).

Backend is selected via HOLUSIGHT_EMBEDDING_BACKEND env var:
  - local  (default) — runs on CPU/GPU/MPS, no API key, no data leaves.
             HOLUSIGHT_EMBEDDING_MODEL picks the model (default
             Qwen/Qwen3-Embedding-8B; see config.EMBEDDING_MODEL_REGISTRY).
  - api    — OpenAI text-embedding-3-large
  - voyage — Voyage AI voyage-code-3 (also the automatic default whenever
             VOYAGE_API_KEY is set, regardless of this env var)
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Protocol

import numpy as np

from .config import (
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_EMBEDDING_MODEL,
    VOYAGE_API_KEY,
    resolve_embedding_dim,
)

logger = logging.getLogger(__name__)

# SentenceTransformer tokenizes an entire input before applying a model's sequence
# limit. Bound text and encode batches by characters first so one pathological
# line cannot turn a local index into an unbounded tokenizer/attention workload.
_MAX_EMBEDDING_TEXT_CHARS = 16_384
_MAX_EMBEDDING_BATCH_CHARS = 16_384


def _bound_texts(texts: list[str]) -> list[str]:
    """SEC-007: apply the same per-text character bound LocalEmbedder already
    uses to every embedding backend. Without this, the OpenAI and Voyage
    paths sent chunk text to a remote API with no character/token bound,
    so a large number of allowed files or pathological content could
    consume excessive provider quota, request size, or cost."""
    return [
        text if len(text) <= _MAX_EMBEDDING_TEXT_CHARS else text[:_MAX_EMBEDDING_TEXT_CHARS]
        for text in texts
    ]


class Embedder(Protocol):
    """Protocol for embedding backends."""

    model_name: str
    expected_dim: int

    def embed(self, texts: list[str]) -> np.ndarray: ...
    def embed_query(self, query: str) -> np.ndarray: ...


def _normalize_rows(vectors: np.ndarray) -> np.ndarray:
    """Normalize embedding rows for cosine similarity search."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return vectors / norms


# ---------------------------------------------------------------------------
# Local backend (sentence-transformers)
# ---------------------------------------------------------------------------


class LocalEmbedder:
    """Wraps a sentence-transformers model for embedding.

    The model is lazily loaded on first use and cached for the process lifetime.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        expected_dim: int = DEFAULT_EMBEDDING_DIM,
    ) -> None:
        self.model_name = model_name
        self.expected_dim = expected_dim
        self._model = None

    @property
    def model(self):
        """Lazy-load the model on first access."""
        if self._model is None:
            logger.info("Loading embedding model: %s", self.model_name)
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name, trust_remote_code=True)
            actual_dim = self._model.get_sentence_embedding_dimension()
            if actual_dim != self.expected_dim:
                logger.warning(
                    "Model dimension %d != expected %d. Updating.",
                    actual_dim,
                    self.expected_dim,
                )
                self.expected_dim = actual_dim
        return self._model

    def embed(self, texts: list[str]) -> np.ndarray:
        """Embed texts with deterministic per-text and per-call character bounds.

        Long inputs are segmented without dropping content. Segment vectors are
        mean-pooled per original input and normalized, preserving one vector per
        caller-provided text while bounding tokenizer and attention work.
        """
        if not texts:
            return np.empty((0, self.expected_dim), dtype=np.float32)

        segments: list[tuple[int, str]] = []
        for text_index, text in enumerate(texts):
            text_segments = [
                text[offset : offset + _MAX_EMBEDDING_TEXT_CHARS]
                for offset in range(0, len(text), _MAX_EMBEDDING_TEXT_CHARS)
            ] or [""]
            segments.extend((text_index, segment) for segment in text_segments)

        per_text_vectors: list[list[np.ndarray]] = [[] for _ in texts]
        batch: list[tuple[int, str]] = []
        batch_chars = 0
        for segment in segments:
            segment_chars = max(1, len(segment[1]))
            if batch and batch_chars + segment_chars > _MAX_EMBEDDING_BATCH_CHARS:
                self._embed_segment_batch(batch, per_text_vectors)
                batch = []
                batch_chars = 0
            batch.append(segment)
            batch_chars += segment_chars
        if batch:
            self._embed_segment_batch(batch, per_text_vectors)

        pooled = np.vstack([
            np.mean(vectors, axis=0) for vectors in per_text_vectors
        ])
        return _normalize_rows(pooled).astype(np.float32)

    def _embed_segment_batch(
        self,
        batch: list[tuple[int, str]],
        per_text_vectors: list[list[np.ndarray]],
    ) -> None:
        """Embed one character-bounded batch and associate vectors to inputs."""
        vectors = self.model.encode(
            [text for _, text in batch],
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        for (text_index, _), vector in zip(batch, vectors, strict=True):
            per_text_vectors[text_index].append(vector)

    def embed_query(self, query: str) -> np.ndarray:
        """Embed a single query string, returning a (dim,) float32 array.

        Applies the model's own "query" prompt when it defines one --
        asymmetric query/document prompting (the query gets an instruction
        prefix, the document does not) is how models like Qwen3-Embedding
        expect to be used, and materially improves retrieval quality for
        them. It is a silent no-op for a model with no ``prompts`` dict
        (all-MiniLM-L6-v2, nomic, mxbai): sentence-transformers exposes an
        empty dict there, never an error, so this never special-cases a
        specific model name.
        """
        bounded = _bound_texts([query])
        encode_kwargs: dict = {
            "show_progress_bar": False,
            "convert_to_numpy": True,
            "normalize_embeddings": True,
        }
        if "query" in getattr(self.model, "prompts", {}):
            encode_kwargs["prompt_name"] = "query"
        vector = self.model.encode(bounded, **encode_kwargs)[0]
        return np.asarray(vector, dtype=np.float32)


# ---------------------------------------------------------------------------
# API backend (OpenAI)
# ---------------------------------------------------------------------------


class APIEmbedder:
    """OpenAI embedding API backend — best quality, requires API key."""

    def __init__(
        self,
        model_name: str = "text-embedding-3-large",
        expected_dim: int = 3072,
    ) -> None:
        self._api_key = os.environ.get("OPENAI_API_KEY")
        if not self._api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable is required for API embedding backend. "
                "Set it or switch to local: HOLUSIGHT_EMBEDDING_BACKEND=local"
            )
        self.model_name = model_name
        self.expected_dim = expected_dim
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self._api_key, timeout=30)
        return self._client

    def embed(self, texts: list[str]) -> np.ndarray:
        """Embed texts via OpenAI API in batches of 512."""
        if not texts:
            return np.empty((0, self.expected_dim), dtype=np.float32)

        texts = _bound_texts(texts)
        all_embeddings = []
        batch_size = 512

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = self.client.embeddings.create(
                model=self.model_name,
                input=batch,
            )
            batch_vecs = [item.embedding for item in response.data]
            all_embeddings.extend(batch_vecs)

        result = np.array(all_embeddings, dtype=np.float32)
        return _normalize_rows(result)

    def embed_query(self, query: str) -> np.ndarray:
        """Embed a single query string."""
        return self.embed([query])[0]


class VoyageEmbedder:
    """Voyage embedding backend for code retrieval."""

    # Voyage max is 120K tokens/batch; large repos need small batches.
    BATCH_SIZE = 8

    def __init__(
        self,
        model_name: str = "voyage-code-3",
        expected_dim: int = 1024,
    ) -> None:
        self._api_key = VOYAGE_API_KEY
        if not self._api_key:
            raise ValueError(
                "VOYAGE_API_KEY environment variable is required for the voyage embedding backend."
            )
        self.model_name = model_name
        self.expected_dim = expected_dim
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import voyageai

            self._client = voyageai.Client(api_key=self._api_key)
        return self._client

    def _embed_with_input_type(self, texts: list[str], input_type: str) -> np.ndarray:
        if not texts:
            return np.empty((0, self.expected_dim), dtype=np.float32)

        texts = _bound_texts(texts)
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i : i + self.BATCH_SIZE]
            response = self.client.embed(
                batch,
                model=self.model_name,
                input_type=input_type,
            )
            all_embeddings.extend(response.embeddings)

        result = np.array(all_embeddings, dtype=np.float32)
        if result.shape[1] != self.expected_dim:
            logger.warning(
                "Model dimension %d != expected %d. Updating.",
                result.shape[1],
                self.expected_dim,
            )
            self.expected_dim = result.shape[1]
        return _normalize_rows(result)

    def embed(self, texts: list[str]) -> np.ndarray:
        """Embed code/document chunks for indexing."""
        return self._embed_with_input_type(texts, input_type="document")

    def embed_query(self, query: str) -> np.ndarray:
        """Embed a single query for code search."""
        return self._embed_with_input_type([query], input_type="query")[0]


# ---------------------------------------------------------------------------
# Daemon-backed local backend
# ---------------------------------------------------------------------------


class DaemonEmbedder:
    """Local Embedder that proxies to a persistent background daemon
    (embedding_daemon.py) instead of loading the model in this process.

    `holus` is a stateless CLI -- without this, every invocation would
    pay the full model-load cost (seconds for a small model, ~12s+ for
    Qwen3-Embedding-8B measured on real hardware) on every single query,
    with no way for in-process caching to help since the process exits
    after each command.

    Transparently falls back to an in-process LocalEmbedder, lazily
    constructed only if actually needed, whenever the daemon is
    unreachable or errors -- a query never fails or blocks because of
    this class, it just runs at in-process (cold-load) speed instead of
    daemon (warm) speed, exactly as if this class didn't exist.
    """

    def __init__(self, model_name: str, expected_dim: int) -> None:
        self.model_name = model_name
        self.expected_dim = expected_dim
        self._fallback: LocalEmbedder | None = None

    def _fallback_embedder(self) -> LocalEmbedder:
        if self._fallback is None:
            self._fallback = LocalEmbedder(
                model_name=self.model_name, expected_dim=self.expected_dim,
            )
        return self._fallback

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.expected_dim), dtype=np.float32)

        from . import embedding_daemon

        vectors = embedding_daemon.call_daemon(self.model_name, self.expected_dim, "embed", texts)
        if vectors is not None:
            return np.array(vectors, dtype=np.float32)
        embedding_daemon.ensure_daemon_spawned()
        return self._fallback_embedder().embed(texts)

    def embed_query(self, query: str) -> np.ndarray:
        from . import embedding_daemon

        vectors = embedding_daemon.call_daemon(
            self.model_name, self.expected_dim, "embed_query", [query],
        )
        if vectors is not None:
            return np.array(vectors[0], dtype=np.float32)
        embedding_daemon.ensure_daemon_spawned()
        return self._fallback_embedder().embed_query(query)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


@lru_cache(maxsize=4)
def get_embedder(
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    expected_dim: int = DEFAULT_EMBEDDING_DIM,
    backend: str = "local",
) -> Embedder:
    """Return a cached Embedder singleton.

    Args:
        model_name: Model identifier from the registry or a custom HuggingFace model.
        expected_dim: Expected embedding dimension.
        backend: 'local' for sentence-transformers, 'api' for OpenAI, 'voyage' for VoyageAI.
    """
    if expected_dim != DEFAULT_EMBEDDING_DIM:
        dim = expected_dim
    else:
        dim = resolve_embedding_dim(model_name)

    if backend == "api":
        logger.info("Using API embedding backend: %s", model_name)
        return APIEmbedder(model_name=model_name, expected_dim=dim)
    if backend == "voyage":
        logger.info("Using Voyage embedding backend: %s", model_name)
        return VoyageEmbedder(model_name=model_name, expected_dim=dim)

    if os.environ.get("HOLUSIGHT_DAEMON_DISABLED", "").lower() in ("1", "true"):
        logger.info("Using local embedding backend (daemon disabled): %s", model_name)
        return LocalEmbedder(model_name=model_name, expected_dim=dim)

    logger.info("Using local embedding backend (daemon-backed): %s", model_name)
    return DaemonEmbedder(model_name=model_name, expected_dim=dim)
