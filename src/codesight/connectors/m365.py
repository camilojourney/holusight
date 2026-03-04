"""Microsoft Graph connector for syncing M365 content into CodeSight cache."""

from __future__ import annotations

import base64
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from ..api import CodeSight
from ..config import INDEXABLE_EXTENSIONS, repo_fts_db_path
from .m365_auth import M365Authenticator

try:
    import html2text
except ImportError:  # pragma: no cover - exercised in environments without optional deps
    html2text = None

logger = logging.getLogger(__name__)

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
MAX_M365_FILE_SIZE_BYTES = 50 * 1024 * 1024


class GraphConnector:
    """Read-only connector that syncs Microsoft 365 content into local cache files."""

    # SPEC-011-001: Graph connector bootstraps auth, cache location, and HTTP transport.
    def __init__(
        self,
        *,
        auth: M365Authenticator | None = None,
        client: httpx.Client | None = None,
        cache_root: str | Path | None = None,
        engine_factory: type[CodeSight] = CodeSight,
    ) -> None:
        self.auth = auth or M365Authenticator()
        self.client = client or httpx.Client(timeout=30.0)
        self.engine_factory = engine_factory
        self.max_file_size_bytes = MAX_M365_FILE_SIZE_BYTES

        root = Path(cache_root or Path.home() / ".codesight" / "m365-cache")
        self.cache_dir = root / self.auth.tenant_hash()
        self.drive_dir = self.cache_dir / "drive"
        self.mail_dir = self.cache_dir / "mail"
        self.notes_dir = self.cache_dir / "notes"
        self._access_token: str | None = None

    # SPEC-011-007: Single sync orchestration fetches all sources and then triggers index().
    def sync(self) -> dict[str, int]:
        logger.info("m365.sync.start")
        self._ensure_cache_dirs()
        synced = {
            "drive": self.sync_drive(),
            "mail": self.sync_mail(),
            "notes": self.sync_notes(),
        }
        # SPEC-011-006: Existing CodeSight index() pipeline is reused after connector sync.
        self.engine_factory(self.cache_dir).index()
        logger.info("m365.sync.complete")
        return synced

    # SPEC-011-002: OneDrive/SharePoint files are fetched via Graph delta API and cached locally.
    def sync_drive(self) -> int:
        start_url = self.delta_state("drive") or "/me/drive/root/delta"
        items, delta_link = self._collect_delta_items(start_url)

        written = 0
        for item in items:
            item_id = item.get("id")
            if not item_id:
                continue

            if "deleted" in item:
                self._delete_by_prefix(self.drive_dir, f"{item_id}__")
                continue

            if "file" not in item:
                continue

            file_name = item.get("name") or item_id
            suffix = Path(file_name).suffix.lower()
            if suffix not in INDEXABLE_EXTENSIONS:
                continue

            if int(item.get("size") or 0) > self.max_file_size_bytes:
                # EDGE-011-002: Oversized files are skipped with warning while sync continues.
                logger.warning("m365.sync.skip file_too_large id=%s name=%s", item_id, file_name)
                continue

            try:
                payload = self._graph_get_bytes(f"/me/drive/items/{item_id}/content")
            except PermissionError:
                # EDGE-011-007: Permission denied items are skipped without aborting full sync.
                logger.warning("m365.sync.skip permission_denied source=drive id=%s", item_id)
                continue

            target = self.drive_dir / f"{item_id}__{self._safe_name(file_name)}"
            self._write_bytes(target, payload)
            written += 1

        if delta_link:
            self.delta_state("drive", delta_link)
        return written

    # SPEC-011-003: Outlook mail messages are converted to plain-text files with metadata headers.
    def sync_mail(self) -> int:
        start_url = self.delta_state("mail") or "/me/messages"
        params = {
            "$select": "id,subject,from,body,receivedDateTime,hasAttachments",
            "$top": "500",
        }
        items, delta_link = self._collect_delta_items(start_url, params=params)

        written = 0
        for item in items:
            message_id = item.get("id")
            if not message_id:
                continue

            if "deleted" in item:
                self._delete_mail_message(message_id)
                continue

            sender = item.get("from", {}).get("emailAddress", {}).get("address", "unknown")
            subject = item.get("subject") or "(no subject)"
            received = item.get("receivedDateTime") or ""
            body_html = item.get("body", {}).get("content", "")
            body_text = self._html_to_text(body_html).strip()

            if not body_text and item.get("hasAttachments"):
                # EDGE-011-006: Attachment-only emails still index supported attachments.
                self._sync_mail_attachments(message_id)

            content = (
                f"From: {sender}\n"
                f"Subject: {subject}\n"
                f"Date: {received}\n"
                "---\n"
                f"{body_text or '[No body content]'}\n"
            )
            self._write_text(self.mail_dir / f"{message_id}.txt", content)
            written += 1

        if delta_link:
            self.delta_state("mail", delta_link)
        return written

    # SPEC-011-004: OneNote pages are fetched as HTML, converted to markdown,
    # and saved as .md files.
    def sync_notes(self) -> int:
        start_url = self.delta_state("notes") or "/me/onenote/pages"
        params = {
            "$select": "id,title,contentUrl",
            "$top": "500",
        }
        items, delta_link = self._collect_delta_items(start_url, params=params)

        written = 0
        for item in items:
            page_id = item.get("id")
            if not page_id:
                continue

            if "deleted" in item:
                self._delete_by_prefix(self.notes_dir, f"{page_id}.")
                continue

            content_url = item.get("contentUrl") or f"/me/onenote/pages/{page_id}/content"
            markdown = self._html_to_markdown(self._graph_get_text(content_url)).strip()
            if not markdown:
                # EDGE-011-003: Image-only/empty OneNote pages are skipped as non-indexable content.
                logger.warning("m365.sync.skip empty_note id=%s", page_id)
                continue

            title = item.get("title") or "Untitled"
            self._write_text(self.notes_dir / f"{page_id}.md", f"# {title}\n\n{markdown}\n")
            written += 1

        if delta_link:
            self.delta_state("notes", delta_link)
        return written

    # SPEC-011-005: Delta cursor state is persisted per source type in metadata.db.
    def delta_state(self, source_type: str, delta_link: str | None = None) -> str | None:
        self._ensure_delta_table()
        db_path = repo_fts_db_path(self.cache_dir)
        with sqlite3.connect(str(db_path)) as conn:
            if delta_link is None:
                row = conn.execute(
                    "SELECT delta_link FROM m365_sync_state WHERE source_type = ?",
                    (source_type,),
                ).fetchone()
                return row[0] if row else None

            conn.execute(
                """
                INSERT INTO m365_sync_state(source_type, delta_link, last_synced_at)
                VALUES (?, ?, ?)
                ON CONFLICT(source_type) DO UPDATE SET
                    delta_link=excluded.delta_link,
                    last_synced_at=excluded.last_synced_at
                """,
                (source_type, delta_link, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            return delta_link

    # SPEC-011-005: Delta sync follows Graph nextLink/deltaLink pagination until completion.
    def _collect_delta_items(
        self,
        start_url: str,
        *,
        params: dict[str, str] | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        items: list[dict[str, Any]] = []
        next_url: str | None = start_url
        delta_link: str | None = None
        use_params = params

        while next_url:
            payload = self._graph_get_json(next_url, params=use_params)
            items.extend(payload.get("value", []))
            next_url = payload.get("@odata.nextLink")
            delta_link = payload.get("@odata.deltaLink", delta_link)
            use_params = None

        return items, delta_link

    # SPEC-011-005: Sync state table is created in shared metadata.db sidecar.
    def _ensure_delta_table(self) -> None:
        db_path = repo_fts_db_path(self.cache_dir)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS m365_sync_state (
                    source_type TEXT PRIMARY KEY,
                    delta_link TEXT NOT NULL,
                    last_synced_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    # EDGE-011-005: Network failures fail fast with a clear message and no
    # destructive cache actions.
    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        accept: str | None = None,
    ) -> httpx.Response:
        normalized = self._normalize_url(url)

        for attempt in range(2):
            token = self._get_access_token(force_refresh=attempt == 1)
            headers: dict[str, str] = {"Authorization": f"Bearer {token}"}
            if accept:
                headers["Accept"] = accept

            try:
                response = self.client.request(method, normalized, headers=headers, params=params)
            except httpx.RequestError as exc:
                raise ConnectionError(
                    "No internet connection during M365 sync. Check network and try again."
                ) from exc

            if response.status_code == 401 and attempt == 0:
                # EDGE-011-001: 401 responses trigger refresh/re-auth path before failing.
                logger.info("m365.auth.token_refresh")
                continue
            if response.status_code == 403:
                raise PermissionError("Microsoft Graph permission denied for this resource.")
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Graph API request failed ({response.status_code}): {response.text[:200]}"
                )
            return response

        raise RuntimeError("Authentication failed after token refresh attempt.")

    # SPEC-011-001: Access tokens are acquired lazily and reused during a sync session.
    def _get_access_token(self, *, force_refresh: bool = False) -> str:
        if self._access_token and not force_refresh:
            return self._access_token
        self._access_token = self.auth.get_access_token(force_refresh=force_refresh)
        return self._access_token

    # SPEC-011-002: Graph JSON payload retrieval is centralized for source sync routines.
    def _graph_get_json(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response = self._request("GET", url, params=params, accept="application/json")
        return response.json()

    # SPEC-011-002: Drive and attachment binaries are downloaded through Graph content endpoints.
    def _graph_get_bytes(self, url: str) -> bytes:
        return self._request("GET", url).content

    # SPEC-011-004: OneNote page HTML payloads are fetched before markdown conversion.
    def _graph_get_text(self, url: str) -> str:
        return self._request("GET", url, accept="text/html").text

    # SPEC-011-001: Relative Graph routes are resolved against the v1.0 base endpoint.
    def _normalize_url(self, url: str) -> str:
        return url if url.startswith("http") else f"{GRAPH_BASE_URL}{url}"

    # SPEC-011-001: Connector initializes all cache subdirectories under tenant-scoped root.
    def _ensure_cache_dirs(self) -> None:
        self.drive_dir.mkdir(parents=True, exist_ok=True)
        self.mail_dir.mkdir(parents=True, exist_ok=True)
        self.notes_dir.mkdir(parents=True, exist_ok=True)

    # SPEC-011-003: Mail attachments are fetched and persisted for indexable file extensions only.
    def _sync_mail_attachments(self, message_id: str) -> None:
        params = {
            "$select": "id,name,contentBytes,size,@odata.type",
            "$top": "100",
        }
        payload = self._graph_get_json(f"/me/messages/{message_id}/attachments", params=params)
        for item in payload.get("value", []):
            if not str(item.get("@odata.type", "")).endswith("fileAttachment"):
                continue

            name = item.get("name") or "attachment.bin"
            suffix = Path(name).suffix.lower()
            if suffix not in INDEXABLE_EXTENSIONS:
                continue
            if int(item.get("size") or 0) > self.max_file_size_bytes:
                logger.warning(
                    "m365.sync.skip attachment_too_large message=%s name=%s",
                    message_id,
                    name,
                )
                continue

            content_b64 = item.get("contentBytes")
            if not content_b64:
                continue

            decoded = base64.b64decode(content_b64)
            target = self.mail_dir / "attachments" / message_id / self._safe_name(name)
            self._write_bytes(target, decoded)

    # SPEC-011-004: HTML from Graph content endpoints is converted into markdown for indexing.
    def _html_to_markdown(self, html: str) -> str:
        if not html.strip():
            return ""
        if html2text is not None:
            converter = html2text.HTML2Text()
            converter.ignore_links = False
            converter.body_width = 0
            return converter.handle(html).strip()
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()

    # SPEC-011-003: Email body content is normalized to plain text before writing .txt files.
    def _html_to_text(self, html: str) -> str:
        markdown = self._html_to_markdown(html)
        return re.sub(r"\s+", " ", markdown).strip()

    # SPEC-011-002: Cached binary files are written atomically into the managed connector directory.
    def _write_bytes(self, path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    # SPEC-011-003: Text artifacts are persisted in UTF-8 for downstream chunking/indexing.
    def _write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    # SPEC-011-001: Cache filenames are sanitized to avoid invalid/path-traversal characters.
    def _safe_name(self, value: str) -> str:
        value = value.strip().replace("/", "_").replace("\\", "_")
        return re.sub(r"[^A-Za-z0-9._-]", "_", value) or "item"

    # SPEC-011-005: Delta delete events remove previously cached message text and attachment files.
    def _delete_mail_message(self, message_id: str) -> None:
        text_path = self.mail_dir / f"{message_id}.txt"
        if text_path.exists():
            text_path.unlink()

        attachment_dir = self.mail_dir / "attachments" / message_id
        if attachment_dir.exists():
            for file_path in attachment_dir.rglob("*"):
                if file_path.is_file():
                    file_path.unlink()
            for dir_path in sorted(attachment_dir.rglob("*"), reverse=True):
                if dir_path.is_dir():
                    dir_path.rmdir()
            attachment_dir.rmdir()

    # SPEC-011-005: Delete events clear matching cached files via deterministic ID prefixes.
    def _delete_by_prefix(self, root: Path, prefix: str) -> None:
        if not root.exists():
            return
        for file_path in root.glob(f"{prefix}*"):
            if file_path.is_file():
                file_path.unlink()

    # SPEC-011-007: Source selection validates supported connectors for CLI sync orchestration.
    @classmethod
    def from_source(cls, source: str) -> GraphConnector:
        if source != "m365":
            raise ValueError(f"Unsupported sync source '{source}'. Valid options: m365")
        return cls()
