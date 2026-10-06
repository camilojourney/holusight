# Holusight Conventions

- Python requirements are in `pyproject.toml`; development commands are in `docs/playbooks/development.md`.
- Read-only invariant: never write to a repository being checked.
- Resolve graph and cited paths within the repository root; reject symlink escapes.
- No implicit network access, embedding, or background process.
- Report precise paths/line evidence and honest stale/unknown/unavailable states; never claim prose truth from graph edges.
