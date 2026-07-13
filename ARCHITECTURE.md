# Architecture -- CodeSight

> Guided tour of the codebase. WHY things are built, not just WHAT.
> **Last Updated:** 2026-04-04

---

## System Overview

```
User (non-technical)
      |
      |  Web browser / Slack / CLI
      v
+-----------------------------------------+
|           Interface Layer               |
|  Streamlit Chat UI  |  CLI  |  (Slack)  |
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
| Embed     |              | Reranker     |
| Store     |              |              |
+----------+              +--------------+
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
```

### Data Flow: What's Local vs External

```
100% LOCAL (no internet, no API, no cost):
├── Document parsing (PDF, DOCX, PPTX)
├── Chunking (code AST + document paragraphs)
├── Embedding (sentence-transformers on CPU/GPU)
├── Indexing (LanceDB + SQLite files on disk)
├── Search (BM25 + vector + RRF merge)
└── Results (ranked chunks with file + page)

OPTIONAL API (higher quality, data goes to Voyage AI):
├── voyage-code-3 embeddings for code files (auto-detected via VOYAGE_API_KEY)
└── voyage rerank-2 reranker (auto-detected via VOYAGE_API_KEY)

EXTERNAL (only when ask() is called — client chooses provider):
└── LLM answer synthesis → Claude API / Azure OpenAI / OpenAI / Ollama (local)
```

---

## Source Layout (`src/codesight/`)

| File            | Purpose                                                                  |
| --------------- | ------------------------------------------------------------------------ |
| `api.py`        | Public Python API. `CodeSight` class — single entry point for all UIs.   |
| `indexer.py`    | Orchestrates the index pipeline: walk -> parse -> chunk -> embed -> store.|
| `search.py`     | Hybrid retrieval: BM25 + vector -> RRF merge -> [reranker] -> results.   |
| `chunker.py`    | AST-based code chunking (tree-sitter) + document chunking (paragraphs).  |
| `parsers.py`    | Document text extraction: PDF (pymupdf), DOCX (python-docx), PPTX.      |
| `llm.py`        | Pluggable LLM backend: Claude, Azure OpenAI, OpenAI, Ollama adapters.   |
| `embeddings.py` | Embedding wrapper: local (sentence-transformers) or API (Voyage/OpenAI). |
| `store.py`      | LanceDB + SQLite FTS5 dual-write. Content hash deduplication.            |
| `config.py`     | Pydantic settings from env vars. Auto-detects Voyage API capabilities.   |
| `git_utils.py`  | .gitignore-aware file walking via `pathspec`.                            |
| `types.py`      | Shared Pydantic models (SearchResult, Answer, IndexStats, RepoStatus).   |
| `__main__.py`   | CLI entry point: `python -m codesight <command>`.                        |

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

The package root exposes the stable public import surface: `CodeSight`, `ServerConfig`, `Answer`, `IndexStats`, `RepoStatus`, and `SearchResult`. The `CodeSight` class is the single entry point. Streamlit, Slack, CLI, and any future interface all call the same methods.

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
    |   +-- read_text() -> chunk_file() -> chunk_file_ast() [tree-sitter]
    |                                   -> regex fallback   [if no tree-sitter]
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
    +-- [VPRF] embed query → initial vector search → blend top-3 doc vectors
    |         (Vector Pseudo-Relevance Feedback, +1-2% nDCG@10)
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
             [Metadata Boost]
             filename-matching chunks promoted
             (e.g. query "embeddings" → embeddings.py rises)
                      |
                      v
             [Reranker — optional]
             voyage rerank-2 (if VOYAGE_API_KEY set) → highest MRR lift
             local ms-marco cross-encoder (opt-in, NOT default)
                      |
                      v
               top K chunks
            (with file path + line range)
```

**Why hybrid matters:** Pure vector search misses exact keyword matches (vendor names, contract numbers, dates). Pure BM25 misses semantic synonyms. RRF merges both with zero extra infrastructure. Most cloud competitors use vector-only search — our hybrid approach beats them for scoped document collections.

**Reranker warning:** The local `ms-marco-MiniLM` cross-encoder is trained on MS-MARCO QA pairs and *hurts* code retrieval ranking. Only enable it explicitly. Voyage rerank-2 is code-aware and gives +0.43 MRR lift over voyage-code-3 embeddings alone.

---

## Embedding Layer

```
Dual embedding strategy (code vs documents):

Code files (.py, .js, .ts, .go, etc.):
  IF VOYAGE_API_KEY is set (recommended):
    voyage-code-3 (1024 dims) → sent to Voyage AI API
    Trained on code, 93 dataset benchmark, +13.8% NDCG@10 vs OpenAI v3-large
  ELSE (local, no API key):
    all-MiniLM-L6-v2 (384 dims) via sentence-transformers
    Free, private, runs on CPU — lower recall on code-specific queries

Text/document files (.md, .pdf, .docx, etc.):
  all-MiniLM-L6-v2 (384 dims) — sentence-transformers (always local)

Configurable via CODESIGHT_EMBEDDING_MODEL + CODESIGHT_EMBEDDING_BACKEND
```

---

## Chunking Strategy

### Code Files — AST-Based (tree-sitter)

For Python, JavaScript, and TypeScript, `chunk_file_ast()` uses tree-sitter to parse the file and extract top-level scope nodes (functions, classes, async functions, decorated definitions).

**Algorithm (cAST approach, EMNLP 2025):**
1. Parse with tree-sitter, collect top-level scope nodes
2. **Merge tiny siblings** (< 5 lines) with the next sibling — prevents stub-function fragments
3. **Sub-split oversized nodes** (> max_lines) with sliding windows
4. **Leading/trailing code** (imports, module docstrings, constants) becomes its own chunk

```
def alpha():          → Chunk 1: function alpha (if >= 5 lines)
    ...

