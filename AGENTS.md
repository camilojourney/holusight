# AGENTS.md


# Holusight

Read-only Graphify graph/source consistency helper for agents; no indexing, search, model, or automatic graph rebuild.

## Structure

> WHERE things go in this repo. Read before creating or moving any file.
> Type D -- small CLI consistency helper with historical specifications.

### Root Level

| File/Dir | Purpose |
|----------|---------|
| `CLAUDE.md` | Claude Code quick reference (<=80 lines). |
| `AGENTS.md` | Universal AI entry point. Agent authority matrix. |
| `ARCHITECTURE.md` | Full system architecture (200-500 lines). |
| `README.md` | Human-facing project overview. |
| `COMPARISON.md` | Competitive comparison analysis. |
| `justfile` | Unified task runner (`just --list` to discover). |
| `landing/` | Static public site for holusight.com (Vercel `outputDirectory`). |
| `vercel.json` | Vercel static deploy config; must point at a directory with `index.html`. |
| `pyproject.toml` | Python package config and dependencies (uv). |
| `src/` | Core Python library (`src/holusight/`). |
| `specs/` | Numbered feature specifications. |
| `docs/` | Structured documentation (four categories only). |
| `tests/` | pytest test suite. |
| `devlog/` | Session devlog entries (YYYY-MM-DD.md). |
| `tasks/` | Temporary session task files (delete when done). |
| `.claude/` | Claude Code configuration, rules, agents. |
| `.self-improvement/` | Autonomous improvement system. |

**Never create files at root** unless they are one of the above.

### Source Code (`src/holusight/`)

| Module | Purpose |
|--------|---------|
| `src/holusight/__main__.py` | `python -m holusight` CLI entry point. |
| `src/holusight/api.py` | Read-only Python API. |
| `src/holusight/consistency.py` | Graphify graph/source checker and provenance verification. |
| `src/holusight/cli_axi.py` | `holus` console-script alias. |

### Docs (`docs/`)

**Exactly four categories -- no others.**

| Path | Purpose |
|------|---------|
| `docs/README.md` | Navigation index. |
| `docs/vision.md` | Product vision. Update at most yearly. |
| `docs/roadmap.md` | Now/Next/Later feature plan. |
| `docs/decisions/NNNN-*.md` | ADRs -- immutable once accepted. |
| `docs/playbooks/*.md` | Current development guide and marked historical playbooks. |

**NEVER create** ad-hoc files in `docs/`. Architecture goes in `ARCHITECTURE.md` (root). Specs go in `specs/`. Research and market analysis go in `specs/` as numbered specs, NOT as standalone files in `docs/`.

**NOTE:** `docs/RESEARCH.md` and `docs/MARKET.md` are legacy violations. Their content should be migrated to numbered specs in `specs/` and the files removed. Do not create new files like these.

### Specs (`specs/`)

Numbered feature specs: `specs/NNN-name.md`. Flat structure only. No subdirectories.

### Tests (`tests/`)

| Path | Purpose |
|------|---------|
| `tests/test_*.py` | Test files matching source modules. |

### `.claude/` -- Claude Code Configuration

| Path | Purpose |
|------|---------|
| `.claude/settings.json` | Permissions and hooks. |
| `.claude/rules/*.md` | Behavioral rules (structure, workflow). |
| `.claude/agents/*.md` | Agent definitions. |
| `.claude/agent-memory/<agent>/` | Per-agent runtime memory (gitignored). |

### `.self-improvement/`

| Path | Purpose |
|------|---------|
| `.self-improvement/workers.yaml` | Worker registry. |
| `.self-improvement/NEXT.md` | Priority queue (Manager writes, all workers read). |
| `.self-improvement/MEMORY.md` | Domain knowledge and lessons learned. |
| `.self-improvement/knowledge/` | Knowledge base files. |
| `.self-improvement/memory/trajectory.jsonl` | Append-only run log (gitignored). |
| `.self-improvement/memory/lessons.json` | Distilled patterns (gitignored). |
| `.self-improvement/reports/<worker>/YYYY-MM-DD.md` | Per-worker output (gitignored). |

