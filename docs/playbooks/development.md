# Playbook: Development Setup

## Prerequisites

- Python 3.11+
- `uv` (recommended) or `pip`

## Setup

```bash
cd codesight
pip install -e ".[dev]"
# or with uv:
uv sync --extra dev
```

## Run Locally

```bash
# Index a folder of documents
python -m codesight index /path/to/documents

# Search
python -m codesight search "payment terms" /path/to/documents

# Ask a question (requires ANTHROPIC_API_KEY)
python -m codesight ask "What are the payment terms?" /path/to/documents

# Check index status
python -m codesight status /path/to/documents

# Launch the web chat UI
uv run --extra demo python -m codesight demo
# or directly:
uv run --extra demo streamlit run demo/app.py
```

## Python API

```python
from codesight import CodeSight

engine = CodeSight("/path/to/documents")
engine.index()
results = engine.search("payment terms")
answer = engine.ask("What are the payment terms?")
```

## Tests

```bash
uv run --extra dev pytest tests/ -x -v
```

## Lint

```bash
uv run --extra dev ruff check src/ tests/
uv run --extra dev ruff format src/ tests/ --check  # dry run
```

## Environment Variables

See `.env.example` for all configuration options.

Key variables:
- `ANTHROPIC_API_KEY` — required for `ask()` / Claude answer synthesis
- `CODESIGHT_DATA_DIR` — index storage location (default: `~/.codesight/data/`)
- `CODESIGHT_EMBEDDING_MODEL` — embedding model (default: `all-MiniLM-L6-v2`)

## Directory Layout

See `ARCHITECTURE.md` for the full source layout.
See `.claude/rules/structure.md` for where new files should go.
