from __future__ import annotations

import base64
import types
from pathlib import Path

import httpx
import pytest

import codesight.connectors.m365_auth as auth_module
from codesight.config import repo_fts_db_path
from codesight.connectors.m365 import GraphConnector
from codesight.connectors.m365_auth import ADMIN_BLOCKED_MESSAGE, M365Authenticator


class _FakeAuth:
    def __init__(self) -> None:
        self.calls: list[bool] = []

    def get_access_token(self, *, force_refresh: bool = False) -> str:
        self.calls.append(force_refresh)
        return "token-refreshed" if force_refresh else "token-initial"

    def tenant_hash(self) -> str:
        return "tenanthash001"


class _StubClient:
    def __init__(self, handler):
        self.handler = handler
        self.calls: list[tuple[str, str, dict[str, str] | None]] = []

    def request(self, method: str, url: str, headers=None, params=None):
        self.calls.append((method, url, params))
        return self.handler(method, url, params)


class _StubEngine:
    last_path: Path | None = None
    index_called = 0

    def __init__(self, path: str | Path) -> None:
        _StubEngine.last_path = Path(path)

    def index(self):
        _StubEngine.index_called += 1
        return None


def _response(
    method: str,
    url: str,
    *,
    status: int = 200,
    json_data=None,
    content: bytes | None = None,
):
    request = httpx.Request(method, url)
    if json_data is not None:
        return httpx.Response(status, json=json_data, request=request)
    return httpx.Response(status, content=content or b"", request=request)


def test_SPEC_011_001_device_code_flow_and_cached_token_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """SPEC-011-001: Device flow authenticates then silent token reuse avoids re-prompt."""

    class _FakeCache:
        def __init__(self):
            self.has_state_changed = True
            self._state = ""

        def deserialize(self, state: str) -> None:
            self._state = state

        def serialize(self) -> str:
            self.has_state_changed = False
            return "{\"token\":\"cached\"}"

    class _FakeApp:
        def __init__(self):
            self.accounts: list[dict[str, str]] = []

        def get_accounts(self):
            return self.accounts

        def acquire_token_silent(self, *_args, **_kwargs):
            if self.accounts:
                return {"access_token": "silent-token"}
            return None

        def initiate_device_flow(self, scopes):
            assert "Files.Read" in scopes
            return {
                "user_code": "ABCD1234",
                "message": "Go sign in",
            }

        def acquire_token_by_device_flow(self, _flow):
            self.accounts = [{"home_account_id": "tenant-user"}]
            return {"access_token": "device-token"}

    fake_app = _FakeApp()
    fake_msal = types.SimpleNamespace(
        SerializableTokenCache=_FakeCache,
        PublicClientApplication=lambda **_kwargs: fake_app,
    )

    monkeypatch.setattr(auth_module, "msal", fake_msal)
    auth = M365Authenticator(
        client_id="client-id",
        tenant_id="common",
        cache_path=tmp_path / "token-cache.json",
    )

    first = auth.get_access_token()
    second = auth.get_access_token()

    assert first == "device-token"
    assert second == "silent-token"
    assert auth.cache_path.exists()
    assert len(auth.tenant_hash()) == 12


def test_EDGE_011_004_admin_block_error_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """EDGE-011-004: Tenant policy block returns explicit admin-contact message."""

    class _FakeCache:
        has_state_changed = False

        def deserialize(self, _state: str) -> None:
            return

        def serialize(self) -> str:
            return "{}"

    class _FakeApp:
        def get_accounts(self):
            return []

        def acquire_token_silent(self, *_args, **_kwargs):
            return None

        def initiate_device_flow(self, scopes):
            return {"user_code": "ABCD1234", "message": "Sign in"}

        def acquire_token_by_device_flow(self, _flow):
            return {
                "error": "unauthorized_client",
                "error_description": "AADSTS65001: consent required",
            }

    fake_msal = types.SimpleNamespace(
        SerializableTokenCache=_FakeCache,
        PublicClientApplication=lambda **_kwargs: _FakeApp(),
    )
    monkeypatch.setattr(auth_module, "msal", fake_msal)

    auth = M365Authenticator(client_id="client-id", cache_path=tmp_path / "cache.json")
    with pytest.raises(PermissionError, match=ADMIN_BLOCKED_MESSAGE):
        auth.get_access_token()


