# Spec: Go-To-Market — Where to Sell, Who to Sell To, and How

## The MVP (What You Ship First)

### What It Does

A conversational AI assistant that searches a company's documents and answers questions with citations, enforcing access controls.

### MVP Scope — Ship in 8 Weeks

| Component | What's Included | What's NOT Included (v2) |
|-----------|----------------|--------------------------|
| **Connectors** | SharePoint/OneDrive (via Graph API), Google Drive, local file upload (PDF, DOCX) | Outlook email, Teams messages, Confluence |
| **Search** | Hybrid vector + keyword search with ACL filtering | Advanced semantic chunking, entity extraction |
| **Chat interface** | Slack bot with citations and source links | Teams bot, Web UI |
| **Auth** | SSO via Azure AD (OIDC) | SAML, Okta, Google Workspace |
| **ACL** | Document-level permissions synced from source | Folder-level inheritance, sensitivity labels |
| **Admin** | Connector status page, index health, basic logs | Full audit trail, search quality metrics |
| **Deploy** | Docker Compose on a single Azure VM / local server | Kubernetes, multi-node HA, auto-scaling |

### MVP Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **API** | Python (FastAPI) | Fast to build, great LLM ecosystem |
| **Embedding** | Azure OpenAI text-embedding-3-large OR local BAAI/bge-large | Depends on mode |
| **LLM** | Azure OpenAI GPT-4o-mini OR local Llama 3.1 8B | Cost-efficient, fast |
| **Vector DB** | Qdrant (Docker) | Open-source, great filtering, easy self-host |
| **Metadata** | PostgreSQL | ACLs, doc metadata, sync state |
| **Doc store** | MinIO or Azure Blob | Original files |
| **Chat bot** | Slack Bolt SDK (Python) | Simple, well-documented |
| **Auth** | Python OIDC library + Azure AD app registration | Standard enterprise SSO |

### MVP Demo Path (Before You Have a Customer)

| Week | Activity | Deliverable |
|------|----------|------------|
| 1 | Set up Qdrant + FastAPI + embedding pipeline | Working indexing pipeline |
| 2 | Index 100 sample documents, build search API | Search endpoint with ACL filtering |
| 3 | Build Slack bot, connect to search API | Working Slack bot with citations |
| 4 | Add SSO, admin status page, polish | **Demo-ready product** |

**After week 4, you have a live demo you can show to prospects.**

---

## Who You're Selling To (Specific Customer Segments)

### Segment 1 — Financial Services (Primary Target)

**Why them:** Highest pain (compliance + knowledge loss), highest willingness to pay, most regulated (ACL story resonates).

| Attribute | Details |
|-----------|---------|
| **Company size** | 200–2,000 employees |
| **Types** | Asset managers, wealth advisors, regional banks, insurance carriers, credit unions |
| **Buyer** | CTO, IT Director, or Chief Compliance Officer |
| **Pain** | Client knowledge trapped in email, analyst turnover = research loss, compliance fears with cloud AI |
| **Budget** | $50K–200K/year |
| **Pricing** | $25–30/user/mo + $35K–75K deployment |

**Example targets:**
- Regional banks (200–1,000 employees) not served by Glean
- Wealth management firms with internal research teams
- Insurance carriers managing policy documents + claims history
- Hedge fund operational teams (50–300 people)

### Segment 2 — Legal & Professional Services

**Why them:** Document-heavy, confidential data, high hourly rates = budget exists for tools that save time.

| Attribute | Details |
|-----------|---------|
| **Company size** | 100–500 employees |
| **Types** | Law firms, accounting firms, consulting firms (non-Big 4) |
| **Buyer** | Managing Partner, COO, or IT Director |
| **Pain** | Associates spend hours searching for precedents, partner knowledge isn't accessible firm-wide |
| **Budget** | $30K–150K/year |
| **Pricing** | $20–25/user/mo + $25K–50K deployment |

**Example targets:**
- Mid-size law firms (50–200 attorneys)
- Regional accounting firms with document management pain
- Engineering/architecture firms with project archives

