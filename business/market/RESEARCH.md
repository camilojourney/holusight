# Research — Enterprise Knowledge Appliance

**Last updated:** 2026-02

---

## 1. Core Technical Approach

### Retrieval-Augmented Generation (RAG)

The system is a RAG pipeline with strict access control enforcement at every layer:

1. **Connectors** ingest from Microsoft Graph (Outlook, Teams, SharePoint), IMAP, SMB, Confluence
2. **Ingestion Pipeline** parses, cleans, chunks, and embeds documents
3. **Vector Store** indexes chunks in Qdrant (local) or Azure AI Search (cloud)
4. **Policy Engine** enforces ACLs at query time — no user sees documents they can't access in the source system
5. **LLM Response** generates answers with citations, filtered by permissions

### Two Deployment Architectures

**Mode A — Strict Local-Only:**
- Local embedding model (BAAI/bge, Nomic)
- Local LLM (Llama 3.1, Mistral, DeepSeek)
- Qdrant vector DB + PostgreSQL + MinIO
- No external network calls. Air-gapped capable.

**Mode B — Azure-Native:**
- Azure AI Search (hybrid + vector + security trimming)
- Azure OpenAI (GPT-4o, text-embedding-3)
- Entra ID + Purview labels for governance

## 2. ACL Enforcement Research

The core differentiator. Most competitors either:
- Trust the LLM to not reveal restricted content (Copilot approach — fails regularly)
- Apply coarse-grained filters (user-level, not document-level)

Our approach: **query-time permission filtering.**

```
User → SSO Auth → Identity Resolution → Group Membership
                                              │
                         Query ───────────────▼
                                      ACL Filter Construction
                                              │
                                    ┌─────────▼──────────┐
                                    │  Filtered Retrieval │
                                    │  (Vector + Keyword) │
                                    └─────────┬──────────┘
                                              │
                                    ┌─────────▼──────────┐
                                    │  LLM Response +     │
                                    │  Citations           │
                                    └─────────┬──────────┘
                                              │
                                         Audit Log
```

Every query is permission-filtered before the LLM sees any content. The filter is constructed from the user's identity (SSO) and group memberships, mapped to source system permissions.

## 3. Embedding & Retrieval Research

### Hybrid Retrieval

Vector-only retrieval misses exact matches (document IDs, error codes, names). BM25-only misses semantic similarity. Best practice: hybrid retrieval with Reciprocal Rank Fusion (RRF).

- **Azure AI Search** supports hybrid natively (vector + BM25 + semantic reranking)
- **Qdrant + SQLite FTS5** for Mode A (same approach as holusight MCP server)

### Embedding Models

| Model | Dims | Context | Notes |
|-------|------|---------|-------|
| text-embedding-3-small (Azure) | 1536 | 8191 | Best cost/performance for Mode B |
| BAAI/bge-large-en-v1.5 | 1024 | 512 | Strong local option for Mode A |
| Nomic-embed-text | 768 | 8192 | Long context, good for email threads |
| all-MiniLM-L6-v2 | 384 | 256 | Fast, lightweight, good for small deployments |

### Chunking Strategy

Enterprise documents vary widely (emails, PDFs, Slack messages, wiki pages). Key decisions:
- **Chunk by structure** (headers, paragraphs) not fixed token count
- **Prepend context headers** (source, author, date, path) to improve retrieval relevance
- **Overlapping chunks** (10-20% overlap) to avoid losing cross-boundary context
- **Thread-aware chunking** for email: keep reply chains together

## 4. Local LLM Research (Mode A)

For air-gapped deployments, LLM inference runs on customer hardware.

### Model Options (2026)

| Model | Params | VRAM | Quality | Notes |
|-------|--------|------|---------|-------|
| Llama 3.1 70B (4-bit) | 70B | ~40GB | High | Best quality for on-prem |
| Mistral Large (4-bit) | 123B | ~64GB | Highest | Requires A100 80GB |
| DeepSeek-V3 (4-bit) | 671B MoE | ~40GB active | High | MoE = efficient inference |
| Llama 3.1 8B (8-bit) | 8B | ~10GB | Medium | Runs on consumer GPU |

### Hardware Requirements

| Company Size | GPU Recommendation | Cost |
|-------------|-------------------|------|
| 100 employees | No GPU (quantized 8B) OR 1x A100 | $12K–$35K |
| 500 employees | 2x A100 80GB | $55K |
| 1,000+ employees | 4x A100 or 8x A100 | $100K–$250K |

## 5. Competitive Technical Analysis

### Microsoft Copilot Limitations
- Data governance failures: surfaces confidential docs to unauthorized users
- Bypasses DLP policies in certain configurations
- Inconsistent behavior across M365 apps
- Limited admin/governance tooling at enterprise scale
- No true hybrid retrieval — relies on Microsoft Search (BM25 only for most content)

### Glean Architecture
- Cloud-only SaaS (no on-prem option)
- Proprietary embedding model + HNSW index
- 200+ pre-built connectors (major advantage)
- Permission model maps to source ACLs (well-implemented)
- Minimum 200 seats, enterprise sales cycle

