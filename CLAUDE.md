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

# CodeSight

AI-powered document search engine — hybrid BM25 + vector + RRF retrieval with pluggable LLM answer synthesis.

## Commands

- Run demo: `streamlit run demo/app.py`
- CLI: `python -m codesight index /path/to/docs`
- Test: `pytest tests/ -x -v`
- Lint: `ruff check src/ tests/`
- Install: `pip install -e ".[dev]"`

## IMPORTANT Rules

- **Read-only invariant** — the engine NEVER writes to indexed folders. It only reads files to build the index. Violating this is the most critical bug possible.
- **Path traversal prevention** — all `folder_path` inputs must be validated against a whitelist or resolved to real paths before use. Never allow `../` escapes.
- **Content hash guard** — always check `sha256(chunk_content)[:16]` before re-embedding. Never embed unchanged content.
- **No full file exposure** — search returns chunks with line ranges, never entire file contents.

## Type
B — ML/API (hybrid BM25 + vector search engine with pluggable LLM synthesis)

## Context

- Architecture: @ARCHITECTURE.md
- Rules: @.claude/rules/
- Decisions: @docs/decisions/
- Env template: @.env.example
- Business ops: @business/README.md

@import .claude/rules/workflow.md

## Structure

> WHERE things go in this repo. Read before creating or moving any file.
> Type D -- Spec-Only repo with demo code (CLI code search tool).

### Root Level

| File/Dir | Purpose |
|----------|---------|
| `CLAUDE.md` | Claude Code quick reference (<=80 lines). |
| `AGENTS.md` | Universal AI entry point. Agent authority matrix. |
| `ARCHITECTURE.md` | Full system architecture (200-500 lines). |
| `README.md` | Human-facing project overview. |
| `COMPARISON.md` | Competitive comparison analysis. |
| `justfile` | Unified task runner (`just --list` to discover). |
| `pyproject.toml` | Python package config and dependencies (uv). |
| `.env.example` | Environment variable template. Never `.env` itself. |
| `src/` | Core Python library (`src/codesight/`). |
| `demo/` | Demo application (app.py + requirements.txt). |
| `specs/` | Numbered feature specifications. |
| `docs/` | Structured documentation (four categories only). |
| `tests/` | pytest test suite. |
| `devlog/` | Session devlog entries (YYYY-MM-DD.md). |
| `tasks/` | Temporary session task files (delete when done). |
| `.claude/` | Claude Code configuration, rules, agents. |
| `.self-improvement/` | Autonomous improvement system. |

**Never create files at root** unless they are one of the above.

### Source Code (`src/codesight/`)

| Module | Purpose |
|--------|---------|
| `src/codesight/__main__.py` | CLI entry point. |
| `src/codesight/api.py` | API layer. |
| `src/codesight/chunker.py` | Code chunking logic. |
| `src/codesight/config.py` | Configuration loading. |
| `src/codesight/embeddings.py` | Embedding model interface. |
| `src/codesight/git_utils.py` | Git repository utilities. |
| `src/codesight/indexer.py` | Code indexing engine. |
| `src/codesight/llm.py` | LLM backend interface. |
| `src/codesight/parsers.py` | Language parsers (tree-sitter). |
| `src/codesight/search.py` | Search and retrieval. |
| `src/codesight/store.py` | Vector store (LanceDB). |
| `src/codesight/types.py` | Shared type definitions. |

### Demo (`demo/`)

| File | Purpose |
|------|---------|
| `demo/app.py` | Demo application showcasing codesight capabilities. |
| `demo/requirements.txt` | Demo-specific dependencies (separate from main pyproject.toml). |

Demo is self-contained. It does not import from `src/codesight/` at runtime.

### Docs (`docs/`)

**Exactly four categories -- no others.**

| Path | Purpose |
|------|---------|
| `docs/README.md` | Navigation index. |
| `docs/vision.md` | Product vision. Update at most yearly. |
| `docs/roadmap.md` | Now/Next/Later feature plan. |
| `docs/decisions/NNNN-*.md` | ADRs -- immutable once accepted. |
| `docs/playbooks/*.md` | Step-by-step operational guides. |

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
| New source module | `src/codesight/{name}.py` |
| Unit test | `tests/test_{module}.py` |
| Demo code | `demo/` |
| Dev session notes | `devlog/YYYY-MM-DD.md` |
| Agent priorities | `.self-improvement/NEXT.md` |
| Worker reports | `.self-improvement/reports/<worker>/YYYY-MM-DD.md` |
| Research/market analysis | `specs/NNN-name.md` (never in `docs/`) |
| Competitive analysis | `COMPARISON.md` (root, already exists) |
