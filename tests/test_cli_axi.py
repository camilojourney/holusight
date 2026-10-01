"""End-to-end public command behavior, including nonzero unknown/stale exits."""

import json
import os
import subprocess
import sys
from pathlib import Path

from .test_consistency import _repo


def _command(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "holusight", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        env=os.environ.copy(),
        check=False,
    )


def test_check_and_status_commands(tmp_path):
    repo = _repo(tmp_path)
    result = _command(repo, "check")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "current"
    result = _command(repo, "status")
    assert result.returncode == 0
    assert json.loads(result.stdout)["provenance"]["state"] == "current"
    graph = json.loads((repo / "graphify-out/graph.json").read_text())
    graph.pop("built_at_commit")
    (repo / "graphify-out/graph.json").write_text(json.dumps(graph))
    result = _command(repo, "check")
    assert result.returncode == 1
    assert json.loads(result.stdout)["status"] == "unknown"


def test_installed_holus_console_script(tmp_path):
    repo = _repo(tmp_path)
    executable = Path(sys.executable).with_name("holus")
    assert executable.exists()
    result = subprocess.run(
        [str(executable), "check"], cwd=repo, text=True, capture_output=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "current"


def test_no_search_or_index_entry_points(tmp_path):
    repo = _repo(tmp_path)
    for command in ("index", "search", "ask", "serve", "demo", "consistency"):
        result = _command(repo, command)
        assert result.returncode != 0
        assert "invalid choice" in result.stderr


def test_public_command_rejects_invalid_source_location(tmp_path):
    repo = _repo(tmp_path)
    graph_path = repo / "graphify-out/graph.json"
    graph = json.loads(graph_path.read_text())
    graph["nodes"][0]["source_location"] = "L0"
    graph_path.write_text(json.dumps(graph))
    result = _command(repo, "check")
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["status"] == "error"
    assert report["error_types"] == {"invalid_source_location": 1}


def test_scope_rejects_traversal(tmp_path):
    repo = _repo(tmp_path)
    result = _command(repo, "check", "--scope", "../outside")
    assert result.returncode != 0
    assert "scope must be a repository-relative path" in result.stderr
