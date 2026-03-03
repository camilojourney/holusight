# Market Opportunity — Enterprise Knowledge Appliance

## Market Size (2025)

| Segment | Size | CAGR |
|---------|------|------|
| AI-Driven Knowledge Management | $7.7B – $9.6B | ~47% |
| Enterprise AI Search | ~$7B | ~21% |
| RAG Market | $1.5B – $2B | ~35% |
| On-Premise KM (60% of total) | ~$4.6B – $5.8B | Fastest-growing |
| AI Consulting | ~$11B | Strong |

On-premise holds **60%+ revenue share** of the AI knowledge management market.

---

## Why Now

### 1. Microsoft 365 Copilot Is Disappointing Enterprises

- Low accuracy on real business tasks (accounting, legal drafting)
- **Data governance failures** — Copilot has surfaced confidential docs to unauthorized users, bypassed DLP policies
- Inconsistent behavior across M365 apps
- Ambiguous ROI at $30/user/month — companies reducing or cancelling licenses
- Limited admin/governance tooling at enterprise scale

### 2. Glean Is Enterprise-Only and Expensive

- $45–50/user/month, minimum $50K–60K annual contract
- No free trials unless 200+ seats
- 7–12% annual price increases
- Paid POCs can cost $70K
- **No offering for sub-500 employee companies**

### 3. 95% of GenAI Investments See Zero Return

- "Brittle workflows" + no contextual learning
- Companies disillusioned with generic AI tools that don't understand their data

### 4. Regulated Industries Have No Good Options

- Finance, healthcare, legal, defense need full data sovereignty
- Can't use cloud-based AI search
- Compliance (GDPR, HIPAA, CMMC) demands on-prem or strict VNet isolation

---

## Competitive Landscape

### Tier 1 — Enterprise Giants

| Company | Focus | Pricing | Key Weakness |
|---------|-------|---------|--------------|
| **Glean** | AI search + assistants | $45–50/user/mo | Too expensive for mid-market |
| **Microsoft Copilot** | M365 AI assistant | $30/user/mo | Security failures, poor accuracy |
| **Moveworks** (→ ServiceNow) | IT service desk AI | Enterprise | Shifting focus post-acquisition |
| **Aisera** | Multi-agent automation | Enterprise | Complex deployment |
| **Coveo** | AI search + recommendations | Enterprise | Developer-heavy |

### Tier 2 — Privacy-First / On-Prem Players

| Company | Focus | Differentiator |
|---------|-------|---------------|
| **Onyx AI** (OSS) | Air-gapped search | Free, self-hosted |
| **LLM.co** | Private internal search | Industry-specific on-prem |
| **AirgapAI** | 100% local AI | Pre-built workflows |
| **Kairntech** | On-prem LLM + ACL | SSO, audit, OSS models |
| **TrueFoundry** | LLM deployment (K8s) | Infrastructure, not end-user |

### The Gap We Own

**Mid-market (100–2,000 employees)** in regulated industries:
- Can't afford Glean ($360K–600K/yr)
- Can't get ROI from Copilot
- Need more support than Onyx (free/OSS, no connectors, no compliance)
- Need real ACL enforcement, not "trust the LLM"

---

## Target Customer Profiles

### Profile A — "Strict Local-Only"

- **Industries**: Financial services, defense, legal
- **Size**: 200–2,000 employees
- **Stack**: On-prem Exchange, file servers, some SharePoint
- **Constraint**: Data cannot leave the network
- **Pain**: Knowledge trapped in email silos, expert departure = knowledge loss
- **Budget**: $50K–200K/year
- **Sell line**: *"Nothing leaves your network."*

### Profile B — "Azure-First"

- **Industries**: Tech, professional services, healthcare SaaS
- **Size**: 100–1,000 employees
- **Stack**: M365 + Azure AD + SharePoint/OneDrive + Teams
- **Constraint**: Cloud OK, but need ACL enforcement + governance
- **Pain**: Copilot unreliable, Glean too expensive
- **Budget**: $30K–150K/year
- **Sell line**: *"Your company's brain, inside your Azure stack."*

### Profile C — "Compliance-Obsessed"

