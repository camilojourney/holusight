# ADR-0019: Local/advisory evaluator finish line — promotion denied

**Date:** 2026-09-16
**Status:** Accepted

## Context

Holusight already ships a local evaluation surface on `master`:

- Fleet v1.2 protocol pilot (spec 016 / ADR-0012): `just fleet-smoke`,
  `agentic/manifest.yaml`, scorecard shaping with no spend, no telemetry,
  and no autonomous promotion.
- Safe continuous-evaluation pilot (spec 017 / ADR-0013):
  `just eval-pilot`, four frozen cases, advisory exit codes only.
- Related vertical slices (specs 013–015, 018–022) for consistency, AXI,
  improvement loop, retrieval variation, subject binding, and versioned
  suite fixtures.

Separately, an overnight AVO / G2 external-acceptance path (PR #32 and
related remediation / integrator work) remains unfinished: no published
branch is currently safe for frozen independent verification of both a
corrected evaluator and AQ-R24 canonical inputs. That path changes
acceptance authority and runtime isolation and must not be conflated with
whether Holusight’s **local** eval surface is ready.

On 2026-09-16 the captain chose the evaluator design that unblocks
finishing Holusight’s eval path: **local/advisory evaluator with
promotion denied** — not the full external-acceptance path, and not a
hold that only reports status forever.

## Decision

1. **Accepted finish line for Holusight evaluations:** the local/advisory
   evaluator surface already on `master` (fleet-smoke + eval-pilot and the
   related no-spend harnesses documented in specs 013–022).
2. **Promotion denied:** `gate_decision`, pilot exit codes, scorecards,
   and comparison outcomes are advisory input for humans only. Nothing in
   this repository may autonomously promote, merge, deploy, retrain, or
   CI-block solely from those verdicts. This reaffirms
   `agentic/manifest.yaml`’s `provenance_policy.default_training_eligibility: false`
   and the no-promotion boundaries in specs 016 and 017.
3. **Deferred, not blocking:** overnight AVO / G2 external acceptance,
   Mini-bounded trial execution, and PR #32 integration remain deferred
   custody work. They are **not** required to call local evaluations
   ready under this decision. Preserve existing protected branches and
   receipts; do not delete or rewrite them under this ADR.
4. **Research stays research:** specs 011 and 012 remain reference-only
   and do not authorize expanding to the 96-task paid suite.

## Operational entrypoint (2026-09-17)

Run the advisory named-suite orchestration with:

```bash
just proper-eval
```

See `docs/playbooks/run-proper-eval.md`. This extends the accepted finish line
with suite identity binding + visible surface orchestration; promotion remains
denied. AVO/G2 external acceptance stays deferred.

## Consequences

### Easier
- Clear captain-facing readiness claim: local evals are the finish line.
- Workers stop treating unfinished AVO/G2 as a blocker for “do we have
  evaluations?”
- Matches shipped code and operator recipes (`just fleet-smoke`,
  `just eval-pilot`).

### Harder / explicit non-goals
- No claim of external acceptance authority or overnight trial readiness.
- No automatic promotion path; human review remains required for any
  candidate that looks “promotable.”
- Expanding the frozen corpus still requires ordinary human-reviewed PRs
  (spec 017 admission playbook).

## Alternatives Considered

| Option | Why not |
|--------|---------|
| Full external-acceptance / G2 path as the finish line | Captain rejected; path not publish-ready; changes acceptance authority. |
| Hold — report only | Captain rejected; decision was needed to finish. |
| Enable autonomous promotion from local gates | Violates standing Holusight/Fleet boundaries and captain preference. |

## How to run (local, advisory)

```bash
just fleet-smoke    # declared Fleet eval_entrypoint; no spend
just eval-pilot     # frozen 4-case pilot + optional scorecard preview
```

Exit codes and scorecards advise humans; they do not authorize promotion.

## Iterative measurement (2026-09-17)

`just improve-iterate` records successive `proper-eval` receipts locally and
emits advisory `progress` / `next_action` signals so agents can improve across
iterations without autonomous promotion.

## Agent focus harness (2026-09-21)

`just agent-focus` gives agents a deterministic context pack and a fixed
alignment council before they change Holusight. It does not spawn chat agents
and does not promote.

