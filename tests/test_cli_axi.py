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


def _document_repo(tmp_path, documents):
    repo = _repo(tmp_path)
    (repo / "docs").mkdir()
    for name, text in documents.items():
        (repo / "docs" / name).write_text(text)
    subprocess.run(["git", "-C", str(repo), "add", "docs"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "document references"], check=True)
    graph_path = repo / "graphify-out/graph.json"
    graph = json.loads(graph_path.read_text())
    graph["built_at_commit"] = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    graph["nodes"].extend(
        {
            "id": name,
            "source_file": f"docs/{name}",
            "source_location": "L1",
            "file_type": "document",
        }
        for name in documents
    )
    graph_path.write_text(json.dumps(graph))
    return repo


def test_proposed_path_is_unverified_not_a_confirmed_current_reference_error(tmp_path):
    repo = _document_repo(
        tmp_path,
        {
            "intentional.md": "# Intentional plans\n\n"
            "The proposed future extension is `src/future.py` (not created yet).\n",
            "current.md": "# Current implementation\n\n"
            "The current implementation is `src/current_missing.py`.\n",
        },
    )
    before = {p.relative_to(repo): p.read_bytes() for p in repo.rglob("*") if p.is_file()}
    result = _command(repo, "check")
    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert report["provenance"]["state"] == "current"
    assert report["status"] == "error"
    assert report["errors"] == 1
    assert report["error_types"] == {"missing_path_claim": 1}
    assert report["unverified"] == 1
    planned = [f for f in report["findings"] if f["file"] == "docs/intentional.md"]
    assert len(planned) == 1
    assert planned[0]["line"] == 3
    assert planned[0]["type"] == "planned_path_reference"
    assert planned[0]["severity"] == "info"
    assert planned[0]["evidence"] == "path:src/future.py"
    scoped = _command(repo, "check", "--scope", "docs/intentional.md")
    assert scoped.returncode == 1
    scoped_report = json.loads(scoped.stdout)
    assert scoped_report["status"] == "unknown"
    assert scoped_report["errors"] == 0 and scoped_report["unverified"] == 1
    assert before == {p.relative_to(repo): p.read_bytes() for p in repo.rglob("*") if p.is_file()}


def test_proposed_annotation_applies_to_its_path_not_the_whole_line(tmp_path):
    repo = _document_repo(
        tmp_path,
        {
            "mixed.md": "The proposed extension is `src/future.py` (not created yet), "
            "but the current implementation is `src/current_missing.py`.\n"
        },
    )
    report = json.loads(_command(repo, "check").stdout)
    assert report["errors"] == 1
    assert report["unverified"] == 1
    assert {f["evidence"] for f in report["findings"] if f["severity"] == "error"} == {
        "path:src/current_missing.py"
    }


def test_planned_findings_remain_bounded_with_honest_counts(tmp_path):
    repo = _document_repo(
        tmp_path,
        {
            "many.md": "".join(f"`src/future{i}.py` (not created yet)\n" for i in range(30))
            + "The current implementation is `src/current_missing.py`.\n"
        },
    )
    report = json.loads(_command(repo, "check").stdout)
    assert report["errors"] == 1 and report["unverified"] == 30
    assert len(report["findings"]) == 16 and report["truncated"]
    assert sum(f["severity"] == "error" for f in report["findings"]) == 1


def test_unannotated_future_mentions_do_not_infer_prose_intent(tmp_path):
    repo = _document_repo(
        tmp_path,
        {
            "future.md": "Future work depends on the current `src/current_missing.py`.\n"
            "The proposed next step also uses `src/other_missing.py`.\n"
            "The current implementation is `src/third_missing.py`; a different extension is "
            "not created yet.\n"
        },
    )
    report = json.loads(_command(repo, "check").stdout)
    assert report["errors"] == 3 and report["unverified"] == 0
    assert all(f["severity"] == "error" for f in report["findings"])


def test_planned_annotation_does_not_downgrade_an_unsafe_path(tmp_path):
    repo = _document_repo(
        tmp_path,
        {"unsafe.md": "The proposed extension is `src/../../outside.py` (not created yet).\n"},
    )
    report = json.loads(_command(repo, "check").stdout)
    assert report["errors"] == 1 and report["unverified"] == 0
    assert report["findings"][0]["severity"] == "error"


def test_scope_rejects_traversal(tmp_path):
    repo = _repo(tmp_path)
    result = _command(repo, "check", "--scope", "../outside")
    assert result.returncode != 0
    assert "scope must be a repository-relative path" in result.stderr
