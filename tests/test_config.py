"""Regression tests for safe local embedding defaults."""

from __future__ import annotations

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
