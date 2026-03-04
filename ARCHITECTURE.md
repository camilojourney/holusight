# Architecture — codesight

> Guided tour of the codebase. WHY things are built, not just WHAT.
> **Last Updated:** 2026-02-28

---

## System Overview

```
User (non-technical)
      |
      |  Web browser / Teams / CLI
      v
+-----------------------------------------+
|           Interface Layer               |
|  Streamlit Chat UI  |  CLI  |  Teams Bot |
+----------+----------+------+-----------+
           |
           v
+-----------------------------------------+
|        CodeSight Python API             |
|        (src/codesight/api.py)           |
|                                         |
|  index(folder)  search(query)           |
|  ask(question)  status()                |
+----------+------------------------------+
           |
     +-----+--------------------------+
     |                                |
     v                                v
+----------+              +--------------+
| Indexer   |              | Search       |
|           |              |              |
| Walk files|              | BM25 (FTS5)  |
| Parse docs|              | Vector search|
| Chunk     |              | RRF merge    |
| Embed     |              |              |
| Store     |              +--------------+
+----------+
           |                       |
     +-----+------+          +----+----+
     v            v           v         v
  LanceDB    SQLite FTS5   LLM Backend (pluggable)
 (vectors)   (keywords)    ├── Claude API
                            ├── Azure OpenAI
                            ├── OpenAI
                            └── Ollama (local)

Storage: ~/.codesight/data/<folder_hash>/
         |- lance/       (vectors)
         |- metadata.db  (SQLite with FTS5)
         |
M365 cache: ~/.codesight/m365-cache/<tenant_hash>/
           |- drive/     (OneDrive/SharePoint files)
           |- mail/      (Outlook messages/attachments)
           |- notes/     (OneNote markdown)
```

### Data Flow: What's Local vs External

```
100% LOCAL (no internet, no API, no cost):
├── Document parsing (PDF, DOCX, PPTX)
├── Chunking (code + document)
├── Embedding (sentence-transformers model on CPU/GPU)
├── Indexing (LanceDB + SQLite files on disk)
├── Search (BM25 + vector + RRF merge)
└── Results (ranked chunks with file + page)

EXTERNAL (only when ask() is called — client chooses provider):
└── LLM answer synthesis → Claude API / Azure OpenAI / OpenAI / Ollama (local)
```

---

## Source Layout (`src/codesight/`)

| File            | Purpose                                                                  |
| --------------- | ------------------------------------------------------------------------ |
| `api.py`        | Public Python API. `CodeSight` class — single entry point for all UIs.   |
| `indexer.py`    | Orchestrates the index pipeline: walk -> parse -> chunk -> embed -> store.|
| `search.py`     | Hybrid retrieval: BM25 + vector -> RRF merge -> return chunks.           |
| `chunker.py`    | Code chunking (scope boundaries) + document chunking (paragraphs/pages). |
| `parsers.py`    | Document text extraction: PDF (pymupdf), DOCX (python-docx), PPTX.      |
| `llm.py`        | Pluggable LLM backend: Claude, Azure OpenAI, OpenAI, Ollama adapters.   |
| `embeddings.py` | Embedding wrapper: local (sentence-transformers) or API (OpenAI).       |
| `store.py`      | LanceDB + SQLite FTS5 dual-write. Content hash deduplication.            |
| `config.py`     | Pydantic settings from env vars. File extension sets, chunk defaults.    |
| `git_utils.py`  | .gitignore-aware file walking via `pathspec`.                            |
| `types.py`      | Shared Pydantic models (SearchResult, Answer, IndexStats, RepoStatus).   |
| `__main__.py`   | CLI entry point: `python -m codesight <command>`.                        |
| `connectors/`   | External sync integrations (M365 Graph connector + MSAL auth).            |
| `bot/`          | Teams bot handler, Adaptive Card builders, and aiohttp app entrypoint.    |

**Do not add modules at the top level** — new capabilities go inside existing modules or as new submodules.

---

## Public API

```python
from codesight import CodeSight

engine = CodeSight("/path/to/documents")
engine.index()                                    # Index all files
results = engine.search("payment terms")          # Hybrid search (always local)
answer = engine.ask("What are the payment terms?") # Search + LLM answer
status = engine.status()                          # Index freshness check
```

The `CodeSight` class is the single entry point. Streamlit, Teams bot, CLI, and any future
interface all call the same methods.

### The `ask()` Pipeline

```
question -> search(question, top_k=5) -> top chunks    (LOCAL)
         -> format chunks as context
         -> LLM call (pluggable backend)                (EXTERNAL or LOCAL)
         -> Answer(text, sources, model)
```

---

## Document Processing Pipeline

