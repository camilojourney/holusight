# Spec 001: Core Search Engine

**Status:** implemented
**Phase:** v0.1 (search engine), v0.2 (document support + Python API + web chat)
**Author:** Juan Martinez
**Created:** 2026-02-24
**Updated:** 2026-02-28

## Problem

Companies have hundreds or thousands of documents — contracts, policies, technical specs, code — scattered across folders. Finding specific information means manually opening files, using Ctrl+F, and reading pages. When someone asks "What are the payment terms in the Acme contract?", there's no tool that can answer instantly from the full document collection.

Existing tools are either too expensive (Glean, Microsoft Copilot at $30/user/mo), too limited (ChatPDF — one file at a time), or require complex cloud setup (Azure AI Search).

## Goals

- Hybrid BM25 + vector search with RRF merge — catches both exact keywords and semantic meaning
- Index entire folders of documents (PDF, DOCX, PPTX, code, text) in seconds
- `ask()` method that returns LLM-generated answers with source citations
- Web chat UI where non-technical users can ask questions in plain English
- CLI for power users and automation
- 100% local search — no data leaves the machine for search/indexing
- Auto-index on first search, auto-refresh when stale — works without setup

## Non-Goals

- Writing to indexed folders — codesight is strictly read-only. This is a security invariant.
- Cloud storage integration (SharePoint, Google Drive) — local paths only for now (connectors are v0.7)
- Multi-folder search — one `CodeSight` instance per folder
- Streaming LLM responses — planned for later

## Solution

```
User (non-technical)
      |
      v
+------------------------------------------+
| Interface Layer                          |
| Web Chat (Streamlit) | CLI | (Slack)    |
+----------+------------------------------|
           |
           v
+------------------------------------------+
| CodeSight Python API (api.py)            |
| index()  search()  ask()  status()       |
+----------+-------------------------------+
           |
     +-----+--------------------------+
     |                                |
     v                                v
+----------+              +--------------+
| Indexer   |              | Search       |
| Walk files|              | BM25 (FTS5)  |
| Parse docs|              | Vector search|
| Chunk     |              | RRF merge    |
| Embed     |              +--------------+
| Store     |                     |
+----------+              +------+-------+
     |                    |              |
     v                    v              v
  LanceDB           SQLite FTS5     LLM Backend
 (vectors)          (keywords)      (ask() only)
```

### The `ask()` Pipeline

```
question → search(question, top_k=5) → top 5 chunks   [LOCAL]
         → format chunks as context with file + page
         → LLM call (Claude/Azure/Ollama)              [CONFIGURABLE]
         → Answer(text, sources, model)
```

### The Hybrid Retrieval Pipeline

```
query → BM25 via SQLite FTS5 → top 20 keyword matches
      → Vector via LanceDB   → top 20 semantic matches
      → Reciprocal Rank Fusion (k=60)
      → top K merged results
```

## API Contract

```python
from codesight import CodeSight

engine = CodeSight("/path/to/documents")

# Stable public imports from package root:
# CodeSight, ServerConfig, Answer, IndexStats, RepoStatus, SearchResult

# Index all files in the folder
engine.index(force_rebuild: bool = False) -> IndexStats
# Returns: IndexStats(total_files, total_chunks, duration_seconds)

# Hybrid search — always local, always free
engine.search(query: str, top_k: int = 8, file_glob: str | None = None,
              source: str | None = None) -> list[SearchResult]
# Returns: list of SearchResult(content, file_path, start_line, end_line, scope, score)
# source: optional filter — "holus" restricts results to imported Holus lineage chunks

# Search + LLM answer synthesis
engine.ask(question: str, top_k: int = 5, file_glob: str | None = None,
           source: str | None = None) -> Answer
# Returns: Answer(text, sources: list[SearchResult], model: str)
# Errors: ValueError if ANTHROPIC_API_KEY not set (or equivalent for chosen backend)

# Index freshness check
engine.status() -> RepoStatus
# Returns: RepoStatus(indexed, total_files, total_chunks, last_indexed_at, is_stale)

# Import one already-fetched, validated Holus v1 lineage export
engine.import_holus_lineage(payload: Mapping[str, Any]) -> HolusImportStats
# Returns: HolusImportStats(source, source_schema_version, records_imported,
#                           records_skipped_unchanged, total_records)
# Read-only: never accesses Holus storage, packages, or producer endpoints
# Errors: ValueError on malformed, unsupported, or unsafe export content
```

