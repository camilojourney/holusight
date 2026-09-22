"""Regression tests for bounded local embedding work."""

from __future__ import annotations

import numpy as np

from holusight import config as config_module
from holusight.api import Holusight
from holusight.config import ServerConfig
from holusight.embeddings import (
    _MAX_EMBEDDING_BATCH_CHARS,
    _MAX_EMBEDDING_TEXT_CHARS,
    LocalEmbedder,
)


class RecordingSentenceTransformer:
    """Deterministic SentenceTransformer stand-in that records encode inputs.

    ``prompts`` mirrors the real sentence-transformers attribute: an empty
    dict for a model with no named prompts (all-MiniLM-L6-v2, nomic,
    mxbai), or e.g. ``{"query": "Instruct: ...\\nQuery:"}`` for a model
    like Qwen3-Embedding that defines an asymmetric query prompt.
    """

    def __init__(self, prompts: dict[str, str] | None = None) -> None:
        self.batches: list[list[str]] = []
        self.encode_kwargs: list[dict] = []
        self.prompts = prompts or {}

    def encode(self, texts: list[str], **kwargs) -> np.ndarray:
        self.batches.append(list(texts))
        self.encode_kwargs.append(kwargs)
        return np.array([[len(text), 1.0] for text in texts], dtype=np.float32)


def _recording_embedder(
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    prompts: dict[str, str] | None = None,
) -> tuple[LocalEmbedder, RecordingSentenceTransformer]:
    model = RecordingSentenceTransformer(prompts=prompts)
    embedder = LocalEmbedder(model_name=model_name, expected_dim=2)
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


class TestQueryPrompting:
    def test_query_gets_prompt_name_when_model_defines_one(self) -> None:
        embedder, model = _recording_embedder(
            model_name="Qwen/Qwen3-Embedding-0.6B",
            prompts={"query": "Instruct: Given a query, retrieve relevant text.\nQuery:"},
        )

        embedder.embed_query("why did I turn down the second offer")

        assert model.encode_kwargs == [{
            "show_progress_bar": False,
            "convert_to_numpy": True,
            "normalize_embeddings": True,
            "prompt_name": "query",
        }]

    def test_query_gets_no_prompt_name_when_model_defines_none(self) -> None:
        embedder, model = _recording_embedder()  # default: no prompts, like all-MiniLM

        embedder.embed_query("why did I turn down the second offer")

        assert "prompt_name" not in model.encode_kwargs[0]

    def test_indexing_documents_never_gets_the_query_prompt(self) -> None:
        embedder, model = _recording_embedder(
            model_name="Qwen/Qwen3-Embedding-0.6B",
            prompts={"query": "Instruct: ...\nQuery:"},
        )

        embedder.embed(["a document chunk, not a query"])

        assert "prompt_name" not in model.encode_kwargs[0]

    def test_query_embedding_is_bounded_like_documents(self) -> None:
        embedder, model = _recording_embedder()
        pathological_query = "x" * (_MAX_EMBEDDING_TEXT_CHARS * 3)

        embedder.embed_query(pathological_query)

        assert len(model.batches[0][0]) == _MAX_EMBEDDING_TEXT_CHARS


def test_holusight_index_routes_a_pathological_single_line_through_the_guard(
    tmp_path, monkeypatch,
) -> None:
    """Exercise Holusight.index -> indexer -> LocalEmbedder for the prior trigger."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    pathological_text = "repository-owned material " * 1000
    (corpus / "single-long-line.txt").write_text(pathological_text, encoding="utf-8")
    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "data")

    embedder, model = _recording_embedder()
    monkeypatch.setattr("holusight.indexer.get_embedder", lambda *_args, **_kwargs: embedder)
    engine = Holusight(
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
