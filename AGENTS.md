# AGENTS.md

# Holusight

Read-only consistency helper for agents. Common usage is owned by `README.md`; module relationships, public interfaces and detailed safety/provenance contracts are owned by `ARCHITECTURE.md`.

## Structure

> WHERE things go in this repo. Read before creating or moving any file.
> Type D -- small CLI consistency helper with historical specifications.

### Root Level

| File/Dir | Purpose |
|----------|---------|
| `CLAUDE.md` | Claude Code pointer to this file. |
| `AGENTS.md` | Universal AI entry point. Agent authority matrix and placement rules. |
| `ARCHITECTURE.md` | System architecture and detailed contracts. |
| `README.md` | Human-facing product overview and common usage. |
| `COMPARISON.md` | Historical competitive comparison analysis. |
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
| `.self-improvement/` | Worker registry, priorities and historical records; no active scheduler. |

**Never create files at root** unless they are one of the above.

### Source and Tests

Use `src/holusight/{name}.py` for source modules and `tests/test_{module}.py` for tests. See `ARCHITECTURE.md` for the current module inventory.

### Docs (`docs/`)

**Exactly four categories -- no others.**

| Path | Purpose |
|------|---------|
| `docs/README.md` | Navigation index. |
| `docs/vision.md` | Product vision. Update at most yearly. |
| `docs/roadmap.md` | Now/Next/Later feature plan. |
| `docs/decisions/NNNN-*.md` | ADRs -- immutable once accepted. |
| `docs/playbooks/*.md` | Current development guide and marked historical playbooks. |

**NEVER create** ad-hoc files in `docs/`. Architecture goes in `ARCHITECTURE.md` (root). Specs and research go in flat numbered `specs/NNN-name.md`, not standalone research/market files in `docs/`. The research formerly in `docs/RESEARCH.md` was preserved in specs 023–027; do not recreate the retired surface.

### `.claude/` -- Claude Code Configuration

| Path | Purpose |
|------|---------|
| `.claude/settings.json` | Permissions and hooks. |
| `.claude/rules/*.md` | Behavioral rules (structure, workflow). |
| `.claude/agents/*.md` | Agent definitions, including explicitly historical roles. |
| `.claude/agent-memory/<agent>/` | Per-agent runtime memory (gitignored). |

### `.self-improvement/`

| Path | Purpose |
|------|---------|
| `.self-improvement/workers.yaml` | Proposed worker registry; not a running scheduler. |
| `.self-improvement/NEXT.md` | Priority queue (Manager proposes, authorized writer updates). |
| `.self-improvement/MEMORY.md` | Domain knowledge and lessons learned. |
| `.self-improvement/knowledge/` | Knowledge base files. |
| `.self-improvement/memory/trajectory.jsonl` | Append-only run log (gitignored). |
| `.self-improvement/memory/lessons.json` | Distilled patterns (gitignored). |
| `.self-improvement/reports/<worker>/YYYY-MM-DD.md` | Per-worker output (gitignored). |

### What Goes Where

| Content | Location |
|---------|----------|
| New feature spec or research/market analysis | `specs/NNN-name.md` |
| Architecture decision | `docs/decisions/NNNN-name.md` |
| Operational guide | `docs/playbooks/name.md` |
| New source module | `src/holusight/{name}.py` |
| Unit test | `tests/test_{module}.py` |
| Dev session notes | `devlog/YYYY-MM-DD.md` |
| Agent priorities | `.self-improvement/NEXT.md` |
| Worker reports | `.self-improvement/reports/<worker>/YYYY-MM-DD.md` |
| Competitive analysis | `COMPARISON.md` (root, already exists) |

## Commands

Development setup, tests, lint and formatting: `docs/playbooks/development.md`. Common CLI and installation: `README.md`. Discover recipes with `just --list`.

## Parallelism & Skills

**Always use agents to parallelize work when available.** Launch multiple Agent() calls for independent tasks; report unavailable tooling rather than inventing dispatch.

**Use skills for repo work when available:**

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
- Running configured lint and tests
- Writing reports to `.self-improvement/reports/`

### Ask First — Propose, wait for approval
- New dependencies in `pyproject.toml`
- Changes to the `Holusight` public API (see `ARCHITECTURE.md#public-contract`)
- New config environment variables

### Never — Hard stop, escalate immediately
- Writing to or deleting files in a repository being checked
- Allowing input paths that traverse outside a validated root
- Returning full file contents from a check (paths and line evidence only)
- Committing secrets or API keys

## Memory and Context

Each worker with `memory: project` uses `.claude/agent-memory/<worker>/MEMORY.md`. Current worker status and priorities are owned by `.self-improvement/NEXT.md`; historical state is in `.self-improvement/MEMORY.md`. Cycle history is in `.self-improvement/memory/trajectory.jsonl`.

- Architecture: @ARCHITECTURE.md
- Rules: @.claude/rules/
- Decisions: @docs/decisions/
- Historical business ops: @business/README.md

@import .claude/rules/workflow.md

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
