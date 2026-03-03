# Spec: Financial Model — Mode A vs Mode B by Company Size

## How to Read This Document

This spec compares the **total cost of ownership (TCO)** for both deployment modes across four company sizes. For each, it breaks down:

1. **Upfront investment** — what the company pays before day one
2. **Monthly ongoing costs** — infrastructure + operations
3. **Your revenue** — what you charge them (consulting + license)
4. **Annual comparison** — full year 1 cost vs. year 2+

All prices are USD estimates as of early 2026. Hardware prices fluctuate; Azure prices are pay-as-you-go unless noted.

---

## Quick Reference — Cost Drivers

### Mode A (Local-Only) Cost Drivers

| Component | Cost Range | Notes |
|-----------|-----------|-------|
| GPU server (A100 80GB) | $10K–15K per GPU | Needed for local LLM inference |
| GPU server (H100 SXM5) | $25K–40K per GPU | Higher performance, future-proof |
| Full server system (4x A100) | $100K–150K | Includes CPU, RAM, storage, networking |
| Full server system (8x A100) | $200K–250K | For large deployments |
| Server (CPU-only, no GPU) | $8K–25K | For embedding + vector DB only (small models) |
| Qdrant (self-hosted) | $0 (OSS) | Infrastructure cost only |
| PostgreSQL | $0 (OSS) | Infrastructure cost only |
| MinIO | $0 (OSS) | Infrastructure cost only |
| Power + cooling | $500–2,000/mo | Per rack, depends on data center |
| DevOps engineer (part-time) | $60K–80K/yr (0.5 FTE) | Maintain appliance, updates, monitoring |
| DevOps engineer (full-time) | $140K–200K/yr | Dedicated for large deployments |

### Mode B (Azure-Native) Cost Drivers

| Component | Cost Range | Notes |
|-----------|-----------|-------|
| Azure AI Search (S1) | ~$245/mo per SU | 160 GB storage, 50 indexes |
| Azure AI Search (S2) | ~$981/mo per SU | 512 GB storage, more capacity |
| Azure OpenAI GPT-4o (input) | $2.50/1M tokens | Standard on-demand |
| Azure OpenAI GPT-4o (output) | $10/1M tokens | Standard on-demand |
| Azure OpenAI GPT-4o-mini (input) | $0.15/1M tokens | Cost-efficient alternative |
| Azure OpenAI Embeddings (Ada) | $0.10/1K tokens | One-time bulk + incremental |
| App Service (Linux B2) | ~$26/mo | 2 vCPU, 3.5 GB RAM |
| App Service (Linux B3) | ~$51/mo | 4 vCPU, 7 GB RAM |
| App Service (P1v3) | ~$138/mo | Production tier |
| AKS control plane (Standard) | ~$73/mo | With SLA |
| AKS worker nodes | $50–500/mo | Depends on VM size and count |
| Azure SQL (Basic) | $5–50/mo | Metadata + ACLs |
| Azure Blob Storage | $5–50/mo | Original documents |

---

## Tier 1 — Small Company (100 employees, ~50K documents)

### Mode A: Local-Only

#### Upfront Investment

| Item | Cost | Notes |
|------|------|-------|
| Server hardware (CPU-only) | $12,000 | No GPU — use quantized models (4-bit Llama 8B) |
| OR Server with 1x A100 | $35,000 | For full 70B model inference |
| Storage (2 TB NVMe) | $400 | Included in server usually |
| Network switch / cabling | $500 | |
| Rack space setup | $1,000 | If using existing server room |
| **Your deployment fee** | **$25,000** | Setup, connector config, SSO, testing |
| **Total upfront (CPU path)** | **$38,900** | |
| **Total upfront (GPU path)** | **$61,900** | |

#### Monthly Ongoing

| Item | Cost/mo | Notes |
|------|---------|-------|
| Power + cooling | $300 | Single server |
| Software updates / patches | $0 | OSS stack |
| **Your license fee** | **$1,500** | 100 users × $15/user/mo |
| **Your support** | **$300** | 20% of license |
| Part-time sysadmin (0.1 FTE) | $1,200 | Usually existing IT staff |
| **Total monthly** | **$3,300** | |

