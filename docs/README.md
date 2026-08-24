# docs - codesight

Project documentation index.

## Contents

| Path | Purpose |
|------|---------|
| [vision.md](vision.md) | Product vision, core business, and design principles |
| [roadmap.md](roadmap.md) | Versioned feature roadmap (v0.1 through v1.0) |
| [decisions/](decisions/) | Architecture Decision Records (ADRs) |
| [playbooks/](playbooks/) | Step-by-step operational guides |

## Playbooks

| Path | Purpose |
|------|---------|
| [playbooks/development.md](playbooks/development.md) | Dev setup, CLI commands, environment variables |
| [playbooks/client-pitch.md](playbooks/client-pitch.md) | Client meeting prep: FAQ, objections, demo script |
| [playbooks/ship-feature.md](playbooks/ship-feature.md) | Process for shipping new features |
| [playbooks/investigate-bug.md](playbooks/investigate-bug.md) | Bug investigation workflow |
| [playbooks/docker-deployment.md](playbooks/docker-deployment.md) | Single-team Docker / FastAPI pilot ops |
| [playbooks/run-retrieval-eval.md](playbooks/run-retrieval-eval.md) | Run the retrieval eval harness: baselines, taxonomy, opt-in embedding variants |
| [playbooks/improvement-control-review.md](playbooks/improvement-control-review.md) | Deterministic staged review and derived-record rebuild for tracked improvement changes |
| [playbooks/run-retrieval-variation-program.md](playbooks/run-retrieval-variation-program.md) | Run the local controlled evidence-display variation baseline/candidate loop |
| [playbooks/versioned-eval-suite-fixtures.md](playbooks/versioned-eval-suite-fixtures.md) | Load and hash-verify the versioned suite/method/holdout dataset foundation (no runner) |

## Rules

**Only these categories belong in `docs/`.**
Do not create new top-level docs files without a corresponding ADR justifying it.

Shipped-vs-planned capability matrix: [specs/010-capability-inventory.md](../specs/010-capability-inventory.md).
Recommended SMB offer: [business/pilot-offer.md](../business/pilot-offer.md).

For feature specifications, use `specs/` instead.
For research and market analysis, use numbered specs in `specs/` or existing business docs outside `docs/`.
For agent instructions, use `.claude/agents/`.
For self-improvement logs, use `.self-improvement/`.
