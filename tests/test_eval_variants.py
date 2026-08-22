"""Tests for eval_variants.py — the opt-in embedding-model variant runner.

These tests exercise the guardrails (never touch the process default model,
never auto-invoke, cost left unknown unless a price is supplied) and the
usage-instrumentation wrapper without requiring network access: the "variant"
under test is always the local sentence-transformers default, so no API key
or download is exercised beyond what's already cached for the rest of the
suite.
"""

from __future__ import annotations

import numpy as np
import pytest

from codesight.config import DEFAULT_EMBEDDING_MODEL
from tests.eval_harness import EvalQuery
from tests.eval_variants import EmbeddingVariantSpec, _InstrumentedEmbedder, run_variant_eval


class _FakeEmbedder:
    """Deterministic stand-in — avoids loading a real model in this test."""

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.zeros((len(texts), 4), dtype=np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        return np.zeros(4, dtype=np.float32)


class TestInstrumentedEmbedder:
    def test_delegates_and_counts_query_calls(self):
        wrapped = _InstrumentedEmbedder(_FakeEmbedder())
        wrapped.embed_query("hello world")
        wrapped.embed_query("second query")

        assert wrapped.usage.query_calls == 2
        assert wrapped.usage.texts_embedded == 2
        assert wrapped.usage.estimated_tokens >= 2  # len//4, floor 1 each

    def test_delegates_and_counts_document_calls(self):
        wrapped = _InstrumentedEmbedder(_FakeEmbedder())
        wrapped.embed(["chunk one text", "chunk two text", "chunk three"])

        assert wrapped.usage.document_calls == 1
        assert wrapped.usage.texts_embedded == 3

    def test_result_shape_unchanged(self):
        wrapped = _InstrumentedEmbedder(_FakeEmbedder())
        result = wrapped.embed(["a", "b"])
        assert result.shape == (2, 4)


class TestEmbeddingVariantSpec:
    def test_requires_explicit_model_and_backend(self):
        # No default constructor — every field must come from the caller.
        with pytest.raises(TypeError):
            EmbeddingVariantSpec()  # type: ignore[call-arg]

        spec = EmbeddingVariantSpec(model_name="some-model", backend="local")
        assert spec.model_name == "some-model"
        assert spec.price_per_1k_input is None


@pytest.fixture(autouse=True)
def _isolated_codesight_data_dir(tmp_path, monkeypatch):
    """Redirect codesight's data directory into pytest's tmp_path for every
    test in this module, so these tests never write into a developer's real
    ~/.codesight/data cache — mirrors the isolation eval_variants.py's CLI
    gets for free via CODESIGHT_DATA_DIR (which only takes effect before
    `codesight` is first imported; in-process tests need this instead)."""
    from codesight import config as config_module

    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "codesight_data_isolated")


class TestRunVariantEvalGuardrails:
    """Full-weight integration test: builds a tiny isolated local index and
    runs one query through it, using the repo's already-indexed default
    model so no network/model download is required."""

    def test_isolated_run_does_not_change_process_default_model(self, tmp_path):
        (tmp_path / "a.py").write_text("def needle_function():\n    return 42\n")

        variant = EmbeddingVariantSpec(model_name=DEFAULT_EMBEDDING_MODEL, backend="local")
        queries = [EvalQuery(query="needle_function", expected_file="a.py", family="exact_lookup")]

        payload = run_variant_eval(queries, tmp_path, variant, top_k=5)

        assert payload["guardrail"]["variant_changed_process_default"] is False
        assert payload["guardrail"]["process_default_embedding_model"] == DEFAULT_EMBEDDING_MODEL
        # Re-import after the call to make sure nothing was mutated in place.
        from codesight import config as config_module

        assert config_module.DEFAULT_EMBEDDING_MODEL == DEFAULT_EMBEDDING_MODEL

    def test_cost_is_null_without_explicit_price(self, tmp_path):
        (tmp_path / "a.py").write_text("def needle_function():\n    return 42\n")
        variant = EmbeddingVariantSpec(model_name=DEFAULT_EMBEDDING_MODEL, backend="local")
        queries = [EvalQuery(query="needle_function", expected_file="a.py")]

        payload = run_variant_eval(queries, tmp_path, variant, top_k=5)

        assert payload["cost"]["estimated"] is None

    def test_cost_computed_when_price_supplied(self, tmp_path):
        (tmp_path / "a.py").write_text("def needle_function():\n    return 42\n")
        variant = EmbeddingVariantSpec(
            model_name=DEFAULT_EMBEDDING_MODEL, backend="local", price_per_1k_input=1.0,
        )
        queries = [EvalQuery(query="needle_function", expected_file="a.py")]

        payload = run_variant_eval(queries, tmp_path, variant, top_k=5)

        assert payload["cost"]["estimated"] is not None
        assert payload["cost"]["estimated"] >= 0.0

    def test_usage_includes_indexing_and_query_calls(self, tmp_path):
        (tmp_path / "a.py").write_text("def needle_function():\n    return 42\n")
        variant = EmbeddingVariantSpec(model_name=DEFAULT_EMBEDDING_MODEL, backend="local")
        queries = [EvalQuery(query="needle_function", expected_file="a.py")]

        payload = run_variant_eval(queries, tmp_path, variant, top_k=5)

        assert payload["usage"]["document_embed_calls"] >= 1
        assert payload["usage"]["query_embed_calls"] == 1

    def test_provider_fields_are_explicit(self, tmp_path):
        (tmp_path / "a.py").write_text("def needle_function():\n    return 42\n")
        variant = EmbeddingVariantSpec(model_name=DEFAULT_EMBEDDING_MODEL, backend="local")
        queries = [EvalQuery(query="needle_function", expected_file="a.py")]

        payload = run_variant_eval(queries, tmp_path, variant, top_k=5)

        assert payload["provider"]["model"] == DEFAULT_EMBEDDING_MODEL
        assert payload["provider"]["backend"] == "local"
        assert payload["provider"]["dimensions"] > 0
