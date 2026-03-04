from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pytest

import codesight.api as api_module
import codesight.config as config_module
import codesight.workspace.db as db_module
import codesight.workspace.manager as manager_module
from codesight import __main__ as cli
from codesight.api import CodeSight
from codesight.config import ServerConfig
from codesight.types import DataSource, IndexStats
from codesight.workspace import (
    CORRUPTED_DB_MESSAGE,
    WorkspaceAccessDenied,
    WorkspaceDB,
    WorkspaceManager,
)


def _manager(tmp_path: Path) -> WorkspaceManager:
    root = tmp_path / ".codesight"
    return WorkspaceManager(db_path=root / "workspaces.db", data_root=root / "data")


def _workspace_db_path(tmp_path: Path) -> Path:
    return tmp_path / ".codesight" / "workspaces.db"


class _StubIndexerEngine:
    def __init__(self, _path: str | Path) -> None:
        pass

    def index(self) -> IndexStats:
        return IndexStats(
            repo_path="stub",
            files_indexed=1,
            chunks_created=0,
            chunks_skipped_unchanged=0,
            chunks_deleted=0,
            total_chunks=0,
            elapsed_seconds=0.0,
        )


class _StubEmbedder:
    def __init__(self, dim: int = 768) -> None:
        self.model_name = "stub-embedder"
        self.expected_dim = dim

    def embed_query(self, _query: str):
        return np.zeros(self.expected_dim, dtype=float)


def test_spec_013_001_first_operation_creates_workspaces_db_when_missing(tmp_path: Path):
    db_path = _workspace_db_path(tmp_path)
    assert not db_path.exists()

    manager = _manager(tmp_path)
    manager.list()

    assert db_path.exists()


