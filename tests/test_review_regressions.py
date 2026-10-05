"""Executable regressions for terminal R1–R5; no analyzed program is executed."""

import json
import subprocess
from contextlib import contextmanager
from pathlib import Path

import pytest

from holusight import Holusight
from holusight import consistency as checker

from .test_alignment import _public
from .test_alignment import _repo as alignment_repo
from .test_cli_axi import _command, _document_repo
from .test_consistency import _repo


@pytest.mark.parametrize(
    "rebinding",
    [
        "OTHER = (LIMIT := 5)\n",
        "def f(value=(LIMIT := 5)):\n    return value\n",
        "@(LIMIT := lambda fn: fn)\ndef f():\n    return 3\n",
        "class Child((LIMIT := object)):\n    pass\n",
        "del LIMIT\n",
        "try:\n    risky()\nexcept Exception as LIMIT:\n    pass\n",
        "match payload:\n    case {'a': LIMIT}:\n        pass\n",
        "from another_module import *\n",
        "OTHER: (LIMIT := int) = 5\n",
    ],
)
def test_r1_unsupported_rebinding_cannot_certify_original_scalar(tmp_path, rebinding):
    repo = alignment_repo(
        tmp_path,
        {
            "src/a.py": "LIMIT = 3\n" + rebinding + "# holus:fact retries = LIMIT\n",
            "docs/a.md": "<!-- holus:fact retries = 3 -->\n",
        },
    )
    command = _public(repo)
    report = json.loads(command.stdout)
    assert command.returncode == 1
    assert report["status"] == "partial" and not report["complete"]
    assert report["coverage"]["facts"] == 1  # only the explicit doc contract
    assert report["skipped_count"] == 1


@pytest.mark.parametrize(
    "source",
    [
        "LIMIT = 3\ndef f():\n    LIMIT = 5\n    # holus:fact retries = LIMIT\n",
        "LIMIT = 3\nclass Consumer:\n    LIMIT = 5\n    # holus:fact retries = LIMIT\n",
        "LIMIT = 3\ndef f():\n    # holus:fact retries = LIMIT\n    LIMIT = 5\n",
    ],
)
def test_r1_nonmodule_marker_does_not_resolve_module_binding(tmp_path, source):
    repo = alignment_repo(
        tmp_path, {"src/a.py": source, "guide.md": "<!-- holus:fact retries = 3 -->"}
    )
    report = json.loads(_public(repo).stdout)
    assert report["status"] == "partial"
    assert report["coverage"]["facts"] == 1


@pytest.mark.parametrize(
    "source",
    [
        "LIMIT = 3\n# holus:fact retries = LIMIT\n",
        "LIMIT = 3  # holus:fact retries = LIMIT\n",
        "LIMIT = 3\ndef f():\n    LIMIT = 5\n    return LIMIT\n# holus:fact retries = LIMIT\n",
    ],
)
def test_r1_ordinary_module_literals_remain_supported(tmp_path, source):
    repo = alignment_repo(
        tmp_path, {"src/a.py": source, "guide.md": "<!-- holus:fact retries = 3 -->"}
    )
    command = _public(repo)
    report = json.loads(command.stdout)
    assert command.returncode == 0 and report["status"] == "ok"
    assert report["coverage"]["facts"] == 2 and report["complete"]


@pytest.mark.parametrize("old_rules", ["holus-alignment/v1", "holus-alignment/v2"])
def test_revised_fact_example_rules_reject_old_baseline(tmp_path, old_rules):
    repo = alignment_repo(tmp_path, {"src/a.py": "LIMIT = 3\n# holus:fact retries = LIMIT\n"})
    report = json.loads(_public(repo).stdout)
    assert report["rules"] == "holus-alignment/v3"
    report["rules"] = old_rules
    (repo / ".holusight").mkdir()
    (repo / ".holusight/before.json").write_text(json.dumps(report))
    command = _public(repo, "--against", ".holusight/before.json")
    assert command.returncode == 2 and "incompatible" in command.stderr


