# Playbook: Ship a Feature

## 1. Write the Spec

Create `specs/NNN-<feature-name>.md` using `specs/000-template.md`.
Get the spec reviewed before writing code.

## 2. Write Tests First

```bash
# Create test file
touch tests/test_<feature>.py
```

Tests must pass before the feature is considered done.
See `.claude/rules/testing.md` for test requirements.

## 3. Implement

Follow patterns in `.claude/rules/code-style.md`.
Keep read-only invariant intact — never write to repo_path.

## 4. Check Security

```bash
# No writes to repo_path
grep -rn "open.*'w'" src/codesight/

# No path traversal
grep -rn "\.\./" src/codesight/
```

## 5. Run Full Suite

```bash
uv run --extra dev pytest tests/ -x -v
uv run --extra dev ruff check src/ tests/
```

## 6. Update Docs

- Update `docs/roadmap.md` to mark the feature complete
- Update `ARCHITECTURE.md` if the module structure changed
- Create an ADR in `docs/decisions/` if a significant design choice was made

## 7. Commit and Push

```bash
git add -p  # stage selectively
git commit -m "feat: <description>"
git push
```
