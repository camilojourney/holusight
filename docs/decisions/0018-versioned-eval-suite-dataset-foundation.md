# ADR-0018: Dataset-only versioned suite and holdout hash-manifest foundation

**Date:** 2026-08-24
**Status:** Accepted

## Context

Holusight already has a visible 85-case retrieval taxonomy (spec 014), an
immutable Git evaluation subject (spec 021 / ADR-0017), and a separately
prepared 32-case pinned public Bookstore holdout. Completeness-gap G2/G3
still require an independent evaluator pin and a frozen comparison packet
before promotion-relevant comparison can run.

Shipping a named-suite runner or holdout loader now would either execute
an unpinned evaluator or expose hidden cases to candidates. The reusable
local evaluation product therefore needs a dataset/schema foundation first.

## Decision

Add project-owned v1 suite, method/config, and hidden-holdout hash-manifest
schemas, plus committed references to the existing 85-case Holusight
taxonomy and the 32-case Bookstore pin. Keep hidden-holdout *payloads* out
of the repository. Provide hash-manifest verification of caller-supplied
bytes only. Document the five-part identity later comparisons must bind
(Git subject, corpus, evaluator, configuration, suite/manifest hashes).
Do not implement a runner, evaluator execution, comparison, promotion,
receipts, or any holdout access path. Evaluator execution stays blocked
until the trusted G2 sandbox lands.

Do not introduce a new root `eval/` tree. Manifests live under
`tests/fixtures/` and models live in `src/codesight/eval_suite.py`, matching
existing placement rules (ADR-0014).

## Consequences

- A later named-suite entrypoint can load `holusight-local-retrieval-v1`
  without inventing a second schema.
- Candidates can see development cases and the Bookstore *corpus pin*, but
  not Bookstore queries or qrels.
- Comparison remains non-ready: `comparison_identity_is_ready` is false
  without a G2 evaluator pin.
- Current `just eval` behavior and taxonomy bytes stay unchanged.

## Alternatives Considered

- **Copy Bookstore queries into `tests/fixtures/`.** Rejected: that would
  make the hidden holdout candidate-visible.
- **Wait for G2 and ship schema plus runner together.** Rejected: the
  dataset identities need to freeze independently of the trusted sandbox.
- **Root `eval/` directory from spec 012 research.** Rejected: ADR-0014
  and repository structure rules keep canonical placement inside existing
  `src/`, `tests/`, `specs/`, and `docs/` trees.
