"""CI drift check for the generated `/holus` skill (acceptance criterion 7).

`.claude/skills/holus/SKILL.md` is generated from `src/codesight/axi_schema.py`
by `src/codesight/axi_skill_gen.py`. This test regenerates the skill text
in-memory and asserts it matches the committed file byte-for-byte, so the
executable's schema and the installable skill cannot silently diverge -
whoever changes `axi_schema.py` without running
`python -m codesight.axi_skill_gen` sees this test fail in the normal
`pytest` run (`just test` / `just check`), which is this repository's
existing CI gate (see AGENTS.md's Agent Authority Matrix: "Running lint
and tests" is already the enforced check - no new CI infrastructure is
introduced here, matching acceptance criterion 9's "no hosted gateway/
production deployment" boundary).
"""

from __future__ import annotations

from codesight.axi_skill_gen import SKILL_PATH, render_skill


def test_skill_file_exists():
    assert SKILL_PATH.exists(), (
        f"{SKILL_PATH} is missing - run `python -m codesight.axi_skill_gen`"
    )


def test_committed_skill_matches_generated_skill():
    committed = SKILL_PATH.read_text(encoding="utf-8")
    generated = render_skill()
    assert committed == generated, (
        "`.claude/skills/holus/SKILL.md` is stale relative to "
        "`src/codesight/axi_schema.py`. Run `python -m codesight.axi_skill_gen` "
        "and commit the result."
    )


def test_generated_skill_mentions_every_stable_job():
    generated = render_skill()
    for usage in ("holus\n", "holus evidence", "holus check", "holus status", "holus providers"):
        assert usage in generated, f"skill is missing a reference to {usage!r}"


def test_generated_skill_has_frontmatter():
    generated = render_skill()
    assert generated.startswith("---\nname: holus\n")
