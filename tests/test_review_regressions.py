"""Executable regressions for terminal R1–R5; no analyzed program is executed."""

import json
from pathlib import Path

import pytest

from holusight import Holusight

from .test_alignment import _public
from .test_alignment import _repo as alignment_repo
from .test_cli_axi import _command


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


def test_r2_invalid_backtick_info_does_not_hide_live_contracts(tmp_path):
    text = "```not`a-valid-fence\n<!-- holus:fact retries = 9 -->\nSee `src/current_missing.py`.\n"
    sources = tmp_path / "source"
    sources.mkdir()
    repo = alignment_repo(
        sources, {"src/a.py": "LIMIT = 3\n# holus:fact retries = LIMIT\n", "docs/guide.md": text}
    )
    report = json.loads(_public(repo).stdout)
    assert report["status"] == "mismatch" and report["coverage"]["facts"] == 2


def test_r5_source_symlink_loop_has_safe_public_reports(tmp_path):
    repo = alignment_repo(tmp_path, {"src/a.py": "VALUE = 1\n"})
    (repo / "src/loop.py").symlink_to("loop.py")
    assert Holusight(repo).align()["status"] == "partial"
    command = _command(repo, "align")
    assert command.returncode == 1 and "Traceback" not in command.stderr


def test_r5_repository_resolution_errors_are_value_errors(tmp_path, monkeypatch):
    repo = alignment_repo(tmp_path, {"src/a.py": "VALUE = 1\n"})
    original_resolve = Path.resolve

    def resolving(path, *args, **kwargs):
        if path == repo:
            raise RuntimeError("Symlink loop from Python 3.11 resolver")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolving)
    with pytest.raises(ValueError, match="cannot be resolved"):
        Holusight(repo)
