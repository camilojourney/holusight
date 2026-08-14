"""FastAPI server contract tests."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from codesight.web import server as web_server

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pilot_docs"
TEST_API_KEY = "test-secret-key-12345"


@pytest.fixture
def server_env(tmp_path, monkeypatch):
    """Configure isolated server environment."""
    monkeypatch.setenv("CODESIGHT_DOCUMENTS_DIR", str(FIXTURES))
    monkeypatch.setenv("CODESIGHT_DATA_DIR", str(tmp_path / "index"))
    monkeypatch.setenv("CODESIGHT_API_KEY", TEST_API_KEY)
    monkeypatch.setenv("CODESIGHT_PRODUCTION", "1")
    monkeypatch.delenv("CODESIGHT_ALLOW_UNAUTHENTICATED", raising=False)
    # Reset module-level engine between tests
    web_server._engine = None
    web_server._index_in_progress = False
    yield


@pytest.fixture
def client(server_env):
    app = web_server.create_app()
    with TestClient(app) as c:
        yield c


def _auth_headers(key: str = TEST_API_KEY) -> dict[str, str]:
    return {"X-API-Key": key}


class TestServerAuth:
    def test_missing_api_key_returns_401(self, client):
        r = client.post("/api/search", json={"query": "payment"})
        assert r.status_code == 401

    def test_invalid_api_key_returns_401(self, client):
        r = client.post(
            "/api/search",
            json={"query": "payment"},
            headers=_auth_headers("wrong"),
        )
        assert r.status_code == 401

    def test_health_is_public(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["auth_required"] is True


class TestServerAPI:
    def test_index_then_search_with_citations(self, client):
        r = client.post(
            "/api/index",
            json={"force_rebuild": True},
            headers=_auth_headers(),
        )
        assert r.status_code == 200
        assert r.json()["total_chunks"] >= 1

        r = client.post(
            "/api/search",
            json={"query": "Net 30 payment"},
            headers=_auth_headers(),
        )
        assert r.status_code == 200
        results = r.json()["results"]
        assert results
        first = results[0]
        assert "file_path" in first
        assert "snippet" in first
        assert "start_line" in first

    def test_empty_query_returns_400(self, client):
        r = client.post(
            "/api/search",
            json={"query": "   "},
            headers=_auth_headers(),
        )
        assert r.status_code == 400

    def test_concurrent_index_returns_409(self, client):
        web_server._index_in_progress = True
        try:
            r = client.post("/api/index", json={}, headers=_auth_headers())
            assert r.status_code == 409
        finally:
            web_server._index_in_progress = False

    def test_bearer_token_auth(self, client):
        client.post("/api/index", json={"force_rebuild": True}, headers=_auth_headers())
        r = client.post(
            "/api/search",
            json={"query": "Net 30"},
            headers={"Authorization": f"Bearer {TEST_API_KEY}"},
        )
        assert r.status_code == 200

    def test_ask_without_llm_returns_503(self, client, monkeypatch):
        client.post("/api/index", json={"force_rebuild": True}, headers=_auth_headers())
        monkeypatch.setenv("CODESIGHT_LLM_BACKEND", "claude")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        web_server._engine = None
        r = client.post(
            "/api/ask",
            json={"question": "What are payment terms?"},
            headers=_auth_headers(),
        )
        assert r.status_code == 503

    def test_status_after_index(self, client):
        client.post("/api/index", json={"force_rebuild": True}, headers=_auth_headers())
        r = client.get("/api/status", headers=_auth_headers())
        assert r.status_code == 200
        body = r.json()
        assert body["indexed"] is True
        assert body["chunk_count"] >= 1

    def test_ui_served_at_root(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "Holusight" in r.text

    def test_malformed_json_returns_422(self, client):
        r = client.post(
            "/api/search",
            content=b"not-json",
            headers={**_auth_headers(), "Content-Type": "application/json"},
        )
        assert r.status_code == 422


class TestProductionAuthRequired:
    def test_production_without_api_key_fails_startup(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CODESIGHT_DOCUMENTS_DIR", str(FIXTURES))
        monkeypatch.setenv("CODESIGHT_PRODUCTION", "1")
        monkeypatch.delenv("CODESIGHT_API_KEY", raising=False)
        monkeypatch.delenv("CODESIGHT_ALLOW_UNAUTHENTICATED", raising=False)
        with pytest.raises(RuntimeError, match="CODESIGHT_API_KEY"):
            web_server.validate_startup()

    def test_dev_allow_unauthenticated(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CODESIGHT_DOCUMENTS_DIR", str(FIXTURES))
        monkeypatch.setenv("CODESIGHT_ALLOW_UNAUTHENTICATED", "true")
        monkeypatch.delenv("CODESIGHT_API_KEY", raising=False)
        assert web_server.require_auth() is False

    def test_missing_documents_dir_fails_startup(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CODESIGHT_DOCUMENTS_DIR", str(tmp_path / "missing"))
        monkeypatch.setenv("CODESIGHT_API_KEY", TEST_API_KEY)
        monkeypatch.setenv("CODESIGHT_PRODUCTION", "1")
        with pytest.raises(RuntimeError, match="Documents directory not found"):
            web_server.validate_startup()
