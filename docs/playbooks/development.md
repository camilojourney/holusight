# Develop and verify the source scanner

Run in a clean, isolated worktree. Provision tooling with `uv sync --extra dev` before using offline commands. See [README](../../README.md) for installation and common CLI usage, and [Architecture](../../ARCHITECTURE.md) for source-scan contracts.

```sh
uv run --offline --extra dev ruff check src/ tests/
uv run --offline --extra dev ruff format --check src/ tests/
uv run --offline --extra dev pytest tests/ -q
uv run --offline holus align .
```

For the before/after repair workflow and fact-marker examples, follow [README: duplication, explicit alignment, and updates](../../README.md#duplication-explicit-alignment-and-updates).

Use `--scope <repo-relative-file-or-directory>` and/or `--docs` to focus findings; see the [selector contract](../../ARCHITECTURE.md#public-contract). Inspect reported paths and lines directly.
