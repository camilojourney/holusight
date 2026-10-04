# Self-Improvement Memory — Holusight

_Current product usage is owned by `README.md`, contracts by `ARCHITECTURE.md`, and priorities by `docs/roadmap.md`. The retrieval/evaluation material below is historical, not runnable guidance._

## Current Reality

The retrieval control plane, scheduled improve-iterate workflow, and agent-focus harness were retired by spec 028. There is no self-improvement heartbeat or active worker scheduler. CI configuration is owned by `.github/workflows/ci.yml`; do not infer live CI results from these historical notes.

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
treat the worker schedule as a historical proposal, not a running system. Retrieval-specific worker definitions are archived and must not be activated for the consistency helper.

## Historical Project State (as of 2026-09-18)

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
- Historical retrieval safety rules are superseded by the current trust boundary in `ARCHITECTURE.md`; do not carry forward re-embedding or chunk-output assumptions.