### Onyx (formerly Danswer) — Open Source
- Self-hosted, MIT license
- Basic connectors (Google Drive, Slack, web crawl)
- No enterprise ACL enforcement
- No compliance certifications
- Small team, limited support

## 6. Key Technical Risks

| Risk | Mitigation |
|------|-----------|
| ACL mapping complexity (source permissions are messy) | Start with SharePoint/OneDrive where Microsoft Graph exposes permissions cleanly |
| Local LLM quality gap vs GPT-4o | Use larger models (70B) with RAG context; test quality thresholds per customer |
| Connector maintenance burden | Start with 3 connectors (SharePoint, Drive, email), add incrementally |
| Embedding model mismatch (re-indexing cost) | Hash-based dedup, incremental re-indexing only on model change |

## 7. Implementation References

- Microsoft Graph API: delta queries for incremental sync, permissions endpoint for ACL mapping
- Azure AI Search: security trimming filters, hybrid retrieval configuration
- Qdrant: payload-based filtering for ACL enforcement, multi-tenancy via collection prefixes
- LangChain/LlamaIndex: connector abstractions, but prefer custom implementation for ACL control
- FastAPI + SSO: OIDC integration for identity resolution

## 8. Unit Economics (Per Customer)

### Mode B (Azure-Native, 500 employees)

| Component | Monthly Cost |
|-----------|-------------|
| Azure AI Search (S1, 2 SU) | $490 |
| Azure OpenAI (GPT-4o, 500 queries/day) | $400 |
| Azure OpenAI (Embeddings, incremental) | $100 |
| App Service (P1v3) | $138 |
| Azure SQL + Blob | $100 |
| **Total infrastructure** | **$1,228** |
| **License revenue** (500 × $25/user) | **$12,500** |
| **Gross margin** | **~90%** |

### Mode A (Local-Only, 500 employees)

| | Year 1 | Year 2+ |
|-|--------|---------|
| Upfront (hardware + deployment) | $115,000 | $0 |
| Monthly ongoing | $16,700 | $16,700 |
| **Your revenue (license + support)** | **$12,000/mo** | **$12,000/mo** |

## 9. Multi-Strategy Retrieval (Added 2026-03)

RAG is a capability, not a foundation. Different data → different retrieval strategy.

### Strategy Matrix

| Strategy | When to Use | Implementation |
|----------|------------|----------------|
| **CAG (Cache-Augmented)** | Corpus < 200 pages, rarely changes | Dump full corpus in LLM context. Zero infrastructure. 40x faster than RAG. |
| **RAG (Retrieval-Augmented)** | 200-50,000 pages, periodic updates | Current hybrid approach (BM25 + vector + RRF). Production default. |
| **JIT Context** | Live data (M365, email, CRM) | Query Graph API / IMAP at query time. Always fresh. No embedding pipeline. |
| **Agentic RAG** | Complex multi-source questions | Agent plans retrieval: "search contracts, cross-reference emails, check policies." 87% multi-hop accuracy vs 23% for naive RAG. |

### Auto-Detection Logic

```
Query arrives
    ├── Corpus < 200 pages AND fits in context window?
    │   YES → CAG (preload everything)
    │
    ├── Query references live data (email, calendar, recent)?
    │   YES → JIT (fetch from connector APIs)
    │
    ├── Query is multi-hop / cross-source?
    │   YES → Agentic RAG (planner + retriever chain)
    │
    └── DEFAULT → RAG (hybrid BM25 + vector + RRF)
```

### Why This Matters

- CAG: 2.3 seconds vs RAG's 94 seconds for small corpora (40x improvement)
- Agentic RAG: 87% accuracy on multi-hop questions vs 23% for naive top-k
- JIT eliminates embedding pipeline maintenance for live data sources
- Standard RAG sits in an awkward middle: slower than CAG for static, dumber than Agentic for complex

Holusight auto-picks the right strategy. No competitor does this.

## 10. Updated Competitive Landscape (2026-03)

### New Competitor: GoSearch
- **Pricing:** ~$8/user/mo
- **Positioning:** Budget Glean alternative
- **Architecture:** RAG-first, faster deployment than Glean
- **Weakness:** SaaS-only, no on-prem option, limited ACL depth
- **Our edge:** On-prem + deep ACL + multi-strategy retrieval + consulting delivery

## 11. Vector DB Strategy (Updated 2026-03)

### Tiered Approach

| Deployment | Size | Vector DB | Rationale |
|-----------|------|-----------|-----------|
| Mode A small (< 500 employees) | < 500K docs | LanceDB (embedded) | Zero infrastructure, file-based, perfect for consulting demos |
| Mode A large (> 500 employees) | > 500K docs | Qdrant (server) | Scales, native payload filtering for ACLs, production-grade |
| Mode B (Azure) | Any | Azure AI Search | Native security trimming, hybrid retrieval, managed service |

LanceDB for simplicity, Qdrant for scale, Azure AI Search for cloud-native. All three share the same ingestion pipeline.
