# AGENTS.md


# CodeSight

AI-powered document search engine — hybrid BM25 + vector + RRF retrieval with pluggable LLM answer synthesis.

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
| `landing/` | Static public site for holusight.com (Vercel `outputDirectory`). |
| `vercel.json` | Vercel static deploy config; must point at a directory with `index.html`. |
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
| `.holusight/` | Gitignored derived state, never canonical truth. See the authoritative storage and rebuild rules in `.claude/rules/structure.md`. |
| `agentic/` | Fleet repository-evaluation-adapter manifest (`fleet.repo_agent_manifest.v1.2`) and memory policy (`fleet.memory_policy.v1.1`). Committed, Holusight-owned data conforming to schemas owned by the Fleet repository, not vendored here. See spec 016. |

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
| `src/codesight/consistency.py` | Holusight-AXI documentation-code consistency engine (Phase 1). See spec 013. |
| `src/codesight/consistency_store.py` | SQLite storage for `.holusight/consistency.db`. |
| `src/codesight/axi_schema.py` | Versioned `holus` command/output schema - single source of truth for the CLI and the generated skill. See spec 015. |
| `src/codesight/axi_providers.py` | `holus` evidence providers (exact/structural/consistency/semantic) - thin wrappers over `consistency.py` and `search.py`. |
| `src/codesight/cli_axi.py` | `holus` CLI entry point (`[project.scripts] holus`). Also hosts the `improve-*` continuous-improvement loop and repository-placement guard. See spec 018. |
| `src/codesight/axi_skill_gen.py` | Generates `.claude/skills/holus/SKILL.md` from `axi_schema.py`. |
| `src/codesight/toon.py` | Compact TOON output encoder (agent-facing projection boundary only; JSON stays canonical). |
| `src/codesight/fleet_scorecard.py` | Bridges `consistency.py`'s `ConsistencyReport` to Fleet `eval-scorecard.v1.2`-shaped documents; `agentic/manifest.yaml`'s `eval_entrypoint` runner. Local, no-spend. See spec 016. |
| `src/codesight/eval_pilot.py` | Safe continuous-evaluation pilot: frozen case corpus runner, candidate lineage, status-quo comparison, Fleet aggregate export (additive, not the declared `eval_entrypoint`). Every result binds to an immutable Git commit/tree subject. Local, no-spend, advisory only. See specs 017, 018, and 021. |
| `src/codesight/eval_suite.py` | Versioned local-evaluation suite, method/config, and hidden-holdout hash-manifest schemas. Dataset foundation only; no runner, no holdout access path. See spec 022. |
| `src/codesight/improvement_control.py` | Deterministic validator and opt-in derived-record writer for the existing `holus improve-*` loop. It verifies tracked manifests, links, hashes, stages, promotion blockers, and (for pilot results) recomputed Git-subject applicability, without egress or canonical writes. See specs 019 and 021. |
| `src/codesight/avo_leakage.py` | AVO Git-export leakage-boundary scanner for persisted/checkpoint records. See `docs/avo/leakage-boundary.md` and spec 023. |
| `src/codesight/avo_purpose.py` | AVO purpose mapping, canonical trial-field, matched-control, and protected-gate validation. See `docs/avo/purpose-mapping.v1.json` and spec 023. |
| `src/codesight/retrieval_variation.py` | Fixed, local evidence-display baseline/candidate evaluator. Content-addresses benchmark and lineage, separates hard constraints from reward, and only permits independent human review. See spec 020. |
| `src/codesight/types.py` | Shared type definitions. |
| `src/codesight/web/server.py` | FastAPI server and authenticated browser API. |
| `src/codesight/web/static/` | Browser UI assets for the FastAPI pilot server. |

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
| `tests/fixtures/*.jsonl` | Frozen case corpora (e.g. the eval-pilot corpus, spec 017/018). Human-reviewed admission only -- see `docs/playbooks/eval-pilot-case-admission.md`. |
| `tests/fixtures/eval_suites/` | Versioned suite and method/config manifests (spec 022). |
| `tests/fixtures/eval_holdout/` | Hidden-holdout hash-manifests only; payloads are not stored or loaded (spec 022). |
| `tests/fixtures/` (other) | Other test fixtures (synthetic docs, eval query sets). |