def test_spec_013_001_schema_version_1_exists_after_bootstrap(tmp_path: Path):
    db_path = _workspace_db_path(tmp_path)
    WorkspaceDB(db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT version FROM schema_version").fetchone()

    assert row is not None
    assert row[0] == 1


def test_spec_013_001_migrations_run_transactionally_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    db_path = _workspace_db_path(tmp_path)
    real_connect = sqlite3.connect

    class _FailingConnection(sqlite3.Connection):
        def execute(self, sql, parameters=(), /):  # type: ignore[override]
            if "CREATE TABLE IF NOT EXISTS data_sources" in sql:
                raise sqlite3.OperationalError("forced migration failure")
            return super().execute(sql, parameters)

    def _failing_connect(*args, **kwargs):
        kwargs["factory"] = _FailingConnection
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(db_module.sqlite3, "connect", _failing_connect)

    with pytest.raises(sqlite3.OperationalError, match="forced migration failure"):
        WorkspaceDB(db_path=db_path)

    with real_connect(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN (?, ?, ?)",
            ("workspaces", "data_sources", "workspace_access"),
        ).fetchall()

    assert rows == []


def test_spec_013_001_corrupted_db_raises_runtime_error_with_exact_message(tmp_path: Path):
    db_path = _workspace_db_path(tmp_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_text("not a sqlite database", encoding="utf-8")

    with pytest.raises(RuntimeError, match=re.escape(CORRUPTED_DB_MESSAGE)):
        WorkspaceDB(db_path=db_path)


def test_spec_013_002_create_inserts_row_and_creates_workspace_dir(tmp_path: Path):
    manager = _manager(tmp_path)

    workspace = manager.create("Sales KB", description="Sales docs")

    assert manager.workspace_data_dir(workspace.id).is_dir()
    with manager.db.connection() as conn:
        row = conn.execute(
            "SELECT name, description FROM workspaces WHERE id = ?", (workspace.id,)
        ).fetchone()

    assert row is not None
    assert row["name"] == "Sales KB"
    assert row["description"] == "Sales docs"


def test_spec_013_002_list_returns_all_workspaces_with_expected_fields(tmp_path: Path):
    manager = _manager(tmp_path)
    a = manager.create("Alpha")
    b = manager.create("Beta", description="Team B")

    rows = manager.list()
    ids = {row.id for row in rows}

    assert ids == {a.id, b.id}
    assert {row.sync_status for row in rows} == {"never"}
    assert all(hasattr(row, "last_synced_at") for row in rows)


def test_spec_013_002_update_changes_name_when_unique(tmp_path: Path):
    manager = _manager(tmp_path)
    workspace = manager.create("Sales")

    updated = manager.update(workspace.id, name="Sales Updated")

    assert updated.name == "Sales Updated"


def test_spec_013_002_delete_removes_dir_and_cascades_related_rows(tmp_path: Path):
    manager = _manager(tmp_path)
    source_dir = tmp_path / "docs"
    source_dir.mkdir()
    (source_dir / "a.txt").write_text("hello", encoding="utf-8")

    workspace = manager.create(
        "Sales",
        sources=[DataSource(source_type="local", source_config={"path": str(source_dir)})],
        allowed_emails=["a@example.com"],
    )
    workspace_dir = manager.workspace_data_dir(workspace.id)
    assert workspace_dir.exists()

    manager.delete(workspace.id)

    assert not workspace_dir.exists()
    with manager.db.connection() as conn:
        workspace_count = conn.execute(
            "SELECT COUNT(*) FROM workspaces WHERE id = ?", (workspace.id,)
        ).fetchone()[0]
        source_count = conn.execute(
            "SELECT COUNT(*) FROM data_sources WHERE workspace_id = ?", (workspace.id,)
        ).fetchone()[0]
        acl_count = conn.execute(
            "SELECT COUNT(*) FROM workspace_access WHERE workspace_id = ?", (workspace.id,)
        ).fetchone()[0]

    assert workspace_count == 0
    assert source_count == 0
    assert acl_count == 0


def test_spec_013_002_duplicate_name_raises_value_error_with_exact_message(tmp_path: Path):
    manager = _manager(tmp_path)
    manager.create("Sales KB")

    with pytest.raises(ValueError, match=re.escape("Workspace 'Sales KB' already exists.")):
        manager.create("sales kb")


def test_spec_013_003_valid_source_type_stores_correctly(tmp_path: Path):
    manager = _manager(tmp_path)

    workspace = manager.create(
        "Sales",
        sources=[
            DataSource(
                source_type="drive",
                source_config={"path": "/Shared Documents/Sales"},
            )
        ],
    )

    with manager.db.connection() as conn:
        row = conn.execute(
            "SELECT source_type, source_config FROM data_sources WHERE workspace_id = ?",
            (workspace.id,),
        ).fetchone()

    assert row is not None
    assert row["source_type"] == "drive"
    assert json.loads(row["source_config"]) == {"path": "/Shared Documents/Sales"}


def test_spec_013_003_local_source_nonexistent_path_raises_value_error(tmp_path: Path):
    manager = _manager(tmp_path)
    workspace = manager.create("Sales")
    missing_path = (tmp_path / "missing-local").resolve()

    with pytest.raises(
        ValueError,
        match=re.escape(f"Local source path '{missing_path}' does not exist."),
    ):
        manager.add_source(
            workspace.id,
            DataSource(source_type="local", source_config={"path": str(missing_path)}),
        )


def test_spec_013_003_unknown_source_type_raises_exact_message(tmp_path: Path):
    manager = _manager(tmp_path)
    workspace = manager.create("Sales")

    with pytest.raises(
        ValueError,
        match=re.escape(
            "Unsupported source type 'ftp'. Valid types: drive, mail, notes, sharepoint, local."
        ),
    ):
        manager.add_source(
            workspace.id,
            DataSource(source_type="ftp", source_config={"path": "/tmp/x"}),
        )


def test_spec_013_003_duplicate_source_raises_value_error(tmp_path: Path):
    manager = _manager(tmp_path)
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    workspace = manager.create("Sales")
    source = DataSource(source_type="local", source_config={"path": str(source_dir)})

    manager.add_source(workspace.id, source)
    with pytest.raises(ValueError, match=re.escape("Source already exists in workspace.")):
        manager.add_source(workspace.id, source)


def test_spec_013_004_sync_creates_running_row_then_marks_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    manager = _manager(tmp_path)
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "doc.txt").write_text("hello", encoding="utf-8")
    workspace = manager.create(
        "Sales",
        sources=[DataSource(source_type="local", source_config={"path": str(source_dir)})],
    )

    observed = {"running_seen": False}
    original_sync_local = manager_module.WorkspaceManager._sync_local_source

    def _checking_sync_local(self, workspace_id: str, source: DataSource) -> int:
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT status FROM sync_runs "
                "WHERE workspace_id = ? ORDER BY started_at DESC LIMIT 1",
                (workspace_id,),
            ).fetchone()
        observed["running_seen"] = bool(row and row["status"] == "running")
        return original_sync_local(self, workspace_id, source)

    monkeypatch.setattr(manager_module, "CodeSight", _StubIndexerEngine)
    monkeypatch.setattr(manager_module.WorkspaceManager, "_sync_local_source", _checking_sync_local)

    result = manager.sync(workspace.id)

    assert observed["running_seen"] is True
    assert result.status == "ok"
    with manager.db.connection() as conn:
        run_status = conn.execute(
            "SELECT status FROM sync_runs WHERE id = ?", (result.id,)
        ).fetchone()[0]

    assert run_status == "ok"


