# Canonical AVO remediation report for the laptop setup owner

## Canonical decision

The reviewed canonical contract is `fm/holusight-avo-setup-v1`.
The Mini audit is independent review evidence, not a competing contract.

The canonical allocation is 1,000 valid trials:

- Calibration: laptop IDs 0001-0050; Mini IDs 0501-0550.
- Product: laptop IDs 0051-0500; Mini IDs 0551-1000.

Four calibration lanes run per machine, followed by eight laptop and four Mini product lanes.

## Required bounded remediation before any valid trial

Publish one reviewed, committed correction on the canonical laptop branch that:

1. Freezes the canonical allocation and purpose mapping above, with no overlap or gap.
2. Provides visible, immutable, content-bound inputs for AQ-R24, the final G2 evaluator implementation and pin, the manifest, and the evaluator identity.
3. Makes a trial non-countable unless it records and validates the canonical ledger schema, manifest/evaluator hashes, matched control, resource limits, and a valid Git checkpoint.
4. Requires the canonical per-trial fields: purpose_id, hypothesis, target failure mode, one intervention, expected effect, falsifier, matched control, protected gates, lineage parent, and decision informed.
5. Enforces the canonical ledger/checkpoint schema, deterministic allocation, duplicate prevention, crash retention, and Git-only checkpoint validation.
6. Keeps the G2 implementation untouched; does not add hidden inputs, credentials, telemetry, promotion, or merge behavior.
7. Includes machine-independent review evidence showing the corrected contract is internally consistent and launch remains denied until both laptop and Mini independently pass review.

After the corrected commit is published, the Mini will fetch that exact commit and perform a fresh independent review. No trial starts or counts before that review passes.
