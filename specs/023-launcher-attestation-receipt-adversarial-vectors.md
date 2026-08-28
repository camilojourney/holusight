# Launcher-Held Attestation and Accepted-Receipt Adversarial Vectors v1

**Status:** Test-design report only; not implementation authorization.
**Depends on:** spec 021 / ADR-0017 immutable Git subject binding; spec 022 / ADR-0018 versioned suite, method, and holdout-manifest identities.
**Blocks:** Any claim that a launcher-held local attestation and an external accepted-receipt manifest anchor are fail-closed.

## Purpose and strict boundary

This is a bounded, local-only set of adversarial vectors for a future,
captain-approved launcher. It describes assertions a test harness must make
without invoking an evaluator, a trial, G2, a network endpoint, telemetry, or
an external anchor. It does not authorize a launcher, receipt format, transport,
signer, evaluator, receipt writer, replay store, or acceptance implementation.

The tokens below are safe synthetic bytes only. They are not an attestation,
manifest, accepted receipt, signature, or evaluator substitute; a future test
harness may use them solely as opaque input atoms.

| Atom | Synthetic bytes | SHA-256 |
|---|---|---|
| `A0` | `attestation|synthetic|v1|A0` | `sha256:4f9999e93d1ddfc4a5e98c749948b39a332581da322c87c498ed853ba3221590` |
| `A1` | `attestation|synthetic|v1|A1` | `sha256:231844d58817804903a31097873efae8da5b217649acde18a47520c80863daad` |
| `R0` | `receipt|synthetic|v1|R0` | `sha256:ef6587e9767c9341b1a0c4f9c0df4ea228f197311199e6a33f5c26482af2d69c` |
| `R1` | `receipt|synthetic|v1|R1` | `sha256:1a7796dcd55a1857881903d5ef4ce45d0667b4f527678b6ad75f4d80319865b8` |
| `M0` | `manifest|synthetic|v1|M0` | `sha256:3ccfc930ecd8c069def65418526e61eb3342e107f1e9884549eaa6ee013ff965` |
| `M1` | `manifest|synthetic|v1|M1` | `sha256:d3b6f891b264e5c82fa811042b38f3b2422fdec631592419fa28e17c343442a7` |

`S0` is the synthetic, clean subject `(repository_id="synthetic/repo",
commit="1" * 40, tree="2" * 40, clean=true)`. `S1` changes only the commit to
`"3" * 40`; `T1` changes only the tree to `"4" * 40`. `L0` and `L1` are
distinct synthetic launch correlation values. These are labels, not real
repository identities.

## Required fail-closed oracle

A future implementation is conformant only if every vector below produces the
listed rejection **before it can become an accepted launch**. An error response
or a retry is never a fallback to acceptance.

For each rejected vector, the harness must assert all applicable facts:

1. no evaluator, trial, promotion, G2 activity, hidden input access, network,
   or telemetry was invoked;
2. no accepted terminal record, accepted-receipt binding, or external-anchor
   success was persisted;
3. no state used as replay/rollback protection was advanced by unverified
   bytes (a reservation may be recorded only as an explicitly non-accepted,
   abortable state); and
4. the rejection has a deterministic, non-secret reason code. It must not
   expose raw holdout, credential, or receipt content.

A received external response may be represented only by an in-process fake or
state-machine event in these tests. It must never contact or emulate a receipt
service. If a response fails validation, it is untrusted input and cannot be
persisted as accepted evidence.

### Required acceptance order

The launcher must make acceptance observable only in this order:

1. freeze and locally verify the clean Git subject, declared tree, approved
   manifest digest(s), and local-attestation digest;
2. reject malformed input, mismatches, and any direct or indirect
   self-reference before an anchor request is eligible;
3. atomically reserve the unique launch correlation value as non-accepted;
4. only then make an anchor request eligible; verify the returned accepted
   receipt binds the exact frozen identities and that response's correlation
   value; and
5. only after all prior checks persist one immutable accepted binding.

A duplicate submission may return the already-created terminal outcome only
when it is the exact same frozen launch. It must not create a second acceptance,
move a monotonic anchor position, or reinterpret altered input as that launch.

## Adversarial vectors

The baseline tuple is `(S0, A0 digest, M0 digest, L0)`. It is a shape-only
precondition for the cases below and **must not be executed as a valid trial**.
Each vector mutates the baseline through a local state-machine input or an
opaque response event.

