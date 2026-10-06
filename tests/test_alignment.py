"""Behavioral evidence for deterministic candidate detection, facts and rescans."""

import hashlib
import json
import subprocess
import sys

import pytest

from holusight import Holusight, alignment

CODE = """LIMIT = 3
# holus:fact retry-limit = LIMIT

def total(items):
    result = 0
    for item in items:
        result += item * 2
    return result
"""
RENAMED = """LIMIT = 3
# holus:fact retry-limit = LIMIT

def calculate(values):
    count = 0
    for value in values:
        count += value * 2
    return count
"""
PARAGRAPH = (
    "Agents should inspect both source locations before consolidating these instructions. "
    "Keep the canonical operational guide linked from each consumer and confirm that its "
    "examples describe the same behavior. Shared text is only a review candidate because "
    "different teams may intentionally maintain separate procedures with different ownership."
)


def _repo(tmp_path, files):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    for key, value in (("user.name", "Test"), ("user.email", "test@example.invalid")):
        subprocess.run(["git", "-C", str(repo), "config", key, value], check=True)
    (repo / ".gitignore").write_text(".holusight/\nignored.md\n")
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "fixture"], check=True)
    return repo


def _public(repo, *args):
    return subprocess.run(
        [sys.executable, "-m", "holusight", "align", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _save(repo, report, name="before.json"):
    path = repo / ".holusight" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report))
    return str(path.relative_to(repo))


def test_renamed_code_candidates_and_changed_literal_negative(tmp_path):
    repo = _repo(
        tmp_path,
        {"src/a.py": CODE, "src/b.py": RENAMED, "src/different.py": RENAMED.replace("* 2", "* 7")},
    )
    report = Holusight(repo).align()
    assert report["status"] == "review"
    findings = report["findings"]
    assert len(findings) == 1
    assert findings[0]["method"] == "code_renamed"
    assert {o["file"] for o in findings[0]["locations"]} == {"src/a.py", "src/b.py"}
    assert findings[0]["severity"] == "candidate"
    assert report["errors"] == 0


def test_doc_duplicates_near_overlap_and_unrelated_control(tmp_path):
    repo = _repo(
        tmp_path,
        {
            "docs/a.md": PARAGRAPH,
            "docs/b.md": PARAGRAPH,
            "docs/c.md": PARAGRAPH + " Always.",
            "docs/d.md": " ".join(f"unrelated{i}" for i in range(45)),
        },
    )
    report = alignment.align(repo)
    assert report["status"] == "review"
    assert {f["type"] for f in report["findings"]} == {"docs_duplicate", "docs_similar"}
    assert all(o["file"] != "docs/d.md" for f in report["findings"] for o in f["locations"])


@pytest.mark.parametrize(
    "files",
    [
        {
            "src/a.py": "LIMIT = 3\n# holus:fact retries = LIMIT\n",
            "docs/a.md": "<!-- holus:fact retries = 5 -->\n",
        },
        {
            "src/a.py": "LIMIT = 3\n# holus:fact retries = LIMIT\n",
            "src/b.py": "LIMIT = 5\n# holus:fact retries = LIMIT\n",
        },
        {
            "docs/a.md": "<!-- holus:fact retries = 3 -->\n",
            "docs/b.md": "<!-- holus:fact retries = 5 -->\n",
        },
    ],
)
def test_explicit_doc_code_code_code_and_doc_doc_mismatches(tmp_path, files):
    repo = _repo(tmp_path, files)
    proc = _public(repo)
    assert proc.returncode == 1, proc.stderr
    report = json.loads(proc.stdout)
    assert report["status"] == "mismatch"
    assert report["errors"] == 1
    finding = report["findings"][0]
    assert finding["fact"] == "retries"
    assert {d["value"] for d in finding["declarations"]} == {3, 5}
    assert all(o["source_hash"] == report["sources"][o["file"]] for o in finding["locations"])


def test_unlinked_constant_names_and_arbitrary_prose_are_not_invented_claims(tmp_path):
    repo = _repo(
        tmp_path,
        {
            "src/a.py": "MAX_RETRIES = 3\n",
            "src/b.py": "MAX_RETRIES = 5\n",
            "docs/a.md": "Requests are retried five times.\n",
        },
    )
    report = alignment.align(repo)
    assert report["errors"] == 0
    assert report["coverage"]["facts"] == 0
    assert not report["findings"]


def test_fact_marker_mentions_are_prose_not_malformed_contracts(tmp_path):
    repo = _repo(tmp_path, {"guide.md": "Use `holus:fact` markers for explicit scalar facts.\n"})
    result = alignment.align(repo)
    assert result["status"] == "ok"
    assert result["coverage"]["facts"] == result["skipped_count"] == 0
    (repo / "guide.md").write_text("<!-- holus:fact broken = [1, 2] -->\n")
    result = alignment.align(repo)
    assert result["status"] == "partial"
    assert result["skipped_count"] == 1


