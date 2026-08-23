# ADR-0013: Safe continuous-evaluation pilot — smallest useful loop, not spec 012's suite

**Date:** 2026-08-23
**Status:** Accepted

## Context

Specs 011 and 012 (research only, no implementation authorization) both
describe substantial continuous-evaluation architectures: spec 011's
"Improvement architecture" (frozen task corpus → candidate in shadow →
paired comparison → canary → promote or rollback) and spec 012's full
96-task private suite with held-out splits, human annotation, a 17-arm
router benchmark, and a multi-stage paid-API experiment ladder.

A captain-authorized delegated decision
(`/Users/camiloslaptop/.treehouse/firstmate-8bf1b0/6/firstmate/data/holusight-eval-safe-pilot-v1/delegated-decisions.md`)
authorized a **bounded, no-spend, Holusight-only pilot** implementing
"the smallest useful local/no-spend continuous evaluation and improvement
loop" — explicitly not spec 012's suite, and explicitly deferring
second-repository generalization, paid-API benchmark arms, and any
registry/interface-study spend.

Separately, PR #20 (commit `e516db769f44f0b9b71c23216bc19b04d5219a22`)
had already reproduced and fixed a real `holus evidence --mode auto`
usage gap (a single provider's own scan budget could starve every other
provider's already-successful evidence out of the capped display list).
That fix shipped with strong unit-test coverage
(`tests/test_cli_axi.py`) but no durable, provenance-carrying regression
mechanism outside the ordinary test suite, and no demonstrated
candidate-vs-status-quo comparison framework this repository could reuse
for a *future* similar fix.

A prior draft of a successor spec (referenced by the delegating decision
as `spec-013-draft-custody`) could not be located in this worktree. The
delegated decision explicitly forbids reconstructing its missing text.

## Decision

Build the smallest possible version of spec 011/012's evaluation loop —
4 frozen, human-admitted cases, all deterministic, all local — as a new
module (`src/codesight/eval_pilot.py`) and a new spec
(`specs/017-holusight-safe-continuous-evaluation-pilot.md`) that is
explicitly built only from specs 011/012 plus current repository
evidence plus merged work (PRs #16–#20), never from the missing draft.

Concretely:

1. **Seed the frozen corpus with the one real, already-reproduced usage
   gap this repository has** (PR #20's provider-starvation fix), rather
   than inventing synthetic bugs. This is the pilot's one genuine
   candidate-vs-status-quo comparative case: the shipped fix runs against
   a frozen pre-fix comparator (`eval_pilot._naive_concatenate_then_slice`,
   kept only as a fixture, never imported by production code) on the same
   synthetic input.
2. **Add three more deterministic regression cases** anchored to
   already-documented spec contracts (dangling-reference detection,
   deterministic hash-diffing, egress-off-by-default) rather than
   inventing new claims this pilot has no authority to assert.
3. **No held-out split, no statistical apparatus, no router benchmark.**
   At 4 deterministic cases with no untrusted candidate executor, none of
   spec 012's machinery for hiding truth from an adversarial candidate
   applies yet — see spec 017 §6.3 for how evaluator-isolation is instead
   enforced (structural read-only access + content-hash pinning + human
   PR review, matching how every other change to this repository is
   already governed).
4. **Two Fleet v1.2-shaped exports, additive only.** A content-free
   aggregate scorecard and a minimal domain-result summary, mirroring
   `fleet_scorecard.py`'s (PR #19, spec 016) existing precedent — but
   **not** wired as `agentic/manifest.yaml`'s declared `eval_entrypoint`,
   which stays `just fleet-smoke` unchanged. This pilot does not touch
   the landed Fleet wiring.
5. **Document, not fix, the spec-002 default drift.** Per the delegated
   decision's `spec002-default-drift` item, spec 002's stated default
   embedding model (`nomic-embed-text-v1.5`) does not match the actually
   shipped default (`all-MiniLM-L6-v2` / `voyage-code-3`). This ADR's
   companion spec adds a status note to spec 002 explaining the drift; no
   code changes.

## Consequences

**Easier:** the next reproduced `holus`/consistency usage gap has a clear,
low-ceremony place to land as a frozen case (`docs/playbooks/eval-pilot-case-admission.md`),
with provenance and a status-quo comparison built in from day one rather
than retrofitted later. A human reviewing a future PR can see, mechanically,
whether it broke something this pilot already knew to check.

**Harder / deferred:** this pilot does **not** give Holusight the ability to
compare architectures (Graphify vs. not, semantic vs. lexical, router vs.
no-router) the way spec 012 envisions — that remains future, separately
authorized work, gated on this pilot first demonstrating value (per the
delegated decision's `second-repo-authorization` deferral). Anyone
tempted to grow the frozen corpus toward spec 012's 96-task design inside
this pilot's existing scope should instead write a new numbered spec
requesting that expansion explicitly, per spec 013's own precedent for
gating Phase 2 work on demonstrated need (spec 013 §5).

## Alternatives Considered

### Alternative A: Reconstruct the missing draft from context clues

Rejected outright by the delegating decision itself ("Do not reconstruct
its missing text... Any successor must be a new tracked artifact"). Even
setting that aside, reconstructing unverifiable prior content risks
silently reintroducing scope, claims, or authorization boundaries no one
currently backs.

### Alternative B: Build directly toward spec 012's 96-task suite

Rejected. The delegated decision is explicit that second-repository
generalization and the fuller experiment ladder are deferred pending
evidence from this smaller pilot. Building the larger apparatus first
would also violate the "smallest useful loop" instruction and introduce
held-out-split/annotation-manual complexity this repository has no
current need for (no untrusted candidate executor exists yet — see
Decision item 3).

### Alternative C: Wire this pilot as the new Fleet `eval_entrypoint`

Rejected. `agentic/manifest.yaml`'s `eval_entrypoint` (`just fleet-smoke`)
is already-landed, tested (spec 016, PR #19) production wiring; replacing
or extending it is a product decision beyond this pilot's delegated scope
and risks destabilizing something already working. This pilot's Fleet
exports are additive previews only.
