# Spec 023: Holusight G2 External Acceptance Authority

**Status:** Implemented correction, pending independent security review
**Phase:** Direct-PR correction slice
**Depends on:** Spec 021 (immutable Git subject binding), spec 022 (versioned suite identity)
**Created:** 2026-08-27
**Updated:** 2026-08-27

## Problem

The first G2 launcher bound candidate, evaluator, corpus, configuration, and
launcher bytes, but its authority could be minted by the requester. A caller
could supply both an HMAC key and acceptance record, replay identical bytes
through a new descriptor, invoke an internal finalization command with spoofed
environment state, or race path-based receipt storage. Candidate-local Git
configuration and unsandboxed candidate import fallbacks added independent
code-execution paths before the evidence boundary was complete.

A receipt produced under those conditions is not independent acceptance
evidence, even when all candidate bytes are correctly hashed.

## Security boundary

The candidate repository is evidence only. The supervisor is a distinct OS
principal that owns three inherited descriptors:

1. an immutable regular authority descriptor containing the authentication key
   and exact acceptance digest
2. an immutable regular descriptor holding canonical acceptance bytes
3. a private state-directory descriptor in which replay identities are consumed
   with create-only markers

The owner of all three descriptors must differ from the candidate worktree
owner. Authority and record descriptors must be immutable while held. The
state descriptor must name a supervisor-owned `0700` directory. The launcher
never reopens acceptance through a pathname.

The supervisor launches the trusted launcher as its own principal. A requester
cannot satisfy this boundary by creating another pipe, file, directory, HMAC,
or descriptor with the same bytes.

## Protocol

The canonical protocol pin is
`specs/023-g2-external-acceptance.protocol.json`.

| Contract | Version |
|---|---|
| Protocol revision | `holus-g2-external-acceptance/v2` |
| Acceptance record | `holus-external-evaluator-acceptance/v2` |
| Supervisor authority | `holus-supervisor-evaluator-authority/v2` |
| Replay marker | `holus-supervisor-replay-state/v1` |
| Prepared worker result | `holus-prepared-trusted-evaluation/v1` |
| Launcher finalization | `holus-trusted-evaluation-finalization/v2` |
| Receipt | `holus-trusted-evaluation-receipt/v1` |

The accepted evaluator pin must name the exact protocol revision and the closed
source set in the protocol pin. Any evaluator or protocol revision requires a
new separately reviewed pin and acceptance. A candidate change manifest does
not grant acceptance and must not contain the acceptance record or its digest.

## Launch sequence

1. Resolve the candidate worktree and run Git preflight with system, global,
   and known executable local configuration disabled.
2. Read authority and acceptance bytes exactly once from held, no-follow,
   supervisor-owned descriptors.
3. Verify canonical closed JSON, the supervisor-owned HMAC, expiry, replay
   identity, byte digests, candidate/evaluator ancestry, corpus, manifest,
   launcher, and no-egress configuration.
4. Atomically create the replay marker in the held supervisor state directory.
   Existing markers reject replay, including replay through a newly opened
   descriptor.
5. Create evaluator and candidate snapshots with hardened Git configuration.
6. Run the accepted evaluator in the outer OS sandbox. Every candidate import
   runs in a second OS sandbox. Missing sandbox support fails closed.
7. Accept only a prepared evaluation result. The worker has no acceptance
   fields, finalization command, receipt builder, or receipt writer.
8. Recheck candidate/configuration binding and expiration after evaluation.
9. Construct the receipt in the launcher using the held one-use replay marker
   capability.
10. Recheck expiration and persist through a held no-follow receipt directory.
    Parent replacement or symlink races reject and clean up.
11. Return advisory progress with `promotion.allowed: false`.

## Required controls

- Candidate imports never fall back to installed or unsandboxed code.
- Environment variables cannot claim an existing outer sandbox, launcher
  authority, resource monitor, or candidate broker bypass.
- Sandbox profiles deny egress and restrict writes to scratch.
- Resource and output limits remain in force for evaluator and candidate work.
- Receipt construction and accepted-receipt persistence reject caller-created
  capabilities and advisory APIs reject external acceptance bindings.
- Replay is consumed before evaluation and remains consumed when evaluation
  fails.
- Expiration is checked at authentication, replay consumption, postflight,
  receipt construction, and immediately before persistence.
- Git operations use no replacement objects and disable executable candidate
  configuration such as `core.fsmonitor` and hooks.
- No code in this contract promotes, deploys, starts trials, accesses hidden
  inputs, or mutates canonical candidate evidence.

## Failure modes

| Failure | Result |
|---|---|
| Descriptor owned by candidate | Reject as requester-mintable |
| Authority/record owners differ | Reject |
| Writable authority or acceptance bytes | Reject |
| Replay marker exists | Reject before evaluation |
| Acceptance expires during evaluation | Reject without receipt |
| Required OS sandbox unavailable | Reject |
| Old internal finalization command or spoofed environment | No accepted receipt path |
| Receipt parent is a symlink or changes while held | Reject and remove partial link |
| Hostile local Git executable configuration | Ignored by preflight and snapshot Git |

## Adversarial coverage

`tests/test_g2_external_acceptance_adversarial.py` directly covers:

- self-minted authority descriptors
- byte-identical replay through a newly opened descriptor
- the complete former internal-finalization forgery shape
- sandbox and broker environment spoofing
- receipt parent symlink and directory-swap races
- hostile local `core.fsmonitor`
- expiry after evaluation and before receipt construction
- caller-created receipt capability descriptors

`tests/test_evaluator_subject_pin.py` retains the byte-binding, replacement
object, nested sandbox, deny-egress, resource-limit, immutable pin, and
no-promotion cases while using the v2 supervisor-descriptor protocol.

## Governance and release boundary

This correction is not an acceptance result. It does not modify an existing G2
branch, recovery ref, PR, trial, promotion, deployment, no-mistakes state, or
history. No validation or hidden-input access is authorized in this slice. A
fresh independent security review must approve the exact correction commit
before any later validation or acceptance run.
