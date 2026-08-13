# ADR 0010: Graphify Extension Contract (Not Integrated in v1)

**Status:** accepted  
**Date:** 2026-08-13

## Context

Graphify builds a code knowledge graph (callers, imports, symbols) that could augment retrieval for code navigation. The v1 SMB pilot must ship a truthful, testable product without optional graph dependencies on the critical path.

## Decision

**Do not integrate Graphify into the retrieval pipeline for v1.** Document an extension contract and keep ordinary document/code search working without any graph artifact.

## Evaluation summary

| Criterion | Result |
|-----------|--------|
| Small, testable integration path | No — importing graph artifacts would touch indexer, search ranking, and deployment images |
| License compatibility | Graphify output is repo-local; no blocker, but not validated in CI |
| Failure isolation | Hard — bad graph data could affect ranking if fused naively |
| Required for document search | No — hybrid BM25 + vector + RRF is sufficient for pilot |

## Extension contract (future experiment)

Optional enhancement behind `CODESIGHT_GRAPHIFY_PATH` (not implemented):

1. **Input:** read-only `graph.json` (or Graphify export) generated out-of-band via `graphify update .`
2. **Use:** when a query returns code chunks, attach `related_symbols: [{file, symbol, relation}]` from the graph — display only, no ranking change in v1 experiment
3. **Failure:** if graph missing or stale, log warning and return search results unchanged
4. **Never:** block indexing or search when graph is absent

## Roadmap

1. Prototype read-only graph enrichment in a feature branch
2. Measure whether operators run `graphify update` reliably in client environments
3. Only promote to **Shipped** in `docs/capabilities.md` after automated tests cover graph-present and graph-absent paths

## Marketing rule

Do not claim “Graphify-powered” or “code graph search” on holusight.com until the extension contract is implemented and tested.
