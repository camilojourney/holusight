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

## Context

- Architecture: @ARCHITECTURE.md
- Rules: @.claude/rules/
- Decisions: @docs/decisions/
- Env template: @.env.example
- Business ops: @business/README.md

@import .claude/rules/workflow.md
