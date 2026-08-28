# Mini AVO verification sweep v1

This aggregate preserves four non-sensitive Mini verification reports as committed coordination evidence.
No report is a trial, checkpoint, evaluator input, or authorization to start a valid trial.

| Area | Source branch | Source commit | Source path | Preserved file |
| --- | --- | --- | --- | --- |
| AQ-R24 and manifest integrity | `fm/mini-verify-input-integrity` | `3c583a9a7466978f1e07d45a9dd6089ac9edf3ef` | `devlog/2026-08-28.md` | `aq-r24-manifest-integrity.md` |
| Ledger, checkpoint, and restart boundary | `fm/mini-verify-ledger-checkpoint` | `2ea9114426ed69ae90def862b80ee1db2467f15b` | `specs/024-avo-ledger-checkpoint-boundary-audit.md` | `ledger-checkpoint-restart.md` |
| Resource and process isolation | `fm/mini-verify-resource-isolation` | `609de3c2224a9ebd0ab3e1dba4144becda9626df` | `docs/avo/resource-isolation-verification.v1.md` | `resource-process-isolation.md` |
| Evaluator, leakage, and purpose schema | `fm/mini-verify-evaluator-leakage` | `523c679a744053c31d0bde1a617ff0395b004c08` | `specs/024-avo-evaluator-and-leakage-input-review.md` | `evaluator-leakage-purpose.md` |

All four reports conclude that valid trials remain paused pending a corrected, reviewed canonical contract with visible immutable inputs and executable enforcement.