- **Industries**: Healthcare, government contractors
- **Size**: Any
- **Stack**: Mixed cloud + on-prem
- **Constraint**: HIPAA/CMMC/SOC2, audit trails mandatory
- **Pain**: Can't adopt AI without a compliance story
- **Budget**: Higher willingness to pay for compliance
- **Sell line**: *"AI search your compliance team approves."*

---

## Pricing Strategy

### Revenue Streams

| Stream | Model | Price Range |
|--------|-------|-------------|
| Discovery & Assessment | Fixed fee | $10K – $25K |
| Deployment & Integration | Project-based | $25K – $75K |
| Appliance License | Per-user/month | $15 – $30/user/mo |
| Support & Maintenance | Annual retainer | 15–20% of license |
| Custom Connectors | Per connector | $10K – $30K |
| Ongoing Advisory | Monthly retainer | $5K – $15K/mo |

### Competitive Pricing Advantage

- **vs Glean** ($45–50/user): 50–70% cheaper
- **vs Copilot** ($30/user): Actually enforces ACLs and works reliably
- **vs Onyx** (free): Deployment, connectors, support, compliance included
- **vs Custom build**: 6–12 months engineering savings

### Example Deal Sizes

| Customer Size | Annual Contract |
|--------------|----------------|
| 100 employees | $30K – $60K |
| 500 employees | $100K – $200K |
| 1,000 employees | $200K – $400K |

---

## Go-To-Market Roadmap

### MVP v1 — "Prove It Works" (Months 1–3)

- Connectors: SharePoint/OneDrive + Google Drive + local folders + PDFs
- Auth: SSO (OIDC)
- Search: Hybrid (vector + BM25) via Qdrant
- Chat: Slack bot with citations
- ACL: Basic document-level from source
- Admin: Connector status + indexing dashboard
- Deploy: Docker Compose on single VM
- **Target**: 1 pilot customer (Azure-native mode)

### v2 — "Enterprise Ready" (Months 4–6)

- Outlook/Exchange email ingestion (Graph delta queries)
- Permission mapping for mailboxes/folders
- Incremental sync + dedup + thread context
- Teams bot
- Audit logging
- Purview label integration
- Search quality metrics in dashboard

### v3 — "Platform" (Months 7–12)

- MCP integration (expose as tools for Claude/agents)
- Tool actions with approvals (create ticket, draft email)
- Multi-tenant
- Azure Arc deployment for managed on-prem
- SOC 2 Type II / HIPAA BAA certifications
- Web UI for search/chat

---

## Engagement Deliverables (What the Customer Gets)

### Per-Customer Delivery Phases

| Phase | Deliverable | What It Is |
|-------|------------|------------|
| **Discovery** | Assessment report | Data sources audit, permission model map, deployment mode recommendation (Mode A or B) |
| **Setup** | Deployed appliance | Working system (Docker/Azure) connected to their data sources (SharePoint, email, drives) |
| **Configuration** | Security + identity | SSO integration, ACL mapping, initial full index built, pilot user testing |
| **Launch** | Live product | Slack bot active, admin dashboard live, user training session delivered |
| **Ongoing** | Monthly support | Connector monitoring, index health reports, quarterly business reviews |

### What the Customer Physically Receives

- ✅ A working Slack bot that answers company questions with citations
- ✅ An admin dashboard showing connector health, index freshness, and search metrics
- ✅ SSO login so only authorized users see authorized documents
- ✅ Incremental sync — new emails and docs become searchable automatically
- ✅ Audit logs for compliance reporting (who searched what, which sources returned)

---

## Deployment Timeline (Per Customer)

| Company Size | Mode B (Azure) | Mode A (Local) | Why Local Is Slower |
|-------------|----------------|----------------|---------------------|
| 100 employees | **4–6 weeks** | 6–8 weeks | Hardware procurement + GPU setup |
| 500 employees | **6–8 weeks** | 8–12 weeks | More connectors, more complex ACLs |
| 1,000+ employees | **8–12 weeks** | 12–16 weeks | Multi-department, custom connectors, HA setup |

### Week-by-Week Breakdown (Typical 500-Employee, Mode B)