### `.claude/` -- Claude Code Configuration

| Path | Purpose |
|------|---------|
| `.claude/settings.json` | Permissions and hooks. |
| `.claude/rules/*.md` | Behavioral rules (structure, workflow). |
| `.claude/agents/*.md` | Agent definitions. |
| `.claude/agent-memory/<agent>/` | Per-agent runtime memory (gitignored). |
| `.claude/skills/holus/SKILL.md` | Generated `/holus` agent skill (see `src/codesight/axi_skill_gen.py`, spec 015). Do not hand-edit - regenerate via `python -m codesight.axi_skill_gen`. |

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

This project has a graphify knowledge graph at graphify-out/.

Rules:
- When `graphify-out/graph.json` exists and the user asks how code is structured, wired, called, or where behavior lives, first run `python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py query "<question>"`. Use `python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py path "<A>" "<B>"` for relationships and `python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py explain "<concept>"` for focused concepts. Answer from query output; read at most one source file only if the query is thin or missing a named symbol.
- Before editing a source file, run the traceable `fleet_graphify.py query` or `fleet_graphify.py path` wrapper to surface dependents/callers/importers. Include connected files in the change set or explicitly call out what else must change.
- Do not re-read multiple source files after a good query unless the user asks for line-level proof.
- Skip graphify for trivial one-line edits already in context, pure shell/commit/run tasks, and external/non-repo research.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw file browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code files in this session, run `python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py update .` to keep the graph current (AST-only, no API cost).
- After modifying docs, notes, images, `AGENTS.md`, `CLAUDE.md`, or `ai-instructions/`, use `python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py . --update` or the installed AGY semantic hook wrapper. Fleet default semantic runner is `agy --model "Gemini 3.5 Flash (Medium)"`.
- In worktrees, use the worktree-local `graphify-out/`; do not share or symlink one graph across active branches.
<!-- graphify:end -->

## Commands

