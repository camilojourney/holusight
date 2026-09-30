# Roadmap — Holusight

## Now

- Read-only `holus check` and `Holusight.check()` over an existing Graphify graph.
- Honest `current`, `stale`, `unknown`, `unavailable`, and source-backed error states.
- Regression tests for graph symlinks, path traversal, malformed/missing graphs, stale provenance, and public CLI behavior.

## Next

- Add independently justified, source-backed relationship checks without guessing prose truth or silently executing Graphify.
- Evaluate usefulness on human-reviewed, synthetic mismatch cases before expanding coverage.

## Later

- A separately authorized isolated graph rebuild workflow, only if no-network execution and provenance can be proved.

The former retrieval, web, evaluation, and embedding roadmap is superseded by spec 028. Earlier specs are historical context, not current product promises.
