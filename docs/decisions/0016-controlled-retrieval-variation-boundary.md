# ADR-0016: Keep retrieval variation inside the existing improvement control plane

**Date:** 2026-08-24
**Status:** Accepted

## Decision

Use the existing `holus improve-*`, `improvement_control`, and no-follow
derived-state storage boundaries for a narrowly scoped evidence-display
variation program. The program owns only fixed baseline/candidate definitions
and deterministic evaluation. Human promotion remains an independent existing
manifest-review decision.

## Consequences

- `retrieval_variation.py` has no arbitrary candidate loader, model call,
  network client, telemetry writer, or production-routing mutation path.
- The clean tracked benchmark and executable definitions are content-addressed.
  The production candidate executes the production display selector. A
  malformed, partial, tampered, unsupported, or independently unrecomputable
  result fails closed.
- Hard constraints and the measured reward are separate. A reward increase
  cannot excuse a protected regression.
- The bounded benchmark cannot establish the required paired statistical
  evidence yet, so v1 deliberately reports an inconclusive candidate rather
  than promoting it.
- Derived records and complete typed results are opt-in and use
  `control_storage.safe_atomic_write` below `.holusight/`; canonical repository
  content is never a program output. Promotion-relevant review additionally
  requires a separate clean tracked manifest that pins every input and result.

A separate framework, automatic candidate generation, and model-as-authority
would duplicate or weaken controls already merged in specs 017-019.
