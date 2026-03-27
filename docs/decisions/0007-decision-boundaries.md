# ADR 0002: Security-Critical Decisions Require Human Escalation

**Status:** Accepted
**Date:** 2026-02

## Context

This product handles sensitive enterprise data with strict ACL enforcement. Autonomous agents (AI workers) contribute to spec refinement, code implementation, and operations. Without clear boundaries, an agent could inadvertently introduce a security regression — a bypass in the ACL logic, a cross-tenant data leak, or a Mode A isolation violation.

The cost of an autonomous agent making the wrong call on a security-critical decision is customer data exposure and loss of the trust that is our core moat.

## Decision

The following decisions **always require human approval** before proceeding:

### Access Control
- Any change to ACL enforcement logic (query-time filtering, group membership resolution, deny-by-default behavior)
- Any suggestion that a document without ACL metadata should be accessible
- Any code path that could expose documents to users who lack permission in the source system
- Any change to the audit log format or retention policy

### Deployment Mode Integrity
- Any external network call introduced in Mode A (strict local-only)
- Any change to the Mode A / Mode B boundary in the infrastructure layer
- Any third-party dependency added to the Mode A deployment that calls home

### Cross-Tenant Isolation
- Any query path where results from Company A could be returned to Company B
- Any shared index design (all customers must have isolated namespaces)
- Any caching layer that doesn't scope cache keys to tenant + user

### Data Handling
- PII detection and scrubbing logic changes (must stay at ingestion, before embedding)
- Any change to how customer data is stored, replicated, or backed up
- Any telemetry, logging, or analytics that could exfiltrate customer content

## Authority Matrix

| Decision Type | Autonomous Agent | Human Required |
|--------------|-----------------|----------------|
| Add new spec | ✓ | |
| Update existing spec (non-security) | ✓ | |
| Refine ACL enforcement spec | Draft only | Final approval |
| Add new connector | Draft spec only | Approve before implementation |
| Change ACL filtering logic | ❌ | ✓ Always |
| Change audit log behavior | ❌ | ✓ Always |
| Add external dependency (Mode A) | ❌ | ✓ Always |
| Cross-tenant namespace design | ❌ | ✓ Always |

## Consequences

### Positive
- Eliminates the risk of autonomous agents introducing ACL bypasses
- Creates clear accountability — humans own security decisions
- Builds customer trust (CISOs can audit the decision log)

### Negative
- Slows down iteration on security-critical features
- Requires human availability for any ACL-related changes

### Neutral
- Agents still contribute to security work (drafting specs, identifying issues) — they just don't finalize decisions