#### Annual Summary

| | Year 1 | Year 2+ |
|-|--------|---------|
| Upfront | $38,900 – $61,900 | $0 |
| Ongoing (12 mo) | $39,600 | $39,600 |
| **Total** | **$78,500 – $101,500** | **$39,600** |

---

### Mode B: Azure-Native

#### Upfront Investment

| Item | Cost | Notes |
|------|------|-------|
| Hardware | $0 | All cloud |
| **Your deployment fee** | **$15,000** | Faster setup — managed services |
| **Total upfront** | **$15,000** | |

#### Monthly Ongoing

| Item | Cost/mo | Notes |
|------|---------|-------|
| Azure AI Search (S1, 1 SU) | $245 | 50K docs fits easily |
| Azure OpenAI (GPT-4o-mini) | $50 | ~100 queries/day, short responses |
| Azure OpenAI (Embeddings) | $30 | Incremental only after initial bulk |
| App Service (Linux B2) | $26 | API + bot |
| Azure SQL (Basic) | $15 | Metadata |
| Blob Storage | $5 | Docs |
| **Your license fee** | **$2,000** | 100 users × $20/user/mo |
| **Your support** | **$400** | 20% of license |
| **Total monthly** | **$2,771** | |

#### Annual Summary

| | Year 1 | Year 2+ |
|-|--------|---------|
| Upfront | $15,000 | $0 |
| Ongoing (12 mo) | $33,252 | $33,252 |
| **Total** | **$48,252** | **$33,252** |

### Tier 1 Verdict

| | Mode A (Local) | Mode B (Azure) | Winner |
|-|----------------|----------------|--------|
| **Upfront** | $38K – $62K | $15K | ✅ Mode B |
| **Monthly** | $3,300 | $2,771 | ✅ Mode B |
| **Year 1 total** | $78K – $102K | $48K | ✅ Mode B |
| **Year 2+** | $40K | $33K | ✅ Mode B |
| **Data stays local** | ✅ Yes | ❌ No | ✅ Mode A |
| **Best for** | Regulated / air-gapped | Everyone else | Depends on policy |

> [!IMPORTANT]
> For 100 employees, **Mode B is almost always the right answer** unless the company has a strict "no cloud" policy. The upfront cost difference alone ($15K vs $62K) is decisive for small companies.

---

## Tier 2 — Mid-Size Company (500 employees, ~250K documents)

### Mode A: Local-Only

#### Upfront Investment

| Item | Cost | Notes |
|------|------|-------|
| Server with 2x A100 80GB | $55,000 | Handles 70B model + embeddings |
| Additional storage server | $5,000 | For document store + backups |
| Network infrastructure | $2,000 | |
| Rack space + UPS | $3,000 | |
| **Your deployment fee** | **$50,000** | More connectors, more complex ACLs |
| **Total upfront** | **$115,000** | |

#### Monthly Ongoing

| Item | Cost/mo | Notes |
|------|---------|-------|
| Power + cooling | $800 | Two servers |
| Hardware warranty / parts | $400 | Annual divided monthly |
| **Your license fee** | **$10,000** | 500 users × $20/user/mo |
| **Your support** | **$2,000** | 20% of license |
| Part-time DevOps (0.25 FTE) | $3,500 | Existing IT or fractional hire |
| **Total monthly** | **$16,700** | |

#### Annual Summary

| | Year 1 | Year 2+ |
|-|--------|---------|
| Upfront | $115,000 | $0 |
| Ongoing (12 mo) | $200,400 | $200,400 |
| **Total** | **$315,400** | **$200,400** |

---

### Mode B: Azure-Native

#### Upfront Investment

| Item | Cost | Notes |
|------|------|-------|
| Hardware | $0 | |
| **Your deployment fee** | **$35,000** | More connectors, Purview integration |
| **Total upfront** | **$35,000** | |

#### Monthly Ongoing

