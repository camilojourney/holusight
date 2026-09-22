# Playbook: Development Setup

## Prerequisites

- Python 3.11+
- `uv` (recommended) or `pip`

## Setup

```bash
cd holusight
pip install -e ".[dev]"
# or with uv:
uv sync --extra dev
```

## Run Locally

```bash
# Index a folder of documents
python -m holusight index /path/to/documents

# Search
python -m holusight search "payment terms" /path/to/documents

# Ask a question (requires ANTHROPIC_API_KEY)
python -m holusight ask "What are the payment terms?" /path/to/documents

# Check index status
python -m holusight status /path/to/documents

# Launch the Streamlit demo UI
uv run --extra demo python -m holusight demo
# or directly:
uv run --extra demo streamlit run demo/app.py

# Production-shaped FastAPI server (requires API key unless unauthenticated dev)
export HOLUSIGHT_API_KEY=dev-key
export HOLUSIGHT_DOCUMENTS_DIR=./tests/fixtures/pilot_docs
uv run --extra server python -m holusight serve ./tests/fixtures/pilot_docs
```

## Python API

```python
from holusight import Holusight

engine = Holusight("/path/to/documents")
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
- `HOLUSIGHT_DATA_DIR` — index storage location (default: `~/.holusight/data/`)
- `HOLUSIGHT_EMBEDDING_MODEL` — embedding model (default: `all-MiniLM-L6-v2`)

## Directory Layout

See `ARCHITECTURE.md` for the full source layout.
See `.claude/rules/structure.md` for where new files should go.