### What Goes Where

| Content | Location |
|---------|----------|
| New feature spec | `specs/NNN-name.md` |
| Architecture decision | `docs/decisions/NNNN-name.md` |
| Operational guide | `docs/playbooks/name.md` |
| New source module | `src/holusight/{name}.py` |
| Unit test | `tests/test_{module}.py` |
| Dev session notes | `devlog/YYYY-MM-DD.md` |
| Agent priorities | `.self-improvement/NEXT.md` |
| Worker reports | `.self-improvement/reports/<worker>/YYYY-MM-DD.md` |
| Research/market analysis | `specs/NNN-name.md` (never in `docs/`) |
| Competitive analysis | `COMPARISON.md` (root, already exists) |

This project has a graphify knowledge graph at graphify-out/.

Rules:
- When Graphify is installed with proven no-network isolation, query its worktree-local graph first; otherwise inspect source and report graph traversal unavailable.
- Before editing a source file, surface callers and dependents from a safe local graph query when available; otherwise inspect local imports and tests.
- Do not re-read multiple source files after a good query unless the user asks for line-level proof.
- Skip graphify for trivial one-line edits already in context, pure shell/commit/run tasks, and external/non-repo research.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw file browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- Do not auto-refresh the historical Graphify graph during Holusight checks; a separately authorized, no-network build is required.
- In worktrees, use the worktree-local `graphify-out/`; do not share or symlink one graph across active branches.
<!-- graphify:end -->

## Commands

- CLI: `python -m holusight check /path/to/repo`
- Test: `uv run --extra dev pytest tests/ -x -v`
- Lint: `uv run --extra dev ruff check src/ tests/`
- Install: `pip install -e ".[dev]"`

## Parallelism & Skills

**Always use agents to parallelize work.** Launch multiple Agent() calls for independent tasks.

**Use skills for repo work:**

| Task | Skill |
|------|-------|
| Implement, fix bugs, add API | `/code holusight` |
| Write specs | `/specs holusight` |
| Research options | `/research holusight` |
| UX/UI audit + fix | `/ux holusight` |
| Acceptance testing | `/verify holusight` |
| Health check, deps, lint | `/maintenance holusight` |
| Multi-step plans | `/plan holusight` |
| Technical decision | `/consult-engineering holusight` |
| Autonomous systems | `/consult-systems holusight` |
| Business decision | `/consult-business` |
| Aesthetic quality | `/taste holusight` |
| ML experiment design | `/consult-experiments holusight` |

**Agent dispatch:** Claude subagents for research/analysis, Codex for implementation, Gemini for cross-model review.

## Agent Authority Matrix

### Autonomous — No confirmation needed
- Bug fixes in the consistency checker that do not touch security boundaries
- Adding tests, updating docs, improving comments
- Reading any file in the repo
- Running lint and tests (`uv run --extra dev ruff check`, `uv run --extra dev pytest`)
- Writing reports to `.self-improvement/reports/`

### Ask First — Propose, wait for approval
- New dependencies in `pyproject.toml`
- Changes to the `Holusight` public API (`check`, `status`)
- New config environment variables
- Changes to the Claude system prompt in `api.py`

### Never — Hard stop, escalate immediately
- Writing to or deleting files in a repository being checked
- Allowing `folder_path` inputs that traverse outside a validated root
- Returning full file contents from a check (paths and line evidence only)
- Committing secrets or API keys

## Workers

| Worker | Trigger | Model |
|--------|---------|-------|
| `manager` | Weekly | Opus |
| `code-improver` | On-demand | Sonnet |
| `security-sentinel` | Weekly | Opus |
| `judge-agent` | Per cycle | Haiku |
| `prompt-optimizer` | Monthly | Sonnet |
| `model-quality-auditor` | Weekly | Sonnet |

## Role

Holusight is a read-only Graphify graph/source consistency helper. Agents use the CLI or Python API to inspect source-backed errors; Graphify traversal remains external.

**Primary concerns:** graph provenance, precise source evidence, safe path handling, and honest unavailable/stale/unknown states.

