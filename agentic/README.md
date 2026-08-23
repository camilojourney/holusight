# Agentic control-plane surface (Fleet v1.2 protocol pilot)

This directory holds Holusight's own repository-evaluation-adapter
manifest and memory policy — data this repository owns and commits,
conforming to schemas it does not own.

## Provenance (do not reconstruct the contracts — read them)

The schemas `manifest.yaml` and `memory.yaml` validate against, the
runner (`run_repo_eval.py`) that consumes them, and the responsibility
boundary they implement all live outside this repository, in:

```
github.com/camilojourney/fleet-system @ 7d396b30f0250a414f9115964c945e29b7afb267
system/shared/contracts/agentic/          (schemas, VERSIONING.md, ADR-001)
system/shared/scripts/run_repo_eval.py    (the canonical runner)
```

PR: https://github.com/camilojourney/fleet-system/pull/58 — "feat: extend
agentic contracts to v1.2 with provenance boundary ADR"

Holusight does not vendor a copy of those JSON Schemas or that ADR. If
that commit becomes unreachable, the exact provenance recorded here
(commit SHA, PR number, file paths) is the pointer to re-locate it — this
directory's own files are not a substitute for reading it.

## Files

| File | Purpose |
|---|---|
| `manifest.yaml` | `fleet.repo_agent_manifest.v1.2` — eval entrypoint, privacy boundary, provenance policy. |
| `memory.yaml` | `fleet.memory_policy.v1.1` — four-tier memory map and the same `exported_to_fleet` / `not_exported_to_fleet` boundary as `manifest.yaml` (the two must agree exactly). |

## What this pilot does and does not do

Wires Holusight's existing Phase 1 documentation-code consistency
evaluator (`src/codesight/consistency.py`, unmodified by this pilot) to
the contracts above via `src/codesight/fleet_scorecard.py`, which shapes
`check_consistency()`'s four outcomes into `fleet.eval_scorecard.v1.2`
documents. See `specs/016-fleet-v1.2-protocol-pilot.md` for the full
design record, scope, and limitations, and
`docs/decisions/0012-fleet-v1.2-protocol-wiring.md` for the decision to
wire additively rather than reconstruct.

Explicitly out of scope for this pilot: nested `/code` invocation, any
production deployment, exposing private/customer content, external
telemetry of any kind, autonomous promotion or merge based on
`gate_decision`, and changing the semantic consistency provider's
opt-in-only default. Everything this directory's files and
`fleet_scorecard.py` produce is local, inert JSON — nothing here makes a
network call.
