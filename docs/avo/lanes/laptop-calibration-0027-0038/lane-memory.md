# Lane memory — laptop-calibration-0027-0038

Persistent operator memory for this lane. Not part of the append-only ledger.

## Identity

- **lane_id:** `laptop-calibration-0027-0038`
- **branch:** `fm/holusight-avo-laptop-calibration-0027-0038`
- **experiment_id_range:** `0027`–`0038`
- **phase:** `evaluator_method_calibration`

## Frozen baseline (pre-manifest)

- **lineage_head:** `e73c4b7a2e80de7d03825123e42ae62dc0e3eb0d`
- **evaluator_identity.digest:** `sha256:d7b969b5cb5d21fa770d0d90f81211d515cb54fa1f5eff8f1052617e9162290a`
  (`src/codesight/retrieval_variation.py` at lineage head)
- **evaluator_identity.method_config_sha256:** `sha256:8507da9e978b3a313f3ab6d8b0c28b752a223b8b27dac13e4a9781f5f62b335a`
  (`tests/fixtures/eval_suites/holusight-local-retrieval-v1.method.json`)

## Manifest gate

- **trials_authorized:** `false`
- **manifest_sha256:** `sha256:28a9f0b69d0c61cf3f223bf13e4412efa11afc8cd90f85fb7cacd2e731f4b876`
- **last_manifest_verify:** `2026-08-28T06:12:00Z` (fetched `origin/fm/holusight-avo-setup-v1`, canonical hash verified)
- **charter_review:** pending independent review and firstmate confirmation

## Counters (valid trials only)

| outcome | count |
|---|---|
| completed | 0 |
| kept | 0 |
| discarded | 0 |
| rejected | 0 |
| indeterminate | 0 |
| crashed | 0 |

## Checkpoint state

- **last_checkpoint_sequence:** 0
- **last_experiment_id:** none
- **ledger_tail_sha256:** none (empty ledger)

## Notes

Bootstrap scaffold only. Manifest published and hash-verified locally, but valid
trials remain blocked until independent charter review and firstmate confirmation.
