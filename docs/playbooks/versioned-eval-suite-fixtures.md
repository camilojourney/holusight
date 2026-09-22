# Playbook: Versioned local-evaluation suite fixtures

See `specs/022-holusight-versioned-suite-fixtures.md` for the contract.
This playbook validates the suite fixtures and runs the named suite only over
its public development fixture. It never accesses hidden-holdout payloads or
provides acceptance authority.

## 1. Load the named suite

```bash
uv run --extra dev python -c \
  'from pathlib import Path; from holusight.eval_suite import load_suite; \
s=load_suite(Path(".")); print(s.suite_id, s.suite.status, s.development_sha256, s.holdout_manifest.case_count)'
```

Expected: `holusight-local-retrieval-v1 local_advisory_execution` plus the
taxonomy SHA-256 and holdout case count `32`.

## 2. Run the named local advisory suite

```bash
just eval-suite
# equivalent to:
uv run --extra dev python -m holusight.eval_suite run \
  --suite holusight-local-retrieval-v1 --top-k 10
```

The runner invokes the existing retrieval harness only on the visible 85-case
development fixture, in a disposable local index with API credentials removed
and model downloads disabled. Its sole JSON result has one outcome:

- `pass` - the clean Git-bound local development run completed. This is
  advisory evidence, not acceptance, promotion, merge, or deployment authority.
- `block` - suite verification or the existing local harness could not complete.
- `indeterminate` - immutable Git subject binding or bounded harness-report
  verification was unavailable or changed while the run executed.

The result records the immutable commit/tree subject and content hashes for the
suite, method, development fixture, hidden-holdout hash manifest, evaluator,
and bounded aggregate metrics. It never emits query-level evidence, holdout
payload bytes, or an external link update.

## 3. What is candidate-visible

- `tests/fixtures/holusight_eval_taxonomy.json` (85 `dev` cases)
- Suite and method/config manifests
- Bookstore corpus pin inside the hash-manifest (URL, commit, tree, MIT license)

## 4. What is not in this repository

Bookstore query text, qrels, and gold paths. The hash-manifest at
`tests/fixtures/eval_holdout/bookstore-public-v1.hash-manifest.json` is the
only holdout identity. There is no payload directory and no loader.

A later G2-trusted evaluator may pass payload bytes to
`verify_holdout_payload_bytes`. Do not add a repository path that reads them.

## 5. Identity later comparisons must bind

Git subject (spec 021), corpus hash, independent evaluator pin, method/config
hash, and suite plus holdout-manifest hashes. The local runner binds the first,
second, fourth, and fifth identities only for advisory development evidence.
Independent evaluator pinning, candidate-independent acceptance, and promotion
stay with G2/AVO.

Do not use `just eval`, `just eval-suite`, suite loading, or development scores
as promotion evidence.