@pytest.mark.parametrize("prefix", ["#holus:fact", "# holus:fact", "#\tholus:fact"])
def test_malformed_python_marker_cannot_resolve_mismatch(tmp_path, prefix):
    repo = _repo(
        tmp_path,
        {
            "src/a.py": f"LIMIT = 3\n{prefix} retries = LIMIT\n",
            "docs/a.md": "<!-- holus:fact retries = 5 -->\n",
        },
    )
    before = Holusight(repo).align()
    assert before["complete"] is True
    assert before["errors"] == 1
    baseline = _save(repo, before)
    (repo / "src/a.py").write_text(f"LIMIT = 3\n{prefix} retries = 3\n")
    after = Holusight(repo).align()
    assert after["status"] == "partial"
    assert after["complete"] is False
    assert after["skipped_count"] == 1
    assert after["skipped"][0]["reason"] == "invalid fact marker"
    with pytest.raises(ValueError, match="partial/unknown"):
        Holusight(repo).align(against=baseline)


def test_dynamic_values_not_executed_and_comment_inside_string_not_a_fact(tmp_path):
    repo = _repo(
        tmp_path,
        {
            "src/a.py": "raise RuntimeError('must never import this file')\n"
            "LIMIT = dangerous_network_call()\n# holus:fact retries = LIMIT\n"
            "TEXT = '''\n# holus:fact fake = LIMIT\n'''\n"
        },
    )
    report = alignment.align(repo)
    assert report["status"] == "partial"
    assert report["coverage"]["facts"] == 0
    assert report["skipped_count"] == 1
    assert "retries" in report["skipped"][0]["reason"]


@pytest.mark.parametrize(
    "suffix",
    [
        "LIMIT = 4\n",
        "LIMIT, OTHER = (4, 5)\n",
        "if enabled:\n    LIMIT = 4\n",
        "from another_module import LIMIT\n",
        "def mutate():\n    global LIMIT\n    LIMIT = 4\n",
    ],
)
def test_ambiguous_literal_fact_does_not_claim_verified_value(tmp_path, suffix):
    repo = _repo(tmp_path, {"src/a.py": "LIMIT = 3\n" + suffix + "# holus:fact retries = LIMIT\n"})
    result = alignment.align(repo)
    assert result["status"] == "partial"
    assert result["coverage"]["facts"] == 0


def test_external_calls_and_defaults_are_not_normalized_away(tmp_path):
    repo = _repo(
        tmp_path,
        {"src/a.py": CODE, "src/b.py": RENAMED.replace("return count", "return other(count)")},
    )
    assert alignment.align(repo)["candidates"] == 0
    (repo / "src/b.py").write_text(RENAMED.replace("values):", "values=global_default):"))
    assert alignment.align(repo)["candidates"] == 0


def test_local_fingerprint_cannot_capture_external_identifier(tmp_path):
    repo = _repo(
        tmp_path,
        {
            "a.py": "def first(arg):\n    value = arg + local_0\n"
            "    value += 2\n    return value\n",
            "b.py": "def second(arg):\n    value = arg + arg\n    value += 2\n    return value\n",
        },
    )
    proc = _public(repo)
    assert proc.returncode == 0
    report = json.loads(proc.stdout)
    assert report["candidates"] == 0
    assert report["rules"] == "holus-alignment/v3"


def test_v2_receipts_cannot_establish_resolution_under_corrected_rules(tmp_path):
    repo = _repo(tmp_path, {"a.py": CODE, "b.py": RENAMED})
    report = alignment.align(repo)
    report["rules"] = "holus-alignment/v2"
    baseline = _save(repo, report)
    with pytest.raises(ValueError, match="analyzer is incompatible"):
        alignment.align(repo, against=baseline)


def test_partial_near_document_scan_does_not_claim_complete(tmp_path, monkeypatch):
    repo = _repo(tmp_path, {"a.md": PARAGRAPH, "b.md": PARAGRAPH + " Always."})
    monkeypatch.setattr(alignment, "MAX_PAIRS", 0)
    result = alignment.align(repo)
    assert result["status"] == "partial"
    assert result["skipped_count"] == 1


