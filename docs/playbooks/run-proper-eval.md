# Run Holusight proper-eval (local / advisory)

## What this is

`just proper-eval` is the **local/advisory named-suite orchestration** accepted
under [ADR-0019](../decisions/0019-local-advisory-evaluator-promotion-denied.md):

1. Load and hash-verify the versioned suite (`holusight-local-retrieval-v1`).
2. Bind an immutable `EvaluationSubject` (commit/tree/clean).
3. Run visible offline surfaces: `fleet-smoke` then `eval-pilot`.
4. Emit a single JSON result with verdict `pass` | `block` | `indeterminate`.
5. **Promotion is always denied.**

It does **not** score hidden-holdout payloads and is **not** the G2 trusted
sandbox. Spec 022 still marks that evaluator execution as blocked.

## How to run

```bash
just proper-eval
```

Or:

```bash
uv run --extra dev python -m codesight.proper_eval
```

Exit codes: `0` pass, `1` block, `3` indeterminate (dirty/unbound subject with
passing surfaces).

## What “ready” means here

- Suite manifests load and digests match.
- Fleet smoke and eval-pilot both pass on a clean Git subject.
- Humans may use the advisory verdict; nothing may auto-promote/merge/deploy.

## Still deferred

- AVO / G2 external acceptance (PR #32 and related).
- Hidden-holdout scoring / trusted-sandbox evaluator isolation beyond this
  advisory judge pin (`codesight.proper_eval/advisory-v1`).
