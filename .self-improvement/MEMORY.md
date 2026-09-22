# Self-Improvement Memory — Holusight

_Last reconciled: 2026-09-18. Previous version described the pre-rename
"holusight" v0.3 state (2026-03-01) and was stale — retained history below._

## Current Reality

- The actual working self-improvement harness is the `holus improve-*`
  control plane: `src/holusight/eval_suite.py`, `proper_eval.py`,
  `improve_iterate.py`, `improvement_control.py`, `retrieval_variation.py`.
  See ADR-0019 (`docs/decisions/0019-local-advisory-evaluator-promotion-denied.md`)
  and `docs/playbooks/run-improve-iterate.md`.
- `just improve-iterate` runs the measurement loop by hand; `.github/workflows/improve-iterate.yml`
  now runs it automatically once a day and on every manual dispatch, uploading
  the JSON receipt as a build artifact and failing the job when progress is
  `regressed`, `blocked`, or `indeterminate`.
- `.github/workflows/ci.yml` now runs `ruff check` + the full `pytest` suite
  on every push/PR to `master`. This did not exist before 2026-09-18 — every
  prior PR's "tests passed" claim was self-reported by whichever agent did
  the work, never machine-verified.
- Promotion is always denied by design (ADR-0019). Nothing in this repo
  auto-merges, auto-deploys, or auto-promotes based on any evaluator output.
  A human reviews every candidate change.

## The workers.yaml cron design (below) is NOT wired up

The scheduled-worker design in `workers.yaml` (a `manager` agent doing weekly
coordination, `code-improver` writing code every 6 hours, `security-sentinel`
auditing daily, etc.) was written early on and never connected to any actual
scheduler, credential, or spend authorization — `.claude/agents/*.md` exist
for these roles but nothing ever invoked them on the documented cadence.

Activating it for real would mean an unsupervised agent writing code on a
schedule in CI, which needs an `ANTHROPIC_API_KEY` GitHub secret and an
explicit, informed decision about recurring spend — that is a captain
decision, not something to wire up silently. Until that decision is made,
treat this file's worker schedule as a proposal, not a running system; the
`improve-iterate` GitHub Action above is the real, currently-running
self-improvement heartbeat.

## Project State (as of 2026-09-18)

- Package: `src/holusight/` (project renamed holusight -> Holusight; package
  name unchanged for import stability)
- Test suite: 716 passing, 1 skipped, ruff clean (verified 2026-09-18, now
  enforced by CI on every push)
- Local retrieval/evidence tool: usable, not yet demonstrated production-ready;
  answer-quality/grounding benchmark (AQ-R24) remains design only

## Historical Notes (pre-2026-09-18, may be stale)

- v0.1: Hybrid BM25+vector code search (MCP server)
- v0.2: Enterprise document search pivot (package rename, parsers, Python API, Streamlit)
- v0.3: Pluggable LLM, configurable embeddings, cross-encoder reranking
- Security invariants (still current, unchanged): no writes to indexed
  folders; all paths validated against traversal; content hash guard before
  re-embedding; no full file content in search results, chunks only
