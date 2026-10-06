"""End-to-end public command behavior, including nonzero partial/unknown exits."""

import json
import os
import subprocess
import sys
from pathlib import Path

from .test_alignment import CODE, RENAMED, _repo


def _command(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "holusight", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        env=os.environ.copy(),
        check=False,
    )


def test_align_command_reports_candidates(tmp_path):
    repo = _repo(tmp_path, {"src/a.py": CODE, "src/b.py": RENAMED})
    result = _command(repo, "align")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "review" and report["complete"]
    assert "graph" not in report


def test_installed_holus_console_script(tmp_path):
    repo = _repo(tmp_path, {"src/a.py": CODE})
    executable = Path(sys.executable).with_name("holus")
    assert executable.exists()
    result = subprocess.run(
        [str(executable), "align"], cwd=repo, text=True, capture_output=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "ok"


def test_only_align_is_a_command(tmp_path):
    repo = _repo(tmp_path, {"src/a.py": CODE})
    for command in ("check", "status", "index", "search", "ask", "serve", "demo", "consistency"):
        result = _command(repo, command)
        assert result.returncode != 0
        assert "invalid choice" in result.stderr


def test_scope_rejects_traversal(tmp_path):
    repo = _repo(tmp_path, {"src/a.py": CODE})
    result = _command(repo, "align", "--scope", "../outside")
    assert result.returncode != 0
    assert "scope must be a repository-relative path" in result.stderr