| Item | Cost/mo | Notes |
|------|---------|-------|
| Azure AI Search (S1, 2 SU) | $490 | 250K docs, 2 replicas for HA |
| Azure OpenAI (GPT-4o) | $400 | ~500 queries/day |
| Azure OpenAI (Embeddings) | $100 | Incremental sync |
| App Service (P1v3) | $138 | Production tier |
| Azure SQL (Standard) | $75 | |
| Blob Storage | $25 | |
| **Your license fee** | **$12,500** | 500 users × $25/user/mo |
| **Your support** | **$2,500** | 20% of license |
| **Total monthly** | **$16,228** | |

#### Annual Summary

| | Year 1 | Year 2+ |
|-|--------|---------|
| Upfront | $35,000 | $0 |
| Ongoing (12 mo) | $194,736 | $194,736 |
| **Total** | **$229,736** | **$194,736** |

### Tier 2 Verdict

| | Mode A (Local) | Mode B (Azure) | Winner |
|-|----------------|----------------|--------|
| **Upfront** | $115K | $35K | ✅ Mode B |
| **Monthly** | $16,700 | $16,228 | ≈ Tie |
| **Year 1 total** | $315K | $230K | ✅ Mode B |
| **Year 2+** | $200K | $195K | ≈ Tie |
| **Break-even (Mode A cheaper)** | — | — | ~Never (roughly equal ongoing) |
| **Data stays local** | ✅ Yes | ❌ No | ✅ Mode A |

> [!TIP]
> At 500 employees, the **monthly costs converge**. Mode A's upfront hardware is the main differentiator. If the company has strong regulatory reasons for local-only, Mode A is justified. Otherwise, Mode B still wins on simplicity.

---

## Tier 3 — Large Company (1,000 employees, ~500K documents)

### Mode A: Local-Only

#### Upfront Investment

| Item | Cost | Notes |
|------|------|-------|
| Server with 4x A100 80GB | $120,000 | Handle concurrent inference + heavy batches |
| Storage cluster (redundant) | $15,000 | PostgreSQL + Qdrant + MinIO |
| Network + monitoring infra | $5,000 | |
| Rack space + redundant power | $5,000 | |
| **Your deployment fee** | **$75,000** | Full enterprise deployment, multi-source |
| **Total upfront** | **$220,000** | |

#### Monthly Ongoing

| Item | Cost/mo | Notes |
|------|---------|-------|
| Power + cooling | $1,500 | Multiple servers |
| Hardware warranty / spares | $800 | |
| **Your license fee** | **$25,000** | 1,000 users × $25/user/mo |
| **Your support** | **$5,000** | 20% of license |
| Dedicated DevOps (0.5 FTE) | $7,000 | Shared with other IT duties |
| **Total monthly** | **$39,300** | |

#### Annual Summary

| | Year 1 | Year 2+ | Year 3+ |
|-|--------|---------|---------|
| Upfront | $220,000 | $0 | $0 |
| Ongoing (12 mo) | $471,600 | $471,600 | $471,600 |
| Hardware refresh (20% of CapEx) | — | — | $44,000 |
| **Total** | **$691,600** | **$471,600** | **$515,600** |

---

### Mode B: Azure-Native

#### Upfront Investment

| Item | Cost | Notes |
|------|------|-------|
| Hardware | $0 | |
| **Your deployment fee** | **$50,000** | |
| **Total upfront** | **$50,000** | |

#### Monthly Ongoing

| Item | Cost/mo | Notes |
|------|---------|-------|
| Azure AI Search (S1, 3 SU) | $735 | 500K docs, 3 replicas |
| Azure OpenAI (GPT-4o) | $1,200 | ~1,000 queries/day |
| Azure OpenAI (Embeddings) | $200 | |
| AKS Standard (control) | $73 | |
| AKS worker nodes (3x D4s_v3) | $450 | |
| Azure SQL (Standard S2) | $150 | |
| Blob Storage | $50 | |
| **Your license fee** | **$27,500** | 1,000 users × $27.50/user/mo |
| **Your support** | **$5,500** | 20% of license |
| **Total monthly** | **$35,858** | |

#### Annual Summary

| | Year 1 | Year 2+ |
|-|--------|---------|
| Upfront | $50,000 | $0 |
| Ongoing (12 mo) | $430,296 | $430,296 |
| **Total** | **$480,296** | **$430,296** |

### Tier 3 Verdict

