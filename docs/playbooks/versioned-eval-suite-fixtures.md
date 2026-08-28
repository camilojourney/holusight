# Playbook: Versioned local-evaluation suite fixtures

See `specs/022-holusight-versioned-suite-fixtures.md` for the contract.
This playbook is dataset validation only. It does not run retrieval eval,
the named-suite runner, or hidden-holdout scoring.

## 1. Load the named suite

```bash
uv run --extra dev python -c \
  'from pathlib import Path; from codesight.eval_suite import load_suite; \
s=load_suite(Path(".")); print(s.suite_id, s.suite.status, s.development_sha256, s.holdout_manifest.case_count)'
```

Expected: `holusight-local-retrieval-v1 dataset_foundation_only` plus the
taxonomy SHA-256 and holdout case count `32`.

## 2. Static runtime-enforcement vectors (not evaluator execution)

`tests/fixtures/runtime_enforcement_adversarial_vectors.v1.json` is a
non-executable, synthetic contract for future G2 sandbox enforcement. It
covers CPU, memory, process, file, wall-time, descendant containment,
cleanup/restart, bounded logs, disk floor, and pause/recovery failure modes.
It must remain `static_vectors_only`, with trials paused; do not turn it into a
host-level stress command or evaluator lifecycle script.

Validate only its static shape and fail-closed assertions:

```bash
uv run --extra dev pytest tests/test_runtime_enforcement_vectors.py -v
```

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
hash, and suite plus holdout-manifest hashes. Evaluator execution and
promotion stay blocked until that G2 pin exists.

Do not use `just eval` output, this suite load, or development scores as
promotion evidence.
