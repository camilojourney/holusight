# Spec 024: AVO ledger/checkpoint boundary audit

**Status:** immutable design audit; no trial authorization or runtime behavior added.
**Audited input:** `origin/fm/holusight-avo-setup-v1` at
`5679a8ba2e1288e14a3b01907699b467756c933c`.
**Scope:** canonical ledger, checkpoint acceptance, restart/replay, and countability.

## Verdict

**The committed v1 foundation does not fail closed before a row can count.** It
contains JSON *shapes* and prose acceptance rules, but no canonical ledger
parser, cross-record verifier, or count reconciler. Consequently,
the two schemas can accept independently well-formed records whose relationship
is invalid. The foundation correctly remains a no-trial scaffold; no valid trial
should be considered countable until a later, explicitly authorized executor
implements the mandatory rejection checks below.

This audit did not run a trial, read a holdout, access a service, or modify G2.

## Evidence and boundary gaps

| Boundary | What v1 constrains | What remains unbound | Result |
|---|---|---|---|
| Duplicate IDs | `experiment_id` has four-digit syntax; prose says IDs are unique per lane | The ledger schema has no uniqueness or ledger-wide comparison | Two entries with the same ID and different sequences validate independently. |
| Canonical identity | Ledger has `campaign_id` and `lane_id`; checkpoint has lane, branch, and manifest digest | Ledger has neither `branch` nor `manifest_sha256`; checkpoint does not bind its lane/branch to a ledger | A row cannot be proven to belong to the accepted manifest, branch, or checkpoint. |
| Restart/crash replay | `crashed` requires a phase/error class; deterministic replay is prose policy | No attempt identity, input/result digest, retry relation, or terminal-state rule | A crash then a same-ID completion is ambiguous: it can be replay, duplicate work, or fabricated replacement. |
| Checkpoint freshness/publication | Checkpoint has `created_at`, sequence, and tail-shaped hash | No source commit/tree, ledger length, publication ref, expiry, or monotonic comparison | A stale or never-published checkpoint is indistinguishable from a current one. |
| Counts | Checkpoint requires six non-negative integers | No equation ties counts to ledger outcomes; no total, valid-trial count, or tail replay | Arbitrary counts can be structurally valid. |
| Lineage | Each row declares `lineage_parent`; checkpoint declares `lineage_head` | Neither value is constrained as a Git SHA, linked to the prior record, nor reconciled with a kept outcome | A checkpoint can assert a lineage head that disagrees with its ledger. |
| Hashes | Digest fields require `sha256:` plus 64 lowercase hex characters | No canonical serialization rule for ledger entries, verification routine, or required chain | A syntactically correct but unrelated digest is accepted; `ledger_chain` is optional. |
| Schema validation | Constants, required fields, patterns, and `additionalProperties: false` reject several malformed objects | JSON Schema alone cannot enforce repository state or relations across JSONL lines/files | Shape validation is necessary but insufficient for countability. |

The relevant sources are `docs/avo/schemas/ledger.schema.json`,
`docs/avo/schemas/checkpoint.schema.json`, `docs/avo/trial-manifest.v1.json`,
`docs/avo/leakage-boundary.md` (Verification), and
`docs/avo/scoring-control-policy.md` (Invalid trial preflight).

## Adversarial safe vectors

These are logical vectors, not trial records and not instructions to execute a
trial. Every digest below is deliberately synthetic (`sha256:` plus one repeated
hex digit). Each case satisfies the named schema's local type/pattern constraints
unless marked **schema-rejected**, but must be rejected by a future canonical
verifier before it updates any count or lineage state.

| ID | Locally shape-valid input | Mandatory semantic rejection before counting |
|---|---|---|
| `duplicate-id` | Two ledger lines: `{sequence: 1, experiment_id: "0001"}` and `{sequence: 2, experiment_id: "0001"}` with all required trial fields | Reject the second line as a duplicate within the canonical lane ledger. |
| `lane-identity-mismatch` | Ledger `lane_id: "laptop-calibration-0001-0013"`; checkpoint `lane_id: "mini-supervisor"`, `branch: "fm/holusight-avo-mini-supervisor"` | Reject unless the checkpoint's registered branch, lane, manifest, and replayed ledger are one identity. |
| `crash-replay-ambiguity` | A `crashed` line for `0002`, followed after restart by `completed` for `0002` | Reject/count neither completion until a declared retry relation, matching frozen inputs/seed, and replay digest establish exactly what is being resumed. |
| `stale-unpublished` | Checkpoint with an old RFC 3339 `created_at`, arbitrary valid `checkpoint_sequence`, and syntactically valid tail digest | Reject unless a verified source commit/ref proves it is published, current relative to the canonical ledger, and within the freshness policy. |
| `lineage-disagreement` | Last `kept` row says `lineage_parent: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"`; checkpoint says `lineage_head: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"` | Reject unless lineage head is derivable from the replayed accepted ledger and verified Git objects. |
| `hash-not-content` | Checkpoint `ledger_tail_sha256: "sha256:` + 64 `c` + `"` and counts all `999` | Reject unless the tail bytes, canonical serialization, chain, sequence, and outcome counts recompute exactly. |
| `schema-rejected` | Unknown `schema_version`, uppercase digest hex, missing required `counts`, or an extra property | Reject at schema validation, before any semantic validation or count update. |

## Required fail-closed acceptance order

A future runner/checkpoint importer must keep candidate state uncounted and
unpublished until all of these checks pass, in this order:

1. Load the verified setup-branch manifest by immutable commit and recompute its
   documented canonical hash; reject a different manifest, schema, lane, branch,
   or partition.
2. Parse the entire canonical lane JSONL strictly. Require contiguous sequences,
   unique experiment IDs (with an explicit, validated retry model if retries are
   later authorized), one canonical encoding per line, and a required hash chain.
3. Recompute every ledger-tail hash and checkpoint count from the parsed ledger.
   Require the checkpoint sequence, last experiment, and tail to identify the
   same ledger prefix.
4. Verify checkpoint publication provenance: registered branch, immutable commit
   and tree, expected path, bounded size, and a freshness/monotonicity policy.
5. Verify lineage transitions against accepted outcomes and Git objects. Only a
   verified `kept` transition may advance the head.
6. Atomically record acceptance only after all checks succeed. On every failure,
   retain zero changes to counts, lineage head, or supervisor state and record
   only a locally safe rejection reason.

The future implementation also needs explicit canonical byte rules for all hashes
and a policy for whether a crashed ID may be retried. Without those decisions,
restart behavior is intentionally uncountable rather than silently accepted.

## Local checks performed

- Confirmed the audited commit is exactly
  `5679a8ba2e1288e14a3b01907699b467756c933c`.
- Inspected the committed schemas, manifest, bootstrap, policy, leakage boundary,
  ADR, and campaign spec only.
- Did not execute an AVO trial or contact any service.
