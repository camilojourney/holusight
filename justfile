# Default: show available commands
default:
    @just --list

# ─── Development ──────────────────────────────────

# Run the demo app
dev:
    uv run --extra demo python -m codesight demo

# Install dependencies (dev)
install:
    pip install -e ".[dev]"

# Inspect CLI commands
inspect:
    uv run python -m codesight --help

# ─── Quality ──────────────────────────────────────

# Run all checks (lint + test)
check: lint test

# Lint source code
lint:
    uv run --extra dev ruff check src/ tests/

# Run tests
test:
    uv run --extra dev pytest tests/ -x -v

# Run holusight 20-query retrieval eval (task-plan harness)
eval:
    uv run --extra dev python tests/eval_holusight.py --top-k 10

# ─── Autonomous Workers ──────────────────────────

# Run self-improvement cycle
improve:
    claude --agent .claude/agents/manager.md

# Run security audit
audit:
    claude --agent .claude/agents/security-sentinel.md

# Verify repo integrity before committing (checks duplicates, specs, schema, dead modules)
verify:
    #!/usr/bin/env bash
    script="${REPO_VERIFY_SCRIPT:-$HOME/github/fleet-system/system/shared/scripts/repo_verify.py}"
    python3 "$script" --repo holusight --skip tests || [ $? -eq 2 ]
