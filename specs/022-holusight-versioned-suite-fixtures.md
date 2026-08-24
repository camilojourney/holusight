# Holusight Versioned Suite Fixtures v1

**Status:** Dataset foundation implemented (bounded direct-PR).
**Depends on:** Spec 014 (85-case visible taxonomy), spec 021 / ADR-0017 (Git
subject identity), the pinned public Bookstore corpus prepared for the
multi-corpus public packet.
**Blocks:** `holusight-named-frozen-suite-entrypoint-v1` (named-suite runner),
actual evaluator execution, candidate comparison, and promotion.

## Purpose and boundary

This is the dependency-independent, dataset-only foundation for Holusight's
reusable local evaluation product. It ships:

- project-owned versioned **suite** and **method/config** manifest schemas
- a public/non-sensitive **visible development-fixture** reference to the
  existing 85-case Holusight taxonomy
- an immutable **hidden-holdout layout** plus **hash-manifest** handling for
  the existing 32-case pinned Bookstore fixture
- explicit **identity-binding expectations** later baseline/candidate
  comparisons must use: Git subject, corpus, evaluator, configuration, and
  suite/manifest hashes

This is deliberately **not** the named-suite runner. `src/codesight/eval_suite.py`
loads and verifies manifests so the later entrypoint can reuse them. It does
not add a CLI, execute evaluators, compare candidates, promote, write receipts,
open a network/control-plane path, change retrieval models, capture queries,
store secrets, or provide a hidden-holdout access path.

Actual evaluator execution and promotion remain blocked until the trusted G2
evaluator sandbox is approved and landed.

## Schemas

Canonical models live in `src/codesight/eval_suite.py` (`extra="forbid"`).
JSON documents are the committed instances.

| Schema | Version string | Committed instance |
|---|---|---|
| Suite | `holusight-eval-suite/v1` | `tests/fixtures/eval_suites/holusight-local-retrieval-v1.suite.json` |
| Method/config | `holusight-eval-method-config/v1` | `tests/fixtures/eval_suites/holusight-local-retrieval-v1.method.json` |
| Hidden-holdout hash-manifest | `holusight-eval-holdout-hash-manifest/v1` | `tests/fixtures/eval_holdout/bookstore-public-v1.hash-manifest.json` |
| Comparison identity | `holusight-eval-comparison-identity/v1` | schema only; no ready instance in this slice |

Unknown `schema_version`, extra fields, path traversal, and digest mismatch
fail closed.

## Visible development fixture

The suite references `tests/fixtures/holusight_eval_taxonomy.json` in place.

- 85 cases, all `split: "dev"`
- SHA-256 `sha256:71a44eb463c9d0b2a02fecaa03815bf718b72b769bb3bc6b48797da34650981f`
- Role: `visible_development_evidence_not_generalization`

Candidates may inspect this fixture. It is known-repository regression and
implementation evidence only. It is not cross-repository generalization proof
and is not a sealed holdout. This change does not rewrite or weaken those
cases, and it does not alter `just eval` / the 20-query default.

## Hidden holdout layout

Tracked layout:

```text
tests/fixtures/eval_holdout/
  bookstore-public-v1.hash-manifest.json
```

The hash-manifest identifies the 32-case Bookstore holdout by:

- case count and case ids
- family counts (four each of eight families)
- payload filename, byte length, and SHA-256
  `sha256:ae996ee16ba8e73eb4da901682f8c5c441110bbadd9a5997f262cc17f11f6370`
- public corpus pin: `https://github.com/makiftutuncu/bookstore.git` at
  commit `a1d44ad56918e43038d4fed061305b5686ec3c87`, tree
  `516007f03e4dd0ecb6b36d3a218bf2cb2ab83ce2`, SPDX MIT

Query text, qrels, expected files, and gold strings are **not** stored in this
repository. `payload_present_in_repository` is `false` and
`payload_access` is `none_in_this_slice`.

Hash-manifest handling is `verify_holdout_payload_bytes(manifest, payload)`:
the caller already holds the bytes. This module never locates, opens, or mounts
a holdout path. A later G2-trusted evaluator may supply those bytes; this
slice does not.

## Method/config identity

`holusight-local-retrieval-hybrid-v1` declares, without executing:

- deterministic rank / exact-file evidence matching; no LLM judge
- signals `exact`, `bm25`, `semantic`, `graphify_structural`, `hybrid`
- RRF `k=60`, CNFB alpha `0.0` (current default, not a production change)
- query enhancement off; reranker disabled unless independently pinned
- no-answer diagnostic-only
- seed `20260824`
- existing AST-plus-fallback chunker unchanged
- `sha256(chunk_content)[:16]` re-embed guard
- network, paid APIs, model-default change, and promotion all `denied`
- evaluator execution `blocked_until_g2_trusted_sandbox`

## Identity binding for later comparisons

A later baseline/candidate comparison is valid only when all five identities
match. Changing any one invalidates the comparison. A legitimate evaluator
revision requires a separately reviewed protocol revision and a new baseline.

| Identity | What binds it |
|---|---|
| Git subject | `EvaluationSubject` from spec 021: `repository_id`, `commit`, `tree`, `clean`. `branch` is annotation only. |
| Corpus | Content-addressed included-path bytes for each named corpus at that Git subject or the pinned public Bookstore commit/tree. |
| Evaluator | Independent G2 evaluator-subject pin. Blocked in this slice. |
| Configuration | SHA-256 of the method/config manifest. |
| Suite/manifest | SHA-256 of the suite file and of the hidden-holdout hash-manifest. |

`comparison_identity_is_ready()` is false while the evaluator pin status is
`blocked_until_g2_trusted_sandbox` or the Git subject is not clean.

## Named-suite reuse

`eval_suite.load_suite(repo_root, "holusight-local-retrieval-v1")` is the
library load path the later `holusight-named-frozen-suite-entrypoint-v1` task
should call. This slice does not add a CLI or a second loader.

## Non-goals

- Named-suite runner / CLI / library entrypoint beyond `load_suite`
- Evaluator logic or `tests.eval_harness` execution
- Candidate comparison, promotion, receipts
- Network service or control-plane changes
- Retrieval-model or production-default changes
- Query capture
- Private/secret storage or vault/Corpus C access
- Hidden-holdout payload access
- Weakening cases or altering current baseline results
- Paid APIs or deployment

## Graphify

The `graphify` CLI and
`python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py`
wrapper were unavailable on this host. This change was checked against
direct source, the existing 85-case fixture bytes, and the already-pinned
Bookstore public corpus identity. Derived `graphify-out/` state was not
modified.

## Evidence and verification

`tests/test_eval_suite.py` covers: named-suite load of the 85/32 references;
taxonomy hash and split preservation; holdout identified by hash without query
text; unknown suite, unknown schema, extra fields, traversal, and digest
mismatch fail closed; payload-byte verification against the hash-manifest;
no runner/holdout-access symbols or evaluator imports; comparison-identity
shape with G2 still blocked.
