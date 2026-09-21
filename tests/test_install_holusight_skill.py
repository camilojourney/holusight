"""Tests for scripts/install_holusight_skill.py's canonical-copy + symlink
fan-out (mirrors ~/.claude/skills/graphify/ being the one real copy with
~/.codex, ~/.cursor, ~/.gemini, ~/.agents each symlinked to it)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "install_holusight_skill.py"
_spec = importlib.util.spec_from_file_location("install_holusight_skill", _SCRIPT_PATH)
install_holusight_skill = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = install_holusight_skill
_spec.loader.exec_module(install_holusight_skill)


def test_install_writes_one_real_copy_and_symlinks_the_rest(tmp_path, monkeypatch):
    monkeypatch.setattr(install_holusight_skill.Path, "home", classmethod(lambda cls: tmp_path))

    install_holusight_skill.install(install_holusight_skill.ALL_HARNESSES)

    canonical = tmp_path / ".claude" / "skills" / "holusight"
    assert canonical.is_dir()
    assert not canonical.is_symlink()
    assert (canonical / "SKILL.md").read_text(encoding="utf-8").startswith("---\nname: holusight\n")

    for harness in ("codex", "cursor", "gemini", "agents"):
        link = tmp_path / f".{harness}" / "skills" / "holusight"
        assert link.is_symlink()
        assert link.resolve() == canonical.resolve()


def test_install_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(install_holusight_skill.Path, "home", classmethod(lambda cls: tmp_path))

    first = install_holusight_skill.install(install_holusight_skill.ALL_HARNESSES)
    second = install_holusight_skill.install(install_holusight_skill.ALL_HARNESSES)

    assert any("wrote" in line for line in first)
    # Second pass: canonical is rewritten (harmless -- same content), but no
    # symlink churn is reported for links that already point correctly.
    linked_lines = [line for line in second if line.startswith("linked ")]
    assert linked_lines == []


def test_install_refuses_to_clobber_a_real_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(install_holusight_skill.Path, "home", classmethod(lambda cls: tmp_path))
    real_dir = tmp_path / ".codex" / "skills" / "holusight"
    real_dir.mkdir(parents=True)
    (real_dir / "someone_elses_file.txt").write_text("not ours", encoding="utf-8")

    changes = install_holusight_skill.install(install_holusight_skill.ALL_HARNESSES)

    assert any("skipped" in line and "not a symlink" in line for line in changes)
    assert (real_dir / "someone_elses_file.txt").read_text(encoding="utf-8") == "not ours"
