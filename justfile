# Default: show available commands
default:
    @just --list

# ─── Development ──────────────────────────────────

# Run the MCP server
dev:
    python -m semantic_search_mcp

# Install dependencies (dev)
install:
    pip install -e ".[dev]"

# Run MCP Inspector
inspect:
    npx @modelcontextprotocol/inspector python -m semantic_search_mcp

# ─── Quality ──────────────────────────────────────

# Run all checks (lint + test)
check: lint test

# Lint source code
lint:
    ruff check src/ tests/

# Run tests
test:
    pytest tests/ -x -v

# ─── Autonomous Workers ──────────────────────────

# Run self-improvement cycle
improve:
    claude --agent .claude/agents/manager.md

# Run security audit
audit:
    claude --agent .claude/agents/security-sentinel.md

# Verify repo integrity before committing (checks duplicates, specs, schema, dead modules)
verify:
    python3 /Users/mini/.openclaw/workspace/github/~Projects/system/shared/scripts/repo_verify.py --repo holusight --skip tests || [ $? -eq 2 ]
