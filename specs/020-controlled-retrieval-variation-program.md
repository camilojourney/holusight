# Controlled Retrieval Variation Program v1

**Status:** Implemented.
**Scope:** A local, deterministic variation program for one existing measured
behavior: provider coverage in the bounded `holus evidence` display list.

## Purpose

This is the smallest extension of the existing `holus improve-*` control plane,
not a parallel candidate framework. It evaluates a frozen legacy baseline and
two fixed candidate definitions over `tests/fixtures/holusight_retrieval_variation_benchmark.json`.
The benchmark is synthetic, repository-owned, and backed by the existing
`holusight_eval_pilot_cases.jsonl` evidence-routing regression fixture. No model
is invoked and no external service is contacted.

Graphify lookup was attempted first through the project-mandated
`/Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py`
wrapper. The exact fallback was: the configured script was absent (`[Errno 2]`),
so this design uses the already-verified local control-plane contracts and
fixtures only.

## Fixed experiment contract

- **Baseline:** `baseline-legacy-concatenate-v1`, the pre-fix fixed-order
  concatenate-and-slice display behavior. Its definition hash is emitted on
  every run and it is never overwritten.
- **Candidates:** `candidate-round-robin-v1` and
  `candidate-equal-quota-no-redistribution-v1`. They vary only display
  selection. They cannot supply executable code, modify the evaluator, or
  select their own benchmark.
- **Benchmark:** content-addressed before every run, with exact, hybrid,
  graph/impact, ambiguity, no-evidence, and adversarial provider-flood cases.
  A semantic-provider case is synthetic, so it tests display routing without
  model usage or egress.
- **Lineage:** baseline/candidate definition hashes, benchmark hash, supporting
  fixture hashes, evaluator digest, and result digest are retained. Raw
  prompts, evidence excerpts, secrets, customer content, absolute paths, and
  telemetry are not output or stored.

## Evaluation and decision boundary

Hard constraints are separate from the reward. A candidate must not exceed the
cap, invent evidence, hide a required available provider, waste available
capacity, or represent no evidence as evidence. The declared reward is mean
required-provider coverage.

A candidate needs a practical reward delta of at least `0.05`, an exact
paired-sign-test result below `0.05`, no hard-constraint failure, and a
byte-equivalent replay before it can be *eligible for independent review*. That still cannot promote it:
`promotion.allowed` is always false. Promotion additionally requires an
independent human review through the existing tracked-manifest
`holus improve-review` control plane. A malformed, partial, tampered, stale,
or untrusted result is rejected before inspection and never counts as an
improvement.

Both failed and inconclusive candidates remain in the result. With the v1
small benchmark, the successful round-robin candidate is intentionally
inconclusive for insufficient paired statistical evidence. This is honest
rather than an automatic claim of significance.

## Storage and feedback

`holus improve-variation-run --record` explicitly writes a content-minimized
record only under `.holusight/improvement-runs/retrieval-variation/`, through
the established no-follow atomic storage guard. Canonical source, fixtures,
baseline, evaluator, and benchmark are never writable destinations. Random
record IDs plus atomic replacement make concurrent derived writes safe; a
symlinked path is refused.

Real-use feedback uses `holus improve-variation-feedback --signal ... --count
...`. It accepts only aggregate counts and creates no canonical state. A human
may turn a reviewed, privacy-safe gap into a future fixture using
`holus improve-intake` and the normal fixture PR process.

## Non-goals

No automatic promotion, merge, rollback, threshold change, online learning,
telemetry, model judging, paid API, external egress, private-content capture,
or mutation of candidates, evaluator, baseline, or benchmark.