def test_spec_013_004_source_failures_do_not_abort_other_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    manager = _manager(tmp_path)

    good_source_dir = tmp_path / "good-source"
    bad_source_dir = tmp_path / "bad-source"
    good_source_dir.mkdir()
    bad_source_dir.mkdir()
    (good_source_dir / "ok.txt").write_text("ok", encoding="utf-8")

    workspace = manager.create(
        "Sales",
        sources=[
            DataSource(source_type="local", source_config={"path": str(good_source_dir)}),
            DataSource(source_type="local", source_config={"path": str(bad_source_dir)}),
        ],
    )
    bad_source_dir.rmdir()

    monkeypatch.setattr(manager_module, "CodeSight", _StubIndexerEngine)

    result = manager.sync(workspace.id)

    assert result.status == "error"
    assert result.error_message is not None
    assert "Source sync failed:" in result.error_message

    sources = manager._list_sources(workspace.id)
    good_source = next(
        s for s in sources if s.source_config["path"] == str(good_source_dir.resolve())
    )
    copied_file = (
        manager.workspace_data_dir(workspace.id) / "local-cache" / good_source.id / "ok.txt"
    )
    assert copied_file.exists()


def test_spec_013_004_sync_updates_last_synced_at_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    manager = _manager(tmp_path)
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "a.txt").write_text("a", encoding="utf-8")
    workspace = manager.create(
        "Sales",
        sources=[DataSource(source_type="local", source_config={"path": str(source_dir)})],
    )

    monkeypatch.setattr(manager_module, "CodeSight", _StubIndexerEngine)
    manager.sync(workspace.id)
    refreshed = manager.get(workspace.id)

    assert refreshed.sync_status == "ok"
    assert refreshed.last_synced_at is not None


def test_spec_013_005_query_workspace_a_never_returns_workspace_b_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "engine-data")

    manager = WorkspaceManager()
    ws_a = manager.create("Workspace A")
    ws_b = manager.create("Workspace B")

    engine_a = CodeSight(workspace=ws_a.id, config=ServerConfig())
    engine_b = CodeSight(workspace=ws_b.id, config=ServerConfig())

    monkeypatch.setattr(CodeSight, "_ensure_indexed", lambda self: None)
    monkeypatch.setattr(api_module, "get_embedder", lambda *_args, **_kwargs: _StubEmbedder())

    engine_a.store.fts.upsert_chunk(
        chunk_id="a-1",
        file_path="a.txt",
        start_line=1,
        end_line=1,
        scope="line 1",
        language="text",
        content_hash="hash-a",
        content="alpha unique",
    )
    engine_a.store.fts.commit()

    engine_b.store.fts.upsert_chunk(
        chunk_id="b-1",
        file_path="b.txt",
        start_line=1,
        end_line=1,
        scope="line 1",
        language="text",
        content_hash="hash-b",
        content="bravo unique",
    )
    engine_b.store.fts.commit()

    a_results = engine_a.search("alpha", top_k=5)
    b_results = engine_b.search("bravo", top_k=5)
    cross_results = engine_a.search("bravo", top_k=5)

    assert [row.chunk_id for row in a_results] == ["a-1"]
    assert [row.chunk_id for row in b_results] == ["b-1"]
    assert cross_results == []


