# Holusight (CodeSight) Conventions

- Python 3.10+, pip install -e ".[dev]"
- Tests via pytest tests/ -x -v
- Lint via ruff check src/ tests/
- Read-only invariant: engine NEVER writes to indexed folders
- Search is always local (BM25 + vector + RRF), LLM only for ask()
- Content hash guard: sha256[:16] before re-embedding
- Pluggable LLM backend: Claude, Azure OpenAI, OpenAI, Ollama
- Storage in ~/.codesight/data/ (outside indexed folders)
