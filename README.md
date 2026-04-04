# CodeSight

AI-powered document search engine — hybrid BM25 + vector + RRF retrieval with pluggable LLM answer synthesis.

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Install with AST chunking support (Python/JS/TS — higher MRR for code)
pip install -e ".[dev,ast]"

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
| Code | `.py`, `.js`, `.ts`, `.go`, `.rs`, etc. | AST-based (tree-sitter) + regex fallback |
| Text | `.md`, `.txt`, `.csv` | Built-in |

## Architecture

- **Document Parsing**: PDF, DOCX, PPTX text extraction with page/section metadata
- **Chunking**: AST-based (tree-sitter) for Python/JS/TS — function/class boundaries preserve semantic units. Regex fallback for other languages. Paragraph-aware splitting for documents.
- **Embeddings**: `voyage-code-3` (API, code files) / `all-MiniLM-L6-v2` (local, docs). Auto-detected via `VOYAGE_API_KEY`.
- **Vector Store**: LanceDB (serverless, file-based)
- **Keyword Search**: SQLite FTS5 sidecar
- **Retrieval**: Hybrid BM25 + vector + code-vector with RRF merge → metadata filename boost → optional reranker
- **Reranker**: `voyage rerank-2` (code-aware, auto-enabled with `VOYAGE_API_KEY`). Local `ms-marco` cross-encoder opt-in only.
- **Answer Synthesis**: Pluggable LLM backend (Claude, Azure OpenAI, OpenAI, Ollama)

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full system tour.

## Performance

Measured on the holusight codebase (96 files, 20 representative queries):

| Configuration | Hit Rate | MRR@10 |
|--------------|----------|--------|
| Baseline (fixed windows, no reranker) | 52.5% | 0.352 |
| + VPRF + voyage reranker | 100% | 0.599 |
| + AST chunking (tree-sitter) | 100% | **0.823** |
| + voyage-code-3 + voyage rerank-2 | 100% | 0.793 |

**AST chunking is the largest single lever** (+0.224 MRR). The local `ms-marco` cross-encoder hurts code retrieval — only enable it explicitly.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Required for Claude backend (`ask()`) |
| `VOYAGE_API_KEY` | — | Enables voyage-code-3 embeddings + voyage rerank-2 (recommended for code) |
| `CODESIGHT_LLM_BACKEND` | `claude` | LLM backend: `claude`, `azure`, `openai`, `ollama` |
| `CODESIGHT_DATA_DIR` | `~/.codesight/data` | Where indexes are stored |
| `CODESIGHT_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Embedding model (overridden by voyage-code-3 for code when key set) |
| `CODESIGHT_LLM_MODEL` | `claude-sonnet-4-20250514` | LLM model for answers |
| `CODESIGHT_RERANKER` | `true` (if VOYAGE_API_KEY set) | Enable reranker |
| `CODESIGHT_RERANKER_BACKEND` | `voyage` (if key set) | Reranker backend: `voyage` or `local` |
| `CODESIGHT_STALE_SECONDS` | `300` | Index freshness threshold (seconds) |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

See [.env.example](.env.example) for all options.

## Stack

- Python 3.11+
- LanceDB + SQLite FTS5
- sentence-transformers + voyage-code-3 (optional)
- tree-sitter (optional — AST chunking for Python/JS/TS)
- Anthropic Claude API / Azure OpenAI / OpenAI / Ollama
- Streamlit (web chat UI)
- pymupdf, python-docx, python-pptx (document parsing)