- Run demo: `uv run --extra demo python -m codesight demo`
- CLI: `python -m codesight index /path/to/docs`
- Test: `uv run --extra dev pytest tests/ -x -v`
- Lint: `uv run --extra dev ruff check src/ tests/`
- Install: `pip install -e ".[dev]"`
- Retrieval eval: `just eval` (20q, hybrid only) or `just eval-taxonomy` (85q
  taxonomy across hybrid/bm25/exact/graphify baselines). See
  `specs/014-retrieval-evaluation-harness-expansion.md` and
  `docs/playbooks/run-retrieval-eval.md`. The `graphify`/`fleet_graphify.py`/
  `agy` tooling this file references elsewhere is not present on every
  execution host — code that depends on it (the eval harness's Graphify
  baseline, `consistency.py`'s structural provider) must degrade to an
  explicit "unavailable" result rather than fail, and does.
- Fleet v1.2 protocol pilot smoke suite: `just fleet-smoke` (20 tasks,
  exact + structural providers only, no network, no spend). This is
  `agentic/manifest.yaml`'s declared `eval_entrypoint`. See
  `specs/016-fleet-v1.2-protocol-pilot.md`.

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
- Bug fixes in chunker, embedder, search, parsers that don't touch security boundaries
- Adding tests, updating docs, improving comments
- Reading any file in the repo
- Running lint and tests (`uv run --extra dev ruff check`, `uv run --extra dev pytest`)
- Writing reports to `.self-improvement/reports/`

### Ask First — Propose, wait for approval
- New dependencies in `pyproject.toml`
- Changes to the `CodeSight` public API (`index`, `search`, `ask`, `status`)
- Changes to the data directory path or index schema
- New config environment variables
- Changes to the Claude system prompt in `api.py`

### Never — Hard stop, escalate immediately
- Writing to or deleting files in any indexed folder
- Allowing `folder_path` inputs that traverse outside a validated root
- Returning full file contents from search (chunks + line ranges only)
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

codesight is an AI-powered document search engine. It indexes folders of documents (PDF, DOCX, PPTX, code, text) and provides hybrid BM25 + vector search with Claude answer synthesis. Users interact via a Streamlit web chat UI, CLI, or the Python API.

**Primary concerns:** retrieval quality, document parsing accuracy, answer quality with source citations.

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
- When `graphify-out/graph.json` exists and the user asks how code is structured, wired, called, or where behavior lives, first run `python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py query "<question>"`. Use `python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py path "<A>" "<B>"` for relationships and `python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py explain "<concept>"` for focused concepts. Answer from query output; read at most one source file only if the query is thin or missing a named symbol.
- Before editing a source file, run the traceable `fleet_graphify.py query` or `fleet_graphify.py path` wrapper to surface dependents/callers/importers. Include connected files in the change set or explicitly call out what else must change.
- Do not re-read multiple source files after a good query unless the user asks for line-level proof.
- Skip graphify for trivial one-line edits already in context, pure shell/commit/run tasks, and external/non-repo research.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw file browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code files in this session, run `python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py update .` to keep the graph current (AST-only, no API cost).
- After modifying docs, notes, images, `AGENTS.md`, `CLAUDE.md`, or `ai-instructions/`, use `python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py . --update` or the installed AGY semantic hook wrapper. Fleet default semantic runner is `agy --model "Gemini 3.5 Flash (Medium)"`.
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

- **Read-only invariant** — the engine NEVER writes to indexed folders. It only reads files to build the index. Violating this is the most critical bug possible.
- **Path traversal prevention** — all `folder_path` inputs must be validated against a whitelist or resolved to real paths before use. Never allow `../` escapes.
- **Content hash guard** — always check `sha256(chunk_content)[:16]` before re-embedding. Never embed unchanged content.
- **No full file exposure** — search returns chunks with line ranges, never entire file contents.

@import .claude/rules/workflow.md

<!-- graphify:start -->
## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- When `graphify-out/graph.json` exists and the user asks how code is structured, wired, called, or where behavior lives, first run `python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py query "<question>"`. Use `python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py path "<A>" "<B>"` for relationships and `python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py explain "<concept>"` for focused concepts. Answer from query output; read at most one source file only if the query is thin or missing a named symbol.
- Before editing a source file, run the traceable `fleet_graphify.py query` or `fleet_graphify.py path` wrapper to surface dependents/callers/importers. Include connected files in the change set or explicitly call out what else must change.
- Do not re-read multiple source files after a good query unless the user asks for line-level proof.
- Skip graphify for trivial one-line edits already in context, pure shell/commit/run tasks, and external/non-repo research.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw file browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code files in this session, run `python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py update .` to keep the graph current (AST-only, no API cost).
- After modifying docs, notes, images, `AGENTS.md`, `CLAUDE.md`, or `ai-instructions/`, use `python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py . --update` or the installed AGY semantic hook wrapper. Fleet default semantic runner is `agy --model "Gemini 3.5 Flash (Medium)"`.
- In worktrees, use the worktree-local `graphify-out/`; do not share or symlink one graph across active branches.
<!-- graphify:end -->

## Commands

- Run demo: `uv run --extra demo python -m codesight demo`
- CLI: `python -m codesight index /path/to/docs`
- Test: `uv run --extra dev pytest tests/ -x -v`
- Lint: `uv run --extra dev ruff check src/ tests/`
- Install: `pip install -e ".[dev]"`
- Retrieval eval: `just eval` (20q, hybrid only) or `just eval-taxonomy` (85q
  taxonomy across hybrid/bm25/exact/graphify baselines). See
  `specs/014-retrieval-evaluation-harness-expansion.md` and
  `docs/playbooks/run-retrieval-eval.md`. The `graphify`/`fleet_graphify.py`/
  `agy` tooling this file references elsewhere is not present on every
  execution host — code that depends on it (the eval harness's Graphify
  baseline, `consistency.py`'s structural provider) must degrade to an
  explicit "unavailable" result rather than fail, and does.
- Fleet v1.2 protocol pilot smoke suite: `just fleet-smoke` (20 tasks,
  exact + structural providers only, no network, no spend). This is
  `agentic/manifest.yaml`'s declared `eval_entrypoint`. See
  `specs/016-fleet-v1.2-protocol-pilot.md`.

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
- Bug fixes in chunker, embedder, search, parsers that don't touch security boundaries
- Adding tests, updating docs, improving comments
- Reading any file in the repo
- Running lint and tests (`uv run --extra dev ruff check`, `uv run --extra dev pytest`)
- Writing reports to `.self-improvement/reports/`

### Ask First — Propose, wait for approval
- New dependencies in `pyproject.toml`
- Changes to the `CodeSight` public API (`index`, `search`, `ask`, `status`)
- Changes to the data directory path or index schema
- New config environment variables
- Changes to the Claude system prompt in `api.py`

### Never — Hard stop, escalate immediately
- Writing to or deleting files in any indexed folder
- Allowing `folder_path` inputs that traverse outside a validated root
- Returning full file contents from search (chunks + line ranges only)
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

codesight is an AI-powered document search engine. It indexes folders of documents (PDF, DOCX, PPTX, code, text) and provides hybrid BM25 + vector search with Claude answer synthesis. Users interact via a Streamlit web chat UI, CLI, or the Python API.

**Primary concerns:** retrieval quality, document parsing accuracy, answer quality with source citations.

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
- When `graphify-out/graph.json` exists and the user asks how code is structured, wired, called, or where behavior lives, first run `python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py query "<question>"`. Use `python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py path "<A>" "<B>"` for relationships and `python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py explain "<concept>"` for focused concepts. Answer from query output; read at most one source file only if the query is thin or missing a named symbol.
- Before editing a source file, run the traceable `fleet_graphify.py query` or `fleet_graphify.py path` wrapper to surface dependents/callers/importers. Include connected files in the change set or explicitly call out what else must change.
- Do not re-read multiple source files after a good query unless the user asks for line-level proof.
- Skip graphify for trivial one-line edits already in context, pure shell/commit/run tasks, and external/non-repo research.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw file browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code files in this session, run `python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py update .` to keep the graph current (AST-only, no API cost).
- After modifying docs, notes, images, `AGENTS.md`, `CLAUDE.md`, or `ai-instructions/`, use `python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py . --update` or the installed AGY semantic hook wrapper. Fleet default semantic runner is `agy --model "Gemini 3.5 Flash (Medium)"`.
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

- **Read-only invariant** — the engine NEVER writes to indexed folders. It only reads files to build the index. Violating this is the most critical bug possible.
- **Path traversal prevention** — all `folder_path` inputs must be validated against a whitelist or resolved to real paths before use. Never allow `../` escapes.
- **Content hash guard** — always check `sha256(chunk_content)[:16]` before re-embedding. Never embed unchanged content.
- **No full file exposure** — search returns chunks with line ranges, never entire file contents.

@import .claude/rules/workflow.md

<!-- graphify:start -->

## graphify

When the user types `/graphify`, invoke the graphify skill before doing anything else.

This project has a graphify knowledge graph at graphify-out/.

Rules:
- When `graphify-out/graph.json` exists and the user asks how code is structured, wired, called, or where behavior lives, first run `python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py query "<question>"`. Use `python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py path "<A>" "<B>"` for relationships and `python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py explain "<concept>"` for focused concepts. Answer from query output; read at most one source file only if the query is thin or missing a named symbol.
- Before editing a source file, run the traceable `fleet_graphify.py query` or `fleet_graphify.py path` wrapper to surface dependents/callers/importers. Include connected files in the change set or explicitly call out what else must change.
- Do not re-read multiple source files after a good query unless the user asks for line-level proof.
- Skip graphify for trivial one-line edits already in context, pure shell/commit/run tasks, and external/non-repo research.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw file browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code files in this session, run `python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py update .` to keep the graph current (AST-only, no API cost).
- After modifying docs, notes, images, `AGENTS.md`, `CLAUDE.md`, or `ai-instructions/`, use `python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py . --update` or the installed AGY semantic hook wrapper. Fleet default semantic runner is `agy --model "Gemini 3.5 Flash (Medium)"`.
- In worktrees, use the worktree-local `graphify-out/`; do not share or symlink one graph across active branches.
<!-- graphify:end -->

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