## Implementation Notes

### Key Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| RRF k constant | 60 | Standard from RRF paper (Cormack et al.), proven effective. Default starting point; per-domain A/B testing recommended per RESEARCH.md §1.1 (RRF is significantly domain-dependent). |
| BM25 top N | 20 | Feed 20 keyword results into RRF |
| Vector top N | 20 | Feed 20 semantic results into RRF |
| Default top_k | 8 (search), 5 (ask) | Balance completeness vs noise |
| Max file size | 10MB | Covers large PDFs without OOM |
| Content hash | sha256[:16] | Dedup without storage overhead |
| Stale threshold | 60 minutes | Configurable via CODESIGHT_STALE_MINUTES |
| Chunk max chars | 1500 (docs), 200 lines (code) | Fits in embedding context window |

### Dependencies

- `lancedb` — serverless vector store
- `sentence-transformers` — local embedding models
- `anthropic` — Claude API for answer synthesis
- `pymupdf` — PDF text extraction
- `python-docx` — DOCX text extraction
- `python-pptx` — PPTX text extraction
- `pathspec` — .gitignore-aware file walking
- `pydantic` / `pydantic-settings` — config and data models
- `streamlit` (optional) — web chat UI
- Depended on by: all other specs (this is the foundation)

### Document Parsing Pipeline

```
File on disk
    |
    |-- Code (.py, .js, .ts, etc.) → read_text() → chunk_file() (scope boundaries)
    |-- Text (.md, .txt, .csv)     → read_text() → chunk_file() (sliding windows)
    +-- Docs (.pdf, .docx, .pptx)  → parsers.extract_text() → chunk_document()
```

### Storage Layout

```
~/.codesight/data/<sha256(folder_path)[:12]>/
    ├── lance/         ← LanceDB vector tables
    └── metadata.db    ← SQLite with FTS5 virtual table + repo metadata
```

## Alternatives Considered

### Alternative A: Vector-only search (no BM25)

Trade-off: Simpler implementation, but misses exact keyword matches (contract numbers, dates, vendor names).
Rejected because: Hybrid BM25+vector+RRF is table stakes (Azure AI Search, Onyx, RAGFlow ship it natively). CodeSight differentiates on: $0 local-first search, pluggable LLM backends, and the strategy router (v0.5).

### Alternative B: Cloud-hosted vector DB (Pinecone, Weaviate)

Trade-off: Scales better, but requires cloud account, API key, and sends document data to a third party.
Rejected because: "Search is 100% local" is a core selling point for enterprise clients.

### Alternative C: LangChain / LlamaIndex framework

Trade-off: More features out of the box, but massive dependency tree, complex API, most features unused.
Rejected because: We need index + search + ask. Our implementation is ~500 lines. LangChain is overkill.

## Edge Cases & Failure Modes

- Empty folder → `index()` returns 0 chunks, `search()` returns empty list, `ask()` says "no documents found"
- Binary files → skipped by file walker (extension check)
- Very large file (>10MB) → skipped with warning logged
- Non-UTF-8 text files → skip with warning, don't crash
- No `ANTHROPIC_API_KEY` → `search()` works fine, `ask()` raises clear error
- Corrupted PDF → `pymupdf` raises, caught and logged, file skipped
- Folder doesn't exist → `ValueError` with clear message
- Path traversal (`../`) → resolved and validated before use

## Acceptance Criteria

- [x] `engine.search("payment terms")` returns ranked chunks from indexed documents
- [x] `engine.index()` processes PDF, DOCX, PPTX, code, and text files
- [x] `engine.ask("What are the payment terms?")` returns LLM-generated answer with source citations
- [x] `engine.status()` reports index health, file count, chunk count, staleness
- [x] Auto-index on first `search()` if no index exists
- [x] Auto-refresh when index is stale (beyond CODESIGHT_STALE_MINUTES)
- [x] `.gitignore`-aware file walking (skip node_modules, .git, dist, etc.)
- [x] Language-aware chunking for 10 languages (Python, JS, TS, Go, Rust, Java, Ruby, PHP, C, C++)
- [x] Document chunking with paragraph boundaries and page metadata
- [x] Content hashing — skip re-embedding unchanged chunks
- [x] Streamlit web chat UI with source citation cards
- [x] CLI with subcommands: index, search, ask, status, demo
- [x] Path traversal inputs raise `ValueError`
- [x] Indexer never writes to the indexed folder (read-only invariant)
