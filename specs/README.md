# Specs — codesight

Feature specifications for codesight.

## Feature Specs

| # | Spec | Status | Phase |
|---|------|--------|-------|
| 000 | [Template](000-template.md) | — | — |
| 001 | [Core Search Engine](001-core-search-tools.md) | Implemented | v0.1 + v0.2 |
| 002 | [Embedding Model Config](002-embedding-model-config.md) | Implemented | v0.3 |
| 003 | [Incremental Refresh](003-incremental-refresh.md) | Planned | v0.5 |
| 004 | [Tree-sitter Chunking](004-tree-sitter-chunking.md) | Planned | Future |
| 005 | [Automatic Re-indexing](005-watch-unwatch-tools.md) | Deprecated | — |
| 006 | [Pluggable LLM Backend](006-pluggable-llm-backend.md) | Implemented | v0.3 |
| 007 | [Cross-Encoder Reranking](007-cross-encoder-reranking.md) | Implemented | v0.3 |
| 008 | [Docker + FastAPI Deployment](008-docker-deployment-fastapi.md) | Implemented (single-team) | v0.5 |
| 009 | [CNFB — Multiplicative Filename Boost](009-cnfb-multiplicative-filename-boost.md) | Approved | v0.5 |
| 010 | [Capability Truth Inventory](010-capability-inventory.md) | Implemented | v0.5 |
| 011 | [Holusight Product Architecture Research](011-holusight-product-architecture-research.md) | Research/reference | Not implementation authorization |
| 012 | [Holusight Overnight Benchmark & Continuous Evaluation Research](012-holusight-overnight-benchmark-continuous-evaluation-research.md) | Research/reference | Not implementation authorization |
| 013 | [Holusight-AXI Documentation-Code Consistency Architecture](013-holusight-axi-consistency-architecture.md) | Phase 1 implemented | Direct-PR |

## Implementation History

### v0.1 — Hybrid Code Search (completed)
Hybrid BM25 + vector + RRF search engine. Language-aware chunking for 10 languages. Local embeddings. Content hash deduplication. See [Spec 001](001-core-search-tools.md).

### v0.2 — Enterprise Document Search (completed)
Major pivot from MCP code search server to enterprise document search engine:
- Package renamed `semantic_search_mcp` → `codesight`
- MCP layer removed, Python API created (`CodeSight` class)
- Document parsers: PDF, DOCX, PPTX
- Claude answer synthesis via Anthropic API
- Streamlit web chat UI + CLI
- See [Spec 001](001-core-search-tools.md) (updated to cover v0.2)

### v0.3 — Pluggable LLM + Better Embeddings + Reranking (completed)
- Pluggable LLM backend: Claude, Azure OpenAI, OpenAI, Ollama — [Spec 006](006-pluggable-llm-backend.md)
- Configurable embedding model + optional API embeddings (OpenAI) — [Spec 002](002-embedding-model-config.md)
- Optional cross-encoder reranking after RRF for better precision — [Spec 007](007-cross-encoder-reranking.md)

### v0.5 — Single-team Docker + FastAPI pilot (implemented)
- Dockerfile, FastAPI server, API-key auth, browser UI — [Spec 008](008-docker-deployment-fastapi.md)
- Capability inventory and citation contract — [Spec 010](010-capability-inventory.md)
- **Not claimed:** 50+ concurrent users, SSO, M365 connectors

> For design decisions (why LanceDB, why hybrid RRF, etc.), see `docs/decisions/`.
> For project roadmap, see `docs/roadmap.md`.
> For client pitch preparation, see `docs/playbooks/client-pitch.md`.
