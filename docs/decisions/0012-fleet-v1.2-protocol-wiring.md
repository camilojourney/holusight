# ADR-0012: Wire to Fleet's landed v1.2 agentic contracts, don't reconstruct them

**Date:** 2026-08-23
**Status:** Accepted

## Context

A launch instruction asked Holusight to implement a "captain-authorized,
direct-PR Holusight Fleet agentic v1.2 protocol pilot": wire this repo's
existing consistency evaluator to canonical Fleet v1.2 contracts, without
reconstructing or copying those contracts into this repository.

Discovery (see `specs/016-fleet-v1.2-protocol-pilot.md` §2 for the full
trail) found that:

- `graphify` and the `fleet_graphify.py` wrapper this repo's own
  `AGENTS.md` references are unavailable in this execution environment
  (matching the documented, already-handled degrade pattern in
  `consistency.py`'s structural provider).
- The canonical contracts exist and were merged same-day, one commit
  before this pilot started: `github.com/camilojourney/fleet-system`,
  commit `7d396b30f0250a414f9115964c945e29b7afb267`
  ([PR #58](https://github.com/camilojourney/fleet-system/pull/58)),
  under `system/shared/contracts/agentic/`. That PR's own `ADR-001` states
  a fleet-side instruction this ADR mirrors on the Holusight side:
  "extend this existing `v1.1` contract additively to `v1.2` rather than
  standing up a second, parallel contract tree."
- That PR's own list of deferred work explicitly names *this* work:
  "Holusight pilot integration ... and actual repository migration onto
  v1.2."
- Fleet's `run_repo_eval.py` (the canonical runner, same repo) has a
  precise, machine-checkable contract for what a repo's declared
  `eval_entrypoint` must do: run to completion, and optionally print one
  JSON object as the *last non-blank stdout line* carrying
  `hidden_correctness`/`scores`/etc. It does not require the repo to
  reimplement Fleet's own hashing, identity, or envelope assembly.
- As of that same commit, `run_repo_eval.py` accepts a
  `fleet.repo_agent_manifest.v1.2` manifest as valid input but still
  hardcodes `"schema": "fleet.eval_scorecard.v1.1"` on its own emitted
  scorecard — v1.2 *output* emission is Fleet-side work not yet landed.
  This ADR's implementation is honest about that gap (see the spec's
  "Scorecard truth and limitations" section) rather than presenting
  Holusight's own v1.2-shaped preview as if it were Fleet's actual
  runner output.

## Decision

Wire additively, at exactly the two points the canonical contract
requires, and nowhere else:

1. `agentic/manifest.yaml` + `agentic/memory.yaml` — Holusight-owned data
   conforming to `fleet.repo_agent_manifest.v1.2` /
   `fleet.memory_policy.v1.1`, declaring one `eval_entrypoint`
   (`just fleet-smoke`) and a matching privacy boundary, per
   `run_repo_eval.py`'s own `validate_agentic_privacy_config` (which
   requires both files to exist and their boundaries to agree exactly).
2. `src/codesight/fleet_scorecard.py` — a pure-function bridge from
   `consistency.check_consistency()`'s existing `ConsistencyReport` (the
   Phase 1 evaluator, unmodified) to Fleet-shaped documents. It reads the
   evaluator's output; it does not re-derive or override the evaluator's
   verdict.

Neither of Fleet's contract schemas, its ADR-001, nor `run_repo_eval.py`
itself is copied into this repository. `agentic/README.md` records the
exact commit/PR pointer to re-locate them if needed.

This pilot deliberately does **not** touch the already-landed
`holus`/AXI command surface (`cli_axi.py`, `axi_providers.py`,
`axi_schema.py`) beyond calling its underlying `consistency` module —
see spec 016 §4 for why a second CLI surface was rejected in favor of
reusing what already exists.

## Consequences

**Easier:**

- No drift between two copies of the same schema: there is only one copy,
  in Fleet's repository, and this repo's `agentic/README.md` points at it
  by commit SHA rather than embedding prose that could silently diverge.
- If Fleet's contracts move to v1.3, only `fleet_scorecard.py`'s mapping
  table and `agentic/manifest.yaml`'s `schema:` string need to change —
  the evaluator itself (`consistency.py`) is untouched by this pilot and
  stays untouched by a future contract bump too.

**Harder:**

- This repo cannot locally validate `agentic/manifest.yaml` /
  `agentic/memory.yaml` against the real JSON Schema files (they aren't
  vendored here) — `tests/test_fleet_smoke.py` instead asserts the
  specific shape constraints (hash patterns, required fields, the
  gate/hidden-correctness invariant) that the schema enforces, as a
  proxy. A schema drift on Fleet's side would not be caught by this
  repo's own test suite until integration.
- `run_repo_eval.py` is not invoked from this repository (it lives in a
  different repo and this pilot does not reach across repos to run it) —
  so `just fleet-smoke`'s actual invocation by Fleet's real runner is
  unverified by this PR. What is verified: the entrypoint command exists,
  is idempotent, costs nothing, and its last stdout line satisfies the
  documented `parse_domain_result()` contract exactly as read from
  Fleet's own source.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Build a new `repository-manifest.schema.json` / `evaluation-protocol.schema.json` pair local to Holusight | This is the exact parallel-contract-tree shape Fleet's own ADR-001 rejected for the same reason: it would duplicate semantics `repo-agent-manifest.schema.json` + `eval-scorecard.schema.json` already cover. |
| Add a new `python -m codesight consistency scorecard` CLI subcommand | Would create a second CLI surface answering a question the already-landed `holus check "<concept>"` (PR #18) already answers (the `ConsistencyReport` for one concept). `fleet_scorecard.py` is a library the smoke suite calls directly instead. |
| Have Holusight's evaluator call Fleet's `run_repo_eval.py` directly (cross-repo invocation) | Out of scope for a direct-PR pilot with no telemetry/deploy mandate, and would require this repo to depend on another repo's script path at runtime — exactly the kind of coupling the ADR's ownership table assigns to Fleet, not to a project repo. |
