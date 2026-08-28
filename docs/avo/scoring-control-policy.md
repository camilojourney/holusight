# AVO Deterministic Scoring and Control Policy v1

**Campaign:** `holusight-avo-v1`  
**Manifest:** `docs/avo/trial-manifest.v1.json`

## Control principle

Hard constraints gate first; reward metrics decide only among constraint-satisfying
outcomes. A reward increase never overrides a protected gate failure (spec 020 precedent).

## Frozen metric identities

| Metric ID | Definition | Source binding |
|---|---|---|
| `required_provider_coverage_mean` | Mean fraction of required providers present in bounded display list | spec 020 / `holus improve-variation-run` |
| `eval_pilot_pass_rate` | Passed cases / total deterministic pilot cases | spec 017 / `holus-eval-pilot-result/v1` |
| `hard_constraint_pass` | Boolean; false if any hard constraint fails | spec 020 hard-constraint set |
| `replay_identical` | Boolean; typed evaluation byte-match on deterministic replay | manifest `deterministic_seeds.replay_required` |
| `git_subject_clean` | Boolean; evaluation subject clean at run time | spec 021 / ADR-0017 |
| `identity_binding_match` | Boolean; suite, method, corpus, evaluator digests match manifest | spec 022 comparison identity |

Primary campaign reward during Phase A (0001–0050): `required_provider_coverage_mean`
under frozen visible-development fixture only. Phase B (0051–0500): combined
`required_provider_coverage_mean` and `eval_pilot_pass_rate` with neither regressed
from lineage parent.

## Hard constraints (always enforced)

1. **No hard-constraint failure** — cap exceeded, invented evidence, hidden required
   provider, wasted capacity, or no-evidence represented as evidence (spec 020).
2. **Protected gate pass** — every trial-declared gate must pass; see manifest
   `protected_gates`.
3. **G2 isolation** — `evaluator_execution: blocked_until_g2_trusted_sandbox` unchanged;
   no G2 branch edits.
4. **No egress** — `egress_allowed: false` for all calibration fixtures.
5. **Hidden holdout custody** — no query text, qrels, or payload bytes read or exported.
6. **Single intervention** — exactly one atomic change per valid trial.
7. **Deterministic replay** — same seed + same inputs ⇒ identical typed result digest.

## Scoring decision table

| Condition | Outcome | Lineage action |
|---|---|---|
| Hard constraint fail | `rejected` | No lineage advance |
| Replay mismatch | `rejected` | No lineage advance |
| Falsifier observed | `discarded` | Record; parent unchanged |
| Reward Δ < 0.05 AND paired p ≥ 0.05 | `indeterminate` | Record; parent unchanged |
| Reward Δ ≥ 0.05 AND paired p < 0.05 AND gates pass | `kept` | Advance lineage head |
| Executor exception | `crashed` | Record crash phase; parent unchanged |
| Supervisor veto | `rejected` | Record `supervisor_veto` |

Statistical thresholds match spec 020 v1: practical delta ≥ `0.05`, paired sign-test
p < `0.05`. At small calibration N, `indeterminate` is an honest outcome, not promotion.

## Protected gates (manifest-frozen)

| Gate ID | Rule |
|---|---|
| `gate.g2.blocked` | G2 evaluator execution remains blocked; no G2 code changes |
| `gate.promotion.denied` | `promotion.allowed` is always false |
| `gate.hidden_holdout.custody` | No holdout payload access or export |
| `gate.egress.off` | No network egress during evaluation |
| `gate.single_intervention` | One intervention per valid trial |
| `gate.manifest.immutable` | Trial invalid if manifest_sha256 differs from verified setup branch |
| `gate.partition.enforced` | experiment_id must fall in lane's registered range |
| `gate.checkpoint.branch_unique` | Checkpoints only from registered experiment branch |

## Seed derivation (deterministic)

```text
trial_seed = uint32( sha256( experiment_id + ":" + str(global_seed) )[:8], hex )
```

Global seed is frozen in the manifest. Lanes must log `seed` on every ledger entry.
Re-running with the same seed and frozen inputs must yield `replay_identical: true`.

## Control authority

| Actor | Authority |
|---|---|
| Laptop lane | Execute trials in assigned ID range; append ledger; publish checkpoints |
| Mini (global supervisor) | Verify manifests; resolve cross-lane conflicts; veto invalid trials; own 0501–1000 |
| Setup branch | Publish immutable manifest only — no trial execution |
| Human / captain | Promotion and merge — never automatic |

The Mini is the **global supervisor**. Laptop lanes must halt new trials when the Mini
declares `campaign_pause` or `lane_close` via supervisor checkpoint.

## Invalid trial preflight

Reject before execution (ledger outcome `rejected`) when any of:

- Manifest not fetched and hash-verified from `origin/fm/holusight-avo-setup-v1`
- Missing any required trial field
- experiment_id outside lane partition
- Multiple interventions declared
- Branch name does not match checkpoint policy pattern
- Resource guardrails cannot be honored
