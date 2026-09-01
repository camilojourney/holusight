# ADR-0019: Supervisor-owned G2 acceptance and launcher-only receipts

**Date:** 2026-08-27
**Status:** Accepted

## Context

The initial external evaluator launcher accepted a requester-supplied HMAC key
and record over a one-shot pipe. Pipe shape did not establish authority because
the requester could create the key, record, and pipe together. Replay state was
not atomically supervisor-owned, internal finalization trusted caller-controlled
arguments and environment markers, and launcher receipt persistence reopened a
path after symlink checks.

Byte binding, sandboxing, deny-egress behavior, resource limits, and the
no-promotion boundary remain useful and should be retained.

## Decision

Use a distinct supervisor OS principal as the G2 trust boundary. The supervisor
passes immutable authority and acceptance regular-file descriptors plus a
private state-directory descriptor. All descriptors have the same supervisor
owner, and that owner must differ from the candidate worktree owner. The
launcher consumes replay with an atomic create-only marker in the held state
directory.

The evaluator worker returns prepared evaluation data only. It receives no
acceptance digest, replay identity, configuration authority, or finalization
command. The launcher constructs accepted receipt bytes only after replay
consumption and postflight checks, using the still-held supervisor-owned marker
descriptor as a one-use capability. Accepted receipts are persisted only by the
launcher through a held no-follow directory chain.

Every candidate import requires an OS sandbox. Environment markers cannot skip
nested sandboxing. All preflight and snapshot Git calls disable host config,
replacement objects, and executable candidate-local configuration.

The pinned protocol is `holus-g2-external-acceptance/v2`; see spec 023 and its
JSON protocol pin.

## Consequences

- A requester-created HMAC, record, pipe, file, directory, or replacement
  descriptor cannot establish G2 authority.
- Reopening the same supervisor state directory does not permit replay.
- A consumed acceptance remains consumed after evaluator failure.
- The worker can be called directly only to produce non-authoritative prepared
  data. It cannot construct or persist an accepted receipt.
- Supervisor provisioning requires a distinct OS owner and inherited descriptor
  handoff. Same-owner development invocations fail closed by design.
- Missing OS sandbox support blocks required candidate imports.
- Receipt and replay state are create-only; operators must issue a new
  acceptance rather than overwrite evidence.

## Alternatives considered

- **Keep requester-supplied HMAC bytes in a pipe.** Rejected because the
  requester can mint the entire authority chain.
- **Trust a read-only pathname outside the worktree.** Rejected because mode
  bits and a final-path check do not protect every parent or prevent races.
- **Use environment variables to identify the trusted caller or outer
  sandbox.** Rejected because callers control process environments.
- **Let the evaluator build a receipt and let the launcher validate it.**
  Rejected because a caller-complete internal invocation can reproduce every
  asserted binding.
- **Retain an unsandboxed public/advisory candidate import path.** Rejected
  because it is trusted-equivalent code execution even if its result is labeled
  advisory.
