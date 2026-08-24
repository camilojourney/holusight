# Repository Structure -- codesight

> WHERE things go in this repo. Read before creating or moving any file.
> Type D -- Spec-Only repo with demo code (CLI code search tool).

## Root Level

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
| `.holusight/` | Gitignored Holusight-AXI cache and opt-in improvement records/results. Derived state only, never canonical truth, and safe to delete and rebuild through the governing `holus` workflow. See specs 013, 019, and 020. |
| `agentic/` | Fleet repository-evaluation-adapter manifest (`fleet.repo_agent_manifest.v1.2`) and memory policy (`fleet.memory_policy.v1.1`). Committed, Holusight-owned data conforming to schemas owned by the Fleet repository, not vendored here. See spec 016. |

**Never create files at root** unless they are one of the above.

## Source Code (`src/codesight/`)

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
| `src/codesight/axi_providers.py` | `holus` evidence providers (exact/structural/consistency/semantic). |
| `src/codesight/cli_axi.py` | `holus` CLI entry point (`[project.scripts] holus`). Also hosts the `improve-*` continuous-improvement loop and repository-placement guard. See spec 018. |
| `src/codesight/axi_skill_gen.py` | Generates `.claude/skills/holus/SKILL.md` from `axi_schema.py`. |
| `src/codesight/toon.py` | Compact TOON output encoder (agent-facing projection boundary only). |
| `src/codesight/fleet_scorecard.py` | Bridges `consistency.py`'s `ConsistencyReport` to Fleet `eval-scorecard.v1.2`-shaped documents. Local, no-spend. See spec 016. |
| `src/codesight/eval_pilot.py` | Safe continuous-evaluation pilot: frozen case corpus runner, candidate lineage, status-quo comparison, Fleet aggregate export (additive, not the declared `eval_entrypoint`). Local, no-spend, advisory only. See specs 017 and 018. |
| `src/codesight/improvement_control.py` | Deterministic validator and opt-in derived-record writer for existing `holus improve-*` review commands. It validates tracked manifests, typed links, hashes, monotonic stages, and promotion blockers. See spec 019. |
| `src/codesight/retrieval_variation.py` | Fixed local evidence-display variation evaluator using the existing improvement-control storage and promotion boundary. See spec 020. |
| `src/codesight/control_storage.py` | Shared no-follow, atomic control-plane derived-state writer. It permits only gitignored result/history paths inside the repository and rejects tracked or symlinked destinations. |
| `src/codesight/types.py` | Shared type definitions. |

## Demo (`demo/`)

| File | Purpose |
|------|---------|
| `demo/app.py` | Demo application showcasing codesight capabilities. |
| `demo/requirements.txt` | Demo-specific dependencies (separate from main pyproject.toml). |

Demo is self-contained. It does not import from `src/codesight/` at runtime.

## Docs (`docs/`)

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

## Specs (`specs/`)

Numbered feature specs: `specs/NNN-name.md`. Flat structure only. No subdirectories.

## Tests (`tests/`)

| Path | Purpose |
|------|---------|
| `tests/test_*.py` | Test files matching source modules. |
| `tests/fixtures/*.jsonl` | Frozen case corpora (e.g. the eval-pilot corpus, spec 017/018). Human-reviewed admission only -- see `docs/playbooks/eval-pilot-case-admission.md`. |
| `tests/fixtures/` (other) | Other test fixtures (synthetic docs, eval query sets). |

## `.claude/` -- Claude Code Configuration

| Path | Purpose |
|------|---------|
| `.claude/settings.json` | Permissions and hooks. |
| `.claude/rules/*.md` | Behavioral rules (structure, workflow). |
| `.claude/agents/*.md` | Agent definitions. |
| `.claude/agent-memory/<agent>/` | Per-agent runtime memory (gitignored). |
| `.claude/skills/holus/SKILL.md` | Generated `/holus` agent skill. Do not hand-edit - regenerate via `python -m codesight.axi_skill_gen`. |

## `.self-improvement/`

| Path | Purpose |
|------|---------|
| `.self-improvement/workers.yaml` | Worker registry. |
| `.self-improvement/NEXT.md` | Priority queue (Manager writes, all workers read). |
| `.self-improvement/MEMORY.md` | Domain knowledge and lessons learned. |
| `.self-improvement/knowledge/` | Knowledge base files. |
| `.self-improvement/memory/trajectory.jsonl` | Append-only run log (gitignored). |
| `.self-improvement/memory/lessons.json` | Distilled patterns (gitignored). |
| `.self-improvement/reports/<worker>/YYYY-MM-DD.md` | Per-worker output (gitignored). |

## What Goes Where

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
