# Spec 010: Capability Truth Inventory

**Status:** implemented (living inventory)
**Phase:** v0.5 SMB pilot
**Updated:** 2026-08-13

> Last verified against branch `fm/holusight-smb-product-v2`.
> Every **Shipped** row maps to executable code and/or an automated test.
> **Planned** rows are labeled explicitly — not marketed as available.

## Legend

| Status | Meaning |
|--------|---------|
| **Shipped** | Implemented and covered by tests or reproducible CLI/API path |
| **Optional** | Implemented but requires extra dependency, API key, or explicit config |
| **Constrained** | Works within documented limits |
| **Planned** | Specified but not implemented in this release |

## Core retrieval

| Capability | Status | Evidence |
|------------|--------|----------|
| Hybrid BM25 + dense vector search | **Shipped** | `src/codesight/search.py`, `tests/test_search.py` |
| Reciprocal Rank Fusion (RRF) merge | **Shipped** | `rrf_merge()` in `search.py`, `TestRRFMerge` |
| Local embeddings (no network) | **Shipped** | `all-MiniLM-L6-v2` default, `tests/test_e2e.py` |
| Voyage code embeddings | **Optional** | `VOYAGE_API_KEY`, `embeddings.py` |
| Cross-encoder reranking | **Optional** | `CODESIGHT_RERANKER`, voyage or local backend |
| VPRF query enhancement | **Optional** | `CODESIGHT_QUERY_ENHANCEMENT=true` |
| CNFB filename boost | **Optional** | `CODESIGHT_CNFB_ALPHA` (default 0) |
| Incremental re-index (content hash) | **Shipped** | `indexer.py`, `test_security.py` read-only |
| Auto-index on first search | **Shipped** | `CodeSight._ensure_indexed()` |

## Document parsing & chunking

| Format | Citation metadata today | Status | Evidence |
|--------|-------------------------|--------|----------|
| PDF (`.pdf`) | `file_path`, **page** number in `start_line`/`end_line`, scope `page N` | **Shipped** | `parsers.py`, chunker |
| Word (`.docx`) | `file_path`, section index as page number, scope `section …` | **Shipped** | `parsers.py` |
| PowerPoint (`.pptx`) | `file_path`, slide number, scope `slide N` | **Shipped** | `parsers.py` |
| Markdown / text | `file_path`, **line** range, scope (paragraph/window) | **Shipped** | `tests/test_e2e.py` |
| Code (`.py`, `.js`, `.ts`, …) | `file_path`, **line** range, scope `function`/`class` name when AST available | **Shipped** | `chunker.py`, AST optional extra |
| AST chunking (Python/JS/TS) | Same as code, function/class boundaries | **Optional** | `pip install -e ".[ast]"` |

**Not claimed:** page-level citations for plain `.txt` (lines only). Chunk text is returned as `snippet`, never full files.

## Interfaces

| Surface | Status | Evidence |
|---------|--------|----------|
| Python API (`CodeSight`) | **Shipped** | `api.py`, CLI, tests |
| CLI (`index`, `search`, `ask`, `status`, `demo`) | **Shipped** | `__main__.py` |
| Streamlit demo UI | **Shipped** | `demo/app.py`, optional `[demo]` extra |
| FastAPI + browser UI (`serve`) | **Shipped** | `src/codesight/web/`, `tests/test_server.py` |
| Docker single-team deployment | **Shipped** | `Dockerfile`, `docker-compose.yml` |
| Public marketing site (holusight.com) | **Shipped** | `landing/`, `tests/test_deployment.py` — static only, no customer data |

## Authentication & security

| Capability | Status | Notes |
|------------|--------|-------|
| API key auth (`X-API-Key` / Bearer) | **Shipped** | Required when `CODESIGHT_PRODUCTION=1` or key set |
| Dev unauthenticated mode | **Constrained** | `CODESIGHT_ALLOW_UNAUTHENTICATED=true` only |
| Read-only document mount | **Shipped** | Engine never writes to source folder — `test_security.py` |
| Path traversal prevention | **Shipped** | `CodeSight` validates directory |
| FTS query sanitization | **Shipped** | `test_security.py` |
| SSO / OAuth / SAML | **Planned** | Spec 008 non-goal |
| Per-document ACL enforcement | **Planned** | `business/specs/001-acl-enforcement.md` |

## Answer synthesis (`ask`)

| Capability | Status | Notes |
|------------|--------|-------|
| `search` without LLM | **Shipped** | Fully local |
| `ask` with Claude | **Optional** | `ANTHROPIC_API_KEY` |
| `ask` with Azure OpenAI | **Optional** | `CODESIGHT_LLM_BACKEND=azure` |
| `ask` with OpenAI | **Optional** | `CODESIGHT_LLM_BACKEND=openai` |
| `ask` with Ollama (local) | **Optional** | `CODESIGHT_LLM_BACKEND=ollama` |
| Fully local answers without any LLM runtime | **Not supported** | Search-only is the local path |

## Explicitly planned / not in v1

| Item | Status | Reference |
|------|--------|-----------|
| M365 / SharePoint connectors | **Planned** | business specs |
| Multi-tenant SaaS control plane | **Planned** | out of scope |
| Kubernetes / Helm | **Planned** | Spec 008 non-goal |
| Graphify code-graph integration | **Planned** | see `docs/decisions/0010-graphify-extension-contract.md` |
| 50-user concurrency SLA | **Not claimed** | single-team pilot scope |
| Compliance certifications (SOC2, etc.) | **Not claimed** | — |

## Citation contract (API / UI)

Each `SearchResult` includes:

- `file_path` — relative to indexed root
- `start_line`, `end_line` — line numbers for code/text; page/slide numbers for documents
- `scope` — human label (`function foo`, `page 3`, `section Introduction`, …)
- `snippet` — chunk text (truncated in UI)
- `score`, `chunk_id`

Tests proving end-to-end citations: `tests/test_e2e.py`, `tests/test_server.py`.
