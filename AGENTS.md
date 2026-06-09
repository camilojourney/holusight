# Agent Instructions — codesight

[Project Docs Index]|root: ./docs
|IMPORTANT: Fetch specific files on demand — do not assume content
|architecture: {ARCHITECTURE.md}
|decisions: {docs/decisions/0001-lancedb-over-chromadb.md, docs/decisions/0002-hybrid-rrf-retrieval.md, docs/decisions/0003-read-only-invariant.md}
|playbooks: {docs/playbooks/development.md, docs/playbooks/ship-feature.md, docs/playbooks/investigate-bug.md}
|specs: {specs/README.md, specs/001-core-search-tools.md, specs/002-embedding-model-config.md, specs/003-incremental-refresh.md, specs/004-tree-sitter-chunking.md}

---

## Role

codesight is an AI-powered document search engine. It indexes folders of documents (PDF, DOCX, PPTX, code, text) and provides hybrid BM25 + vector search with Claude answer synthesis. Users interact via a Streamlit web chat UI, CLI, or the Python API.

**Primary concerns:** retrieval quality, document parsing accuracy, answer quality with source citations.

## Agent Authority Matrix

### Autonomous — No confirmation needed
- Bug fixes in chunker, embedder, search, parsers that don't touch security boundaries
- Adding tests, updating docs, improving comments
- Reading any file in the repo
- Running lint and tests (`ruff check`, `pytest`)
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

## Memory

Each worker with `memory: project` writes to `.claude/agent-memory/<worker>/MEMORY.md`.
Cycle history is in `.self-improvement/memory/trajectory.jsonl`.
Current priorities are in `.self-improvement/NEXT.md`.

## Output Paths

- Worker reports → `.self-improvement/reports/<worker>/YYYY-MM-DD.md`
- Trajectory → `.self-improvement/memory/trajectory.jsonl`
- New specs → `specs/NNN-name.md`
- Decisions → `docs/decisions/NNNN-name.md`

## graphify

When the user types `/graphify`, invoke the graphify skill before doing anything else.

This project has a graphify knowledge graph at graphify-out/.

Rules:
- When `graphify-out/graph.json` exists and the user asks how code is structured, wired, called, or where behavior lives, first run `graphify query "<question>"`. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. Answer from query output; read at most one source file only if the query is thin or missing a named symbol.
- Before editing a source file, run `graphify query` or `graphify path` to surface dependents/callers/importers. Include connected files in the change set or explicitly call out what else must change.
- Do not re-read multiple source files after a good query unless the user asks for line-level proof.
- Skip graphify for trivial one-line edits already in context, pure shell/commit/run tasks, and external/non-repo research.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw file browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost).
<!-- graphify:end -->