### Segment 3 — Healthcare Operations

**Why them:** HIPAA compliance is non-negotiable, strong need for knowledge access, risk-averse (ACL story is critical).

| Attribute | Details |
|-----------|---------|
| **Company size** | 200–1,000 employees |
| **Types** | Hospital systems, specialty clinics, health tech companies |
| **Buyer** | CIO, CISO, or VP of Operations |
| **Pain** | Clinical knowledge scattered across EHR, shared drives, email; compliance blocks generic AI tools |
| **Budget** | $50K–200K/year |
| **Pricing** | $25–30/user/mo + $50K–75K deployment |

---

## Where to Sell (Sales Channels)

### Channel 1 — LinkedIn Outbound (Start Here)

**Why:** 10–25% response rate vs 1–5% for cold email. Direct access to decision-makers. Free to start.

| Step | Action |
|------|--------|
| 1 | Optimize your LinkedIn profile: headline = "I help companies find answers in their own data — without sending it to the cloud" |
| 2 | Use LinkedIn Sales Navigator ($99/mo) to find: CTO/CIO at companies with 200–2,000 employees in financial services, legal |
| 3 | Connect with 20–30 prospects per week with personalized notes referencing their company |
| 4 | Post 2–3x/week: Copilot failures, data governance, ACL enforcement, ROI of knowledge management |
| 5 | When connected, start conversation (don't pitch). Ask about their knowledge management challenges |
| 6 | Offer a **free 30-minute discovery call** to assess their data sources and deployment fit |

**Template connection message:**
> "Hi [Name] — I work with [industry] companies on AI-powered internal search that enforces the same access controls as their existing systems. Seeing a lot of companies struggle with Copilot data governance. Would love to hear how you're thinking about it."

### Channel 2 — Microsoft Partner Network

**Why:** Access to Azure Marketplace (3,000+ AI offerings), co-sell with Microsoft reps, customer Azure commit credits apply to your solution.

| Step | Action |
|------|--------|
| 1 | Enroll in **Microsoft AI Cloud Partner Program** (free) |
| 2 | Build Azure-native deployment to qualify for co-sell |
| 3 | List your solution on Azure Marketplace |
| 4 | Customers can use their existing Azure commit to pay for your service |
| 5 | Microsoft reps get credit for referring customers to partner solutions |

**This is critical for Mode B sales.** Customers with Azure Enterprise Agreements can pay from their existing cloud budget — no new procurement process needed.

### Channel 3 — Industry Events & Communities

**Best events for prospect discovery:**

| Event / Community | Focus | When to Attend |
|-------------------|-------|----------------|
| **AI Banking Leadership Forum** | AI in financial services | Ongoing community |
| **Global CTO Forum** | CTO networking and mentorship | Year-round |
| **Fintech Builders Summit** | Fintech CTOs and developers | Annual |
| **Transformational CIO Financial Services Assembly** | CIO-level, financial services | Annual (March) |
| **Emerging Technology and Generative AI Forum** (Thomson Reuters) | Professional services + AI | Annual (July) |
| **Local CTO Forum** (LA, NYC, etc.) | Private CTO peer groups | Monthly |

**Strategy:** Attend 1–2 events to start. Give a talk about "ACL enforcement in enterprise AI search" or "Why Copilot's data governance is broken." Position yourself as expert, not salesman.

### Channel 4 — Clutch & Toptal (Credibility + Inbound)

| Platform | Use It For | Expected Result |
|----------|-----------|----------------|
| **Clutch.co** | Profile your company as an AI consulting firm with verified reviews | Inbound leads from companies searching "AI consulting" |
| **Toptal** | List yourself as a vetted AI consultant for premium engagements | High-budget clients ($50K+ projects) |
| **Upwork** | NOT recommended for enterprise — too price-sensitive | N/A |

### Channel 5 — Referral Network

**The highest-converting channel.** Every customer you land should generate 2–3 referrals.

| Who to Partner With | Why They Refer You |
|---------------------|-------------------|
| **Microsoft CSPs** (Cloud Solution Providers) | They sell Azure; your product adds value to Azure deals |
| **IT MSPs** (Managed Service Providers) | They manage mid-market IT; your appliance is a new revenue stream for them |
| **Compliance consultants** | They audit companies; your tool solves a gap they identify |
| **ERP / CRM integrators** | They're already inside companies selling tech; your product complements theirs |

---

## Pricing (Final Recommendation)

### License Tiers

| Tier | Users | Price/User/Mo | Includes |
|------|-------|--------------|----------|
| **Starter** | Up to 100 | $20/user | 2 connectors, Slack bot, basic ACLs, email support |
| **Professional** | 100–500 | $25/user | 4 connectors, admin dashboard, audit logs, priority support |
| **Enterprise** | 500+ | $27.50–30/user | Unlimited connectors, custom integrations, dedicated support, SLA |

### Deployment Fees

| Scope | Fee | Includes |
|-------|-----|----------|
| **Quick Start** (100 users, 1–2 sources) | $15K–25K | Setup, SSO, 1 connector, 4-week deployment |
| **Standard** (500 users, 3–4 sources) | $35K–50K | Setup, SSO, multi-connector, ACL mapping, 8-week deployment |
| **Enterprise** (1,000+ users, full scope) | $50K–100K | Everything above + custom connectors, HA, 12-week deployment |

### What the Customer Buys (Simple Pitch)

> "For **$25/user/month** + a one-time setup fee, your team gets an AI assistant that:
> - Searches all your company's documents
> - Only shows results people are authorized to see
> - Gives citations so you can verify answers
> - Works right inside Slack
> - Your data never leaves your network (or your Azure tenant)"

---

## First 90 Days Action Plan

### Month 1: Build the Demo

| Week | Action | Goal |
|------|--------|------|
| 1 | Set up Qdrant + FastAPI + embedding model | Working backend |
| 2 | Build indexing pipeline for PDFs + Google Drive | Searchable document store |
| 3 | Build Slack bot with citations | Live demo |
| 4 | Add SSO stub + admin status page | **Demo-ready product** |

### Month 2: Find Your First Customer

| Week | Action | Goal |
|------|--------|------|
| 5 | Optimize LinkedIn profile, start posting content | Build presence |
| 6 | Connect with 50 prospects (financial services CTOs/CIOs) | Start conversations |
| 7 | Offer 3–5 free discovery calls | Qualify leads |
| 8 | Propose pilot to best-fit prospect (free or discounted) | **Signed pilot** |

### Month 3: Deploy Pilot + Start Pipeline

| Week | Action | Goal |
|------|--------|------|
| 9–10 | Deploy pilot: connect SharePoint, set up SSO, build index | Working system |
| 11 | Pilot users testing, gather feedback, tune search quality | Proven value |
| 12 | Convert pilot to paid contract, ask for referrals | **First paying customer** |

---

## Revenue Projections (Year 1)

| Scenario | Customers | Avg Contract | Year 1 Revenue |
|----------|-----------|-------------|----------------|
| **Conservative** | 2 customers (200 users each) | $75K | **$150K** |
| **Moderate** | 4 customers (300 users avg) | $100K | **$400K** |
| **Aggressive** | 6 customers (400 users avg) | $140K | **$840K** |

The moderate scenario ($400K) requires landing one customer every 3 months — realistic with active LinkedIn outbound + one channel partner referral.

---

## What You Need Before Day One

| Asset | Status | Priority |
|-------|--------|----------|
| Working Slack bot demo | Build in Month 1 | 🔴 Critical |
| LinkedIn profile optimized for AI consulting | Do this week | 🔴 Critical |
| 1-page PDF pitch (problem → solution → pricing) | Create with demo | 🟡 High |
| Microsoft Partner Network enrollment | Sign up for free | 🟡 High |
| Clutch.co company profile | Set up after first client review | 🟢 Medium |
| Company website / landing page | After demo is working | 🟢 Medium |
