"""Regression tests for safe local embedding defaults."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from holusight.config import ServerConfig, _resolve_default_embedding_model


def test_local_default_uses_memory_bounded_qwen_model(monkeypatch) -> None:
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    monkeypatch.delenv("HOLUSIGHT_EMBEDDING_MODEL", raising=False)

    assert _resolve_default_embedding_model() == "Qwen/Qwen3-Embedding-0.6B"
    assert ServerConfig().embedding_model == "Qwen/Qwen3-Embedding-0.6B"


def test_explicit_embedding_model_remains_authoritative(monkeypatch) -> None:
    monkeypatch.setenv("HOLUSIGHT_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-8B")

    assert _resolve_default_embedding_model() == "Qwen/Qwen3-Embedding-8B"
    assert ServerConfig().embedding_model == "Qwen/Qwen3-Embedding-8B"


def test_voyage_default_remains_authoritative_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
    monkeypatch.delenv("HOLUSIGHT_EMBEDDING_MODEL", raising=False)

    assert _resolve_default_embedding_model() == "voyage-code-3"
    assert ServerConfig().embedding_backend == "voyage"


@pytest.mark.parametrize(
    ("max_lines", "overlap_lines", "message"),
    [
        (0, 0, "chunk_max_lines must be greater than 0"),
        (-1, 0, "chunk_max_lines must be greater than 0"),
        (2, -1, "chunk_overlap_lines must be greater than or equal to 0"),
        (2, 2, "chunk_overlap_lines must be less than chunk_max_lines"),
        (2, 3, "chunk_overlap_lines must be less than chunk_max_lines"),
    ],
)
def test_line_window_config_rejects_nonprogressing_values(
    max_lines: int, overlap_lines: int, message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        ServerConfig(chunk_max_lines=max_lines, chunk_overlap_lines=overlap_lines)


@pytest.mark.parametrize(("max_lines", "overlap_lines"), [(1, 0), (2, 1), (20, 5)])
def test_line_window_config_accepts_progressing_values(
    max_lines: int, overlap_lines: int
) -> None:
    config = ServerConfig(
        chunk_max_lines=max_lines,
        chunk_overlap_lines=overlap_lines,
    )

    assert config.chunk_max_lines == max_lines
    assert config.chunk_overlap_lines == overlap_lines
