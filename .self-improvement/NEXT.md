# NEXT — Holusight

## Current priorities

Use [the roadmap](../docs/roadmap.md#next) as the authoritative priority list. Retrieval ranking, generated-answer benchmarking, production MCP deployment and the retired improve-iterate/agent-focus commands are not current tasks. No worker schedule is active; see [MEMORY.md](MEMORY.md).

## Historical branch dispositions (2026-09-18)

- **PR #27** (frozen-benchmark retrieval variation program) — **closed**,
  2026-09-18: its verdict engine had a proven adversarial hole (a
  reviewer could fabricate a "promotable" result from impossible rank
  data) and duplicated the then-merged improve-iterate loop.
  Branch preserved at `fm/holusight-continuous-variation-program-v1`
  if anyone wants to salvage the benchmark fixtures later.
- **PR #32** (AVO overnight campaign foundation) — **closed**, 2026-09-18:
  infrastructure-only, calibration lanes stuck with no supported recovery
  path, superseded at the time by that simpler loop. Branch preserved at
  `fm/holusight-avo-setup-v1`.

These are historical records, not evidence of current branch publication, CI or shipping status.
