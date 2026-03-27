# ADR 0001: Support Two Deployment Modes from Day One

**Status:** Accepted
**Date:** 2026-02

## Context

Mid-market enterprise customers fall into two categories with incompatible data residency requirements:

1. **Regulated industries** (healthcare, legal, government, finance) — data cannot leave the customer's network under any circumstances. Azure OpenAI, even in a private endpoint, is unacceptable to their security teams. They need fully local inference.

2. **Fast-moving companies** — willing to use Azure managed services. Want fastest time-to-value. Already have Azure spend. Don't need local LLMs.

Building only Mode A (local-only) locks us out of the larger, faster-moving market. Building only Mode B (Azure-native) locks us out of regulated industries — which are often the most willing to pay for security.

## Decision

Support both deployment modes from day one:
- **Mode A — Strict Local-Only:** Local embedding (BAAI/bge or Nomic), local LLM (Llama 3.1, Mistral, or DeepSeek), Qdrant + PostgreSQL + MinIO. Zero external calls.
- **Mode B — Azure-Native:** Azure AI Search (hybrid + vector + security trimming), Azure OpenAI (GPT-4o), Entra ID + Purview labels. Fastest deployment.

The ACL enforcement logic, API layer, and chat interfaces are shared. Only the infrastructure layer differs.

See [specs/002-deployment-modes.md](../../specs/002-deployment-modes.md) for full technical specs.

## Consequences

### Positive
- Addresses full TAM — both regulated and fast-moving customers
- Mode A creates a strong moat (local LLM inference is hard to do well)
- Mode B enables rapid demos and pilot deployments

### Negative
- Doubles infrastructure complexity — two infrastructure implementations to maintain
- Testing matrix is 2x (must test both modes for every feature)
- Documentation burden is higher

### Neutral
- Forces a clean abstraction layer between the API/ACL logic and the infrastructure — this is good architecture regardless
