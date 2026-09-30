# Holusight

Holusight is a small **read-only consistency helper for agents**. It checks an existing Graphify `graphify-out/graph.json` against the repository the graph describes. It reports graph integrity errors, missing source paths/lines, and explicit repository-path references in graph-backed Markdown that no longer exist. It does **not** build the graph, index documents, search, synthesize answers, claim prose is true from graph edges, or call a model/network service.

## Run

```sh
uv run --offline python -m holusight check [repo-path]
uv run --offline python -m holusight check [repo-path] --scope docs/guide.md
uv run --offline python -m holusight status [repo-path]
# after installation: holus check [repo-path]
```

Output is JSON. `status` is `current` only when `built_at_commit` is a full SHA equal to Git HEAD **and** the working tree is clean. A missing or invalid commit is `unknown`, a mismatch or dirty tree is `stale`, and missing/malformed graph data is `unavailable`. Graphify's historical graph in this repository is intentionally **not refreshed** during checks; expect `stale` until an operator rebuilds it independently and proves its provenance. A scope not represented by graph-backed source evidence is `unknown`, not a clean pass. Exit code 0 means a current graph with no detected errors or unverified checks; exit code 1 covers errors, stale, unknown, or unavailable. Error findings in stale graphs are useful leads, not a current clean bill of health.

Graph integrity and literal source/path evidence are bounded checks, not semantic doc/code verification. Agents should inspect cited source lines and use Graphify directly for traversal. No source or graph files are written by `check`.

## Development

```sh
uv run --offline --extra dev pytest tests/ -q
uv run --offline --extra dev ruff check src/ tests/
```

See `ARCHITECTURE.md` and `specs/028-graphify-consistency-helper.md` for the supported contract and migration disposition. Earlier numbered specs and accepted decisions are historical context for the retired retrieval product, not current interfaces.