_EXAMPLE = "<!-- holus:fact retries = 9 -->\n`src/example.py`\n"
_EXAMPLES = [
    "````markdown\n```\n" + _EXAMPLE + "````\n",
    "```markdown\n~~~\n" + _EXAMPLE + "```\n",
    "```markdown\n``` trailing text\n" + _EXAMPLE + "```\n",
    "```markdown\n```\u00a0\n" + _EXAMPLE + "```\n",
    "    <!-- holus:fact retries = 9 -->\n    `src/example.py`\n\n",
    "\t<!-- holus:fact retries = 9 -->\n\t`src/example.py`\n\n",
]


@pytest.mark.parametrize("example", _EXAMPLES)
def test_r2_examples_are_not_live_facts_or_paths_but_following_prose_is(tmp_path, example):
    text = example + "<!-- holus:fact retries = 3 -->\nSee `src/current_missing.py`.\n"
    sources = tmp_path / "source"
    sources.mkdir()
    repo = alignment_repo(
        sources, {"src/a.py": "LIMIT = 3\n# holus:fact retries = LIMIT\n", "docs/guide.md": text}
    )
    report = json.loads(_public(repo).stdout)
    assert report["status"] == "ok" and report["coverage"]["facts"] == 2
    graph_home = tmp_path / "graph"
    graph_home.mkdir()
    graph_repo = _document_repo(graph_home, {"guide.md": text})
    report = json.loads(_command(graph_repo, "check").stdout)
    assert report["errors"] == 1
    assert report["findings"][0]["evidence"] == "path:src/current_missing.py"


def test_r2_invalid_backtick_info_does_not_hide_live_contracts(tmp_path):
    text = "```not`a-valid-fence\n<!-- holus:fact retries = 9 -->\nSee `src/current_missing.py`.\n"
    sources = tmp_path / "source"
    sources.mkdir()
    repo = alignment_repo(
        sources, {"src/a.py": "LIMIT = 3\n# holus:fact retries = LIMIT\n", "docs/guide.md": text}
    )
    report = json.loads(_public(repo).stdout)
    assert report["status"] == "mismatch" and report["coverage"]["facts"] == 2
    graph_home = tmp_path / "graph"
    graph_home.mkdir()
    graph_repo = _document_repo(graph_home, {"guide.md": text})
    report = json.loads(_command(graph_repo, "check").stdout)
    assert report["errors"] == 1
    assert report["findings"][0]["evidence"] == "path:src/current_missing.py"


def _restamp(repo):
    graph_path = repo / "graphify-out/graph.json"
    graph = json.loads(graph_path.read_text())
    graph["built_at_commit"] = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    graph_path.write_text(json.dumps(graph))


@pytest.mark.parametrize("method", ["status", "check", "align"])
def test_r3_commit_between_head_and_status_is_not_current(tmp_path, monkeypatch, method):
    repo = _repo(tmp_path)
    engine = Holusight(repo)
    original_git = checker._git
    changed = False

    def committing_git(root, *args):
        nonlocal changed
        if args[0] == "status" and not changed:
            changed = True
            (repo / "src/mod.py").write_text("def changed():\n    return 2\n")
            subprocess.run(["git", "-C", str(repo), "add", "src/mod.py"], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "commit", "-qm", "concurrent commit"], check=True
            )
        return original_git(root, *args)

    monkeypatch.setattr(checker, "_git", committing_git)
    result = getattr(engine, method)()
    proof = result["graph"] if method == "align" else result["provenance"]
    assert changed and proof["state"] != "current"
    assert result["status"] != "current"


@pytest.mark.parametrize("method", ["check", "align"])
def test_r3_edit_after_clean_status_cannot_retain_current_graph(tmp_path, monkeypatch, method):
    repo = _repo(tmp_path)
    original_git = checker._git
    changed = False

    def editing_git(root, *args):
        nonlocal changed
        result = original_git(root, *args)
        if args[0] == "status" and not changed:
            changed = True
            (repo / "src/mod.py").write_text("def changed():\n    return 2\n")
        return result

    monkeypatch.setattr(checker, "_git", editing_git)
    report = getattr(Holusight(repo), method)()
    proof = report["graph"] if method == "align" else report["provenance"]
    assert changed and proof["state"] != "current"
    assert report["status"] == "unknown"


