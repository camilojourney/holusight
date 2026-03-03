# Delivery Planner — Memory

**Last updated:** 2026-02-28

## CodeSight Current State (v0.2 — Implemented)

- Hybrid BM25 + vector search with RRF merge (working)
- Document parsing: PDF, DOCX, PPTX (working)
- Code search: 10 languages with language-aware chunking (working)
- Streamlit web chat UI: `python -m codesight demo` (working)
- CLI: `codesight index / search / ask / status` (working)
- Python API: `index()`, `search()`, `ask()`, `status()` (working)
- Claude answer synthesis with citations (working)
- Local embeddings: all-MiniLM-L6-v2, no API key (working)
- Content hash deduplication on re-index (working)

## NOT Built Yet

- Pluggable LLM backends (Ollama, Azure, OpenAI) — v0.3
- Better embeddings (nomic-embed-text-v1.5) — v0.3
- Docker + FastAPI production server — v0.4
- Incremental refresh (git diff / mtime) — v0.5
- M365 connectors (SharePoint, Outlook) — v0.7

## Delivery Implications

- Can demo TODAY with any folder of PDFs/DOCX/PPTX
- For "100% local / no data leaves" pitch, need Ollama backend (v0.3)
- For 50+ users, need Docker+FastAPI (v0.4)
- M365 auto-sync not ready — clients must export/sync folders manually for now
- Demo setup takes ~5 minutes (index folder + launch UI)

## Delivery Patterns

_No engagements delivered yet. Will track actual timelines vs estimates._