## Memory

Each worker with `memory: project` writes to `.claude/agent-memory/<worker>/MEMORY.md`.
Cycle history is in `.self-improvement/memory/trajectory.jsonl`.
Current priorities are in `.self-improvement/NEXT.md`.

## Output Paths

- Worker reports → `.self-improvement/reports/<worker>/YYYY-MM-DD.md`
- Trajectory → `.self-improvement/memory/trajectory.jsonl`
- New specs → `specs/NNN-name.md`
- Decisions → `docs/decisions/NNNN-name.md`

When the user types `/graphify`, invoke the graphify skill before doing anything else.

This project has a graphify knowledge graph at graphify-out/.

Rules:
- When Graphify is installed with proven no-network isolation, query its worktree-local graph first; otherwise inspect source and report graph traversal unavailable.
- Before editing a source file, surface callers and dependents from a safe local graph query when available; otherwise inspect local imports and tests.
- Do not re-read multiple source files after a good query unless the user asks for line-level proof.
- Skip graphify for trivial one-line edits already in context, pure shell/commit/run tasks, and external/non-repo research.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw file browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- Do not auto-refresh the historical Graphify graph during Holusight checks; a separately authorized, no-network build is required.
- In worktrees, use the worktree-local `graphify-out/`; do not share or symlink one graph across active branches.
<!-- graphify:end -->

## Context

- Architecture: @ARCHITECTURE.md
- Rules: @.claude/rules/
- Decisions: @docs/decisions/
- Env template: @.env.example
- Business ops: @business/README.md

@import .claude/rules/workflow.md

## IMPORTANT Rules

- **Read-only invariant** — the checker NEVER writes to the repository it inspects. It only reads the graph and source evidence.
- **Path traversal prevention** — all `folder_path` inputs must be validated against a whitelist or resolved to real paths before use. Never allow `../` escapes.
- **No full file exposure** — findings report paths and line evidence, never entire file contents.

@import .claude/rules/workflow.md

<!-- graphify:start -->
## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- When Graphify is installed with proven no-network isolation, query its worktree-local graph first; otherwise inspect source and report graph traversal unavailable.
- Before editing a source file, surface callers and dependents from a safe local graph query when available; otherwise inspect local imports and tests.
- Do not re-read multiple source files after a good query unless the user asks for line-level proof.
- Skip graphify for trivial one-line edits already in context, pure shell/commit/run tasks, and external/non-repo research.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw file browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- Do not auto-refresh the historical Graphify graph during Holusight checks; a separately authorized, no-network build is required.
- In worktrees, use the worktree-local `graphify-out/`; do not share or symlink one graph across active branches.
<!-- graphify:end -->

## Commands

- CLI: `python -m holusight check /path/to/repo`
- Test: `uv run --extra dev pytest tests/ -x -v`
- Lint: `uv run --extra dev ruff check src/ tests/`
- Install: `pip install -e ".[dev]"`

## Parallelism & Skills

**Always use agents to parallelize work.** Launch multiple Agent() calls for independent tasks.

**Use skills for repo work:**

| Task | Skill |
|------|-------|
| Implement, fix bugs, add API | `/code holusight` |
| Write specs | `/specs holusight` |
| Research options | `/research holusight` |
| UX/UI audit + fix | `/ux holusight` |
| Acceptance testing | `/verify holusight` |
| Health check, deps, lint | `/maintenance holusight` |
| Multi-step plans | `/plan holusight` |
| Technical decision | `/consult-engineering holusight` |
| Autonomous systems | `/consult-systems holusight` |
| Business decision | `/consult-business` |
| Aesthetic quality | `/taste holusight` |
| ML experiment design | `/consult-experiments holusight` |

**Agent dispatch:** Claude subagents for research/analysis, Codex for implementation, Gemini for cross-model review.

## Agent Authority Matrix

### Autonomous — No confirmation needed
- Bug fixes in the consistency checker that do not touch security boundaries
- Adding tests, updating docs, improving comments
- Reading any file in the repo
- Running lint and tests (`uv run --extra dev ruff check`, `uv run --extra dev pytest`)
- Writing reports to `.self-improvement/reports/`