def test_r3_ignored_source_mutating_after_read_is_not_current(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    (repo / ".gitignore").write_text("graphify-out/\nsrc/ignored.py\n")
    subprocess.run(["git", "-C", str(repo), "add", ".gitignore"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "ignore fixture"], check=True)
    _restamp(repo)
    source = repo / "src/ignored.py"
    source.write_text("def hello():\n    return 1\n")
    graph_path = repo / "graphify-out/graph.json"
    graph = json.loads(graph_path.read_text())
    graph["nodes"][0]["source_file"] = graph["links"][0]["source_file"] = "src/ignored.py"
    graph_path.write_text(json.dumps(graph))
    original_open = Path.open
    changed = False

    class RacingRead:
        def __init__(self, stream):
            self.stream = stream

        def read(self, *args, **kwargs):
            nonlocal changed
            result = self.stream.read(*args, **kwargs)
            if not changed:
                changed = True
                source.write_text("def changed():\n    return 2\n")
            return result

    @contextmanager
    def opening(path, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        with original_open(path, *args, **kwargs) as stream:
            yield RacingRead(stream) if path == source and mode in {"r", "rb"} else stream

    monkeypatch.setattr(Path, "open", opening)
    report = Holusight(repo).check()
    assert changed and report["status"] == "unknown"
    assert report["provenance"]["state"] != "current"
    assert source.read_text().startswith("def changed")


def test_r3_stable_unreadable_source_is_unknown_without_invented_change(tmp_path):
    repo = _repo(tmp_path)
    (repo / "src/mod.py").write_bytes(b"\xff\n")
    subprocess.run(["git", "-C", str(repo), "add", "src/mod.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "non-UTF fixture"], check=True)
    _restamp(repo)
    report = Holusight(repo).check()
    assert report["status"] == "unknown" and report["unverified"] > 0
    assert report["errors"] == 0 and not report.get("inputs_changed_during_check", False)


def test_r4_empty_source_is_unavailable_not_an_escape(tmp_path):
    repo = _repo(tmp_path)
    graph_path = repo / "graphify-out/graph.json"
    graph = json.loads(graph_path.read_text())
    graph["nodes"].append({"id": "external", "source_file": "", "source_location": ""})
    graph["links"][0]["source_file"] = graph["links"][0]["source_location"] = ""
    graph_path.write_text(json.dumps(graph))
    report = json.loads(_command(repo, "check").stdout)
    assert report["status"] == "unknown" and report["errors"] == 0
    assert report["unverified"] == 2
    assert all(f["type"] == "unavailable_source" for f in report["findings"])
    graph["nodes"].append({"id": "unsafe", "source_file": "../outside.py"})
    graph_path.write_text(json.dumps(graph))
    report = json.loads(_command(repo, "check").stdout)
    assert report["error_types"] == {"unsafe_path": 1}
    assert report["unverified"] == 2


def test_r5_source_symlink_loop_has_safe_public_reports(tmp_path):
    repo = _repo(tmp_path)
    (repo / "src/loop.py").symlink_to("loop.py")
    graph_path = repo / "graphify-out/graph.json"
    graph = json.loads(graph_path.read_text())
    graph["nodes"].append({"id": "loop", "source_file": "src/loop.py", "source_location": "L1"})
    graph_path.write_text(json.dumps(graph))
    report = Holusight(repo).check()
    assert report["error_types"] in ({"unsafe_path": 1}, {"missing_source": 1})
    assert Holusight(repo).align()["status"] == "partial"
    command = _command(repo, "check")
    assert command.returncode == 1 and "Traceback" not in command.stderr


def test_r5_python311_style_resolution_errors_are_contained(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    graph_path = repo / "graphify-out/graph.json"
    graph_path.unlink()
    graph_path.symlink_to("graph.json")
    original_resolve = Path.resolve

    def resolving(path, *args, **kwargs):
        if path == graph_path:
            raise RuntimeError("Symlink loop from Python 3.11 resolver")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolving)
    engine = Holusight(repo)
    assert engine.check()["status"] == engine.status()["status"] == "unavailable"
    assert engine.align()["graph"]["state"] == "unavailable"


def test_r5_repository_resolution_errors_are_value_errors(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    original_resolve = Path.resolve

    def resolving(path, *args, **kwargs):
        if path == repo:
            raise RuntimeError("Symlink loop from Python 3.11 resolver")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolving)
    with pytest.raises(ValueError, match="cannot be resolved"):
        Holusight(repo)
