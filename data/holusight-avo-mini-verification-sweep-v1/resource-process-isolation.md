# AVO Resource and Process-Isolation Verification v1

**Status:** paused — implementation gate not satisfied.
**Basis:** committed canonical input `origin/fm/holusight-avo-setup-v1` at
`5679a8ba2e1288e14a3b01907699b467756c933c`.
**Method:** static, non-executing verification only; no lane, trial, service, hidden
input, credential, or network operation was started.

## Bounded result

The input is intentionally a Git-only foundation, not an AVO executor: its commit
adds only `docs/avo/`, ADR-0019, and spec 023, and no `src/` or `tests/` file at the
basis commit mentions `holusight-avo`. It declares CPU and memory ceilings and a
pause intent, but it cannot yet enforce the fault cases below. Therefore **no valid
trial may start** from this basis; valid-trial state remains **paused** until a later,
separately authorized executor supplies every required enforcement boundary.

Static checks passed:

- The manifest content hash recomputes to its recorded `manifest_sha256`.
- The manifest declares CPU `80`, memory `48 GiB`, `nice_cpu_heavy: true`, and
  `pause_on_pressure: true`.
- The ledger schema can record `crashed` and `rejected` / `resource_limit` outcomes.
- The checkpoint schema is closed (`additionalProperties: false`) and contains neither
  `campaign_pause` nor `lane_close`.

The last result is a contract gap: the policy says lanes halt on either flag via a
supervisor checkpoint, while the published checkpoint schema rejects both flags.

## Non-executing fault vectors

These are acceptance vectors for a future executor. They are not commands and must
not be run against a host until that executor and its authorization exist.

| ID | Fault input | Required oracle before a valid trial can start | Basis result |
|---|---|---|---|
| `RIP-01` | Available workspace disk is below a configured floor. | Reject before creating a child process or durable trial output; record only a bounded `rejected` / `resource_limit` outcome. | **Gap:** no disk-floor field, measurement definition, or enforcement point. |
| `RIP-02` | Sustained CPU exceeds 80% or memory exceeds 48 GiB. | Pause dispatch, terminate no unrelated process, and reject the pending trial without lineage advance. The metric, sampling window, and scope must be defined. | **Partial declaration only:** numeric ceilings exist; no sampler or executor exists. |
| `RIP-03` | A second trial is submitted while the configured concurrency allowance is exhausted. | Refuse the second dispatch; do not queue an unbounded backlog or duplicate an experiment ID. | **Gap:** no concurrency allowance or ownership/lock protocol exists. |
| `RIP-04` | Child stdout/stderr exceeds a configured local capture limit. | Keep a bounded local capture only; do not `tee` raw output to Git, checkpoints, ledgers, telemetry, or the parent transcript. Record a digest/classification only if permitted. | **Partial policy only:** raw-log export is forbidden, but no byte cap, capture sink, or no-tee implementation exists. |
| `RIP-05` | Child exits nonzero, is killed, or its parent faults during evaluation. | Mark the attempt `crashed`, preserve the parent lineage, reap the complete child process group, remove only executor-owned temporary state, and leave protected worktrees untouched. | **Partial vocabulary only:** `crashed` is recordable; cleanup, ownership, and reaping are unspecified. |
| `RIP-06` | Trial code attempts to escape its assigned worktree, alter G2, or affect another lane/process. | Deny the operation through a per-trial isolation boundary; the supervisor and unrelated processes remain intact. | **Gap:** Git branch partitioning is documented, but no OS/process/worktree sandbox is defined. |
| `RIP-07` | A fixture or dependency attempts network egress, reads a credential-bearing environment variable, or emits telemetry. | Start credential-minimized and egress-disabled; fail closed without retry/export; redact any diagnostic to the leakage-boundary allowlist. | **Partial policy only:** egress and export are prohibited, with no runtime egress or environment enforcement. |
| `RIP-08` | Supervisor declares resource/custody/conflict pause before dispatch or between trials. | Start no new trial; preserve current lineage and bounded local state; resume only after an explicit, schema-valid authorization. | **Blocked by schema gap:** policy names `campaign_pause` / `lane_close`, but checkpoint v1 cannot encode them. |

## Preconditions for any future execution

A later implementation must make the following explicit and testable before lifting
this pause: disk floor and monitored paths; CPU/memory measurement window and process
scope; concurrency limit and duplicate-dispatch lock; local log byte cap and sink;
child process-group lifecycle; worktree/sandbox ownership; fail-closed egress and
credential environment; and a schema-valid pause/resume signal. These are design
inputs, not values selected by this report.

## Scope boundary

This record does not modify the frozen manifest, schemas, G2, a laptop branch, or an
executor. It is not a checkpoint or ledger entry and exports no raw logs, telemetry,
credentials, paths, or hidden-holdout material.
