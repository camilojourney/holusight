# Develop and verify the consistency helper

Run in a clean, isolated worktree. Holusight does not build or refresh Graphify's graph.

```sh
uv run --offline --extra dev ruff check src/ tests/
uv run --offline --extra dev pytest tests/ -q
uv run --offline python -m holusight check .
uv run --offline python -m holusight status .
uv run --offline holus align .
```

For a before/after source workflow, explicitly save `holus align . > .holusight/before.json`, inspect cited source, edit it, then run `holus align . --against .holusight/before.json`. Duplicate-only findings need agent review, not automatic deletion. Explicit `holus:fact` annotations define values that must agree; arbitrary prose is not understood or certified. Every run re-reads source; no background daemon or hidden Graphify refresh occurs. Incomplete/incompatible receipts cannot claim resolution.

A historical graph may correctly return `stale` and nonzero even when tests pass. Do not force a rebuild or claim a current verdict from that result. Use `--scope <repo-relative-path>` to focus a graph-backed source file. Inspect reported paths and lines directly; graph edges are not proof of prose claims.
