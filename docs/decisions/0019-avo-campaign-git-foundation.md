# ADR-0019: AVO campaign Git-only foundation

**Date:** 2026-08-28
**Status:** Accepted

## Context

The captain authorized an overnight Autonomous Variation Operator (AVO) campaign
requiring a clean Git foundation before any calibration trial is valid. Existing
control planes (specs 017–022) provide eval pilot, improvement review, retrieval
variation, subject binding, and versioned suite fixtures — but they do not define
multi-host experiment ID partitions, Mini global supervision, or compact checkpoint
exchange between laptop and Mini lanes.

G2 evaluator-subject pinning remains blocked and must not be modified by this
campaign scaffold.

## Decision

Add a Git-only foundation on branch `fm/holusight-avo-setup-v1`:

1. **Immutable trial manifest** (`docs/avo/trial-manifest.v1.json`) with content hash
   `manifest_sha256`, partitioning laptop `0001`–`0500` and Mini `0501`–`1000`.
2. **Purpose charter and leakage boundary** defining exportable vs forbidden artifacts.
3. **Deterministic scoring and control policy** freezing seeds, metric identities,
   hard constraints, and protected gates.
4. **Append-only ledger schema** and **compact checkpoint schema** for lane branches.
5. **Mini bootstrap documentation** with an exact verification command; Mini is
   global supervisor.

No application code, G2 changes, trial runners, or networking beyond documented
`git fetch` bootstrap.

## Consequences

- Laptop calibration lanes must fetch and verify the manifest before valid trials.
- Checkpoints are permitted only from uniquely named `fm/holusight-avo-*` branches.
- Rejected, indeterminate, and crashed attempts are first-class ledger outcomes.
- Promotion and merge remain human/captain authority — never automatic.
- A later implementation slice may add lane executors; this ADR does not authorize them.

## Rejected alternatives

- **Embed manifest in Python module.** Rejected: Git JSON with content hash is
  inspectable without importing code and matches spec 022 manifest precedent.
- **Shared `.holusight/` telemetry store.** Rejected: violates leakage boundary;
  Git checkpoints only.
- **Single-host campaign.** Rejected: captain partition requires laptop + Mini with
  supervisor role on Mini.
