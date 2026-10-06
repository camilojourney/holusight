# ADR 0020: Retire Graphify graph checks

**Status:** Accepted
**Date:** 2026-10-06

## Context

Spec 028 made Holusight a read-only checker of `graphify-out/graph.json` against its repository (`holus check`/`status`), plus the source scanner from spec 029 (`holus align`). Graphify is now retired across the owner's repositories: in practice the graphs went stale, needed paid LLM extraction to stay current, and did not reduce agent token use in real runs. With no graphs left to check, the graph checker has no input.

## Decision

Remove the Graphify graph checks. Holusight keeps only the deterministic source scanner (`holus align`).

- Delete `consistency.py`, `check`/`status` commands and `Holusight.check()/.status()`.
- Move shared path and Markdown helpers to `paths.py`.
- Remove graph fields from alignment reports (`graph`, `graph_nodes`, `coverage.graph_mapped_files`) and bump the report schema to `holus-alignment-report/v2`. Analyzer rules stay `holus-alignment/v3`, but v1 reports are now incompatible baselines because the schema changed.
- Stop excluding `graphify-out/` from the scanned inventory.

## Consequences

Agents that called `holus check`/`status` get an invalid-command error. Path-claim and graph-integrity findings are gone; duplication and fact-drift findings are unchanged.
