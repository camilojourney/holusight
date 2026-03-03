# codesight

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
