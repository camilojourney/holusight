# Playbook: G2 external acceptance handoff

See `specs/023-holusight-g2-external-acceptance.md` and
`docs/decisions/0019-supervisor-owned-g2-acceptance-authority.md`.

This playbook describes the authority boundary. It is not authorization to run
validation, trials, hidden inputs, promotion, or deployment.

## Preconditions

- A fresh independent security review approved the exact launcher/evaluator
  commit and protocol revision `holus-g2-external-acceptance/v2`.
- The candidate worktree is clean and owned by the requester principal.
- The supervisor uses a different OS owner.
- The supervisor has reviewed the candidate change manifest, evaluator pin,
  corpus, launcher, configuration, and expiration window.
- `sandbox-exec` on macOS or `bwrap` on Linux is present. Missing sandbox
  support is a hard stop.

## Supervisor-owned descriptors

The supervisor prepares and opens:

1. A `0400` regular authority document conforming to
   `holus-supervisor-evaluator-authority/v2`.
2. A `0400` canonical acceptance document conforming to
   `holus-external-evaluator-acceptance/v2`.
3. A `0700` replay-state directory.

Authority and record files and the replay directory have the same supervisor
owner. Their owner differs from the candidate worktree owner. Pass open file
descriptors, not paths. Do not expose key bytes to the requester.

The authority document binds the exact acceptance SHA-256, replay epoch and
sequence, key identity, and protocol revision. The acceptance HMAC uses
`hmac-sha256-supervisor-fd-v2` and covers canonical acceptance bytes excluding
only the `attestation` object.

## Launch shape

The trusted supervisor invokes the reviewed launcher with inherited descriptors:

```text
python -I <reviewed-trusted_eval_launcher.py> \
  --repo-root <clean-candidate-worktree> \
  --acceptance-record-fd <record-fd> \
  --supervisor-authority-fd <authority-fd> \
  --supervisor-state-fd <state-directory-fd> \
  --cases tests/fixtures/holusight_eval_pilot_cases.jsonl \
  --candidate-id <accepted-id>
```

Do not substitute path arguments, pipes, environment authority flags, or the
removed `trusted-evaluate-internal` command. The launcher closes authority and
record descriptors after one read. It closes the state descriptor after the
atomic replay marker is created. A supervisor-owned marker descriptor stays
held until receipt persistence consumes it.

## Expected output

A successful launcher response contains:

- finalization schema `holus-trusted-evaluation-finalization/v2`
- external acceptance digest and replay identity
- content-addressed receipt and repository-relative receipt path
- advisory progress
- `promotion.allowed: false`

The receipt path is under
`.holusight/improvement-results/receipts/`. The launcher creates it through a
held no-follow parent and never overwrites an existing receipt.

## Hard stops

Stop without retrying the same acceptance when any of these occurs:

- requester-mintable or mismatched descriptor ownership
- noncanonical or writable authority/acceptance bytes
- an existing replay marker
- expired acceptance, including expiration during evaluation
- changed candidate, evaluator, corpus, manifest, launcher, or configuration
- missing OS sandbox
- sandbox, resource, timeout, or output-limit failure
- receipt parent symlink or directory replacement
- existing receipt identity

Issue a new reviewed acceptance with a new replay identity only after the
failure is independently assessed. Never delete a replay marker to retry.

## Release boundary

A launcher receipt is still advisory evidence. It cannot merge, promote,
deploy, start trials, or authorize hidden-input access. Those actions remain
outside this playbook and require their own reviewed authority.
