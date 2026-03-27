# CodeSight

AI-powered document search engine — hybrid BM25 + vector + RRF retrieval with pluggable LLM answer synthesis.

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Index a folder of documents
python -m codesight index /path/to/documents

# Search (hybrid BM25 + vector)
python -m codesight search "payment terms" /path/to/documents

# Filter by file type
python -m codesight search "auth" /path/to/code --glob '*.py'

# Ask a question (requires LLM API key — see Configuration)
python -m codesight ask "What are the payment terms?" /path/to/documents

# Machine-readable output
python -m codesight search "query" /path --json

# Check index status
python -m codesight status /path/to/documents

# Launch the web chat UI
pip install -e ".[demo]"
python -m codesight demo
```

## Python API

```python
from codesight import CodeSight

engine = CodeSight("/path/to/documents")
engine.index()                                     # Index all files
results = engine.search("payment terms")           # Hybrid search
answer = engine.ask("What are the payment terms?") # Search + LLM answer
status = engine.status()                           # Index freshness check
```

## Supported Formats

| Format | Extension | Parser |
|--------|-----------|--------|
| PDF | `.pdf` | pymupdf |
| Word | `.docx` | python-docx |
| PowerPoint | `.pptx` | python-pptx |
| Code | `.py`, `.js`, `.ts`, `.go`, `.rs`, etc. | Built-in (10 languages) |
| Text | `.md`, `.txt`, `.csv` | Built-in |

## Architecture

- **Document Parsing**: PDF, DOCX, PPTX text extraction with page/section metadata
- **Chunking**: Language-aware regex splitting (code) + paragraph-aware splitting (documents)
- **Embeddings**: `all-MiniLM-L6-v2` via sentence-transformers (local, no API key)
- **Vector Store**: LanceDB (serverless, file-based)
- **Keyword Search**: SQLite FTS5 sidecar
- **Retrieval**: Hybrid BM25 + vector with RRF merge
- **Answer Synthesis**: Pluggable LLM backend (Claude, Azure OpenAI, OpenAI, Ollama)

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full system tour.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Required for Claude backend (`ask()`) |
| `CODESIGHT_LLM_BACKEND` | `claude` | LLM backend: `claude`, `azure`, `openai`, `ollama` |
| `CODESIGHT_DATA_DIR` | `~/.codesight/data` | Where indexes are stored |
| `CODESIGHT_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Embedding model |
| `CODESIGHT_LLM_MODEL` | `claude-sonnet-4-20250514` | LLM model for answers |
| `CODESIGHT_STALE_SECONDS` | `300` | Index freshness threshold (seconds) |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

See [.env.example](.env.example) for all options.

## Stack

- Python 3.11+
- LanceDB + SQLite FTS5
- sentence-transformers
- Anthropic Claude API / Azure OpenAI / OpenAI / Ollama
- Streamlit (web chat UI)
- pymupdf, python-docx, python-pptx (document parsing)
