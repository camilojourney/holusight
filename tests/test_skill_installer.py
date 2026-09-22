"""Tests for holusight.skill_installer's canonical-copy + symlink fan-out
(mirrors ~/.claude/skills/graphify/ being the one real copy with
~/.codex, ~/.cursor, ~/.gemini, ~/.agents each symlinked to it)."""

from __future__ import annotations

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


def test_install_refuses_to_clobber_a_real_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(skill_installer.Path, "home", classmethod(lambda cls: tmp_path))
    real_dir = tmp_path / ".codex" / "skills" / "holusight"
    real_dir.mkdir(parents=True)
    (real_dir / "someone_elses_file.txt").write_text("not ours", encoding="utf-8")

    changes = skill_installer.install(skill_installer.ALL_HARNESSES)

    assert any("skipped" in line and "not a symlink" in line for line in changes)
    assert (real_dir / "someone_elses_file.txt").read_text(encoding="utf-8") == "not ours"
