"""Public behavior for directory/Markdown selectors and focused repair receipts."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from holusight import Holusight, alignment

from .test_alignment import CODE, PARAGRAPH, RENAMED, _repo, _save


def _fixture(tmp_path):
    repo = _repo(
        tmp_path,
        {
            "specs/guide.md": PARAGRAPH + "\n\n<!-- holus:fact retry-limit = 5 -->\n",
            "docs/guide.md": PARAGRAPH,
            "src/app/a.py": CODE,
            "src/app/b.py": RENAMED,
            "src/other/a.py": CODE.replace("retry-limit", "other-limit").replace("* 2", "* 7"),
            "src/other/b.py": RENAMED.replace("retry-limit", "other-limit").replace("* 2", "* 7"),
            "docs/noise.md": "<!-- holus:fact other-limit = 9 -->\n",
            "specs-other/broken.md": "The current file is `src/missing.py`.\n",
        },
    )
    graph_dir = repo / "graphify-out"
    graph_dir.mkdir()
    names = [n for n in alignment._inventory(repo)]
    graph = {
        "built_at_commit": subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
        ).strip(),
        "nodes": [
            {
                "id": n,
                "source_file": n,
                "source_location": "L1",
                "file_type": "document" if n.endswith(".md") else "code",
            }
            for n in names
        ],
        "links": [
            {
                "source": "specs/guide.md",
                "target": "src/app/a.py",
                "source_file": "specs/guide.md",
                "source_location": "L1",
            },
            {
                "source": "src/other/a.py",
                "target": "missing-global-endpoint",
                "source_file": "src/other/a.py",
                "source_location": "L1",
            },
        ],
    }
    (graph_dir / "graph.json").write_text(json.dumps(graph))
    return repo


def _public(repo, command, *options, console=False):
    executable = (
        [str(Path(sys.executable).with_name("holus"))]
        if console
        else [sys.executable, "-m", "holusight"]
    )
    return subprocess.run(
        [*executable, command, str(repo), *options], text=True, capture_output=True, check=False
    )


def _report(process):
    assert process.stdout, process.stderr
    return json.loads(process.stdout)


@pytest.mark.parametrize("console", [False, True])
def test_public_directory_check_excludes_unrelated_global_failures(tmp_path, console):
    repo = _fixture(tmp_path)
    before = {p: p.read_bytes() for p in repo.rglob("*") if p.is_file()}
    whole = _report(_public(repo, "check", console=console))
    focused_process = _public(repo, "check", "--scope", "specs/", console=console)
    focused = _report(focused_process)
    assert whole["errors"] >= 2
    assert focused_process.returncode == 0
    assert focused["status"] == "current" and focused["checked"] > 0
    assert focused["errors"] == 0
    assert focused["scope"] == "specs"
    assert focused["selector"] == {"scope": "specs", "kind": "directory", "docs": False}
    assert focused["coverage"]["global_integrity"] is False
    assert before == {p: p.read_bytes() for p in repo.rglob("*") if p.is_file()}


def test_api_directory_alignment_keeps_cross_focus_partners(tmp_path):
    repo = _fixture(tmp_path)
    engine = Holusight(repo)
    whole = engine.align()
    focused = engine.align(scope="specs/")
    assert focused["status"] == "mismatch" and focused["complete"]
    assert len(focused["findings"]) < len(whole["findings"])
    assert {f["type"] for f in focused["findings"]} == {"docs_duplicate", "alignment_mismatch"}
    assert focused["coverage"]["focused_files"] == 1
    assert focused["coverage"]["files"] > focused["coverage"]["focused_files"]
    for finding in focused["findings"]:
        assert any(o["file"] == "specs/guide.md" for o in finding["locations"])
        assert any(not o["file"].startswith("specs/") for o in finding["locations"])
    assert engine.align(scope="specs")["finding_ids"] == focused["finding_ids"]
    assert not any(f.get("fact") == "other-limit" for f in focused["findings"])


@pytest.mark.parametrize("console", [False, True])
def test_docs_selector_and_intersection_use_public_commands(tmp_path, console):
    repo = _fixture(tmp_path)
    docs = _report(_public(repo, "align", "--docs", console=console))
    both = _report(_public(repo, "align", "--docs", "--scope", "specs/", console=console))
    assert docs["docs"] is True and both["docs"] is True
    assert both["complete"] and both["errors"] == 1
    assert docs["errors"] == 2
    assert all(f["type"] != "code_duplicate" for f in docs["findings"])
    assert any(o["file"].endswith(".py") for f in both["findings"] for o in f["locations"])
    assert _report(_public(repo, "check", "--docs", console=console))["errors"] == 1
    assert (
        _report(_public(repo, "check", "--docs", "--scope", "specs/", console=console))["errors"]
        == 0
    )


def test_application_scope_has_code_candidates_and_document_partner(tmp_path):
    repo = _fixture(tmp_path)
    result = Holusight(repo).align(scope="src/app/")
    assert result["complete"] and result["errors"] == 1
    assert {f["type"] for f in result["findings"]} == {"code_duplicate", "alignment_mismatch"}
    assert any(o["file"] == "specs/guide.md" for f in result["findings"] for o in f["locations"])


def test_docs_api_excludes_ignored_private_and_symlink_sources(tmp_path):
    repo = _fixture(tmp_path)
    (repo / "ignored.md").write_text("<!-- holus:fact retry-limit = 99 -->\n")
    private = repo / ".holusight"
    private.mkdir()
    (private / "secret.md").write_text("PRIVATE_CANARY `src/absent-private.py`.\n")
    graph_path = repo / "graphify-out/graph.json"
    graph = json.loads(graph_path.read_text())
    graph["nodes"].extend(
        {"id": n, "source_file": n, "source_location": "L1", "file_type": "document"}
        for n in ["ignored.md", ".holusight/secret.md"]
    )
    graph_path.write_text(json.dumps(graph))
    result = Holusight(repo).check(docs=True)
    assert result["errors"] == 1
    assert "PRIVATE_CANARY" not in json.dumps(result)
    assert not any(f["file"] in {"ignored.md", ".holusight/secret.md"} for f in result["findings"])
    scan = Holusight(repo).align(docs=True)
    assert "ignored.md" not in scan["sources"] and ".holusight/secret.md" not in scan["sources"]
    (repo / "specs/link.md").symlink_to(private / "secret.md")
    graph["nodes"].append({"id": "link", "source_file": "specs/link.md", "file_type": "document"})
    graph_path.write_text(json.dumps(graph))
    checked = Holusight(repo).check(docs=True, scope="specs/")
    assert checked["error_types"] == {"unsafe_path": 1}
    assert "absent-private" not in json.dumps(checked)
    assert Holusight(repo).align(docs=True, scope="specs/")["status"] == "partial"


@pytest.mark.parametrize(
    "scope", ["../outside", "/etc", "specs/../../outside", "specs\\guide.md", ""]
)
def test_invalid_scopes_are_refused_by_both_apis(tmp_path, scope):
    repo = _fixture(tmp_path)
    engine = Holusight(repo)
    for method in [engine.check, engine.align]:
        with pytest.raises(ValueError, match="scope must be"):
            method(scope=scope)


def test_directory_symlink_escape_is_refused(tmp_path):
    repo = _fixture(tmp_path)
    (repo / "outside").symlink_to(tmp_path, target_is_directory=True)
    for method in [Holusight(repo).check, Holusight(repo).align]:
        with pytest.raises(ValueError, match="scope must be"):
            method(scope="outside/")


@pytest.mark.parametrize("scope,docs", [("absent/", False), ("src/", True), (".holusight/", False)])
def test_empty_or_unrepresented_focus_is_not_a_clean_pass(tmp_path, scope, docs):
    repo = _fixture(tmp_path)
    engine = Holusight(repo)
    assert engine.check(scope=scope, docs=docs)["status"] == "unknown"
    report = engine.align(scope=scope, docs=docs)
    assert report["status"] == "partial" and report["complete"] is False
    assert report["coverage"]["focused_files"] == 0


def test_normalized_focus_baseline_and_justified_repair_while_global_issues_remain(tmp_path):
    repo = _fixture(tmp_path)
    engine = Holusight(repo)
    before = engine.align(scope="specs/", docs=True)
    baseline = _save(repo, before)
    # Code is the explicit authority for retry-limit; keep one canonical paragraph
    # and replace the duplicated spec paragraph with a consumer reference.
    (repo / "specs/guide.md").write_text(
        "See `docs/guide.md` for the operational procedure.\n\n"
        "<!-- holus:fact retry-limit = 3 -->\n"
    )
    after = engine.align(scope="specs", docs=True, against=baseline)
    assert after["complete"] and after["status"] == "ok"
    assert len(after["delta"]["resolved"]) == 2
    assert after["delta"]["changed_sources"] == ["specs/guide.md"]
    assert engine.align()["errors"] == 1  # unrelated other-limit deliberately remains
    assert engine.check()["errors"] >= 2  # unrelated dangling edge / missing path remain
    assert after["graph"]["state"] == "stale"  # source repairs never refresh the graph
    with pytest.raises(ValueError, match="incompatible"):
        engine.align(scope="specs", against=baseline)
    with pytest.raises(ValueError, match="incompatible"):
        engine.align(scope="docs", docs=True, against=baseline)


def test_default_v2_baseline_remains_comparable(tmp_path):
    repo = _fixture(tmp_path)
    report = Holusight(repo).align()
    report.pop("docs", None)  # pre-selector v2 receipt
    report.pop("selector", None)
    baseline = _save(repo, report)
    result = Holusight(repo).align(against=baseline)
    assert result["delta"]["new"] == result["delta"]["resolved"] == []


def test_focus_anchor_survives_bounded_partner_projection(tmp_path):
    files = {f"docs/partner{i:02}.md": PARAGRAPH for i in range(35)}
    files["specs/focus.md"] = PARAGRAPH
    repo = _repo(tmp_path, files)
    finding = Holusight(repo).align(scope="specs/", docs=True)["findings"][0]
    assert finding["location_count"] == 36 and finding["locations_truncated"]
    assert len(finding["locations"]) == 30
    assert finding["locations"][0]["file"] == "specs/focus.md"
    assert any(o["file"].startswith("docs/") for o in finding["locations"])


def test_file_becoming_directory_invalidates_selector_baseline(tmp_path):
    repo = _fixture(tmp_path)
    engine = Holusight(repo)
    baseline = _save(repo, engine.align(scope="specs/guide.md", docs=True))
    path = repo / "specs/guide.md"
    path.unlink()
    path.mkdir()
    (path / "child.md").write_text(PARAGRAPH)
    with pytest.raises(ValueError, match="incompatible"):
        engine.align(scope="specs/guide.md", docs=True, against=baseline)


def test_unverified_comparison_partner_prevents_resolution(tmp_path):
    repo = _fixture(tmp_path)
    engine = Holusight(repo)
    baseline = _save(repo, engine.align(scope="specs/", docs=True))
    (repo / "src/app/a.py").write_text("LIMIT = dynamic()\n# holus:fact retry-limit = LIMIT\n")
    assert engine.align(scope="specs/", docs=True)["complete"] is False
    with pytest.raises(ValueError, match="partial"):
        engine.align(scope="specs/", docs=True, against=baseline)


def test_relevant_graph_edge_is_checked_even_with_outside_source(tmp_path):
    repo = _fixture(tmp_path)
    path = repo / "graphify-out/graph.json"
    graph = json.loads(path.read_text())
    graph["links"].append(
        {
            "source": "specs/guide.md",
            "target": "missing-relevant-endpoint",
            "source_file": "src/other/a.py",
            "source_location": "L1",
        }
    )
    path.write_text(json.dumps(graph))
    result = Holusight(repo).check(scope="specs/", docs=True)
    assert result["error_types"] == {"dangling_edge": 1}
    assert result["findings"][0]["evidence"] == "links[2]"


@pytest.mark.parametrize("flag", ["--docs", "--scope"])
def test_status_rejects_selectors_with_actionable_guidance(tmp_path, flag):
    repo = _fixture(tmp_path)
    options = [flag] if flag == "--docs" else [flag, "specs/"]
    proc = _public(repo, "status", *options)
    assert proc.returncode == 2
    assert "whole" in proc.stderr.lower() and "check" in proc.stderr and "align" in proc.stderr
