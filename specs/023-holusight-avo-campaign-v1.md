# Spec 023: Holusight AVO Campaign Git Foundation v1

**Status:** Foundation implemented (bounded direct-PR, unmerged pending review).
**Authorization boundary:** captain-authorized overnight AVO campaign scaffold.
This spec authorizes **Git-tracked charter, manifest, schemas, and bootstrap
documentation only**. It does not authorize trial execution, promotion, merge,
networking, telemetry, or G2 modification.

**Depends on:** specs 017–022 (eval pilot, improvement control, retrieval variation,
subject binding, versioned suite fixtures).
**Blocks:** laptop calibration lanes and Mini supervisor lanes until manifest is
merged and verified.

## 1. Purpose

Ship the clean, `origin/master`-based Git-only foundation for the captain-authorized
overnight **Autonomous Variation Operator (AVO)** campaign. Lanes may prepare local
ledger structure but cannot run valid trials until this manifest is published,
fetched, and hash-verified.

The Mini is the **global supervisor** (`0501`–`1000`). Laptop lanes own `0001`–`0500`
only.

## 2. What is built (this PR)

| Artifact | Path |
|---|---|
| Purpose charter | `docs/avo/charter.md` |
| Leakage boundary | `docs/avo/leakage-boundary.md` |
| Immutable trial manifest | `docs/avo/trial-manifest.v1.json` |
| Scoring and control policy | `docs/avo/scoring-control-policy.md` |
| Ledger schema | `docs/avo/schemas/ledger.schema.json` |
| Checkpoint schema | `docs/avo/schemas/checkpoint.schema.json` |
| Trial manifest schema | `docs/avo/schemas/trial-manifest.schema.json` |
| Mini bootstrap | `docs/avo/mini-bootstrap.md` |
| Decision record | `docs/decisions/0019-avo-campaign-git-foundation.md` |

## 3. Experiment ID partition (frozen)

| Host | Range | Phase |
|---|---|---|
| Laptop | `0001`–`0050` | Phase A: evaluator-method calibration |
| Laptop | `0051`–`0500` | Phase B: product interventions |
| Mini | `0501`–`1000` | Global supervisor + Mini-owned trials |

## 4. Valid trial contract

Every valid trial must record, before execution:

- `purpose_id`
- `hypothesis`
- `target_failure_mode`
- exactly **one** `intervention`
- `expected_effect`
- `falsifier`
- `control`
- `protected_gates`
- `lineage_parent`
- `decision_informed`
- `seed` (deterministic derivation from manifest)
- `evaluator_identity`

Ledger schema: `docs/avo/schemas/ledger.schema.json`. Outcomes include
`rejected`, `indeterminate`, and `crashed` — all must be recorded, not dropped.

## 5. Frozen controls

- **Deterministic seeds:** global seed `926223`; per-trial derivation in manifest.
- **Metric identities:** see `docs/avo/scoring-control-policy.md`.
- **Resource guardrails:** ≤80% sustained CPU, ≤48 GiB memory, `nice` for CPU-heavy work.
- **Checkpoint format:** `holusight-avo-checkpoint/v1`; every 10 valid trials.
- **Branch rule:** only `^fm/holusight-avo-[a-z0-9-]+$` may publish checkpoints.

## 6. Mini bootstrap

Exact command: `docs/avo/mini-bootstrap.md`. Lanes must not start valid trials until
the Mini completes bootstrap and manifest verification succeeds.

## 7. Non-goals

- Running trials from this branch.
- Touching G2 code or branches.
- Networking beyond `git fetch` at bootstrap.
- Telemetry, credentials, deployment, promotion, or automatic merge.
- Pushing raw logs, hidden inputs, caches, or local manifests.

## 8. Relationship to existing control planes

AVO reuses vocabulary and thresholds from specs 017, 020, and 022 but adds stricter
partition, checkpoint, and supervisor rules. It does not replace `holus improve-review`,
eval pilot, or retrieval variation — lanes operate within those gates.

See `docs/decisions/0019-avo-campaign-git-foundation.md`.