def test_SPEC_011_002_SPEC_011_005_drive_sync_filters_files_and_persists_delta(tmp_path: Path):
    """SPEC-011-002/005: Drive sync writes supported files and persists delta state."""
    auth = _FakeAuth()

    def handler(method: str, url: str, _params):
        if url.endswith("/me/drive/root/delta"):
            return _response(
                method,
                url,
                json_data={
                    "value": [
                        {"id": "doc1", "name": "report.pdf", "file": {}, "size": 1000},
                        {"id": "big1", "name": "huge.pdf", "file": {}, "size": 60 * 1024 * 1024},
                        {"id": "bad1", "name": "tool.exe", "file": {}, "size": 10},
                    ],
                    "@odata.deltaLink": "https://graph.microsoft.com/v1.0/me/drive/root/delta?token=abc",
                },
            )
        if url.endswith("/me/drive/items/doc1/content"):
            return _response(method, url, content=b"pdf-bytes")
        if "delta?token=abc" in url:
            return _response(
                method,
                url,
                json_data={"value": [], "@odata.deltaLink": "https://graph.microsoft.com/next"},
            )
        raise AssertionError(f"Unexpected URL: {url}")

    connector = GraphConnector(
        auth=auth,
        client=_StubClient(handler),
        cache_root=tmp_path / "m365-cache",
        engine_factory=_StubEngine,
    )

    first_written = connector.sync_drive()
    assert first_written == 1
    drive_files = list((connector.cache_dir / "drive").glob("doc1__*"))
    assert len(drive_files) == 1
    assert drive_files[0].read_bytes() == b"pdf-bytes"

    assert connector.delta_state("drive")
    second_written = connector.sync_drive()
    assert second_written == 0
    assert connector.delta_state("drive") == "https://graph.microsoft.com/next"


def test_SPEC_011_003_and_EDGE_011_006_mail_sync_includes_attachment_only_messages(
    tmp_path: Path,
):
    """SPEC-011-003/EDGE-011-006: Mail is indexed as text and attachment-only email stores files."""
    auth = _FakeAuth()
    encoded_pdf = base64.b64encode(b"attachment-bytes").decode("utf-8")

    def handler(method: str, url: str, _params):
        if url.endswith("/me/messages"):
            return _response(
                method,
                url,
                json_data={
                    "value": [
                        {
                            "id": "mail1",
                            "subject": "Budget",
                            "from": {"emailAddress": {"address": "sender@example.com"}},
                            "receivedDateTime": "2026-03-01T00:00:00Z",
                            "body": {"content": "<p>Budget approved.</p>"},
                            "hasAttachments": False,
                        },
                        {
                            "id": "mail2",
                            "subject": "Attachments only",
                            "from": {"emailAddress": {"address": "sender@example.com"}},
                            "receivedDateTime": "2026-03-02T00:00:00Z",
                            "body": {"content": ""},
                            "hasAttachments": True,
                        },
                    ],
                    "@odata.deltaLink": "https://graph.microsoft.com/v1.0/me/messages/delta?token=m1",
                },
            )

        if url.endswith("/me/messages/mail2/attachments"):
            return _response(
                method,
                url,
                json_data={
                    "value": [
                        {
                            "@odata.type": "#microsoft.graph.fileAttachment",
                            "name": "syllabus.pdf",
                            "size": 1024,
                            "contentBytes": encoded_pdf,
                        }
                    ]
                },
            )
        raise AssertionError(f"Unexpected URL: {url}")

    connector = GraphConnector(
        auth=auth,
        client=_StubClient(handler),
        cache_root=tmp_path / "cache",
    )
    written = connector.sync_mail()

    assert written == 2
    first_mail = (connector.cache_dir / "mail" / "mail1.txt").read_text(encoding="utf-8")
    assert "From: sender@example.com" in first_mail
    assert "Budget approved." in first_mail

    attachment = connector.cache_dir / "mail" / "attachments" / "mail2" / "syllabus.pdf"
    assert attachment.exists()
    assert attachment.read_bytes() == b"attachment-bytes"