def test_spec_013_006_allow_stores_lowercase_email(tmp_path: Path):
    manager = _manager(tmp_path)
    workspace = manager.create("Sales")

    manager.allow(workspace.id, "User.Name@Example.COM")

    with manager.db.connection() as conn:
        row = conn.execute(
            "SELECT email FROM workspace_access WHERE workspace_id = ?", (workspace.id,)
        ).fetchone()

    assert row is not None
    assert row["email"] == "user.name@example.com"


def test_spec_013_006_check_access_is_case_insensitive(tmp_path: Path):
    manager = _manager(tmp_path)
    workspace = manager.create("Sales")
    manager.allow(workspace.id, "user@example.com")

    assert manager.check_access(workspace.id, "USER@EXAMPLE.COM") is True


def test_spec_013_006_empty_acl_denies_all(tmp_path: Path):
    manager = _manager(tmp_path)
    workspace = manager.create("Sales")

    assert manager.check_access(workspace.id, "user@example.com") is False


def test_spec_013_006_deny_removes_email_and_future_checks_fail(tmp_path: Path):
    manager = _manager(tmp_path)
    workspace = manager.create("Sales")
    manager.allow(workspace.id, "user@example.com")

    manager.deny(workspace.id, "USER@EXAMPLE.COM")

    assert manager.check_access(workspace.id, "user@example.com") is False


def test_spec_013_006_invalid_email_raises_value_error(tmp_path: Path):
    manager = _manager(tmp_path)
    workspace = manager.create("Sales")

    with pytest.raises(ValueError, match=re.escape("Invalid email address 'bad-email'.")):
        manager.allow(workspace.id, "bad-email")


def test_spec_013_007_cli_creates_workspace_and_outputs_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    monkeypatch.setattr(sys, "argv", ["codesight", "workspace", "create", "Sales KB"])
    cli.main()

    out = capsys.readouterr().out
    assert "Created workspace 'Sales KB'" in out


def test_spec_013_007_cli_list_outputs_expected_columns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    monkeypatch.setattr(sys, "argv", ["codesight", "workspace", "create", "Alpha"])
    cli.main()
    capsys.readouterr()

    monkeypatch.setattr(sys, "argv", ["codesight", "workspace", "list"])
    cli.main()

    out = capsys.readouterr().out.splitlines()
    assert out
    header_tokens = re.split(r"\s{2,}", out[0].strip())
    assert header_tokens == ["id", "name", "sync_status", "last_synced_at"]
    assert any("Alpha" in line for line in out[1:])


def test_spec_013_008_codesight_path_mode_still_works_without_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "engine-data")

    docs = tmp_path / "docs"
    docs.mkdir()
    # Corrupted workspace DB should not affect legacy folder-path mode.
    workspaces_db = tmp_path / ".codesight" / "workspaces.db"
    workspaces_db.parent.mkdir(parents=True, exist_ok=True)
    workspaces_db.write_text("broken", encoding="utf-8")

    engine = CodeSight(docs)

    assert engine.workspace_id is None
    assert engine.folder_path == docs.resolve()


def test_edge_013_001_duplicate_workspace_name_rejected_before_filesystem_writes(tmp_path: Path):
    manager = _manager(tmp_path)
    manager.create("Sales KB")
    existing_dirs = set(manager.data_root.iterdir())

    with pytest.raises(ValueError, match=re.escape("Workspace 'Sales KB' already exists.")):
        manager.create("sales kb")

    assert set(manager.data_root.iterdir()) == existing_dirs


def test_edge_013_002_invalid_workspace_name_rejected(tmp_path: Path):
    manager = _manager(tmp_path)

    with pytest.raises(
        ValueError,
        match=re.escape(
            "Workspace name is invalid. Use 1-100 characters: letters, numbers, space, _, -, ."
        ),
    ):
        manager.create("bad/name")