def beta():           → Chunk 2: function beta (if >= 5 lines)
    ...

import os             → Leading chunk (imports before first function)
import sys
```

**Why better than fixed windows:** Function boundaries are semantically complete. A fixed 200-line window can split a function in half, making both halves harder to retrieve. AST chunking gave +0.224 MRR@10 in benchmark (0.599 → 0.823).

**Fallback chain:** tree-sitter AST → regex boundary patterns → sliding window

### Documents
Paragraph-aware splitting respecting page boundaries. Each chunk gets metadata:
- `start_line` / `end_line` = page numbers
- `scope` = heading or "page N"
- `language` = "pdf", "docx", "pptx"

### Context Headers
Every chunk gets a context header prepended before embedding:
```
# File: src/codesight/search.py
# Scope: function hybrid_search
# Lines: 189-303
```

This implements Anthropic's contextual retrieval technique — prepending file/scope context reduces retrieval failures by 35–67%.

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
    |   +-- chunks.lance  <- chunk_id, embedding vector (all-MiniLM or voyage)
    |   +-- code_chunks.lance  <- chunk_id, code embedding (voyage-code-3, if available)
    +-- metadata.db       <- SQLite with FTS5 virtual table
        |-- chunks         <- chunk_id, content, file_path, lines
        |-- chunks_fts     <- FTS5 index (auto-synced via triggers)
        +-- repo_meta      <- last_indexed_at, last_commit, etc.
```

**Content hashing:** Each chunk is hashed `sha256(content)[:16]`. On re-index, unchanged chunks are skipped entirely — no re-embedding, no write.

---

## Performance Benchmarks

Measured on the holusight codebase (96 files, 20 representative queries):

| Configuration | Hit Rate | MRR@10 | Notes |
|--------------|----------|--------|-------|
| Baseline (fixed windows, no reranker) | 52.5% | 0.352 | v0.2 |
| + VPRF + voyage reranker | 100% | 0.599 | Phase 1 |
| + AST chunking (tree-sitter) | 100% | 0.823 | Phase 2 — largest lever |
| + voyage-code-3 + voyage rerank-2 | 100% | **0.793** | Phase 4 — best overall |

**Key finding:** AST chunking was the single largest lever (+0.224 MRR). The local ms-marco cross-encoder *hurts* code retrieval. voyage rerank-2 adds +0.43 MRR on top of voyage-code-3 embeddings alone.

---

## Deployment Tiers

| Tier | Users | Deployment | Embedding | Reranker |
|------|-------|-----------|-----------|----------|
| Demo/pilot | 1-5 | Laptop | all-MiniLM (local) | off |
| Small team | 5-10 | Single VM | voyage-code-3 (API) | voyage rerank-2 |
| Department | 20-50 | Docker on cloud | voyage-code-3 (API) | voyage rerank-2 |
| Company | 100+ | Docker + FastAPI + auth | voyage-code-3 (API) | voyage rerank-2 |
| Air-gapped | Any | On-prem server | nomic-embed (local) | off |

---

## Context Injection Integration (Added 2026-04-04)

CodeSight is used as a runtime context provider inside the OpenClaw skill pipeline. When a developer runs `/code` on any repo, `codesight_context.py` searches that repo's index and injects the top-5 relevant chunks into the Codex prompt.

```
/code skill invoked
  → fleet_brain_hook.py "$REPO" "code"     (~150 tokens, project state)
  → codesight_context.py "$REPO_PATH" "$TASK"  (~1000-2000 tokens, code context)
  → both injected into RICH_TASK for Codex
```

**Key design decisions:**
- Engine lives in `holusight/src/codesight/` — shared across all repos
- Index is per-repo at `~/.codesight/data/<sha256(repo_path)[:12]>/` — isolated, no cross-repo bleed
- VOYAGE_API_KEY loaded from `holusight/.env` explicitly in `codesight_context.py` (not from CWD)
- Batch size capped at 8 chunks/request to stay under Voyage's 120K token/batch limit
- Stale threshold: 5 min — auto-reindexes changed files on next `/code` invocation

**Experiment results (3×3 eval, 2026-04-04):**
- No context: avg 76.3 | Fleet Brain only: avg 93.0 | Fleet + CodeSight: avg 93.8
- Context helps most on architecturally complex tasks (+25 pts on task requiring dual-store knowledge)
- Easy tasks already near-ceiling without context (99/99/99)

**Repos indexed:** holusight (230 chunks, 28s), pythia (875 chunks, 346s)

---

## What NOT to Change Without Discussion

1. **RRF k=60 constant** — changing this shifts recall/precision tradeoff. Benchmark before changing.
2. **Data directory location** (`~/.codesight/data/`) — changing this invalidates all existing indexes.
3. **Content hash algorithm** — changing from `sha256[:16]` invalidates all deduplication state.
4. **FTS5 trigger schema** — the SQLite triggers that sync FTS5 from the chunks table. Incorrect triggers cause silent search failures.
5. **LLM system prompt** — the `SYSTEM_PROMPT` in `llm.py` controls answer quality across all backends. Test changes with real documents.
6. **AST min_lines=5 threshold** — the merge-small threshold. Lowering it creates fragment chunks; raising it merges logically separate functions. Benchmark before changing.