| | Mode A (Local) | Mode B (Azure) | Winner |
|-|----------------|----------------|--------|
| **Upfront** | $220K | $50K | ✅ Mode B |
| **Monthly** | $39,300 | $35,858 | ✅ Mode B (slightly) |
| **Year 1 total** | $692K | $480K | ✅ Mode B |
| **Year 2+** | $472K | $430K | ✅ Mode B |
| **Year 3+ (w/ refresh)** | $516K | $430K | ✅ Mode B |

> [!NOTE]
> Mode A starts to become competitive ongoing at this scale, but the **$170K upfront gap** and **hardware refresh costs** in year 3+ keep Mode B ahead financially. Mode A wins only when compliance mandates it.

---

## Tier 4 — Enterprise (2,000+ employees, ~1M+ documents)

### Mode A: Local-Only

#### Upfront Investment

| Item | Cost | Notes |
|------|------|-------|
| Server cluster (8x A100 system) | $250,000 | DGX-level or equivalent |
| Redundant server (failover) | $80,000 | HA requirement |
| Storage cluster (HA) | $30,000 | |
| Network fabric (25GbE+) | $15,000 | |
| Data center prep (rack, UPS, cooling) | $20,000 | |
| **Your deployment fee** | **$100,000** | Full enterprise, multi-department, custom connectors |
| **Total upfront** | **$495,000** | |

#### Monthly Ongoing

| Item | Cost/mo | Notes |
|------|---------|-------|
| Power + cooling | $3,000 | Multi-rack |
| Hardware warranty / spares | $2,000 | |
| **Your license fee** | **$50,000** | 2,000 users × $25/user/mo |
| **Your support** | **$10,000** | 20% of license |
| Dedicated DevOps (1 FTE) | $14,000 | Full-time, dedicated to appliance |
| Security audit (amortized) | $2,000 | Annual pen test / compliance |
| **Total monthly** | **$81,000** | |

#### Annual Summary

| | Year 1 | Year 2+ | Year 3+ |
|-|--------|---------|---------|
| Upfront | $495,000 | $0 | $0 |
| Ongoing (12 mo) | $972,000 | $972,000 | $972,000 |
| Hardware refresh | — | — | $99,000 |
| **Total** | **$1,467,000** | **$972,000** | **$1,071,000** |

---

### Mode B: Azure-Native

#### Upfront Investment

| Item | Cost | Notes |
|------|------|-------|
| Hardware | $0 | |
| **Your deployment fee** | **$75,000** | |
| **Total upfront** | **$75,000** | |

#### Monthly Ongoing

| Item | Cost/mo | Notes |
|------|---------|-------|
| Azure AI Search (S2, 2 SU) | $1,962 | 1M+ docs, high throughput |
| Azure OpenAI (GPT-4o) | $3,000 | ~2,000+ queries/day |
| Azure OpenAI (Embeddings) | $500 | |
| AKS Standard (control) | $73 | |
| AKS worker nodes (6x D4s_v3) | $900 | |
| Azure SQL (Standard S3) | $300 | |
| Blob Storage | $100 | |
| Azure Monitor + Insights | $200 | |
| **Your license fee** | **$55,000** | 2,000 users × $27.50/user/mo |
| **Your support** | **$11,000** | 20% of license |
| **Total monthly** | **$73,035** | |

#### Annual Summary

| | Year 1 | Year 2+ |
|-|--------|---------|
| Upfront | $75,000 | $0 |
| Ongoing (12 mo) | $876,420 | $876,420 |
| **Total** | **$951,420** | **$876,420** |

### Tier 4 Verdict

| | Mode A (Local) | Mode B (Azure) | Winner |
|-|----------------|----------------|--------|
| **Upfront** | $495K | $75K | ✅ Mode B |
| **Monthly** | $81,000 | $73,035 | ✅ Mode B |
| **Year 1 total** | $1.47M | $951K | ✅ Mode B |
| **Year 2+** | $972K | $876K | ✅ Mode B |
| **5-year TCO** | ~$5.4M | ~$4.5M | ✅ Mode B |
| **Data sovereignty** | ✅ Full | ❌ Azure region | ✅ Mode A |

