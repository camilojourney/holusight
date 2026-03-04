"""Workspace manager APIs for multi-tenant storage, source binding, sync, and ACL."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..api import CodeSight
from ..connectors import GraphConnector
from ..types import DataSource, SyncRunResult, Workspace
from .db import WorkspaceDB

logger = logging.getLogger(__name__)

VALID_SOURCE_TYPES = ("drive", "mail", "notes", "sharepoint", "local")
SOURCE_REQUIRED_CONFIG: dict[str, str] = {
    "drive": "path",
    "mail": "mailbox",
    "notes": "notebook",
    "sharepoint": "site_url",
    "local": "path",
}
WORKSPACE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,99}$")
EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$"
)


class WorkspaceAccessDenied(PermissionError):
    """Raised when caller email is not authorized for a workspace."""


class WorkspaceManager:
    """CRUD, source management, ACL, and sync orchestration for workspaces."""

    def __init__(
        self,
        db: WorkspaceDB | None = None,
        *,
        db_path: str | Path | None = None,
        data_root: str | Path | None = None,
    ) -> None:
        self.db = db or WorkspaceDB(db_path=db_path)
        self.data_root = Path(data_root or Path.home() / ".codesight" / "data").expanduser()
        self.data_root.mkdir(parents=True, exist_ok=True)

    # // SPEC-013-002: CRUD create with UUIDv4 and workspace data dir provisioning.
    def create(
        self,
        name: str,
        description: str | None = None,
        sources: list[DataSource] | None = None,
        allowed_emails: list[str] | None = None,
    ) -> Workspace:
        self._validate_workspace_name(name)
        workspace_id = str(uuid.uuid4())
        now = self._utc_now()

        with self.db.transaction() as conn:
            existing = conn.execute(
                "SELECT id, name FROM workspaces WHERE name = ? COLLATE NOCASE",
                (name,),
            ).fetchone()
            if existing:
                # // EDGE-013-001: Duplicate workspace name rejected before filesystem writes.
                raise ValueError(f"Workspace '{existing['name']}' already exists.")

            conn.execute(
                """
                INSERT INTO workspaces(id, name, description, created_at, updated_at, sync_status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (workspace_id, name, description, now, now, "never"),
            )

            for source in (sources or []):
                self._insert_source_row(conn, workspace_id, source)

            for email in (allowed_emails or []):
                self._insert_access_row(conn, workspace_id, email)

        try:
            self.ensure_workspace_storage(workspace_id)
        except Exception:
            with self.db.transaction() as conn:
                conn.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
            raise

        logger.info(
            "workspace.create workspace_id=%s source_count=%d",
            workspace_id,
            len(sources or []),
        )
        return self.get(workspace_id)

    # // SPEC-013-002: Workspace list returns status fields for each row.
    def list(self) -> list[Workspace]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, name, description, created_at, updated_at, last_synced_at, sync_status
                FROM workspaces
                ORDER BY name COLLATE NOCASE ASC
                """
            ).fetchall()
        return [self._row_to_workspace(row) for row in rows]

    def get(self, name_or_id: str) -> Workspace:
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT id, name, description, created_at, updated_at, last_synced_at, sync_status
                FROM workspaces
                WHERE id = ? OR name = ? COLLATE NOCASE
                LIMIT 1
                """,
                (name_or_id, name_or_id),
            ).fetchone()
        if row is None:
            raise ValueError(f"Workspace '{name_or_id}' not found.")
        return self._row_to_workspace(row)

    def update(
        self,
        workspace_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Workspace:
        if name is not None:
            self._validate_workspace_name(name)

        with self.db.transaction() as conn:
            existing = conn.execute(
                "SELECT id, name, description FROM workspaces WHERE id = ?",
                (workspace_id,),
            ).fetchone()
            if existing is None:
                raise ValueError(f"Workspace '{workspace_id}' not found.")

            if name is not None and name.lower() != str(existing["name"]).lower():
                duplicate = conn.execute(
                    "SELECT id, name FROM workspaces WHERE name = ? COLLATE NOCASE",
                    (name,),
                ).fetchone()
                if duplicate is not None:
                    raise ValueError(f"Workspace '{duplicate['name']}' already exists.")

            next_name = name if name is not None else str(existing["name"])
            next_description = description if description is not None else existing["description"]
            conn.execute(
                "UPDATE workspaces SET name = ?, description = ?, updated_at = ? WHERE id = ?",
                (next_name, next_description, self._utc_now(), workspace_id),
            )

        return self.get(workspace_id)

    def delete(self, workspace_id: str, *, force: bool = False) -> None:
        workspace = self.get(workspace_id)
        if workspace.sync_status == "syncing" and not force:
            # // EDGE-013-004: Syncing workspace cannot be deleted without force.
            raise ValueError(
                f"Workspace '{workspace.name}' is syncing. Wait for sync completion or use --force."
            )

        with self.db.transaction() as conn:
            conn.execute("DELETE FROM workspaces WHERE id = ?", (workspace.id,))

        self._remove_workspace_storage(workspace.id)

    # // SPEC-013-003: Bind validated sources to a workspace with dedupe checks.
    def add_source(self, workspace_id: str, source: DataSource) -> DataSource:
        workspace = self.get(workspace_id)
        with self.db.transaction() as conn:
            source_id = self._insert_source_row(conn, workspace.id, source)
            row = conn.execute(
                """
                SELECT id, workspace_id, source_type, source_config, created_at
                FROM data_sources
                WHERE id = ?
                """,
                (source_id,),
            ).fetchone()
        return self._row_to_source(row)

    def remove_source(self, workspace_id: str, source_id: str) -> None:
        workspace = self.get(workspace_id)
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM data_sources WHERE id = ? AND workspace_id = ?",
                (source_id, workspace.id),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Source '{source_id}' not found in workspace '{workspace.id}'.")

    # // SPEC-013-006: ACL allow/deny/check with lowercase normalization.
    def allow(self, workspace_id: str, email: str) -> None:
        workspace = self.get(workspace_id)
        with self.db.transaction() as conn:
            self._insert_access_row(conn, workspace.id, email)

    def deny(self, workspace_id: str, email: str) -> None:
        workspace = self.get(workspace_id)
        normalized = self._normalize_email(email, validate=False)
        with self.db.transaction() as conn:
            conn.execute(
                "DELETE FROM workspace_access WHERE workspace_id = ? AND email = ?",
                (workspace.id, normalized),
            )

    def check_access(self, workspace_id: str, email: str) -> bool:
        workspace = self.get(workspace_id)
        normalized = self._normalize_email(email, validate=False)

        with self.db.connection() as conn:
            acl_count = conn.execute(
                "SELECT COUNT(*) FROM workspace_access WHERE workspace_id = ?",
                (workspace.id,),
            ).fetchone()[0]

            if acl_count == 0:
                # // EDGE-013-008: Empty ACL denies all callers.
                logger.warning(
                    "workspace.access.denied workspace_id=%s email_hash=%s reason=empty_acl",
                    workspace.id,
                    self._email_hash_prefix(normalized),
                )
                return False

            found = conn.execute(
                "SELECT 1 FROM workspace_access WHERE workspace_id = ? AND email = ? LIMIT 1",
                (workspace.id, normalized),
            ).fetchone()
            allowed = found is not None

        if not allowed:
            logger.warning(
                "workspace.access.denied workspace_id=%s email_hash=%s reason=missing_match",
                workspace.id,
                self._email_hash_prefix(normalized),
            )
        return allowed

    def require_access(self, workspace_id: str, email: str) -> None:
        workspace = self.get(workspace_id)
        if not self.check_access(workspace.id, email):
            raise WorkspaceAccessDenied(
                f"You don't have access to workspace '{workspace.name}'. Contact your admin."
            )

    # // SPEC-013-004: Workspace sync creates a sync run and updates status on completion.
    def sync(self, workspace_id: str) -> SyncRunResult:
        workspace = self.get(workspace_id)
        sources = self._list_sources(workspace.id)
        started_at = self._utc_now()
        run_id = str(uuid.uuid4())

        with self.db.transaction() as conn:
            lock_row = conn.execute(
                "SELECT sync_status FROM workspaces WHERE id = ?",
                (workspace.id,),
            ).fetchone()
            if lock_row is None:
                raise ValueError(f"Workspace '{workspace_id}' not found.")
            if lock_row["sync_status"] == "syncing":
                # // EDGE-013-003: Sync lock conflict rejects second request.
                raise RuntimeError(f"Sync already in progress for workspace '{workspace.name}'.")

            conn.execute(
                "UPDATE workspaces SET sync_status = ?, updated_at = ? WHERE id = ?",
                ("syncing", started_at, workspace.id),
            )
            conn.execute(
                """
                INSERT INTO sync_runs(
                    id, workspace_id, started_at, completed_at, status,
                    files_added, files_updated, files_deleted, error_message
                )
                VALUES (?, ?, ?, NULL, ?, 0, 0, 0, NULL)
                """,
                (run_id, workspace.id, started_at, "running"),
            )

        logger.info(
            "workspace.sync.start workspace_id=%s source_count=%d",
            workspace.id,
            len(sources),
        )

        self.ensure_workspace_storage(workspace.id)
        workspace_dir = self.workspace_data_dir(workspace.id)
        source_errors: list[str] = []
        files_added = 0
        files_updated = 0
        files_deleted = 0
        m365_connector: GraphConnector | None = None

        for source in sources:
            try:
                if source.source_type == "local":
                    synced = self._sync_local_source(workspace.id, source)
                else:
                    if m365_connector is None:
                        m365_connector = GraphConnector(cache_root=workspace_dir / "m365-cache")
                    synced = self._sync_m365_source(m365_connector, source)
                files_added += synced
            except Exception as exc:
                # // EDGE-013-005: Source failures are isolated and do not abort remaining sources.
                source_errors.append(self._source_error_message(source, exc))
                logger.warning(
                    "workspace.sync.source_error workspace_id=%s source_id=%s error=%s",
                    workspace.id,
                    source.id,
                    self._sanitize_error(exc),
                )

        try:
            # // SPEC-013-004: Local/workspace indexing uses existing CodeSight.index().
            stats = CodeSight(workspace_dir).index()
            files_added = max(files_added, stats.files_indexed)
        except Exception as exc:
            source_errors.append(self._source_error_message(None, exc))

        completed_at = self._utc_now()
        status = "error" if source_errors else "ok"
        error_message = "; ".join(source_errors)[:500] if source_errors else None

        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE sync_runs
                SET completed_at = ?, status = ?, files_added = ?, files_updated = ?,
                    files_deleted = ?, error_message = ?
                WHERE id = ?
                """,
                (
                    completed_at,
                    status,
                    files_added,
                    files_updated,
                    files_deleted,
                    error_message,
                    run_id,
                ),
            )

            workspace_still_exists = conn.execute(
                "SELECT 1 FROM workspaces WHERE id = ?",
                (workspace.id,),
            ).fetchone()
            if workspace_still_exists:
                if status == "ok":
                    conn.execute(
                        """
                        UPDATE workspaces
                        SET sync_status = ?, last_synced_at = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (status, completed_at, completed_at, workspace.id),
                    )
                else:
                    conn.execute(
                        "UPDATE workspaces SET sync_status = ?, updated_at = ? WHERE id = ?",
                        (status, completed_at, workspace.id),
                    )

        logger.info(
            "workspace.sync.complete workspace_id=%s status=%s files_added=%d "
            "files_updated=%d files_deleted=%d",
            workspace.id,
            status,
            files_added,
            files_updated,
            files_deleted,
        )
        return SyncRunResult(
            id=run_id,
            workspace_id=workspace.id,
            started_at=started_at,
            completed_at=completed_at,
            status=status,
            files_added=files_added,
            files_updated=files_updated,
            files_deleted=files_deleted,
            error_message=error_message,
        )

    def workspace_data_dir(self, workspace_id: str) -> Path:
        return self.data_root / f"ws_{workspace_id}"

    def ensure_workspace_storage(self, workspace_id: str) -> Path:
        workspace_dir = self.workspace_data_dir(workspace_id)
        workspace_dir.mkdir(parents=True, exist_ok=True)

        # // SPEC-013-005: Resolve workspace index to canonical ws_<id> directory.
        alias_dir = self._workspace_alias_dir(workspace_id)
        if alias_dir != workspace_dir and not alias_dir.exists():
            try:
                alias_dir.symlink_to(workspace_dir, target_is_directory=True)
            except OSError:
                # Best-effort fallback where symlinks are unavailable.
                logger.warning(
                    "workspace.storage.symlink_unavailable workspace_id=%s alias=%s",
                    workspace_id,
                    alias_dir,
                )
        return workspace_dir

    def _insert_source_row(self, conn: Any, workspace_id: str, source: DataSource) -> str:
        source_type, config_json = self._normalize_source(source)
        source_id = str(uuid.uuid4())

        try:
            conn.execute(
                """
                INSERT INTO data_sources(id, workspace_id, source_type, source_config, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (source_id, workspace_id, source_type, config_json, self._utc_now()),
            )
        except sqlite3.IntegrityError as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise ValueError("Source already exists in workspace.") from exc
            raise
        return source_id

    def _insert_access_row(self, conn: Any, workspace_id: str, email: str) -> None:
        normalized = self._normalize_email(email, validate=True)
        conn.execute(
            """
            INSERT OR IGNORE INTO workspace_access(id, workspace_id, email, granted_at)
            VALUES (?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), workspace_id, normalized, self._utc_now()),
        )

    def _list_sources(self, workspace_id: str) -> list[DataSource]:
        with self.db.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, workspace_id, source_type, source_config, created_at
                FROM data_sources
                WHERE workspace_id = ?
                ORDER BY created_at ASC
                """,
                (workspace_id,),
            ).fetchall()
        return [self._row_to_source(row) for row in rows]

    def _sync_local_source(self, workspace_id: str, source: DataSource) -> int:
        source_path = Path(source.source_config["path"]).expanduser()
        if not source_path.exists():
            raise FileNotFoundError(f"Local source path '{source_path}' does not exist.")

        target_dir = self.workspace_data_dir(workspace_id) / "local-cache" / source.id
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(source_path, target_dir)
        return sum(1 for path in target_dir.rglob("*") if path.is_file())

    def _sync_m365_source(self, connector: GraphConnector, source: DataSource) -> int:
        if source.source_type == "drive":
            return connector.sync_drive()
        if source.source_type == "mail":
            return connector.sync_mail()
        if source.source_type == "notes":
            return connector.sync_notes()
        if source.source_type == "sharepoint":
            # Existing connector path for tenant-backed drive/sharepoint document stores.
            return connector.sync_drive()
        raise ValueError(f"Unsupported source type '{source.source_type}'.")

    def _source_error_message(self, source: DataSource | None, exc: Exception) -> str:
        label = "workspace"
        if source is not None:
            config_value = source.source_config.get(SOURCE_REQUIRED_CONFIG[source.source_type], "")
            label = f"{source.source_type}:{config_value}"
        return f"Source sync failed: {label} ({self._sanitize_error(exc)})."

    def _validate_workspace_name(self, name: str) -> None:
        if not WORKSPACE_NAME_PATTERN.fullmatch(name) or "/" in name or "\\" in name:
            # // EDGE-013-002: Invalid workspace names are rejected deterministically.
            raise ValueError(
                "Workspace name is invalid. Use 1-100 characters: letters, numbers, space, _, -, ."
            )

    def _normalize_source(self, source: DataSource) -> tuple[str, str]:
        source_type = source.source_type
        if source_type not in VALID_SOURCE_TYPES:
            valid = ", ".join(VALID_SOURCE_TYPES)
            raise ValueError(f"Unsupported source type '{source_type}'. Valid types: {valid}.")

        required_key = SOURCE_REQUIRED_CONFIG[source_type]
        raw_config = source.source_config
        if required_key not in raw_config or not str(raw_config[required_key]).strip():
            raise ValueError(f"Source type '{source_type}' requires config key '{required_key}'.")

        normalized_config = dict(raw_config)
        if source_type == "local":
            local_path = Path(str(normalized_config["path"])).expanduser().resolve()
            if not local_path.exists():
                raise ValueError(f"Local source path '{local_path}' does not exist.")
            normalized_config["path"] = str(local_path)

        config_json = json.dumps(normalized_config, sort_keys=True, separators=(",", ":"))
        return source_type, config_json

    def _normalize_email(self, email: str, *, validate: bool) -> str:
        normalized = email.strip().lower()
        if validate and not EMAIL_PATTERN.fullmatch(normalized):
            # // EDGE-013-007: Malformed ACL emails are rejected without mutating ACL.
            raise ValueError(f"Invalid email address '{email}'.")
        return normalized

    def _workspace_alias_dir(self, workspace_id: str) -> Path:
        workspace_dir = self.workspace_data_dir(workspace_id)
        canonical = os.path.realpath(str(workspace_dir))
        short_hash = hashlib.sha256(canonical.encode()).hexdigest()[:12]
        return self.data_root / short_hash

    def _remove_workspace_storage(self, workspace_id: str) -> None:
        workspace_dir = self.workspace_data_dir(workspace_id)
        alias_dir = self._workspace_alias_dir(workspace_id)

        if alias_dir.is_symlink():
            alias_dir.unlink(missing_ok=True)
        elif alias_dir.exists() and alias_dir.is_dir():
            shutil.rmtree(alias_dir, ignore_errors=True)

        if workspace_dir.exists():
            shutil.rmtree(workspace_dir, ignore_errors=True)

    def _row_to_workspace(self, row: Any) -> Workspace:
        return Workspace(
            id=str(row["id"]),
            name=str(row["name"]),
            description=row["description"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            last_synced_at=row["last_synced_at"],
            sync_status=str(row["sync_status"]),
        )

    def _row_to_source(self, row: Any) -> DataSource:
        return DataSource(
            id=str(row["id"]),
            workspace_id=str(row["workspace_id"]),
            source_type=str(row["source_type"]),
            source_config=json.loads(str(row["source_config"])),
            created_at=str(row["created_at"]),
        )

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _sanitize_error(exc: Exception) -> str:
        text = str(exc).replace("\n", " ").strip()
        return text[:200]

    @staticmethod
    def _email_hash_prefix(email: str) -> str:
        return hashlib.sha256(email.encode("utf-8")).hexdigest()[:8]
