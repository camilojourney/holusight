# Lane `laptop-calibration-0027-0038`

**Campaign:** `holusight-avo-v1`  
**Branch:** `fm/holusight-avo-laptop-calibration-0027-0038`  
**Host:** laptop  
**Experiment IDs:** `0027`–`0038` (phase A evaluator-method calibration)  
**Purpose:** Deterministic evaluator-method calibration interventions under the
immutable trial manifest on `origin/fm/holusight-avo-setup-v1`.

## Branch-local artifacts

| Path | Role |
|---|---|
| `ledger.jsonl` | Append-only trial ledger (`holusight-avo-ledger/v1`) |
| `checkpoints/` | Compact checkpoint summaries (`holusight-avo-checkpoint/v1`) |
| `lane-memory.md` | Persistent lane state (not a trial record) |

Schemas and campaign policy live on the setup branch — see `docs/avo/charter.md`
there. This lane branch publishes only ledger tails and checkpoints permitted by
`docs/avo/leakage-boundary.md`.

## Authorization gate

No valid trial runs until `docs/avo/trial-manifest.v1.json` is fetched from
`origin/fm/holusight-avo-setup-v1`, byte-verified, and `manifest_sha256` matches.
