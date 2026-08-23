# ADR-0015: Deterministic improvement review manifests and derived records

**Date:** 2026-08-23
**Status:** Accepted

## Context

Specs 017 and 018 establish frozen local evaluation, candidate lineage,
content-minimized intake, an advisory improvement loop, and pre-creation
placement evidence. They do not give a later reviewer one deterministic answer
for a change's stage, its missing traceability links, its next allowed action,
or its promotion blockers.

A free-form model classification would conflict with Holusight's existing
canonical-truth and no-promotion boundaries. A tracked result store would also
risk turning run history into a second source of truth or a training lake.

## Decision

Add the `holus improve-review`, `improve-history`, and `improve-integration`
commands to the existing schema-generated CLI surface. A tracked JSON manifest
with exact classifications, constrained structured sections, repository-relative
links, and SHA-256 link hashes is the only input authority. Structured Markdown
`**Status:**` values may expose a contradiction, but prose is never interpreted
as authority.

Accepted, implemented, and evaluated conclusions must link to a governing
spec/ADR, implementation, tests, explanatory documentation, evaluation case,
and evaluation result. Missing, dangling, wrong-role, duplicate, contradictory,
and stale links are explicit blockers. Research-only, rejected, and superseded
material stays non-authoritative and never receives a false code requirement.

`--record` writes content-minimized history only below the existing gitignored
`.holusight/improvement-runs/` derived-state root. Delete/rebuild is supported;
canonical tracked truth is never written. Promotion remains permanently human
review only, and the stable integration result is local advisory output for a
future consumer, not an actual No Mistakes/Fleet integration.

## Consequences

- Review outcomes are reproducible from tracked metadata and current repository
  bytes, not a model guess.
- Failed candidates and repeated stagnation remain inspectable without gaining
  evaluator authority.
- The interface adds no provider, external egress, paid research action,
  universal directory migration, or parallel CLI family.
- A manifest must be maintained alongside accepted/implemented conclusions.
  This is intentional: explicit traceability is preferable to a plausible but
  guessed link graph.
