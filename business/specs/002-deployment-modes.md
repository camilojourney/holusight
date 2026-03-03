# Spec: Deployment Modes

## Decision Matrix

Every customer answers 2 questions:

| Question | Option A | Option B |
|----------|----------|----------|
| **Where can data live?** | Local-only (on-prem / VNet) | Azure cloud allowed |
| **Where can inference happen?** | Local models only | Cloud LLM allowed |

These answers determine the deployment mode.

---

## Mode A — Strict Local-Only

> *"Nothing leaves your network."*

### When to Use

- Customer requires air-gap or VNet isolation
- Regulatory: CMMC, ITAR, certain HIPAA scenarios, financial services with strict data residency
- Customer has no Azure subscription or refuses cloud AI services

### Architecture

```
┌────────────────────────────────────────────────────────┐
│                  Company Network                        │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │              Appliance (VM / Docker)              │  │
│  │                                                    │  │
│  │  ┌─────────┐   ┌──────────┐   ┌───────────────┐  │  │
│  │  │Connectors│──▶│ Ingestion │──▶│  Vector Store  │  │  │
│  │  │ Graph/   │   │ Parse,    │   │  (Qdrant)     │  │  │
│  │  │ IMAP/SMB │   │ Chunk,    │   └───────┬───────┘  │  │
│  │  └─────────┘   │ Embed     │   ┌───────▼───────┐  │  │
│  │                 └──────────┘   │  Doc Store    │  │  │
│  │                                │  (Postgres +  │  │  │
│  │  ┌─────────┐   ┌──────────┐   │   MinIO)      │  │  │
│  │  │Local LLM │──▶│ API Layer│◀──┴───────────────┘  │  │
│  │  │Llama/    │   │          │                        │  │
│  │  │Mistral   │   │          │◀── Policy Engine       │  │
│  │  └─────────┘   └────┬─────┘    (ACL Filter)       │  │
│  │                      │                              │  │
│  │  ┌─────────────┐    │    ┌────────────────┐       │  │
│  │  │Admin Console │    │    │ SSO (SAML/OIDC)│       │  │
│  │  └─────────────┘    │    └────────────────┘       │  │
│  └──────────────────────┼──────────────────────────┘  │
│                         │                              │
│         ┌───────────────┼────────────────┐             │
│         │               │                │             │
│    ┌────▼───┐     ┌────▼────┐     ┌────▼───┐         │
│    │Slack Bot│     │Teams Bot│     │ Web UI │         │
│    └────────┘     └─────────┘     └────────┘         │
└────────────────────────────────────────────────────────┘
```

### Technology Stack

| Component | Technology | Notes |
|-----------|-----------|-------|
| **Embedding Model** | BAAI/bge-large-en-v1.5 or Nomic Embed | Runs on CPU (slower) or GPU (fast) |
| **LLM** | Llama 3.1 70B / Mistral Large / DeepSeek-R1 | Requires GPU (A100/H100) or quantized (4-bit) on consumer GPU |
| **Vector DB** | Qdrant | Local, single-binary, easy to operate |
| **Doc Store** | PostgreSQL | Metadata, ACLs, chunks |
| **Object Store** | MinIO | S3-compatible, stores original docs |
| **Search** | Qdrant (vector) + PostgreSQL FTS (keyword) | Hybrid retrieval |
| **Identity** | SAML/OIDC via ADFS, Okta, or local IdP | Maps to AD groups |
| **Deployment** | Docker Compose (small) / K8s (scale) | Single VM for <500 users |
| **Monitoring** | Prometheus + Grafana | Standard ops stack |

### Hardware Requirements

| Scale | CPU | RAM | GPU | Storage |
|-------|-----|-----|-----|---------|
| Small (< 500 users, < 100K docs) | 8 cores | 32 GB | Optional (CPU inference OK for small models) | 500 GB SSD |
| Medium (500–2K users, < 1M docs) | 16 cores | 64 GB | 1x A10/A100 (24–40 GB VRAM) | 1 TB SSD |
| Large (2K+ users, > 1M docs) | 32+ cores | 128+ GB | 2x A100 | 2+ TB SSD |

### Optional: Azure Arc Management

For IT teams that want Azure-style governance over on-prem workloads:

- Deploy appliance on K8s cluster
- Attach via Azure Arc-enabled Kubernetes
- Azure becomes the control plane (policy, monitoring, updates)
- Compute and data stay local

**Benefit**: Sells well to Azure-first IT teams who want centralized management without cloud data residency.

---

## Mode B — Azure-Native

> *"Fastest enterprise deployment inside your Azure stack."*

### When to Use

- Customer is already on Azure (Entra ID + M365)
- Cloud data residency is acceptable
- Customer wants fastest deployment and managed services
- Budget for Azure consumption costs

### Architecture