| Week | Activity |
|------|----------|
| 1–2 | Discovery: audit data sources, map permissions, choose deployment mode |
| 3–4 | Setup: provision Azure resources, deploy services, connect first data source |
| 5–6 | Integration: connect remaining sources, configure SSO, build initial index |
| 7 | Testing: pilot with 10–20 users, validate ACL enforcement, tune search quality |
| 8 | Launch: roll out to all users, deliver admin training, go live |

---

## Sales Readiness — What You Need to Land Client #1

### Minimum Viable Sales Kit

| Asset | Purpose | Status |
|-------|---------|--------|
| **1-page pitch deck** | Explain the problem + your solution in 5 minutes | Needed |
| **Live demo** | Show a working Slack bot answering questions from realistic company data | Needed (MVP) |
| **Pricing sheet** | Simple table: what they get, what it costs | ✅ Done (`money-model.md`) |
| **Architecture diagram** | Show the IT team it's real and secure | ✅ Done (`deployment-modes.md`) |
| **ACL story** | "We enforce permissions end-to-end, Copilot doesn't" — wins the CISO | ✅ Done (`acl-enforcement.md`) |
| **1 reference customer or pilot** | Social proof — even a free pilot counts | Needed |

### Fastest Path to a Working Demo (1–2 Weeks)

1. Set up a Qdrant instance + small embedding model locally
2. Index 50–100 sample PDFs/docs (public knowledge base content works)
3. Build a simple Slack bot that queries and responds with citations
4. Record a 3-minute walkthrough video

This demo is your #1 sales weapon. Everything else is documentation.

### Who to Talk To First

| Role | Why | What They Care About |
|------|-----|---------------------|
| **IT Director / CTO** | Decision-maker for infrastructure | Security, deployment model, ops burden |
| **CISO / Compliance** | Gatekeeper — can block or champion | ACLs, audit logs, data residency, certifications |
| **CEO / COO** | Budget authority | ROI, time-to-value, competitive advantage |
| **Knowledge Manager / Ops Lead** | Power user, internal champion | Search quality, coverage, daily usefulness |

### Ideal First Customer Profile

- 200–500 employees
- On M365 + Azure AD (Mode B = fastest deployment)
- In financial services, legal, or professional services
- Has experienced knowledge loss from employee turnover
- Has budget authority who understands AI value

---

## How Pricing Was Derived

### Infrastructure Costs (Researched Market Prices)

| Component | Source | Price |
|-----------|--------|-------|
| NVIDIA A100 80GB GPU | Industry pricing (2025–2026) | $10K–15K per unit |
| NVIDIA H100 SXM5 GPU | Industry pricing (2025–2026) | $25K–40K per unit |
| Full 4x A100 server system | Dell, Supermicro, Lambda estimates | $100K–150K |
| Azure AI Search (S1 tier) | Microsoft published pricing | ~$245/mo per search unit |
| Azure OpenAI GPT-4o | Microsoft published pricing | $2.50 input / $10 output per 1M tokens |
| Azure OpenAI GPT-4o-mini | Microsoft published pricing | $0.15 input / $0.60 output per 1M tokens |
| Azure OpenAI Embeddings (Ada) | Microsoft published pricing | $0.10 per 1K tokens |
| Azure App Service (Linux B2) | Microsoft published pricing | ~$26/mo |
| DevOps engineer (US) | ZipRecruiter, Indeed (2025) | $120K–200K/yr full-time |
| Data center power + cooling | Industry standard | $500–2,000/mo per rack |

### License Fee Basis ($15–30/user/mo)

- **Floor**: Must cover your support + margin costs (at least $15/user)
- **Ceiling**: Must undercut Glean ($45–50) by 50%+ to win deals
- **Anchor**: Microsoft Copilot at $30/user — you match or beat with better ACLs
- **Scale**: Price increases slightly per-user for larger tiers (more value, more complexity)

### Deployment Fee Basis ($15K–100K)

- Based on AI consulting market rates: $150–300/hr × 2–4 week engagement
- Entry deployment (100 employees, Mode B): ~100 hours × $150/hr = $15K
- Complex deployment (2,000 employees, Mode A): ~400 hours × $250/hr = $100K
