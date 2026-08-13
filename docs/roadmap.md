# Roadmap — codesight

_Updated: 2026-04-04_

---

## v0.1 — Hybrid Code Search Engine ✅ DONE

- [x] Hybrid BM25 + vector retrieval with RRF merge
- [x] LanceDB vectors + SQLite FTS5 sidecar
- [x] Language-aware regex chunking (10 languages)
- [x] `all-MiniLM-L6-v2` local embeddings (no API key)
- [x] `.gitignore`-aware file walking
- [x] Content hashing (skip unchanged chunks)

## v0.2 — Enterprise Document Search ✅ DONE

- [x] Package rename: `semantic_search_mcp` → `codesight`
- [x] Document parsers: PDF (pymupdf), DOCX (python-docx), PPTX (python-pptx)
- [x] Document-aware chunking (paragraph boundaries, page metadata)
- [x] Python API: `CodeSight` class with `index()`, `search()`, `ask()`, `status()`
- [x] Claude answer synthesis with source citations
- [x] Streamlit web chat UI (`demo/app.py`)
- [x] CLI: `python -m codesight index|search|ask|status|demo`
- [x] Auto-index on first search, auto-refresh when stale

## v0.3 — Pluggable LLM + Better Embeddings ✅ DONE

- [x] Pluggable LLM backend: Claude, Azure OpenAI, OpenAI, Ollama
- [x] `CODESIGHT_LLM_BACKEND` config
- [x] Optional API embedding (Voyage) via `VOYAGE_API_KEY` + `CODESIGHT_EMBEDDING_BACKEND`
- [x] Cross-encoder reranker after RRF (voyage rerank-2)

## v0.4 — Retrieval Quality ✅ DONE — 2026-04-04

_Benchmark: 52.5% hit rate / MRR 0.352 → 100% hit rate / MRR 0.823_

- [x] **AST-based chunking** (tree-sitter) — Python/JS/TS function/class boundaries. +0.224 MRR lift. Largest single lever.
  - cAST algorithm: merge tiny siblings (<5 lines) + sub-split oversized (>max_lines)
  - Context headers prepended before embedding (Anthropic contextual retrieval)
  - Regex fallback when tree-sitter not installed
- [x] **voyage-code-3 embeddings** — code-specific 1024-dim model, auto-detected via `VOYAGE_API_KEY`
- [x] **voyage rerank-2** — code-aware reranker, +0.43 MRR on top of voyage-code-3
- [x] **Metadata filename boost** — stable re-ordering promoting chunks from filename-matching files
- [x] **VPRF** (Vector Pseudo-Relevance Feedback) — query vector blended with top-3 retrieved doc vectors
- [x] **Reranker auto-detection** — voyage rerank-2 auto-enables when `VOYAGE_API_KEY` set; ms-marco cross-encoder local opt-in only (hurts code retrieval)
- [x] **Dual LanceDB tables** — separate `chunks.lance` (doc embeddings) + `code_chunks.lance` (voyage-code-3)
- [x] **95 passing tests** covering AST chunking, RRF merge, VPRF, metadata boost, reranker routing

## v0.5 — Single-team Docker + FastAPI pilot ✅ DONE — 2026-08-13

_Consulting-ready for one team. Not a multi-tenant SaaS or M365 platform._

- [x] **Dockerfile** + `docker-compose.yml` for single-command deployment
- [x] **FastAPI web server** with browser search/ask UI and citations
- [x] **API key auth** (`X-API-Key` / Bearer) required in production-shaped runs
- [x] Read-only document mount + persistent index volume
- [x] Search works without an LLM key; Ask distinguishes synthesis provider
- [x] Capability inventory: [specs/010-capability-inventory.md](../specs/010-capability-inventory.md)

Still planned (not in this slice):
- [ ] **Microsoft Graph connector** — SharePoint + OneDrive
- [ ] **Outlook/Exchange connector**
- [ ] **Email parsing** — `.eml`, `.msg`, `.xlsx`
- [ ] **Document sync** from Azure Blob / S3
- [ ] Concurrent-user SLA (not claimed)

## v0.6 — ACL Enforcement

_The core differentiator. This is what makes CodeSight enterprise-grade._

- [ ] **SSO integration** — OIDC/OAuth2 identity resolution
- [ ] **Group membership mapping** — Entra ID / Active Directory groups
- [ ] **Query-time permission filtering** — construct ACL filter from user identity
- [ ] **SharePoint permission sync** — map Graph API permissions to search filters
- [ ] **Audit logging** — every query logged with user, results, permissions applied
- [ ] Filter applied BEFORE LLM sees any content (security guarantee)

## v0.7 — Multi-Strategy Retrieval

_Not everything is RAG. Auto-pick the right strategy per query._

- [ ] **CAG mode** — corpus < 200 pages → dump full context to LLM (skip embeddings)
- [ ] **JIT mode** — live data queries → fetch from Graph API / IMAP at query time
- [ ] **Agentic RAG** — complex multi-source questions → planner picks retrieval chain
- [ ] **Auto-detection** — analyze corpus size + query type → select strategy
- [ ] **RAG** remains default for 200-50K page corpora

## v0.8 — Scale + Advanced Features

- [ ] **Qdrant option** for large deployments (>500K docs)
- [ ] **Azure AI Search** integration (native security trimming)
- [ ] Incremental refresh (git-diff + file-watcher based)
- [ ] Slack Bot — slash commands + thread Q&A
- [ ] Google Drive connector

## v1.0 — Production Ready

- [ ] Comprehensive test suite (unit + integration + e2e)
- [ ] SSO production hardening (SAML + OIDC)
- [ ] Apple Silicon GPU acceleration (MPS backend)
- [ ] Batch embedding optimization
- [ ] Multi-folder search (cross-collection queries)
- [ ] Compliance reporting (SOC2, HIPAA audit trail)
- [ ] PyPI package publishing

---

## Retrieval Quality History

| Version | Hit Rate | MRR@10 | Key change |
|---------|----------|--------|------------|
| v0.1 baseline | 52.5% | 0.352 | Fixed windows, no reranker |
| v0.3 + VPRF + reranker | 100% | 0.599 | Phase 1 |
| v0.4 + AST chunking | 100% | 0.823 | Phase 2 — largest lever (+0.224) |
| v0.4 + voyage-code-3 + rerank-2 | 100% | **0.793** | Phase 4 — best overall config |

---

## Revenue Milestones

| Version | Date | Milestone |
|---------|------|-----------|
| v0.4 | Apr 2026 | Demo-ready, 100% hit rate, MRR 0.793 |
| v0.5 | TBD | First consulting demo (multi-user, Docker, M365) |
| v0.6 | TBD | Enterprise-grade (ACL, audit, SSO) |
| v0.7 | TBD | Competitive edge (multi-strategy retrieval) |
| v1.0 | TBD | Production deployments, first paying clients |