| ID | Mutation / setup | Required rejection | Additional assertion |
|---|---|---|---|
| AR-01 receipt substitution | Response event for `L0` supplies `R1` while its declared binding is for a different attestation or a different receipt digest than the frozen `A0`. | `receipt_binding_mismatch` | `R1` is not retained as an accepted receipt for `L0`. |
| AR-02 manifest substitution | Response binds `M1`, or a local request carries `M1`, while the frozen manifest is `M0`. | `manifest_digest_mismatch` | No request is eligible for the local mismatch; a bad response cannot repair it. |
| AR-03 rollback | Seed the local rollback high-water mark above the response anchor position, or make the response protocol/policy generation older than the frozen approved generation. | `rollback_detected` | The high-water mark and accepted state remain unchanged. |
| AR-04 cross-launch replay | First present an otherwise well-formed opaque response for `L0`; then present the same response for `L1`. | `receipt_replay_or_correlation_mismatch` | `L1` has no accepted state and cannot inherit `L0`'s result. |
| AR-05 duplicate delivery replay | Deliver the same response twice for `L0`, including after an accepted terminal state would otherwise exist. | `duplicate_delivery` or exact idempotent replay of the original terminal result | Exactly one immutable acceptance and one monotonic-position update exist. |
| AR-06 self-reference | Put `R0`'s digest or an accepted-receipt identifier in the pre-anchor attestation/manifest, or make a manifest digest field point to its own enclosing object. | `self_reference_forbidden` | Validation stops before reservation or request eligibility. |
| AR-07 malformed response | Supply empty, truncated, non-UTF-8, invalid-structure, unknown-version, duplicate-key, or forbidden-extra-field opaque response bytes. | `receipt_malformed` | Parser failure is terminal for that delivery; no permissive/default field is used. |
| AR-08 local digest mismatch | Declare `A0` while supplying `A1`, and separately declare `M0` while supplying `M1`. | `attestation_digest_mismatch` / `manifest_digest_mismatch` | Reject before any anchor-request event. |
| AR-09 wrong subject | Bind the response or local declaration to `S1` while frozen input is `S0`. | `subject_commit_mismatch` | A matching receipt digest does not override subject binding. |
| AR-10 wrong tree | Bind the response or local declaration to `T1` while frozen input is `S0`. | `subject_tree_mismatch` | A matching commit alone is insufficient. |
| AR-11 dirty or incomplete subject | Set `clean=false`, omit repository identity, commit, or tree, or use a non-canonical identifier. | `subject_not_immutable` | No normalization or branch annotation may fill the missing binding. |
| AR-12 wrong manifest set | Omit a required suite, method/config, or holdout-manifest digest; add an undeclared digest; or permute a set when ordering is part of the approved canonical digest. | `manifest_set_mismatch` | Partial matching never grants acceptance. |
| AR-13 request-before-verification | Inject a request-eligible or sent event before all local steps 1--3 complete. | `acceptance_order_violation` | No external I/O abstraction is called; no reservation becomes accepted. |
| AR-14 accept-before-receipt-verification | Inject an accepted-state write before a response has passed full binding, digest, replay, and rollback checks. | `acceptance_order_violation` | The write is rejected/rolled back; no accepted record remains. |
| AR-15 response-before-reservation | Deliver an otherwise matching response without an existing `L0` reservation, or after an aborted reservation. | `unexpected_or_stale_receipt` | It cannot create a reservation or acceptance retrospectively. |
| AR-16 competing acceptance order | Interleave two local attempts for `L0` so each observes a pre-accept state, then deliver one response. | `concurrent_launch_conflict` for the loser | At most one terminal acceptance is possible; loser cannot retry with changed bytes under `L0`. |

## Harness discipline and completion criteria

These are adversarial contract tests, not trial tests. A future harness should
inject only the listed synthetic atoms and state transitions, record a local
event trace, and assert the oracle after every case. It must omit any live
endpoint configuration and prohibit imports or calls that run evaluators,
access holdouts, create receipts, or transmit data.

The implementation gate is satisfied only when every vector has an automated,
local-only test and every rejection is fail-closed as specified. Until the
captain separately approves and lands the launcher and trusted external anchor,
all valid trials remain paused.

## Verification performed for this report

- `uv run --extra dev pytest tests/test_eval_suite.py -q`
- graphify semantic incremental update was attempted after this document and
  the specs index change, but the local updater required an unavailable LLM
  backend for 129 documentation inputs; its installed wrapper also rejected
  the local `--code-only` fallback. No credential was sought and derived
  `graphify-out/` state remains unchanged.

No evaluator, trial, receipt service, external anchor, G2, hidden input,
credential, network, or telemetry was accessed.
