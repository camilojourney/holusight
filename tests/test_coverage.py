"""Public coverage honesty without parsing unsupported or private source contents."""

import json

import pytest

from holusight import Holusight, alignment

from .test_alignment import CODE, RENAMED, _public, _repo, _save


def test_mixed_languages_are_partial_but_keep_python_candidates(tmp_path, monkeypatch):
    repo = _repo(
        tmp_path,
        {
            "src/a.py": CODE,
            "src/b.py": RENAMED,
            "app/main.swift": "UNSUPPORTED_PRIVATE_CANARY",
            "web/view.tsx": "not valid TypeScript",
        },
    )
    original = alignment._source
    reads = []

    def read_supported(root, name):
        assert name.endswith((".py", ".md"))
        reads.append(name)
        return original(root, name)

    monkeypatch.setattr(alignment, "_source", read_supported)
    report = Holusight(repo).align()
    assert report["status"] == "partial" and report["complete"] is False
    assert report["candidates"] == 1 and report["errors"] == 0
    assert report["coverage"]["extensions"] == {".py": 2, ".swift": 1, ".tsx": 1}
    assert report["coverage"]["inventory_files"] == 4
    assert report["coverage"]["files"] == report["coverage"]["supported_files"] == 2
    assert report["coverage"]["unsupported_files"] == 2
    assert report["coverage"]["focused_unsupported_files"] == 2
    assert set(reads) == {"src/a.py", "src/b.py"}
    assert "UNSUPPORTED_PRIVATE_CANARY" not in json.dumps(report)
    proc = _public(repo)
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["complete"] is False


@pytest.mark.parametrize("files", [{}, {"only.ts": "export const x = 1;"}])
def test_empty_and_unsupported_only_are_never_complete(tmp_path, files):
    repo = _repo(tmp_path, files)
    report = Holusight(repo).align()
    assert report["status"] == ("partial" if files else "unavailable")
    assert report["complete"] is False
    assert report["coverage"]["files"] == 0
    assert _public(repo).returncode == 1


def test_supported_focus_and_docs_declare_bounded_not_repository_coverage(tmp_path):
    repo = _repo(
        tmp_path,
        {"src/a.py": CODE, "app/main.ts": "private", "guide.md": "A guide.\n"},
    )
    engine = Holusight(repo)
    for options in ({"scope": "src/"}, {"docs": True}):
        report = engine.align(**options)
        assert report["complete"] and report["status"] == "ok"
        assert report["coverage"]["unsupported_files"] == 1
        assert report["coverage"]["focused_unsupported_files"] == 0
        assert report["coverage"]["focused_files"] == 1
    assert engine.align(scope="app/")["status"] == "partial"
    assert engine.align(scope="app/main.ts")["complete"] is False
    assert engine.align(scope="app/", docs=True)["status"] == "partial"


def test_ignored_derived_and_symlink_boundaries_remain_intact(tmp_path):
    repo = _repo(tmp_path, {"src/a.py": CODE})
    (repo / ".gitignore").write_text("ignored/\n")
    for folder in ("ignored", "node_modules", ".holusight"):
        (repo / folder).mkdir()
        (repo / folder / "private.ts").write_text("PRIVATE_CANARY")
    (repo / "link.ts").symlink_to(tmp_path / "outside.ts")
    report = Holusight(repo).align()
    assert report["coverage"]["extensions"] == {".py": 1, ".ts": 1}
    assert set(report["sources"]) == {"src/a.py"}
    assert report["status"] == "partial"
    assert "PRIVATE_CANARY" not in json.dumps(report)
    with pytest.raises(ValueError, match="scope must be"):
        Holusight(repo).align(scope="link.ts")


def test_added_unsupported_source_invalidates_inventory_during_scan(tmp_path, monkeypatch):
    repo = _repo(tmp_path, {"src/a.py": CODE})
    original = alignment._source

    def racing_read(root, name):
        data = original(root, name)
        (root / "added.go").write_text("package app\n")
        return data

    monkeypatch.setattr(alignment, "_source", racing_read)
    report = Holusight(repo).align()
    assert report["status"] == "unknown"
    assert report["inputs_changed_during_scan"] and not report["complete"]


def test_new_unsupported_file_prevents_false_baseline_resolution(tmp_path):
    repo = _repo(tmp_path, {"a.py": CODE, "b.py": RENAMED})
    baseline = _save(repo, Holusight(repo).align())
    (repo / "b.py").unlink()
    (repo / "b.swift").write_text("func implementation() {}\n")
    with pytest.raises(ValueError, match="partial/unknown"):
        Holusight(repo).align(against=baseline)


@pytest.mark.parametrize("git", [True, False])
def test_unsupported_metadata_does_not_consume_supported_file_budget(tmp_path, monkeypatch, git):
    files = {"src/a.ts": "private", "src/z.py": CODE}
    if git:
        repo = _repo(tmp_path, files)
    else:
        repo = tmp_path
        (repo / "src").mkdir()
        for name, text in files.items():
            (repo / name).write_text(text)
    monkeypatch.setattr(alignment, "MAX_FILES", 1)
    report = Holusight(repo).align()
    assert report["coverage"]["files"] == 1
    assert set(report["sources"]) == {"src/z.py"}
    assert report["status"] == "partial"
    assert not any("budget" in item["reason"] for item in report["skipped"])
