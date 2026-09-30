"""Behavioral tests for read-only Graphify/source checks."""

import json
import subprocess
from pathlib import Path

import pytest

from holusight import Holusight
from holusight.consistency import check


def _repo(tmp_path: Path, *, graph_commit: str | None = "head") -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    (repo / ".gitignore").write_text("graphify-out/\n")
    (repo / "src").mkdir()
    (repo / "src/mod.py").write_text("def hello():\n    return 1\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "baseline"], check=True)
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    (repo / "graphify-out").mkdir()
    graph = {
        "built_at_commit": head if graph_commit == "head" else graph_commit,
        "nodes": [
            {
                "id": "hello",
                "source_file": "src/mod.py",
                "source_location": "L1",
                "file_type": "code",
            }
        ],
        "links": [
            {
                "source": "hello",
                "target": "hello",
                "relation": "calls",
                "source_file": "src/mod.py",
                "source_location": "L1",
            }
        ],
    }
    (repo / "graphify-out/graph.json").write_text(json.dumps(graph))
    return repo


def test_check_is_read_only_and_offline(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    graph_path = repo / "graphify-out/graph.json"
    before = {
        p.relative_to(repo): p.read_bytes()
        for p in repo.rglob("*")
        if p.is_file() and ".git" not in p.parts
    }
    import holusight.consistency as checker

    original_run = checker.subprocess.run

    def git_only(command, *args, **kwargs):
        assert command[0] == "git"
        return original_run(command, *args, **kwargs)

    monkeypatch.setattr(checker.subprocess, "run", git_only)
    assert check(repo)["status"] == "current"
    assert graph_path.is_file()
    after = {
        p.relative_to(repo): p.read_bytes()
        for p in repo.rglob("*")
        if p.is_file() and ".git" not in p.parts
    }
    assert before == after


def test_clean_graph_with_provenance_is_current(tmp_path):
    repo = _repo(tmp_path)
    result = Holusight(repo).check()
    assert result["status"] == "current"
    assert result["errors"] == 0
    assert result["checked"] >= 2


def test_unverified_oversized_source_prevents_clean_verdict(tmp_path):
    repo = _repo(tmp_path)
    (repo / "src/mod.py").write_text("#" * 2_000_001 + "\n")
    subprocess.run(["git", "-C", str(repo), "add", "src/mod.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "large source"], check=True)
    graph_path = repo / "graphify-out/graph.json"
    graph = json.loads(graph_path.read_text())
    graph["built_at_commit"] = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    graph_path.write_text(json.dumps(graph))
    result = check(repo)
    assert result["status"] == "unknown"
    assert result["unverified"] >= 1
    assert result["errors"] == 0


def test_broken_graph_edge_and_missing_source_report_evidence(tmp_path):
    repo = _repo(tmp_path)
    graph_path = repo / "graphify-out/graph.json"
    graph = json.loads(graph_path.read_text())
    graph["nodes"].append({"id": "missing", "source_file": "src/gone.py", "source_location": "L1"})
    graph["links"][0]["target"] = "not_a_node"
    graph_path.write_text(json.dumps(graph))
    result = check(repo)
    assert result["status"] == "error"
    assert {item["type"] for item in result["findings"]} == {"missing_source", "dangling_edge"}
    assert any(item["evidence"] == "node:missing" for item in result["findings"])


def test_dirty_or_mismatched_graph_never_reports_current(tmp_path):
    repo = _repo(tmp_path, graph_commit="0" * 40)
    assert check(repo)["status"] == "stale"
    graph_path = repo / "graphify-out/graph.json"
    graph = json.loads(graph_path.read_text())
    graph["built_at_commit"] = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    graph_path.write_text(json.dumps(graph))
    (repo / "src/mod.py").write_text("def changed():\n    return 2\n")
    assert check(repo)["status"] == "stale"
    graph.pop("built_at_commit")
    graph_path.write_text(json.dumps(graph))
    assert check(repo)["status"] == "unknown"


def test_nested_directory_cannot_inherit_parent_git_provenance(tmp_path):
    repo = _repo(tmp_path)
    nested = repo / "nested"
    nested.mkdir()
    (nested / "graphify-out").mkdir()
    (nested / "graphify-out/graph.json").write_bytes(
        (repo / "graphify-out/graph.json").read_bytes()
    )
    assert check(nested)["status"] == "unknown"


def test_missing_malformed_and_unsafe_graph_are_unavailable(tmp_path):
    repo = _repo(tmp_path)
    graph_path = repo / "graphify-out/graph.json"
    graph_path.unlink()
    assert check(repo)["status"] == "unavailable"
    graph_path.write_text("not json")
    assert check(repo)["status"] == "unavailable"
    graph_path.unlink()
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    graph_path.symlink_to(outside)
    assert check(repo)["status"] == "unavailable"


def test_graph_source_symlink_escape_is_reported_without_reading(tmp_path):
    repo = _repo(tmp_path)
    outside = tmp_path / "secret.py"
    outside.write_text("SECRET_DO_NOT_EXPOSE\n")
    (repo / "src/escaped.py").symlink_to(outside)
    graph_path = repo / "graphify-out/graph.json"
    graph = json.loads(graph_path.read_text())
    graph["nodes"].append({"id": "escaped", "source_file": "src/escaped.py"})
    graph_path.write_text(json.dumps(graph))
    result = check(repo)
    assert result["status"] == "stale"  # untracked symlink invalidates provenance
    assert any(f["type"] == "unsafe_path" for f in result["findings"])
    assert "SECRET_DO_NOT_EXPOSE" not in json.dumps(result)


def test_malformed_edge_does_not_crash_or_escape(tmp_path):
    repo = _repo(tmp_path)
    graph_path = repo / "graphify-out/graph.json"
    graph = json.loads(graph_path.read_text())
    graph["links"][0]["target"] = {"malformed": "object"}
    graph_path.write_text(json.dumps(graph))
    assert check(repo)["findings"][0]["type"] == "dangling_edge"


def test_scoped_path_cannot_escape_repository(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(ValueError):
        check(repo, scope="../outside")
    with pytest.raises(ValueError):
        check(repo, scope="/etc/passwd")
    assert check(repo, refresh=True)["status"] == "unavailable"
    assert check(repo, scope="src/not-in-graph.py")["status"] == "unknown"


def test_explicit_path_claim_and_missing_line(tmp_path):
    repo = _repo(tmp_path)
    (repo / "docs").mkdir()
    (repo / "docs/guide.md").write_text("See `src/gone.py` for details.\n")
    subprocess.run(["git", "-C", str(repo), "add", "docs/guide.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "docs"], check=True)
    graph_path = repo / "graphify-out/graph.json"
    graph = json.loads(graph_path.read_text())
    graph["built_at_commit"] = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    graph["nodes"].append(
        {
            "id": "guide",
            "file_type": "document",
            "source_file": "docs/guide.md",
            "source_location": "L9",
        }
    )
    graph_path.write_text(json.dumps(graph))
    result = check(repo)
    assert result["status"] == "error"
    assert {item["type"] for item in result["findings"]} == {"missing_line", "missing_path_claim"}
    assert any(item["file"] == "docs/guide.md" and item["line"] == 1 for item in result["findings"])
