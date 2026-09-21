# CodeSight

AI-powered document search engine — hybrid BM25 + vector + RRF retrieval with pluggable LLM answer synthesis.

The live public site is [holusight.com](https://holusight.com/). That is Holusight's public marketing site; document indexing stays local-first, so indexed files are not published there and do not leave your environment by default.

## Install anywhere (two commands)

Distributed the same way `graphify` is: one global CLI, plus a `/holusight` skill that installs once and is available in every AI coding harness on your machine (Claude Code, Codex, Cursor, Gemini, Agents). Requires [`uv`](https://docs.astral.sh/uv/).

```bash
# 1. Install the CLI, globally, from anywhere
uv tool install git+https://github.com/camilojourney/holusight

# 2. Distribute the /holusight skill to every AI harness on this machine
holusight-install-skill
```

That's it. `holus`, `holusight-install-skill`, and every other `[project.scripts]` entry this package ships land on your `PATH` (`uv tool install` puts them in `~/.local/bin` -- make sure that's on `PATH`). Step 2 writes one real copy to `~/.claude/skills/holusight/SKILL.md` and symlinks `~/.codex`, `~/.cursor`, `~/.gemini`, `~/.agents` to it, exactly like graphify's own skill layout.

From then on, in **any** project, either run `holus` directly or invoke `/holusight` from an agent using one of those harnesses:

```bash
cd ~/some/other/project   # a repo holusight has never seen
holus                      # exact + structural + consistency evidence, no setup at all
python -m codesight index . && holus evidence "how does X work?"   # add semantic search
```

`/holusight`'s own `SKILL.md` also self-bootstraps `holus` the first time it's invoked from an agent in a fresh project that doesn't have it yet, the same way graphify's skill bootstraps `graphify`. There is nothing to configure per-project: `holus` always operates on the current working directory, and its index lives outside the indexed folder in `~/.codesight/data/` (see Configuration below), keyed by that folder's path -- never written where it reads.

Useful variations:

```bash
# Upgrade later
uv tool install --upgrade git+https://github.com/camilojourney/holusight

# From a local checkout instead of GitHub (e.g. while developing this repo)
uv tool install --editable .
holusight-install-skill

# Only link specific harnesses
holusight-install-skill --harness claude,codex

# Preview the generated skill without writing anything
holusight-install-skill --print

# Uninstall the CLI
uv tool uninstall codesight
```

Uninstalling the skill itself is a plain `rm`: remove `~/.claude/skills/holusight/` (the real copy) and the four symlinks it created (`~/.codex/skills/holusight`, `~/.cursor/skills/holusight`, `~/.gemini/skills/holusight`, `~/.agents/skills/holusight`).

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

# Production server (FastAPI + browser UI)
pip install -e ".[server]"
export CODESIGHT_API_KEY=$(openssl rand -hex 24)
export CODESIGHT_DOCUMENTS_DIR=/path/to/documents
python -m codesight serve

# Or use Docker (see docs/playbooks/docker-deployment.md)
export CODESIGHT_DOCUMENTS_HOST_DIR=/path/to/documents
docker compose up --build
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

The package root exports `CodeSight`, `ServerConfig`, `Answer`, `IndexStats`,
`RepoStatus`, and `SearchResult` for stable public imports.

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

## Deployment (pilot)

Single-team production shape: FastAPI server, browser UI, API key auth, read-only document mount.

```bash
export CODESIGHT_API_KEY=$(openssl rand -hex 24)
export CODESIGHT_DOCUMENTS_HOST_DIR=/path/to/documents
docker compose up --build
```

See [docs/playbooks/docker-deployment.md](docs/playbooks/docker-deployment.md) and the [capability matrix](specs/010-capability-inventory.md) for what is shipped vs planned.

**holusight.com** is a static marketing site only — customer documents are indexed on the customer's deployment.

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
- Streamlit (local demo UI)
- FastAPI + uvicorn (single-team production server, optional `[server]` extra)
- pymupdf, python-docx, python-pptx (document parsing)
