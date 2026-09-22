# Vision — holusight

_Updated: 2026-03-03 — Aligned with RESEARCH.md_

## What It Is

Holusight is an AI-powered enterprise knowledge search appliance. Deploy it for a client — point it at their documents, emails, SharePoint — and it indexes everything into a hybrid search index with strict access control enforcement. Users ask questions in plain English and get precise answers with source citations. No unauthorized user ever sees content they shouldn't.

## The Core Business

**Consulting tool → Enterprise product.**

Phase 1: Walk into a company with a laptop. "Give me access to your SharePoint and documents." Index it, show them the web chat, they're amazed. Deliverable: deployed instance + training + ongoing support. You charge for the engagement ($5K-50K depending on scope).

Phase 2: Productize. Self-service deployment. Per-user licensing. Recurring revenue.

## The Problem

Enterprise knowledge is trapped in email threads, SharePoint folders, shared drives, and chat histories. Employees spend 9+ hours/week searching for information. When experts leave, their knowledge disappears.

Existing solutions:
- **Microsoft Copilot** ($30/user/mo) — data governance failures, surfaces confidential docs to unauthorized users
- **Glean** ($45-50/user/mo) — too expensive for mid-market, 200-seat minimum
- **Open source (Onyx/Danswer)** — no enterprise ACL, no compliance story
- **GoSearch** ($8/user/mo) — SaaS only, no on-prem option

## The Solution

Two deployment architectures for two trust levels:

**Mode A — Strict Local-Only:** Nothing leaves the network. Local embeddings, local LLM, local vector DB. Air-gapped capable. For finance, defense, legal, healthcare.

**Mode B — Azure-Native:** Fastest deployment. Azure AI Search + Azure OpenAI in client's own tenant. Entra ID for governance. For tech companies, professional services.

## Key Differentiators

1. **ACL enforcement at query time.** Permission filtering happens BEFORE the LLM sees any content. Not after. This is the #1 selling point.
2. **Hybrid retrieval (BM25 + vector + RRF).** Catches exact matches (contract numbers, dates, vendor names) that vector-only competitors miss.
3. **Multi-strategy retrieval.** Not everything is RAG. Auto-picks: CAG for small corpora, RAG for large, JIT for live data, Agentic RAG for complex multi-source questions.
4. **On-prem option.** Glean can't do this. GoSearch can't do this. Copilot can't be trusted with it.
5. **Mid-market pricing.** $15-25/user vs Glean's $45-50/user.

## The Stack

### Mode A (Local-Only)
- Connectors: SharePoint (Graph API), Outlook, file shares
- Embeddings: BAAI/bge-large or Nomic (local, no API)
- Storage: LanceDB + SQLite FTS5 (small) | Qdrant (large)
- LLM: Ollama / vLLM (Llama 3.1 70B, DeepSeek-V3)
- Deploy: Docker on any machine

### Mode B (Azure-Native)
- Connectors: Microsoft Graph API (SharePoint, OneDrive, Outlook, Teams)
- Embeddings: Azure OpenAI text-embedding-3-small
- Storage: Azure AI Search (hybrid + security trimming)
- LLM: Azure OpenAI GPT-4o (client's tenant)
- Deploy: Azure App Service

## Target Customer

| Profile | Industries | Size | Budget | Sell Line |
|---------|-----------|------|--------|-----------|
| Strict Local | Finance, defense, legal | 200-2000 | $50K-200K/yr | "Nothing leaves your network." |
| Azure-First | Tech, professional services | 100-1000 | $30K-150K/yr | "Your company's brain, inside your Azure." |
| Compliance | Healthcare, gov contractors | Any | $50K-200K/yr | "AI search your compliance team approves." |

## Design Principles

1. **Security first** — ACL filtering before LLM sees content. Always.
2. **Data stays where the client wants** — local, Azure, or hybrid.
3. **Pluggable everything** — LLM, embeddings, vector DB, connectors.
4. **Read-only** — never writes to source systems. Zero data corruption risk.
5. **Right tool for the job** — CAG, RAG, JIT, or Agentic RAG depending on query.
6. **Deploy anywhere** — Docker runs on Azure, AWS, on-prem, or a laptop.