def test_SPEC_011_004_and_EDGE_011_003_notes_html_to_markdown_skips_empty_pages(tmp_path: Path):
    """SPEC-011-004/EDGE-011-003: OneNote HTML is converted to markdown and empty pages skipped."""
    auth = _FakeAuth()

    def handler(method: str, url: str, _params):
        if url.endswith("/me/onenote/pages"):
            return _response(
                method,
                url,
                json_data={
                    "value": [
                        {"id": "note1", "title": "Week 1", "contentUrl": "https://content/n1"},
                        {"id": "note2", "title": "Images", "contentUrl": "https://content/n2"},
                    ],
                    "@odata.deltaLink": "https://graph.microsoft.com/v1.0/me/onenote/pages/delta?token=n1",
                },
            )
        if url == "https://content/n1":
            return _response(method, url, content=b"<h1>Intro</h1><p>Hello world</p>")
        if url == "https://content/n2":
            return _response(method, url, content=b"<img src='x' />")
        raise AssertionError(f"Unexpected URL: {url}")

    connector = GraphConnector(
        auth=auth,
        client=_StubClient(handler),
        cache_root=tmp_path / "cache",
    )
    written = connector.sync_notes()

    assert written == 1
    note_file = connector.cache_dir / "notes" / "note1.md"
    assert note_file.exists()
    assert "Hello world" in note_file.read_text(encoding="utf-8")
    assert not (connector.cache_dir / "notes" / "note2.md").exists()


def test_SPEC_011_006_SPEC_011_007_sync_runs_all_sources_then_indexes_cache(tmp_path: Path):
    """SPEC-011-006/007: Full sync runs source syncs then invokes CodeSight.index(cache_dir)."""
    _StubEngine.last_path = None
    _StubEngine.index_called = 0
    auth = _FakeAuth()

    def handler(method: str, url: str, _params):
        if url.endswith("/me/drive/root/delta"):
            return _response(method, url, json_data={"value": [], "@odata.deltaLink": "d1"})
        if url.endswith("/me/messages"):
            return _response(method, url, json_data={"value": [], "@odata.deltaLink": "m1"})
        if url.endswith("/me/onenote/pages"):
            return _response(method, url, json_data={"value": [], "@odata.deltaLink": "n1"})
        raise AssertionError(f"Unexpected URL: {url}")

    connector = GraphConnector(
        auth=auth,
        client=_StubClient(handler),
        cache_root=tmp_path / "cache",
        engine_factory=_StubEngine,
    )
    stats = connector.sync()

    assert stats == {"drive": 0, "mail": 0, "notes": 0}
    assert _StubEngine.last_path == connector.cache_dir
    assert _StubEngine.index_called == 1
    assert repo_fts_db_path(connector.cache_dir).exists()


def test_EDGE_011_001_token_refresh_after_401_retries_once(tmp_path: Path):
    """EDGE-011-001: 401 triggers refresh and successful retry with fresh token."""
    auth = _FakeAuth()
    calls = {"count": 0}

    def handler(method: str, url: str, _params):
        if url.endswith("/me/drive/root/delta"):
            calls["count"] += 1
            if calls["count"] == 1:
                return _response(method, url, status=401, json_data={"error": "expired"})
            return _response(method, url, json_data={"value": []})
        raise AssertionError(f"Unexpected URL: {url}")

    connector = GraphConnector(
        auth=auth,
        client=_StubClient(handler),
        cache_root=tmp_path / "cache",
    )
    payload = connector._graph_get_json("/me/drive/root/delta")

    assert payload == {"value": []}
    assert auth.calls == [False, True]


def test_EDGE_011_005_network_failure_raises_clear_connection_error(tmp_path: Path):
    """EDGE-011-005: Request failures raise explicit no-internet guidance."""
    auth = _FakeAuth()

    def handler(method: str, url: str, _params):
        raise httpx.RequestError("offline", request=httpx.Request(method, url))

    connector = GraphConnector(
        auth=auth,
        client=_StubClient(handler),
        cache_root=tmp_path / "cache",
    )
    with pytest.raises(ConnectionError, match="No internet connection during M365 sync"):
        connector.sync_drive()
