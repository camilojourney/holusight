# Proposal Template — Full Client Proposal

> Copy to `proposals/clients/<name>/proposal.md` and customize bracketed fields.
> This is a 3-4 page document. Keep it tight — busy people don't read long proposals.

---

# AI-Powered Document Search for [Company Name]

**Prepared by:** Camilo Martinez — AI Consulting
**Date:** [YYYY-MM-DD]
**Version:** 1.0

---

## 1. Executive Summary

[Company Name] has [X] employees working across [X] projects. Your team currently spends [estimated hours] per week searching for information across [their systems]. When [specific pain point — key people leave, documents are scattered, questions go unanswered].

We propose deploying an AI-powered search system that makes your existing documents instantly searchable. Your team asks questions in plain English and gets precise answers with source citations — in seconds instead of minutes.

**Investment:** $[1,000–2,000 recommended starting range] for a 2-week single-team pilot. See `business/pilot-offer.md`.

---

## 2. The Problem

[Write 2-3 sentences specific to THIS client's pain. Use what they told you in the discovery call.]

**The cost:**
- [X] employees × [X] searches/day × [X] minutes each × $[hourly rate]
- = **$[X]/month in lost productivity**

---

## 3. The Solution

We deploy **CodeSight** — a hybrid AI search engine that combines keyword matching with semantic understanding. Unlike basic search (Ctrl+F, SharePoint search), it:

- **Answers questions**, not just finds files — "What are the payment terms in the Acme contract?" returns the actual answer with the page number
- **Searches across documents** — finds information scattered across multiple files
- **Runs on your infrastructure** — document indexing and search stay on your deployment

### What gets indexed

[Customize — list their actual document types]

| Document Type | Examples |
|--------------|---------|
| [Contracts] | [Vendor agreements, service contracts] |
| [Policies] | [SOPs, employee handbook, compliance docs] |
| [Project docs] | [Specs, meeting notes, status reports] |

### How it works

```
Your team member opens web chat
    → Types: "What did we agree with [vendor] about delivery dates?"
    → Gets: "According to the Service Agreement (page 12),
             delivery is due within 30 days of purchase order..."
    → Clicks source to see the exact document and page
```

---

## 4. Technical Approach

| Component | How |
|-----------|-----|
| **Search engine** | Hybrid BM25 + vector search with Reciprocal Rank Fusion |
| **Document types** | PDF, Word, PowerPoint, text files |
| **Embeddings** | Local model — no data sent anywhere for indexing |
| **Answer synthesis** | [Claude API / Azure OpenAI / local LLM] — your choice |
| **Interface** | Web chat UI accessible from any browser |
| **Hosting** | [Your laptop / your server / your cloud VM] |

### Data privacy

- Search and indexing: **100% local**. No internet needed.
- Answer synthesis: goes to [chosen LLM provider] — you own the API key.
- We are never in the middle. No data flows through us.
- Software is open source — you can audit every line of code.

---

## 5. Engagement Phases

### Phase 1: Pilot — [2 weeks, $X]

| Week | Deliverables |
|------|-------------|
| **Week 1** | Audit document structure, set up CodeSight, index [pilot project/dept] |
| **Week 2** | Deploy web chat, train [X] power users, test with real questions, tune results |

**Done when:** Your team can search [pilot scope] and get relevant answers with citations.

### Phase 2: Scale — [2-4 weeks, $X per project]

| Deliverable | Details |
|-------------|---------|
| Additional projects | Index [remaining departments/projects] |
| User training | Train full team on effective questioning |
| Search tuning | Optimize for your specific document types and terminology |

### Phase 3: Maintenance — [$X/month]

| Deliverable | Details |
|-------------|---------|
| Monitoring | Index freshness, search quality checks |
| Reindexing | [Weekly/daily] refresh as documents change |
| Support | [X] hours/month for questions, tuning, new document types |

---

## 6. Pricing

| Phase | What | Timeline | Investment |
|-------|------|----------|-----------|
| **Pilot** | Single team, Docker/VM deploy, training | 2 weeks | **$1,000–$2,000** (recommended starting range) |
| **Scale** | Additional teams / corpora | Separate SOW | Quote after pilot |
| **Optional support** | Updates, index health, minor config | Monthly | **$500–$1,000**/month |
| **Customer infra + LLM** | VM/cloud + API usage | Monthly | Customer-owned (typical small VM $50–200; LLM billed to their account) |

Do not publish unverified Copilot/Glean ROI or per-user comparisons in the client-facing copy unless the client supplies their own numbers.

**Terms:** 50% upfront, 50% on delivery. Any guarantee must be explicitly negotiated in the SOW.

---

## 7. Why Us

1. **Working product.** CodeSight is built and deployed — not a prototype. We demo with your actual documents.
2. **Speed.** Working system in days, not months.
3. **Privacy.** Document indexing and search run on your infrastructure; cloud answer providers may receive retrieved context. Open source, fully auditable.
4. **Cost.** Fraction of enterprise alternatives (Glean: $45-50/user/month, Copilot: $30/user/month).
5. **No lock-in.** Open source tool. If you stop working with us, the system keeps running.

---

## Next Step

Let's schedule a 30-minute demo using your actual documents. I'll index a sample folder on the spot and show you the results live.

**Contact:** [email] | [phone] | [website]
