"""Regression tests for bounded local embedding work."""

from __future__ import annotations

import numpy as np

from codesight import config as config_module
from codesight.api import CodeSight
from codesight.config import ServerConfig
from codesight.embeddings import (
    _MAX_EMBEDDING_BATCH_CHARS,
    _MAX_EMBEDDING_TEXT_CHARS,
    LocalEmbedder,
)


class RecordingSentenceTransformer:
    """Deterministic SentenceTransformer stand-in that records encode inputs."""

    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    def encode(self, texts: list[str], **_kwargs) -> np.ndarray:
        self.batches.append(list(texts))
        return np.array([[len(text), 1.0] for text in texts], dtype=np.float32)


def _recording_embedder() -> tuple[LocalEmbedder, RecordingSentenceTransformer]:
    model = RecordingSentenceTransformer()
    embedder = LocalEmbedder(model_name="sentence-transformers/all-MiniLM-L6-v2", expected_dim=2)
    embedder._model = model
    return embedder, model


def test_long_text_is_segmented_and_character_batched_without_data_loss() -> None:
    embedder, model = _recording_embedder()
    text = "repository-owned material " * 1000

    vectors = embedder.embed([text])

    encoded_segments = [segment for batch in model.batches for segment in batch]
    assert "".join(encoded_segments) == text
    assert all(len(segment) <= _MAX_EMBEDDING_TEXT_CHARS for segment in encoded_segments)
    assert all(
        sum(max(1, len(segment)) for segment in batch) <= _MAX_EMBEDDING_BATCH_CHARS
        for batch in model.batches
    )
    assert vectors.shape == (1, 2)
    np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), [1.0])


def test_default_minilm_sized_text_remains_one_encode_input() -> None:
    embedder, model = _recording_embedder()
    text = "short default MiniLM input"

    vectors = embedder.embed([text])

    assert model.batches == [[text]]
    assert vectors.shape == (1, 2)


def test_codesight_index_routes_a_pathological_single_line_through_the_guard(
    tmp_path, monkeypatch,
) -> None:
    """Exercise CodeSight.index -> indexer -> LocalEmbedder for the prior trigger."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    pathological_text = "repository-owned material " * 1000
    (corpus / "single-long-line.txt").write_text(pathological_text, encoding="utf-8")
    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "data")

    embedder, model = _recording_embedder()
    monkeypatch.setattr("codesight.indexer.get_embedder", lambda *_args, **_kwargs: embedder)
    engine = CodeSight(
        corpus,
        config=ServerConfig(
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            embedding_backend="local",
            embedding_dim=2,
            reranker=False,
        ),
    )

    stats = engine.index(force_rebuild=True)

    assert stats.chunks_created == 1
    assert "".join(segment for batch in model.batches for segment in batch) == (
        "# File: single-long-line.txt\n# Scope: repository-owned\n# Lines: 1-1\n"
        + pathological_text
    )
    assert all(
        sum(max(1, len(segment)) for segment in batch) <= _MAX_EMBEDDING_BATCH_CHARS
        for batch in model.batches
    )
