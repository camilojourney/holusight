# AVO Campaign Purpose Charter v1

**Campaign:** `holusight-avo-v1`  
**Authorization:** captain-authorized overnight AVO campaign; Git-only foundation.  
**Status:** frozen scaffold — no trial execution authorized by this document alone.

## Purpose

Establish a deterministic, leak-bounded overnight **Autonomous Variation Operator (AVO)**
campaign over Holusight retrieval and evaluator-method behavior. The campaign seeks
calibrated, lineage-tracked interventions that improve measured outcomes without
violating protected gates, hidden-holdout custody, or G2 evaluator isolation.

This charter authorizes **only** the tracked manifest, schemas, policies, and bootstrap
documentation on branch `fm/holusight-avo-setup-v1`. It does **not** authorize
promotion, merge, deployment, paid API use, telemetry export, or modification of G2
code or branches.

## Success criteria (campaign-level)

1. Every valid trial is hypothesis-driven, single-intervention, falsifiable, and
   lineage-linked before execution.
2. Laptop lanes own experiment IDs `0001`–`0500`; the Mini owns `0501`–`1000` and
   acts as **global supervisor**.
3. Checkpoints published to Git contain only compact, schema-valid summaries — never
   raw logs, hidden inputs, credentials, caches, or telemetry.
4. Scoring and control decisions are reproducible from frozen seeds, metric identities,
   and the immutable trial manifest.

## Non-goals

- Running trials from this setup branch.
- Accessing hidden holdout payloads, private/customer content, or credentials.
- Networking, telemetry, autonomous promotion, or merge.
- Touching G2 evaluator-subject pin code or branches.
- Replacing specs 017–022 control planes; AVO extends them under stricter partition
  and checkpoint rules.

## Authoritative artifacts

| Artifact | Path |
|---|---|
| Immutable trial manifest | `docs/avo/trial-manifest.v1.json` |
| Leakage boundary | `docs/avo/leakage-boundary.md` |
| Scoring and control policy | `docs/avo/scoring-control-policy.md` |
| Append-only ledger schema | `docs/avo/schemas/ledger.schema.json` |
| Checkpoint schema | `docs/avo/schemas/checkpoint.schema.json` |
| Trial manifest schema | `docs/avo/schemas/trial-manifest.schema.json` |
| Mini bootstrap | `docs/avo/mini-bootstrap.md` |
| Decision record | `docs/decisions/0019-avo-campaign-git-foundation.md` |
| Spec index entry | `specs/023-holusight-avo-campaign-v1.md` |

Lanes must fetch and verify the manifest from `origin/fm/holusight-avo-setup-v1`
before any valid trial. See `docs/avo/mini-bootstrap.md`.