def test_repeatable_rescan_after_repair_and_deletion(tmp_path):
    repo = _repo(
        tmp_path,
        {
            "src/a.py": CODE,
            "src/b.py": RENAMED,
            "docs/a.md": PARAGRAPH + "\n\n<!-- holus:fact retry-limit = 5 -->\n",
            "docs/b.md": PARAGRAPH,
        },
    )
    before_proc = _public(repo)
    before = json.loads(before_proc.stdout)
    assert before_proc.returncode == 1
    assert before["errors"] == 1 and before["candidates"] == 2
    baseline = _save(repo, before)
    same = alignment.align(repo, against=baseline)
    assert same["source_snapshot"] == before["source_snapshot"]
    assert same["delta"]["new"] == same["delta"]["resolved"] == []
    assert len(same["delta"]["persisting"]) == 3
    (repo / "src/b.py").unlink()
    (repo / "docs/b.md").unlink()
    (repo / "docs/a.md").write_text(PARAGRAPH + "\n\n<!-- holus:fact retry-limit = 3 -->\n")
    after_proc = _public(repo, "--against", baseline)
    assert after_proc.returncode == 0, after_proc.stderr
    after = json.loads(after_proc.stdout)
    assert after["status"] == "ok"
    assert after["source_snapshot"] != before["source_snapshot"]
    assert len(after["delta"]["resolved"]) == 3
    assert after["delta"]["changed_sources"] == ["docs/a.md", "docs/b.md", "src/b.py"]
    assert "src/b.py" not in after["sources"]
    # Reintroducing a mismatch is newly detected, not suppressed by cached success.
    newer = _save(repo, after, "after.json")
    (repo / "docs/a.md").write_text("<!-- holus:fact retry-limit = 9 -->\n")
    regression = alignment.align(repo, against=newer)
    assert regression["errors"] == 1
    assert len(regression["delta"]["new"]) == 1


def test_scan_is_read_only_and_scope_safe(tmp_path):
    repo = _repo(tmp_path, {"src/a.py": CODE, "src/b.py": RENAMED})
    before = {
        str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in repo.rglob("*")
        if p.is_file()
    }
    result = alignment.align(repo, scope="src/a.py")
    assert result["status"] == "review" and "graph" not in result
    assert "graph_nodes" not in result["findings"][0]["locations"][0]
    after = {
        str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in repo.rglob("*")
        if p.is_file()
    }
    assert before == after
    with pytest.raises(ValueError):
        alignment.align(repo, scope="../outside")
    (repo / "src/link.py").symlink_to(tmp_path / "secret.py")
    result = alignment.align(repo)
    assert result["status"] == "partial"
    assert result["skipped"][0]["file"] == "src/link.py"


def test_ignored_derived_sources_are_not_scanned(tmp_path):
    repo = _repo(tmp_path, {"src/a.py": CODE})
    (repo / "ignored.md").write_text("<!-- holus:fact retry-limit = 99 -->")
    derived = repo / ".holusight"
    derived.mkdir()
    (derived / "private.py").write_text(CODE.replace("3", "100"))
    result = alignment.align(repo)
    assert result["errors"] == 0
    assert set(result["sources"]) == {"src/a.py"}


def test_budget_or_incompatible_baseline_cannot_claim_resolution(tmp_path, monkeypatch):
    repo = _repo(tmp_path, {"src/a.py": CODE, "src/b.py": RENAMED})
    baseline = _save(repo, alignment.align(repo))
    monkeypatch.setattr(alignment, "MAX_FILES", 1)
    assert alignment.align(repo)["status"] == "partial"
    with pytest.raises(ValueError, match="partial"):
        alignment.align(repo, against=baseline)
    monkeypatch.setattr(alignment, "MAX_FILES", 500)
    with pytest.raises(ValueError, match="incompatible"):
        alignment.align(repo, scope="src/a.py", against=baseline)
    report = json.loads((repo / baseline).read_text())
    report["source_snapshot"] = "tampered"
    (repo / baseline).write_text(json.dumps(report))
    with pytest.raises(ValueError, match="invalid"):
        alignment.align(repo, against=baseline)


def test_failed_git_inventory_does_not_bypass_ignore_rules(tmp_path, monkeypatch):
    repo = _repo(tmp_path, {"src/a.py": CODE})
    calls = []

    def failed_inventory(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="unavailable")

    monkeypatch.setattr(alignment.subprocess, "run", failed_inventory)
    with pytest.raises(ValueError, match="ignore rules cannot be verified"):
        alignment.align(repo)
    assert calls[0][1:4] == ["--no-optional-locks", "-c", "core.fsmonitor=false"]


def test_concurrent_change_invalidates_receipt(tmp_path, monkeypatch):
    repo = _repo(tmp_path, {"src/a.py": CODE})
    original = alignment._source
    first = True

    def racing_read(root, name):
        nonlocal first
        data = original(root, name)
        if first:
            first = False
            (root / name).write_bytes(data + b"# concurrently edited\n")
        return data

    monkeypatch.setattr(alignment, "_source", racing_read)
    result = alignment.align(repo)
    assert result["status"] == "unknown"
    assert not result["complete"]
    assert result["inputs_changed_during_scan"]