### Ask First — Propose, wait for approval
- New dependencies in `pyproject.toml`
- Changes to the `Holusight` public API (`check`, `status`)
- New config environment variables
- Changes to the Claude system prompt in `api.py`

### Never — Hard stop, escalate immediately
- Writing to or deleting files in a repository being checked
- Allowing `folder_path` inputs that traverse outside a validated root
- Returning full file contents from a check (paths and line evidence only)
- Committing secrets or API keys

## Workers

| Worker | Trigger | Model |
|--------|---------|-------|
| `manager` | Weekly | Opus |
| `code-improver` | On-demand | Sonnet |
| `security-sentinel` | Weekly | Opus |
| `judge-agent` | Per cycle | Haiku |
| `prompt-optimizer` | Monthly | Sonnet |
| `model-quality-auditor` | Weekly | Sonnet |

## Role

Holusight is a read-only Graphify graph/source consistency helper. Agents use the CLI or Python API to inspect source-backed errors; Graphify traversal remains external.

**Primary concerns:** graph provenance, precise source evidence, safe path handling, and honest unavailable/stale/unknown states.

## Memory

Each worker with `memory: project` writes to `.claude/agent-memory/<worker>/MEMORY.md`.
Cycle history is in `.self-improvement/memory/trajectory.jsonl`.
Current priorities are in `.self-improvement/NEXT.md`.

## Output Paths

- Worker reports → `.self-improvement/reports/<worker>/YYYY-MM-DD.md`
- Trajectory → `.self-improvement/memory/trajectory.jsonl`
- New specs → `specs/NNN-name.md`
- Decisions → `docs/decisions/NNNN-name.md`

When the user types `/graphify`, invoke the graphify skill before doing anything else.

This project has a graphify knowledge graph at graphify-out/.

Rules:
- When Graphify is installed with proven no-network isolation, query its worktree-local graph first; otherwise inspect source and report graph traversal unavailable.
- Before editing a source file, surface callers and dependents from a safe local graph query when available; otherwise inspect local imports and tests.
- Do not re-read multiple source files after a good query unless the user asks for line-level proof.
- Skip graphify for trivial one-line edits already in context, pure shell/commit/run tasks, and external/non-repo research.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw file browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- Do not auto-refresh the historical Graphify graph during Holusight checks; a separately authorized, no-network build is required.
- In worktrees, use the worktree-local `graphify-out/`; do not share or symlink one graph across active branches.
<!-- graphify:end -->

## Context

- Architecture: @ARCHITECTURE.md
- Rules: @.claude/rules/
- Decisions: @docs/decisions/
- Env template: @.env.example
- Business ops: @business/README.md

@import .claude/rules/workflow.md

## IMPORTANT Rules

- **Read-only invariant** — the checker NEVER writes to the repository it inspects. It only reads the graph and source evidence.
- **Path traversal prevention** — all `folder_path` inputs must be validated against a whitelist or resolved to real paths before use. Never allow `../` escapes.
- **No full file exposure** — findings report paths and line evidence, never entire file contents.

@import .claude/rules/workflow.md

<!-- graphify:start -->

## graphify

When the user types `/graphify`, invoke the graphify skill before doing anything else.

This project has a graphify knowledge graph at graphify-out/.

Rules:
- When Graphify is installed with proven no-network isolation, query its worktree-local graph first; otherwise inspect source and report graph traversal unavailable.
- Before editing a source file, surface callers and dependents from a safe local graph query when available; otherwise inspect local imports and tests.
- Do not re-read multiple source files after a good query unless the user asks for line-level proof.
- Skip graphify for trivial one-line edits already in context, pure shell/commit/run tasks, and external/non-repo research.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw file browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- Do not auto-refresh the historical Graphify graph during Holusight checks; a separately authorized, no-network build is required.
- In worktrees, use the worktree-local `graphify-out/`; do not share or symlink one graph across active branches.
<!-- graphify:end -->

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
