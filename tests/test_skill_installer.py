"""Tests for holusight.skill_installer's canonical-copy + symlink fan-out
(mirrors ~/.claude/skills/graphify/ being the one real copy with
~/.codex, ~/.cursor, ~/.gemini, ~/.agents each symlinked to it)."""

from __future__ import annotations

import pytest

from holusight import skill_installer


def test_install_writes_one_real_copy_and_symlinks_the_rest(tmp_path, monkeypatch):
    monkeypatch.setattr(skill_installer.Path, "home", classmethod(lambda cls: tmp_path))

    skill_installer.install(skill_installer.ALL_HARNESSES)

    canonical = tmp_path / ".claude" / "skills" / "holusight"
    assert canonical.is_dir()
    assert not canonical.is_symlink()
    assert (canonical / "SKILL.md").read_text(encoding="utf-8").startswith("---\nname: holusight\n")

    for harness in ("codex", "cursor", "gemini", "agents"):
        link = tmp_path / f".{harness}" / "skills" / "holusight"
        assert link.is_symlink()
        assert link.resolve() == canonical.resolve()


def test_install_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(skill_installer.Path, "home", classmethod(lambda cls: tmp_path))

    first = skill_installer.install(skill_installer.ALL_HARNESSES)
    second = skill_installer.install(skill_installer.ALL_HARNESSES)

    assert any("wrote" in line for line in first)
    # Second pass: canonical is rewritten (harmless -- same content), but no
    # symlink churn is reported for links that already point correctly.
    linked_lines = [line for line in second if line.startswith("linked ")]
    assert linked_lines == []


def test_project_local_install_is_missing_only_and_does_not_touch_home(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setattr(skill_installer.Path, "home", classmethod(lambda cls: home))

    first = skill_installer.install_project_local()
    skill = project / ".agents" / "skills" / "holusight" / "SKILL.md"
    assert skill.exists()
    assert not (home / ".claude").exists()
    original = skill.read_text(encoding="utf-8")

    skill.write_text("project-owned", encoding="utf-8")
    second = skill_installer.install_project_local()
    assert second == [f"skipped {skill.parent}: project-local skill already exists"]
    assert skill.read_text(encoding="utf-8") == "project-owned"
    assert any("wrote" in line for line in first)
    assert original.startswith("---\nname: holusight\n")


def test_project_local_cli_installs_fresh_project(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setattr(skill_installer.Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.setattr("sys.argv", ["holusight-install-skill", "--project-local"])

    assert skill_installer.main() == 0
    assert (project / ".agents" / "skills" / "holusight" / "SKILL.md").is_file()
    assert not (tmp_path / "home").exists()


def test_project_local_install_rejects_escaping_symlink(tmp_path):
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    (project / ".agents").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="escapes project root"):
        skill_installer.install_project_local(project)
    assert not (outside / "skills").exists()


def test_install_refuses_to_clobber_a_real_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(skill_installer.Path, "home", classmethod(lambda cls: tmp_path))
    real_dir = tmp_path / ".codex" / "skills" / "holusight"
    real_dir.mkdir(parents=True)
    (real_dir / "someone_elses_file.txt").write_text("not ours", encoding="utf-8")

    changes = skill_installer.install(skill_installer.ALL_HARNESSES)

    assert any("skipped" in line and "not a symlink" in line for line in changes)
    assert (real_dir / "someone_elses_file.txt").read_text(encoding="utf-8") == "not ours"
