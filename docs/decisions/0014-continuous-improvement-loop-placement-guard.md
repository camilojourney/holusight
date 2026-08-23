# ADR-0014: Continuous-improvement loop v1 — evidence-only placement guard, no directory migration

**Date:** 2026-08-23
**Status:** Accepted

## Context

The captain-authorized launch brief for the Holusight continuous-
improvement loop v1 required two capabilities beyond the already-shipped
eval pilot (spec 017): (1) a discoverable `holus` command family covering
the whole gap-to-regression-case lifecycle, and (2) "safe repository-
placement compliance before proposed artifact creation ... using
`.claude/rules/structure.md`, existing concepts, and canonical locations
... Produce evidence and a recommended existing/new path only; never edit
files automatically. This must address wrong-file and duplicate-artifact
creation without a universal directory migration."

Three design questions needed a decision before implementation:

1. Should the placement guard be able to create directories on the
   caller's behalf when recommending a new path (a candidate first draft
   did exactly this, via `Path.mkdir(parents=True, exist_ok=True)`)?
2. Should the existing generic `docs` artifact type allow any filename
   under `docs/`, or should it enforce `.claude/rules/structure.md`'s
   stated "exactly four categories" rule?
3. How rigorously should the guard enforce each artifact type's specific
   structural convention (`specs/` flat, `tests/test_*.py` naming), versus
   just directory membership?

## Decision

1. **The placement guard performs zero filesystem writes, unconditionally.**
   `cli_axi._recommended_new_path` only calls `.exists()` to steer around a
   name collision; it never creates a directory or file. This is
   independent of whether every schema-declared artifact type's canonical
   root happens to already exist in this repository today — the property
   holds structurally, not by coincidence. `--proposed-path` inputs that
   are absolute or escape the repository (`..`) are resolved through
   `cli_axi._safe_repo_relative_path` before any filesystem check, so an
   adversarial or mistaken path never causes a stat/read against the real
   host filesystem outside this repository either.
2. **The generic `docs` artifact type is restricted to the three fixed
   top-level files** (`docs/README.md`, `docs/vision.md`,
   `docs/roadmap.md`) `.claude/rules/structure.md` actually documents as
   root-level docs/ content. `adr`/`decision` and `playbook` are separate
   artifact types already scoped to `docs/decisions/` and
   `docs/playbooks/` respectively. Any other proposed `docs/*` path is
   refused with `recommended_path: null` and an explicit `guidance`
   string pointing at the correct artifact type — there is no safe
   auto-generated fallback path for an ad-hoc docs/ file, because
   `.claude/rules/structure.md` explicitly forbids one (the
   `docs/RESEARCH.md`/`docs/MARKET.md` "legacy violations" it calls out
   by name are exactly this failure mode).
3. **Structural fine print is enforced per artifact type, narrowly, only
   where `.claude/rules/structure.md` already states it in prose**:
   `spec` must be flat (no subdirectory — "Flat structure only. No
   subdirectories."); `test` must be `test_*.py` directly under `tests/`
   (not `tests/fixtures/`, which is its own `case`/`fixture` type). No
   other artifact type gets an invented rule beyond canonical-location
   membership and duplicate-name detection — `.claude/skills/`,
   `.claude/agents/`, and `src/codesight/` all have real, legitimate
   nested-file conventions (`.claude/skills/holus/SKILL.md`,
   `tests/fixtures/pilot_docs/...`) that a blanket flat-only rule would
   have wrongly rejected.

## Consequences

- **No universal directory migration.** This decision explicitly
  reaffirms the brief's non-goal: the guard is additive evidence layered
  on the existing structure contract, not a rewrite of it. Existing
  content, including the already-known `docs/RESEARCH.md`/`docs/MARKET.md`
  legacy violations (`AGENTS.md`), is left exactly where it is — the
  guard only ever advises on a *new* proposed path.
- **A caller who wants to add content to `docs/` for a purpose that isn't
  README/vision/roadmap/decision/playbook must be told "no" rather than
  handed a plausible-looking new path.** This is a deliberate asymmetry
  with every other artifact type (which do get a generated fallback path)
  — `docs/`'s "exactly four categories" rule has no fifth category to
  fall back into, so inventing one would silently reproduce the exact
  anti-pattern this guard exists to prevent.
- **The guard's structural checks will need a new per-type rule any time
  `.claude/rules/structure.md` adds one.** This is accepted as ordinary
  maintenance, symmetric with how `consistency.py`'s classifier already
  depends on that same file (spec 013 §"Purpose-aware classification").

## Alternatives considered

- **Auto-create the recommended directory/file.** Rejected outright — the
  launch brief is explicit ("never edit files automatically"), and doing
  so for a *placement* check specifically (as opposed to the intake or
  run commands, which never touch the filesystem at all) would have been
  the one place in this loop that quietly crossed from advisory into
  mutating.
- **A single universal "is this path under some tracked top-level
  directory" check**, with no per-type rules. Simpler, but would not have
  caught the two concrete failure modes the brief names by name
  (wrong-file creation via an ad-hoc `docs/` file, duplicate-artifact
  creation via a same-named `tests/test_*.py`) — see spec 018 §6.1 for the
  duplicate-artifact proof this decision makes possible.
- **A general directory-migration proposal** (moving all fixtures under a
  new canonical namespace, etc.). Out of scope per the brief and per
  `.claude/rules/structure.md`'s own stated philosophy — this repository's
  structure is already exact and enforced elsewhere; the gap was evidence
  at *proposal* time, not the structure itself.