> [!WARNING]
> At enterprise scale, Mode A only makes financial sense if the company **already has GPU infrastructure** or is mandated by regulation (CMMC, ITAR, SOX strict interpretation). The $420K upfront difference and ongoing DevOps costs make Mode B significantly cheaper.

---

## Grand Comparison — All Tiers

### Year 1 Total Cost (Company Pays)

| Company Size | Mode A (Local) | Mode B (Azure) | Savings with Mode B |
|-------------|----------------|----------------|---------------------|
| 100 employees | $78K – $102K | $48K | **$30K – $54K (38–53%)** |
| 500 employees | $315K | $230K | **$85K (27%)** |
| 1,000 employees | $692K | $480K | **$212K (31%)** |
| 2,000 employees | $1.47M | $951K | **$516K (35%)** |

### Year 2+ Annual Cost (Company Pays)

| Company Size | Mode A (Local) | Mode B (Azure) | Savings with Mode B |
|-------------|----------------|----------------|---------------------|
| 100 employees | $40K | $33K | **$7K (17%)** |
| 500 employees | $200K | $195K | **$5K (3%)** |
| 1,000 employees | $472K | $430K | **$42K (9%)** |
| 2,000 employees | $972K | $876K | **$96K (10%)** |

### Your Revenue (What You Earn)

| Company Size | Deployment Fee | Monthly License + Support | Annual Recurring Revenue |
|-------------|---------------|--------------------------|-------------------------|
| 100 employees | $15K – $25K | $1,800 – $2,400 | **$21,600 – $28,800** |
| 500 employees | $35K – $50K | $12,500 – $15,000 | **$150,000 – $180,000** |
| 1,000 employees | $50K – $75K | $30,500 – $33,000 | **$366,000 – $396,000** |
| 2,000 employees | $75K – $100K | $60,000 – $66,000 | **$720,000 – $792,000** |

---

## When Mode A Beats Mode B (Decision Framework)

Mode A is only the better financial choice when:

| Condition | Why It Tips to Mode A |
|-----------|----------------------|
| Company already owns GPU servers | Eliminates $100K–250K upfront |
| Regulation requires air-gap | No choice — Mode A mandatory |
| Query volume is extremely high (10K+/day) | Azure OpenAI costs scale linearly; local LLM is fixed cost |
| Multi-year commitment (5+ years) | Hardware amortizes; cloud costs compound |
| Company has existing DevOps team | No incremental staffing cost |

### Break-Even Analysis: When Local Becomes Cheaper

For a 500-employee company, Mode A ongoing ($16,700/mo) ≈ Mode B ongoing ($16,228/mo). But Mode A has $80K more upfront.

```
Break-even = $80,000 ÷ ($16,228 - $16,700)/mo
           = $80,000 ÷ (-$472)/mo
           = NEVER (Mode A is slightly MORE expensive monthly)
```

For 1,000 employees with very high query volume (5K+ queries/day):

```
Azure OpenAI cost jumps to ~$4,000/mo (from $1,200)
Mode B monthly becomes ~$38,658
Mode A monthly stays at $39,300

Still roughly equal. Break-even on upfront: $170K ÷ $642/mo = ~265 months = never practical.
```

> [!CAUTION]
> **Mode A almost never wins on pure cost.** It wins on **compliance, sovereignty, and policy**. Price your Mode A deployments with a premium — the customer is buying security posture, not cost savings.

---

## Pricing Recommendations by Tier

| Tier | License Price | Deployment Fee | Total Year 1 Revenue | Gross Margin Target |
|------|--------------|----------------|----------------------|---------------------|
| 100 employees | $15–20/user/mo | $15–25K | $33K – $49K | 60–70% |
| 500 employees | $20–25/user/mo | $35–50K | $155K – $200K | 65–75% |
| 1,000 employees | $25–27.50/user/mo | $50–75K | $350K – $405K | 70–80% |
| 2,000+ employees | $25–30/user/mo | $75–100K | $675K – $820K | 75–85% |

> [!TIP]
> **Margin improves with scale** because your per-customer support cost doesn't scale linearly. A 2,000-employee customer doesn't require 20x the support of a 100-employee customer.
