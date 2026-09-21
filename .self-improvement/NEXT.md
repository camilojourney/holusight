# NEXT — Holusight

_Reconciled 2026-09-18 — previous version described the stale 2026-03-01
"codesight" v0.3 backlog. See `.self-improvement/MEMORY.md` for what changed._

## Status

- **Self-improvement measurement loop** — `just improve-iterate`, live in CI
  daily via `.github/workflows/improve-iterate.yml` — **running**
- **Deterministic agent-focus harness** — `just agent-focus` (context pack +
  fixed alignment council, no LLM) — **shipping**
- **Basic CI** (lint + full test suite on every push/PR) — **running**,
  added 2026-09-18 (did not exist before)
- **PR #27** (frozen-benchmark retrieval variation program) — **closed**,
  2026-09-18: its verdict engine had a proven adversarial hole (a
  reviewer could fabricate a "promotable" result from impossible rank
  data) and duplicated what the simpler, already-merged `improve-iterate`
  loop does. Branch preserved at `fm/holusight-continuous-variation-program-v1`
  if anyone wants to salvage the benchmark fixtures later.
- **PR #32** (AVO overnight campaign foundation) — **closed**, 2026-09-18:
  infrastructure-only, calibration lanes stuck with no supported recovery
  path, superseded by the same simpler loop. Branch preserved at
  `fm/holusight-avo-setup-v1`.

## P0 — Next real gaps

- [ ] **Answer-quality/grounding benchmark** (AQ-R24) still doesn't exist.
  `improve-iterate` measures retrieval ranking, not whether generated
  answers are correct or grounded in the cited chunks. Until this exists,
  "improving" only proves retrieval got better, not the product.
- [ ] **Decide on the `workers.yaml` cron-worker design** — activate it for
  real (needs `ANTHROPIC_API_KEY` secret + explicit spend approval) or
  retire it in favor of the CI-driven measurement loop. See
  `.self-improvement/MEMORY.md`.
- [ ] Production deployment / live MCP still unverified end-to-end.

## Blocked

_Nothing blocked._