def test_edge_013_003_sync_lock_conflict_returns_deterministic_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    manager = _manager(tmp_path)
    workspace = manager.create("Sales KB")

    with manager.db.transaction() as conn:
        conn.execute("UPDATE workspaces SET sync_status = 'syncing' WHERE id = ?", (workspace.id,))

    monkeypatch.setattr(manager_module, "CodeSight", _StubIndexerEngine)
    with pytest.raises(
        RuntimeError,
        match=re.escape(f"Sync already in progress for workspace '{workspace.name}'."),
    ):
        manager.sync(workspace.id)


def test_edge_013_004_delete_during_sync_fails_without_force(tmp_path: Path):
    manager = _manager(tmp_path)
    workspace = manager.create("Sales KB")

    with manager.db.transaction() as conn:
        conn.execute("UPDATE workspaces SET sync_status = 'syncing' WHERE id = ?", (workspace.id,))

    with pytest.raises(
        ValueError,
        match=re.escape(
            "Workspace 'Sales KB' is syncing. Wait for sync completion or use --force."
        ),
    ):
        manager.delete(workspace.id)


def test_edge_013_005_source_unreachable_marks_error_and_continues_other_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    manager = _manager(tmp_path)
    good_source_dir = tmp_path / "good"
    bad_source_dir = tmp_path / "bad"
    good_source_dir.mkdir()
    bad_source_dir.mkdir()
    (good_source_dir / "ok.txt").write_text("ok", encoding="utf-8")

    workspace = manager.create(
        "Sales KB",
        sources=[
            DataSource(source_type="local", source_config={"path": str(good_source_dir)}),
            DataSource(source_type="local", source_config={"path": str(bad_source_dir)}),
        ],
    )
    bad_source_dir.rmdir()

    monkeypatch.setattr(manager_module, "CodeSight", _StubIndexerEngine)
    result = manager.sync(workspace.id)

    assert result.status == "error"
    assert result.error_message is not None
    assert "Source sync failed:" in result.error_message
    assert "does not exist" in result.error_message


def test_edge_013_006_corrupted_workspaces_db_fails_with_repair_guidance(tmp_path: Path):
    db_path = _workspace_db_path(tmp_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_text("not a db", encoding="utf-8")

    with pytest.raises(RuntimeError, match=re.escape(CORRUPTED_DB_MESSAGE)):
        WorkspaceManager(db_path=db_path, data_root=tmp_path / "data")


def test_edge_013_007_invalid_acl_email_rejected_without_acl_mutation(tmp_path: Path):
    manager = _manager(tmp_path)
    workspace = manager.create("Sales KB")

    with pytest.raises(ValueError, match=re.escape("Invalid email address 'bad'.")):
        manager.allow(workspace.id, "bad")

    with manager.db.connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM workspace_access WHERE workspace_id = ?", (workspace.id,)
        ).fetchone()[0]

    assert count == 0


def test_edge_013_008_empty_acl_query_attempt_denied_with_exact_message(tmp_path: Path):
    manager = _manager(tmp_path)
    workspace = manager.create("Sales KB")

    with pytest.raises(
        WorkspaceAccessDenied,
        match=re.escape(
            "You don't have access to workspace 'Sales KB'. Contact your admin."
        ),
    ):
        manager.require_access(workspace.id, "user@example.com")


def test_spec_013_007_unknown_workspace_subcommand_exits_1_and_prints_valid_commands(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    monkeypatch.setattr(sys, "argv", ["codesight", "workspace", "nope"])

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "Unknown workspace subcommand 'nope'." in out
    assert "Valid subcommands:" in out


def test_spec_013_007_delete_without_yes_prompts_and_aborts_on_negative_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    monkeypatch.setattr(sys, "argv", ["codesight", "workspace", "create", "Demo"])
    cli.main()
    capsys.readouterr()

    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    monkeypatch.setattr(sys, "argv", ["codesight", "workspace", "delete", "Demo"])
    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "Aborted." in out


def test_spec_013_007_repair_runs_integrity_check_and_reports_passed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    monkeypatch.setattr(sys, "argv", ["codesight", "workspace", "list"])
    cli.main()
    capsys.readouterr()

    monkeypatch.setattr(sys, "argv", ["codesight", "workspace", "repair"])
    cli.main()

    out = capsys.readouterr().out
    assert "workspaces.db integrity check passed." in out
