# Develop and verify the consistency helper

Run in a clean, isolated worktree. Holusight does not build or refresh Graphify's graph.

```sh
uv run --offline --extra dev ruff check src/ tests/
uv run --offline --extra dev pytest tests/ -q
uv run --offline python -m holusight check .
uv run --offline python -m holusight status .
```

A historical graph may correctly return `stale` and nonzero even when tests pass. Do not force a rebuild or claim a current verdict from that result. Use `--scope <repo-relative-path>` to focus a graph-backed source file. Inspect reported paths and lines directly; graph edges are not proof of prose claims.
