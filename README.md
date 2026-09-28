# Holusight

AI-powered document search engine — hybrid BM25 + vector + RRF retrieval with pluggable LLM answer synthesis.

The live public site is [holusight.com](https://holusight.com/). That is Holusight's public marketing site; document indexing stays local-first, so indexed files are not published there and do not leave your environment by default.

## Install anywhere

Install the CLI globally, then bootstrap the skill in each project that uses it. The skill bootstrap is project-local and missing-only: it writes only `.agents/skills/holusight/` and preserves an existing project copy. It does not require or create a machine-wide skill directory. Requires [`uv`](https://docs.astral.sh/uv/).

```bash
uv tool install git+https://github.com/camilojourney/holusight
cd ~/some/project
holusight-install-skill --project-local
```

`holus`, `holusight-install-skill`, and the other `[project.scripts]` entries land on your `PATH` (`uv tool install` puts them in `~/.local/bin` -- make sure that's on `PATH`). From then on, invoke `/holusight` inside that project.

To install that project-local skill explicitly from a checkout or an installed CLI:

```bash
holusight-install-skill --project-local
```

The project-local destination is validated against the current project root and symlink escapes are rejected.

```bash
cd ~/some/other/project   # a repo holusight has never seen
holus                      # exact + structural + consistency evidence, no setup at all
python -m holusight index . && holus evidence "how does X work?"   # add semantic search
```

`/holusight`'s own `SKILL.md` bootstraps `holus` and then the project-local skill on first invocation. If the freshly installed command is not yet on `PATH`, it invokes the module through the interpreter recorded by the bootstrap, so no new shell or global skill directory is needed. `holus` always operates on the current working directory, and its index lives outside the indexed folder in `~/.holusight/data/` (see Configuration below), keyed by that folder's path -- never written where it reads.

### Bounded public URL research

```bash
holus research-urls "What does the policy require?" \
  --url https://example.org/policy --url https://example.net/guide \
  --allow-egress --format json
```

Supply one question and 2-3 distinct public HTTPS URLs. Without `--allow-egress`, no DNS lookup or fetch occurs. Redirects and non-public addresses are refused. The command writes a dated Markdown report and JSON receipt under the current project's gitignored `.holusight/public-research/`, never to the private search index. Its reported claims are only verbatim, citation-verified excerpts; it does not synthesize an answer or validate source truth. An empty match is explicitly unanswered, and failed verification exits nonzero. Keep sensitive questions and URLs out of public requests.

Useful variations:

```bash
# Upgrade later
uv tool install --upgrade git+https://github.com/camilojourney/holusight

# From a local checkout instead of GitHub (e.g. while developing this repo)
uv tool install --editable .
holusight-install-skill --project-local

# Preview the generated skill without writing anything
holusight-install-skill --print

# Uninstall the CLI
uv tool uninstall holusight
```

The project-local skill can be removed with `rm -rf .agents/skills/holusight` when the project no longer needs it.

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Install with AST chunking support (Python/JS/TS — higher MRR for code)
pip install -e ".[dev,ast]"

# Index a folder of documents
python -m holusight index /path/to/documents

# Search (hybrid BM25 + vector)
python -m holusight search "payment terms" /path/to/documents

# Filter by file type
python -m holusight search "auth" /path/to/code --glob '*.py'

# Ask a question (requires LLM API key — see Configuration)
python -m holusight ask "What are the payment terms?" /path/to/documents

# Machine-readable output
python -m holusight search "query" /path --json

# Check index status
python -m holusight status /path/to/documents

# Launch the web chat UI
pip install -e ".[demo]"
python -m holusight demo

# Production server (FastAPI + browser UI)
pip install -e ".[server]"
export HOLUSIGHT_API_KEY=$(openssl rand -hex 24)
export HOLUSIGHT_DOCUMENTS_DIR=/path/to/documents
python -m holusight serve

# Or use Docker (see docs/playbooks/docker-deployment.md)
export HOLUSIGHT_DOCUMENTS_HOST_DIR=/path/to/documents
docker compose up --build
```

## Python API

```python
from holusight import Holusight

engine = Holusight("/path/to/documents")
engine.index()                                     # Index all files
results = engine.search("payment terms")           # Hybrid search
answer = engine.ask("What are the payment terms?") # Search + LLM answer
status = engine.status()                           # Index freshness check
```

The package root exports `Holusight`, `ServerConfig`, `Answer`, `IndexStats`,
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
- **Embeddings**: `voyage-code-3` (API, every file) or `Qwen/Qwen3-Embedding-8B` (local, every file, the default — strongest open-weight MTEB retrieval score, at real per-embed cost) — auto-detected via `VOYAGE_API_KEY`. With a key, code files additionally get a second `voyage-code-3` embedding into their own table. `HOLUSIGHT_EMBEDDING_MODEL` overrides the local model (`-0.6B`/`-4B` trade quality for speed on lighter hardware).
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
export HOLUSIGHT_API_KEY=$(openssl rand -hex 24)
export HOLUSIGHT_DOCUMENTS_HOST_DIR=/path/to/documents
docker compose up --build
```

See [docs/playbooks/docker-deployment.md](docs/playbooks/docker-deployment.md) and the [capability matrix](specs/010-capability-inventory.md) for what is shipped vs planned.

**holusight.com** is a static marketing site only — customer documents are indexed on the customer's deployment.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Required for Claude backend (`ask()`) |
| `VOYAGE_API_KEY` | — | Enables voyage-code-3 embeddings + voyage rerank-2 (recommended for code) |
| `HOLUSIGHT_LLM_BACKEND` | `claude` | LLM backend: `claude`, `azure`, `openai`, `ollama` |
| `HOLUSIGHT_DATA_DIR` | `~/.holusight/data` | Where indexes are stored |
| `HOLUSIGHT_EMBEDDING_MODEL` | `Qwen/Qwen3-Embedding-8B` | Local embedding model for every file (`-0.6B`/`-4B` for less quality but more speed); overridden entirely by `voyage-code-3` when `VOYAGE_API_KEY` is set |
| `HOLUSIGHT_LLM_MODEL` | `claude-sonnet-4-20250514` | LLM model for answers |
| `HOLUSIGHT_RERANKER` | `true` (if VOYAGE_API_KEY set) | Enable reranker |
| `HOLUSIGHT_RERANKER_BACKEND` | `voyage` (if key set) | Reranker backend: `voyage` or `local` |
| `HOLUSIGHT_STALE_SECONDS` | `300` | Index freshness threshold (seconds) |
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
