# Recommended SMB Pilot Offer

> **Internal / sales framing.** This is a recommended starting engagement — not evidence of market traction or a published SaaS price list.

## Ideal customer profile

- **Size:** 10–75 knowledge workers; one team owns the pilot (engineering, ops, or professional services)
- **Content:** 500–50,000 files — policies, contracts, runbooks, and code in a shared folder or git mirror
- **Pain:** Teams cannot find answers across scattered docs; `grep` and shared drives are failing; they need cited answers, not another chatbot without sources
- **Constraints:** Documents must stay in the customer environment (on-prem VM, customer VPC, or private Azure subscription)
- **Not a fit (yet):** Company-wide SSO + per-document ACLs, M365 live sync, multi-tenant SaaS, or “replace Sourcegraph/Glean” expectations

## Two-week pilot scope

| Week | Activities |
|------|------------|
| **Week 1** | Discovery call; mount read-only doc folder; deploy Docker or VM install; index corpus; validate search + citations with 10–15 real team questions |
| **Week 2** | Configure answer provider (customer’s Claude/Azure/OpenAI or local Ollama); train 3–5 champions; acceptance review; handoff runbook |

**Deliverables:** running Holusight deployment, indexed corpus, operator runbook (`docs/playbooks/docker-deployment.md`), short findings memo (what worked / gaps).

## Acceptance metrics (pilot)

| Metric | Target |
|--------|--------|
| Top-3 search hit on agreed “golden” questions | ≥ 70% of curated set (typically 15–20 questions) |
| Every displayed answer includes ≥ 1 source with file + line/page | 100% |
| Search works with LLM disabled | Required |
| Deployment survives container restart with index intact | Required |
| No writes to source document folder | Required (read-only invariant) |

## Deployment options

| Option | Who hosts | Best for |
|--------|-----------|----------|
| **A — Customer VM / on-prem** | Customer | Data residency, air-gapped or private network |
| **B — Customer cloud (single VM)** | Customer Azure/AWS/GCP account | Faster procurement, customer owns VPC |
| **C — Consultant-hosted lab** | Holusight team (temporary) | Evaluation only — not production; data deleted after pilot |

**Public site note:** [holusight.com](https://holusight.com) is static marketing/docs only. Customer documents are never processed by Vercel.

## Pricing (recommended starting range)

Aligned across site, proposals, and this doc:

| Item | Recommended range (USD) |
|------|-------------------------|
| **Pilot setup fee** (2 weeks, single team) | **$1,000 – $2,000** |
| **Optional monthly support** (updates, index health, minor config) | **$500 – $1,000 / month** after pilot |
| **Customer infrastructure** | Billed by customer cloud/provider (typical: $50–200/mo for a small VM + disk) |
| **LLM API usage** (if not using Ollama) | Billed to customer’s API account |

No per-seat license is required for v1 single-team deployments. Expansion (additional teams, connectors, SSO) is scoped separately after pilot.

## Exclusions (v1 pilot)

- SSO / SAML / OAuth
- Per-document ACLs or Microsoft 365 connector build
- Multi-tenant hosted SaaS on holusight.com
- Kubernetes / Helm production hardening
- Graphify graph integration (see ADR 0010)
- Compliance attestations (SOC 2, HIPAA BAA, etc.)
- Guaranteed concurrent user counts or uptime SLAs

## Handoff & expansion path

1. Customer receives Docker compose (or image), env template, backup procedure for `/index` volume
2. Optional support retainer for upgrades and re-index health
3. Expansion quotes: additional corpora, SSO, ACL connector design, Graphify experiment — each as a separate SOW

## Discovery checklist (first call)

- [ ] Where do documents live today? (SharePoint export, git, file server)
- [ ] Approximate file count and formats
- [ ] Any “no cloud” or “LLM data residency” policies?
- [ ] Who will own the VM and API keys?
- [ ] 15 example questions the team actually asks
- [ ] Success criteria in their words (avoid promising ROI hours we cannot verify)
