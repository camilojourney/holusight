"""Embedding model wrapper — local (sentence-transformers) or API (OpenAI).

Backend is selected via CODESIGHT_EMBEDDING_BACKEND env var:
  - local  (default) — runs on CPU/GPU, no API key, no data leaves
  - api    — OpenAI text-embedding-3-large, best quality
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
        """Embed a list of texts, returning an (N, dim) float32 array."""
        if not texts:
            return np.empty((0, self.expected_dim), dtype=np.float32)
        embeddings = self.model.encode(
            texts,
            show_progress_bar=len(texts) > 100,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return embeddings.astype(np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        """Embed a single query string, returning a (dim,) float32 array."""
        return self.embed([query])[0]


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
                "Set it or switch to local: CODESIGHT_EMBEDDING_BACKEND=local"
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

    BATCH_SIZE = 8  # Voyage max is 120K tokens/batch; large repos need small batches (~15K tokens each)

    def __init__(
        self,
        model_name: str = "voyage-code-3",
        expected_dim: int = 1024,
    ) -> None:
        self._api_key = VOYAGE_API_KEY
        if not self._api_key:
            raise ValueError(
                "VOYAGE_API_KEY environment variable is required for the voyage embedding "
                "backend."
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

    logger.info("Using local embedding backend: %s", model_name)
    return LocalEmbedder(model_name=model_name, expected_dim=dim)

