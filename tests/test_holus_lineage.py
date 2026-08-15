"""Contract tests for read-only Holus lineage ingestion."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from codesight import config as config_module
from codesight.api import CodeSight
from codesight.config import ServerConfig


class StaticEmbedder:
    """Deterministic embeddings for source-filtering tests."""

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = []
        for text in texts:
            vector = np.zeros(self.dim, dtype=np.float32)
            lowered = text.lower()
            if "checkout" in lowered:
                vector[0] = 1.0
            elif "native" in lowered:
                vector[1] = 1.0
            else:
                vector[2] = 1.0
            vectors.append(vector)
        return np.vstack(vectors)

    def embed_query(self, query: str) -> np.ndarray:
        return self.embed([query])[0]


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    root.mkdir()
    (root / "native.md").write_text(
        "# Native handbook\n\nNative approval guidance belongs to indexed files.\n",
        encoding="utf-8",
    )
    return root


@pytest.fixture
def engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source_dir: Path) -> CodeSight:
    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "index-data")
    instance = CodeSight(
        source_dir,
        config=ServerConfig(
            embedding_backend="local",
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            embedding_dim=384,
            reranker=False,
        ),
    )
    instance._embedder = StaticEmbedder(dim=instance.config.embedding_dim)
    return instance


def _holus_export() -> dict:
    return {
        "schema_version": "1.0",
        "snapshot_seq": 2,
        "records": [
            {
                "schema_version": "1.0",
                "event_id": "event:content-set:checkout",
                "seq": 1,
                "recorded_at": "2026-08-15T00:00:00+00:00",
                "node": {
                    "schema_version": "1.0",
                    "node_id": "content-set:checkout",
                    "artifact_type": "content_set",
                    "artifact_id": "checkout",
                    "producer": "holus.thought_content_pipeline",
                    "created_at": "2026-08-15T00:00:00+00:00",
                    "run_id": "run:checkout",
                    "correlation_id": "checkout",
                    "status": "pending_review",
                    "artifact_ref": "content-queue/checkout.yaml",
                    "content_hash": "a" * 64,
                    "metadata": {"topic": "checkout approval"},
                },
                "edges": [],
            },
            {
                "schema_version": "1.0",
                "event_id": "event:content:checkout",
                "seq": 2,
                "recorded_at": "2026-08-15T00:01:00+00:00",
                "node": {
                    "schema_version": "1.0",
                    "node_id": "content:checkout-linkedin",
                    "artifact_type": "content_variant",
                    "artifact_id": "checkout-linkedin",
                    "producer": "holus.thought_content_pipeline",
                    "created_at": "2026-08-15T00:01:00+00:00",
                    "run_id": "run:checkout",
                    "correlation_id": "checkout",
                    "status": "pending_review",
                    "artifact_ref": "content-queue/checkout-linkedin.yaml",
                    "content_hash": "b" * 64,
                    "metadata": {"topic": "checkout approval"},
                },
                "edges": [
                    {
                        "schema_version": "1.0",
                        "edge_id": "edge:checkout-contains-linkedin",
                        "from_node_id": "content-set:checkout",
                        "to_node_id": "content:checkout-linkedin",
                        "relation": "contains",
                        "created_at": "2026-08-15T00:01:00+00:00",
                        "run_id": "run:checkout",
                        "metadata": {"phase": "generation"},
                    }
                ],
            },
        ],
    }


class TestHolusLineageImport:
    def test_import_is_idempotent_and_preserves_lineage_identity(self, engine: CodeSight) -> None:
        first = engine.import_holus_lineage(_holus_export())
        second = engine.import_holus_lineage(_holus_export())

        assert first.source == "holus"
        assert first.source_schema_version == "1.0"
        assert first.records_imported == 2
        assert first.records_skipped_unchanged == 0
        assert second.records_imported == 0
        assert second.records_skipped_unchanged == 2

        results = engine.search("checkout approval", source="holus", top_k=5)
        result = next(
            item for item in results if item.lineage_node_id == "content:checkout-linkedin"
        )
        assert result.source == "holus"
        assert result.source_label == "Holus lineage"
        assert result.source_schema_version == "1.0"
        assert result.lineage_edge_ids == ["edge:checkout-contains-linkedin"]
        assert "checkout approval" in result.snippet.lower()

    @pytest.mark.parametrize(
        ("mutate", "message"),
        [
            (lambda export: export.update(schema_version="2.0"), "schema_version"),
            (
                lambda export: export["records"][0]["node"].update(artifact_ref="../private.yaml"),
                "artifact_ref",
            ),
            (
                lambda export: export["records"][0]["node"].update(metadata={"url": "https://private.example"}),
                "metadata",
            ),
            (
                lambda export: export["records"][1]["edges"][0].update(
                    to_node_id="content:missing"
                ),
                "unknown lineage node",
            ),
        ],
    )
    def test_import_rejects_invalid_or_private_contract_before_writing(
        self,
        engine: CodeSight,
        mutate,
        message: str,
    ) -> None:
        export = _holus_export()
        mutate(export)

        with pytest.raises(ValueError, match=message):
            engine.import_holus_lineage(export)

        assert engine.store.chunk_count == 0


class TestHolusLineageSearchAndAttribution:
    def test_source_filter_keeps_holus_and_existing_file_results_distinct(
        self, engine: CodeSight
    ) -> None:
        engine.import_holus_lineage(_holus_export())

        holus_results = engine.search("checkout approval", source="holus", top_k=5)
        assert holus_results
        assert {result.source for result in holus_results} == {"holus"}

        native_results = engine.search("native approval", top_k=5)
        assert any(result.source == "indexed_files" for result in native_results)

    def test_browser_api_and_ui_truthfully_attribute_holus_source(
        self,
        engine: CodeSight,
        source_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient

        from codesight.web import server as web_server

        monkeypatch.setenv("CODESIGHT_DOCUMENTS_DIR", str(source_dir))
        monkeypatch.setenv("CODESIGHT_API_KEY", "test-key")
        monkeypatch.setenv("CODESIGHT_PRODUCTION", "1")
        web_server._engine = engine
        try:
            with TestClient(web_server.create_app()) as client:
                imported = client.post(
                    "/api/sources/holus/import",
                    json={"payload": _holus_export()},
                    headers={"X-API-Key": "test-key"},
                )
                assert imported.status_code == 200
                assert imported.json()["records_imported"] == 2

                response = client.post(
                    "/api/search",
                    json={"query": "checkout approval", "source": "holus"},
                    headers={"X-API-Key": "test-key"},
                )
        finally:
            web_server._engine = None

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["source"] == "holus"
        assert result["source_label"] == "Holus lineage"
        assert result["lineage_node_id"].startswith("content")
        assert result["source_schema_version"] == "1.0"
        assert "content-queue" not in result["snippet"]
        assert "https://" not in result["snippet"]

        app_js = (Path(__file__).parents[1] / "src/codesight/web/static/app.js").read_text(
            encoding="utf-8"
        )
        assert "source_label" in app_js
        assert "Holus lineage" in app_js
