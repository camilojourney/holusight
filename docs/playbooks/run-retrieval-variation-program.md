# Playbook: Run the controlled retrieval variation program

This program is a local, no-egress experiment over the fixed evidence-display
benchmark. See `specs/020-controlled-retrieval-variation-program.md` for its
safety contract and `docs/decisions/0016-controlled-retrieval-variation-boundary.md`
for the placement decision.

## 1. Inspect the frozen loop

```bash
holus improve-variation-run --format json
```

Inspect `run.program.benchmark_hash`, `run.program.source_fixture_hashes`,
`run.program.implementation_hashes`, and `run.program.evaluator_digest`. Confirm
both candidate definition hashes are present. Read `hard_constraints`
independently from `reward`; do not treat a higher reward as permission to
ignore a protected failure.

The result always has `run.promotion.allowed: false`. Failed and `inconclusive`
results are retained evidence, not outcomes to hide or rewrite.

## 2. Retain an operator-requested derived record

```bash
holus improve-variation-run --record --format json
```

The AXI response keeps the sealed run under `run` and returns paths separately
under `derived_state`. It writes a minimal history record under
`.holusight/improvement-runs/retrieval-variation/` and a complete typed result
under `.holusight/improvement-results/retrieval-variation/`. Neither is
canonical promotion evidence by itself. If a write is refused because of an
unsafe path, investigate rather than bypassing the no-follow storage guard.

## 3. Request independent promotion review

A candidate is never self-promoting. Only after the declared practical and
paired-statistical requirements, replay, and protected constraints pass may a
human create the normal tracked change manifest and use:

```bash
holus improve-review specs/<change>.change.json --phase pre_promotion
```

The tracked manifest must hash-link the canonical benchmark, its source
fixture, every path emitted in `run.program.implementation_hashes`, and the
complete typed result. The result is independently recomputed from clean
tracked inputs, and the manifest itself
must be clean and tracked. Failed or inconclusive candidates remain blocked.
The review still reports `promotion.allowed: false`; the independent human
reviewer decides whether to approve a separate production change. A baseline,
benchmark, evaluator, or candidate must not be modified to make a result pass.

## 4. Add a real-use gap for future review

Report aggregate feedback only:

```bash
holus improve-variation-feedback --signal failure_case --count 2
```

Do not include raw prompts, evidence, customer material, secrets, or personal
data. A human can use `holus improve-intake` to prepare a privacy-screened
proposal, then follow `docs/playbooks/eval-pilot-case-admission.md` and submit
a normal reviewed fixture PR. Feedback never changes gold labels, thresholds,
evaluators, or authority automatically.