```
┌────────────────────────────────────────────────────────┐
│                     Azure Cloud                         │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │           Your Service (App Service / AKS)        │  │
│  │                                                    │  │
│  │  ┌─────────┐   ┌──────────┐   ┌───────────────┐  │  │
│  │  │Connectors│──▶│ Ingestion │──▶│Azure AI Search│  │  │
│  │  │ MS Graph │   │ Pipeline  │   │Hybrid + Vector│  │  │
│  │  └─────────┘   └──────────┘   │+ Sec Trimming │  │  │
│  │                                └───────┬───────┘  │  │
│  │  ┌──────────┐                          │          │  │
│  │  │Azure Blob │   ┌──────────┐          │          │  │
│  │  │ Storage   │   │Azure AOAI│──▶ API Layer ◀──────┘  │  │
│  │  └──────────┘   │GPT-4o    │          │              │
│  │                  └──────────┘          │              │  │
│  │                                       │              │  │
│  │  ┌──────────────┐  ┌────────────┐     │              │  │
│  │  │Purview Labels │  │ Entra ID   │─────┘              │  │
│  │  │(Governance)  │  │(Sec Trim)  │                    │  │
│  │  └──────────────┘  └────────────┘                    │  │
│  │                                                       │  │
│  │  ┌─────────────┐                                     │  │
│  │  │Admin Console │                                     │  │
│  │  └─────────────┘                                     │  │
│  └──────────────────────────────────────────────────────┘  │
│                         │                                    │
│         ┌───────────────┼────────────────┐                   │
│    ┌────▼───┐     ┌────▼────┐     ┌────▼───┐               │
│    │Slack Bot│     │Teams Bot│     │ Web UI │               │
│    └────────┘     └─────────┘     └────────┘               │
└──────────────────────────────────────────────────────────────┘
```

### Technology Stack

| Component | Technology | Notes |
|-----------|-----------|-------|
| **Search** | Azure AI Search | Hybrid (keyword + vector), security trimming built-in |
| **Embedding** | Azure OpenAI text-embedding-3-large | Managed, no GPU needed |
| **LLM** | Azure OpenAI GPT-4o | Managed, pay-per-token |
| **Storage** | Azure Blob Storage + Azure SQL | Managed, scalable |
| **Identity** | Entra ID | Native security group trimming |
| **Governance** | Microsoft Purview | Sensitivity labels, compliance |
| **Deployment** | Azure App Service (simple) or AKS (scale) | PaaS or K8s |
| **Monitoring** | Azure Monitor + Application Insights | Integrated |

### Azure Cost Estimates

| Component | Approx. Monthly Cost | Notes |
|-----------|---------------------|-------|
| Azure AI Search (S1) | $250 – $750 | Depends on index size |
| Azure OpenAI (GPT-4o) | $200 – $2,000 | Depends on query volume |
| Azure OpenAI (Embeddings) | $50 – $300 | One-time bulk + incremental |
| App Service (B2) | $50 – $200 | Or AKS for scale |
| Azure SQL (Basic) | $5 – $50 | Metadata + ACLs |
| Blob Storage | $5 – $50 | Original documents |
| **Total Platform** | **~$560 – $3,350/mo** | Before your license fee |

---

## Mode Comparison

| Dimension | Mode A (Local-Only) | Mode B (Azure-Native) |
|-----------|--------------------|-----------------------|
| **Data residency** | 100% on-prem | Azure region |
| **Setup complexity** | Higher (GPU, infra) | Lower (managed services) |
| **Time to deploy** | 2–4 weeks | 1–2 weeks |
| **LLM quality** | Good (Llama/Mistral) | Best (GPT-4o) |
| **Embedding quality** | Good (bge/Nomic) | Best (text-embedding-3) |
| **ACL enforcement** | Qdrant payload filter | Azure Search sec trimming |
| **Governance** | Custom | Purview labels |
| **Ops burden** | Customer or you | Azure managed |
| **Cost structure** | CapEx (hardware) + license | OpEx (Azure) + license |
| **Best for** | Finance, defense, legal | Tech, services, healthcare SaaS |

---

## Customer Decision Flow

```
Does data MUST stay on-prem / air-gapped?
├── YES → Mode A (Local-Only)
│         └── Does IT want Azure-managed control plane?
│             ├── YES → Mode A + Azure Arc
│             └── NO  → Mode A standalone
│
└── NO  → Is the customer already on Azure + M365?
          ├── YES → Mode B (Azure-Native)
          │         └── Is governance/Purview needed?
          │             ├── YES → Mode B + Purview labels
          │             └── NO  → Mode B standard
          │
          └── NO  → Mode A (default to local, 
                     even if not air-gapped,
                     for simplicity)
```

---

## MCP Integration Layer (Both Modes)

Regardless of deployment mode, expose the appliance as MCP tools:

```typescript
// MCP Tool Definitions
tools: [
  {
    name: "search",
    description: "Search company knowledge base with ACL enforcement",
    parameters: {
      query: string,
      user_context: { user_id: string, groups: string[] },
      filters?: { source?: string, date_range?: DateRange }
    },
    returns: { results: SearchResult[], total: number }
  },
  {
    name: "get_document",
    description: "Retrieve a specific document by ID (ACL-checked)",
    parameters: { doc_id: string, user_context: UserContext },
    returns: { content: string, metadata: DocMetadata }
  },
  {
    name: "get_snippet",
    description: "Retrieve a specific chunk/snippet with citation",
    parameters: { chunk_id: string, user_context: UserContext },
    returns: { text: string, source_url: string, citation: Citation }
  }
]
```

This makes the appliance usable by Claude, ChatGPT, or any MCP-compatible agent as a tool — without replacing the core search/retrieval product.
