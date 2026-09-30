# Holusight Conventions

- Python 3.11+; `uv run --offline --extra dev pytest tests/ -q` and `uv run --offline --extra dev ruff check src/ tests/`.
- Read-only invariant: never write to a repository being checked.
- Resolve graph and cited paths within the repository root; reject symlink escapes.
- No implicit Graphify process, network access, embedding, or graph refresh.
- Report precise paths/line evidence and honest stale/unknown/unavailable states; never claim prose truth from graph edges.
