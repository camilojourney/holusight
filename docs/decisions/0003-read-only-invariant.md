# ADR-0003: Strict Read-Only Invariant on Indexed Repositories

**Date:** 2026-02-24
**Status:** Accepted

## Context

holusight is a search tool. It has no business writing to the repositories it indexes. If it did write, it could corrupt user code — catastrophic for a developer tool.

Additionally, Claude Code agents can call MCP tools. An agent that modifies files through a search MCP could cause unintended side effects that are hard to audit.

## Decision

**holusight never writes to `repo_path`.** The only writes are to `SEMANTIC_SEARCH_DATA_DIR` (default: `~/.semantic-search/data`), which is explicitly separate from any indexed repository.

Enforcement:
1. All file I/O uses `open(..., 'r')` exclusively for repo files
2. Path traversal guard: all resolved paths must start with `repo_path`
3. `security-sentinel` checks for `open.*'w'` in all changed source files every cycle

## Consequences

- Users can trust holusight will never corrupt their code
- Simplifies the security model significantly
- Makes the tool auditable: any write to repo_path is a bug, not a feature

## Alternatives Considered

None. This is a hard invariant, not a design choice.
