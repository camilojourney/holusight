# Market — Enterprise Knowledge Appliance

**Last updated:** 2026-02

---

## The Problem

Enterprise knowledge is trapped in email threads, SharePoint folders, shared drives, and chat histories. Employees spend 9+ hours/week searching for information. When experts leave, their knowledge disappears. Existing solutions either don't enforce access controls properly (Microsoft Copilot), are too expensive for mid-market (Glean: $45–50/user/mo), or require too much technical expertise (open-source RAG tools).

## Why Now

1. **Microsoft 365 Copilot is disappointing enterprises.** Low accuracy on real business tasks, data governance failures (surfacing confidential docs to unauthorized users), ambiguous ROI at $30/user/month. Companies are reducing or cancelling licenses.
2. **Glean is enterprise-only and expensive.** $45–50/user/month, minimum $50K–60K annual contract, no free trials under 200 seats, 7–12% annual price increases.
3. **95% of GenAI investments see zero return.** "Brittle workflows" with no contextual learning. Companies are disillusioned with generic AI that doesn't understand their data.
4. **Regulated industries have no good options.** Finance, healthcare, legal, defense need full data sovereignty. Can't use cloud-based AI search. Compliance (GDPR, HIPAA, CMMC) demands on-prem or strict VNet isolation.
5. **On-premise holds 60%+ revenue share** of the AI knowledge management market — and it's the fastest-growing segment.

## Category

AI-powered enterprise knowledge search with ACL enforcement. Two deployment modes: Mode A (strict local-only, nothing leaves the network) and Mode B (Azure-native, fastest deployment).

## Target Customer

### Profile A — "Strict Local-Only"
- **Industries:** Financial services, defense, legal
- **Size:** 200–2,000 employees
- **Constraint:** Data cannot leave the network
- **Pain:** Knowledge trapped in email silos, expert departure = knowledge loss
- **Budget:** $50K–200K/year
- **Sell line:** *"Nothing leaves your network."*

### Profile B — "Azure-First"
- **Industries:** Tech, professional services, healthcare SaaS
- **Size:** 100–1,000 employees
- **Constraint:** Cloud OK, but need ACL enforcement + governance
- **Pain:** Copilot unreliable, Glean too expensive
- **Budget:** $30K–150K/year
- **Sell line:** *"Your company's brain, inside your Azure stack."*

### Profile C — "Compliance-Obsessed"
- **Industries:** Healthcare, government contractors
- **Constraint:** HIPAA/CMMC/SOC2, audit trails mandatory
- **Pain:** Can't adopt AI without a compliance story
- **Sell line:** *"AI search your compliance team approves."*

## Competitive Landscape

### Tier 1 — Enterprise Giants

| Company | Pricing | Key Weakness |
|---------|---------|--------------|
| **Glean** | $45–50/user/mo | Too expensive for mid-market |
| **Microsoft Copilot** | $30/user/mo | Security failures, poor accuracy |
| **Moveworks** (→ ServiceNow) | Enterprise | Shifting focus post-acquisition |
| **Aisera** | Enterprise | Complex deployment |
| **Coveo** | Enterprise | Developer-heavy |

### Tier 2 — Privacy-First / On-Prem

| Company | Differentiator |
|---------|---------------|
| **Onyx AI** (OSS) | Free, self-hosted. No connectors, no compliance |
| **LLM.co** | Industry-specific on-prem |
| **AirgapAI** | 100% local AI, pre-built workflows |
| **Kairntech** | On-prem LLM + ACL, SSO, audit, OSS models |

### The Gap We Own

Mid-market (100–2,000 employees) in regulated industries: can't afford Glean ($360K–600K/yr), can't get ROI from Copilot, need more support than Onyx (free/OSS), need real ACL enforcement.

## Market Size

| Segment | Size | CAGR |
|---------|------|------|
| AI-Driven Knowledge Management | $7.7B – $9.6B | ~47% |
| Enterprise AI Search | ~$7B | ~21% |
| RAG Market | $1.5B – $2B | ~35% |
| On-Premise KM (60% of total) | ~$4.6B – $5.8B | Fastest-growing |

## Business Model

### Revenue Streams

| Stream | Model | Price Range |
|--------|-------|-------------|
| Discovery & Assessment | Fixed fee | $10K – $25K |
| Deployment & Integration | Project-based | $25K – $75K |
| Appliance License | Per-user/month | $15 – $30/user/mo |
| Support & Maintenance | Annual retainer | 15–20% of license |
| Custom Connectors | Per connector | $10K – $30K |

### Pricing Advantage

- **vs Glean** ($45–50/user): 50–70% cheaper
- **vs Copilot** ($30/user): Actually enforces ACLs and works reliably
- **vs Onyx** (free): Deployment, connectors, support, compliance included

### Deal Sizes

| Customer Size | Annual Contract |
|--------------|----------------|
| 100 employees | $30K – $60K |
| 500 employees | $100K – $200K |
| 1,000 employees | $200K – $400K |

## Growth Strategy

### Phase 1 — "Prove It Works" (Months 1–3)
- SharePoint/OneDrive + Google Drive connectors, Slack bot, basic ACL, Docker deploy
- Target: 1 pilot customer (Azure-native mode)
- Build working demo (Qdrant + embedding model + Slack bot with citations)

### Phase 2 — "Enterprise Ready" (Months 4–6)
- Email ingestion, incremental sync, audit logging, Teams bot, Purview labels

### Phase 3 — "Platform" (Months 7–12)
- MCP integration, tool actions with approvals, multi-tenant, SOC 2 Type II / HIPAA BAA

## Moats

1. **ACL enforcement as the foundation.** Most competitors treat access control as an afterthought. We build it first. Hardest part — most defensible.
2. **Two deployment modes from day one.** Mode A captures regulated industries that can't use cloud AI. Mode B captures fast-moving companies. One product, two markets.
3. **Mid-market specialization.** 100–500 employee companies are underserved. Too big for consumer tools, too price-sensitive for Glean.

## Kill Criteria

- No pilot customer interest after 3 months of outreach
- Unable to build working ACL enforcement that passes CISO review
- Microsoft Copilot fixes its permission enforcement (eliminates core differentiation)
