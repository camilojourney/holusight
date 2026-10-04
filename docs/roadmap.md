# Roadmap — Holusight

## Now

- Read-only `holus check` and `Holusight.check()` over an existing Graphify graph.
- Honest `current`, `stale`, `unknown`, `unavailable`, and source-backed error states.
- `holus align` and `Holusight.align()` for Python AST and Markdown duplication candidates, explicit code/code, docs/code and docs/docs scalar-fact alignment.
- Content-addressed before/after reports, changed/deleted inputs and new/resolved/persisting finding IDs.
- Regression tests for unsafe paths, malformed graphs, stale provenance, false positives, ambiguous facts, concurrent edits and public CLI behavior.

## Next

- Add independently justified, source-backed relationship checks without guessing prose truth or silently executing Graphify.
- Evaluate agent usefulness with paired human-reviewed tasks; current synthetic public-command proofs show detection and rescanning, not productivity gains.

## Later

- A separately authorized isolated graph rebuild workflow, only if no-network execution and provenance can be proved.

The former retrieval, web, evaluation, and embedding roadmap is superseded by specs 028 and 029. Earlier specs are historical context, not current product promises.
