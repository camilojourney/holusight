# AVO Leakage Boundary v1

**Campaign:** `holusight-avo-v1`  
**Applies to:** all laptop lanes (`0001`–`0500`) and Mini supervisor lane (`0501`–`1000`).

## Principle

Git is the only durable interchange. Anything not explicitly exportable below must
stay local, untracked, or never created.

## Never export (Git push, PR body, checkpoint, or ledger)

| Category | Examples |
|---|---|
| Secrets and credentials | `.env`, API keys, tokens, SSH material |
| Raw execution logs | pytest stdout, stack traces, agent transcripts |
| Hidden holdout content | Bookstore query text, qrels, gold strings, payload bytes (spec 022) |
| Private/customer content | Indexed customer folders, production corpora |
| Local manifests and caches | `.holusight/`, `.pytest_cache/`, `.ruff_cache/`, `.venv/`, worktree-local copies |
| Generated telemetry | Timings, token counts, provider traces, embedding vectors |
| Unredacted evidence excerpts | Snippets from live corpora beyond schema-permitted digests |
| Absolute paths | Host-specific filesystem paths in committed artifacts |

## Permitted Git exports

| Artifact | Location | Constraints |
|---|---|---|
| Immutable trial manifest | `docs/avo/trial-manifest.v1.json` | Setup branch only; content-addressed |
| Lane ledger entries | lane branch `docs/avo/lanes/<lane_id>/ledger.jsonl` | Schema-valid, append-only |
| Compact checkpoints | lane branch `docs/avo/lanes/<lane_id>/checkpoints/` | Schema-valid; max 4 KiB per file |
| Lineage head commits | lane branch only | Current-best intervention code only |
| Campaign schemas/policies | setup branch | This foundation slice |
| Canonical purpose mapping | `docs/avo/purpose-mapping.v1.json` | Remediation slice; content-addressed |

## Checkpoint publication rule

Only a **uniquely named experiment branch** matching:

```text
^fm/holusight-avo-[a-z0-9-]+$
```

may publish compact checkpoints. The branch name must appear in the manifest
`lane_registry` or be registered by the Mini supervisor before first checkpoint.
Default branch, `master`, `main`, and G2 branches are forbidden checkpoint publishers.

## Mini supervisor boundary

The Mini (`0501`–`1000`) may aggregate **hashes and counts** from lane checkpoints.
It must not re-export lane-forbidden content. It is the sole authority to declare
campaign pause, lane close, or cross-lane conflict resolution.

## Verification

Before accepting a remote checkpoint or ledger tail:

1. Branch name matches the experiment-branch pattern and lane registry.
2. JSON validates against the published schema.
3. No forbidden key names (`prompt`, `snippet`, `api_key`, `token`, `telemetry`, `path_absolute`).
4. Total serialized size ≤ schema `max_bytes` where defined.
5. `manifest_sha256` matches the verified setup-branch manifest.
6. Purpose mapping digest matches `docs/avo/purpose-mapping.v1.json`.
7. Trial preflight passes `codesight.avo_purpose.validate_trial_preflight` and export
   scan passes `codesight.avo_leakage.validate_export_record`.

Failure at any step ⇒ reject; record as `rejected` ledger entry locally; do not merge
checkpoint into supervisor state.