```
File on disk
    |
    |-- Code files (.py, .js, .ts, etc.)
    |   +-- read_text() -> chunk_file() (scope boundaries)
    |
    |-- Text files (.md, .txt, .csv)
    |   +-- read_text() -> chunk_file() (sliding windows)
    |
    +-- Documents (.pdf, .docx, .pptx)
        +-- parsers.extract_text() -> chunk_document() (paragraph boundaries)
            |
            |-- PDF: pymupdf -> text per page
            |-- DOCX: python-docx -> text per heading section
            +-- PPTX: python-pptx -> text per slide
```

---

## Retrieval Pipeline (The Core)

```
query string
    |
    +-----------------------------------------+
    |                                         |
    v                                         v
SQLite FTS5                               LanceDB
BM25 keyword matching                vector similarity
(exact names, dates,                (semantic meaning,
 contract numbers)                   concept proximity)
    |                                         |
    +-----------------+-----------------------+
                      v
             Reciprocal Rank Fusion
             score = sum 1/(k + rank_i)  where k=60
                      |
                      v
               top K chunks
            (with file path + page/line range)
```

**Why hybrid matters:** Pure vector search misses exact keyword matches (vendor names, contract numbers, dates). Pure BM25 misses semantic synonyms. RRF merges both with zero extra infrastructure. Most cloud competitors use vector-only search — our hybrid approach beats them for scoped document collections.

---

## Embedding Layer

```
Local embedding (default — no API, no cost, no data leaves):
   Document text → sentence-transformers model → vector (numbers)
   Model downloaded once (~270MB), runs on CPU/GPU
   Default: nomic-embed-text-v1.5 (768 dims, 8K context) [target]
   Current: all-MiniLM-L6-v2 (384 dims)

Optional API embedding (better quality, data goes to API):
   Document text → OpenAI/Voyage API → vector
   Configurable via CODESIGHT_EMBEDDING_BACKEND
```

---

## LLM Backend (Pluggable)

The LLM is only used by `ask()` — search runs without it.

```
CODESIGHT_LLM_BACKEND=claude    → Anthropic API (best quality)
CODESIGHT_LLM_BACKEND=azure     → Azure OpenAI (data in client's tenant)
CODESIGHT_LLM_BACKEND=openai    → OpenAI API
CODESIGHT_LLM_BACKEND=ollama    → Local model, zero network (privacy-first)
```

Client chooses based on their security requirements. We are never in the middle.

---

## Storage Layout

All indexes live in `~/.codesight/data/` (outside the indexed folder — never write inside it).

```
~/.codesight/data/
+-- <sha256(folder_path)[:12]>/
    |-- lance/            <- LanceDB vector tables
    |   +-- chunks.lance  <- chunk_id, embedding vector
    +-- metadata.db       <- SQLite with FTS5 virtual table
        |-- chunks         <- chunk_id, content, file_path, lines
        |-- chunks_fts     <- FTS5 index (auto-synced via triggers)
        +-- repo_meta      <- last_indexed_at, last_commit, etc.
```

**Content hashing:** Each chunk is hashed `sha256(content)[:16]`. On re-index, unchanged chunks are skipped entirely — no re-embedding, no write.

---

## Chunking Strategy

### Code Files
Language-aware regex splits on scope boundaries (class/function/block) for 10 languages: Python, JS, TS, Go, Rust, Java, Ruby, PHP, C, C++. Unknown languages fall back to sliding window with overlap.

### Documents
Paragraph-aware splitting respecting page boundaries. Each chunk gets metadata:
- `start_line` / `end_line` = page numbers
- `scope` = heading or "page N"
- `language` = "pdf", "docx", "pptx"

### Context Headers
Every chunk gets a context header prepended before embedding:
```
# File: contracts/vendor-agreement.pdf
# Scope: section Payment Terms
# Lines: 3-3
```

---

## Deployment Tiers

| Tier | Users | Deployment | LLM Backend |
|------|-------|-----------|-------------|
| Demo/pilot | 1-5 | Laptop | Ollama (local) |
| Small team | 5-10 | Single VM | Ollama or API |
| Department | 20-50 | Docker on cloud | Claude/Azure OpenAI API |
| Company | 100+ | Docker + FastAPI + auth | Azure OpenAI |
| Air-gapped | Any | On-prem server | Ollama / vLLM |

---

## What NOT to Change Without Discussion

1. **RRF k=60 constant** — changing this shifts recall/precision tradeoff. Benchmark before changing.
2. **Data directory location** (`~/.codesight/data/`) — changing this invalidates all existing indexes.
3. **Content hash algorithm** — changing from `sha256[:16]` invalidates all deduplication state.
4. **FTS5 trigger schema** — the SQLite triggers that sync FTS5 from the chunks table. Incorrect triggers cause silent search failures.
5. **LLM system prompt** — the `SYSTEM_PROMPT` in `llm.py` controls answer quality across all backends. Test changes with real documents.
