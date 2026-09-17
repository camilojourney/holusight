# Next Tasks — codesight

_Tasks for Juan + Fruco to complete. Check off when done._

---

## Evaluation (local/advisory) — accepted finish line (2026-09-16)

Per [ADR-0019](../docs/decisions/0019-local-advisory-evaluator-promotion-denied.md):

- [x] Local Fleet smoke (`just fleet-smoke`) — pilot on `master`
- [x] Local eval pilot (`just eval-pilot`) — 4 frozen cases on `master`
- [x] Named local retrieval suite (`just eval-suite`) — 85 visible dev cases with
  pass/block/indeterminate advisory evidence bound to a clean Git subject
- [x] Promotion denied (no autonomous promote/merge/deploy from gates)
- [ ] Overnight AVO / G2 external acceptance — **deferred**, not blocking;
  remains owner of independent evaluator pinning and candidate-independent acceptance

## Product (still open beyond eval)

- [ ] v0.6 ACL / SSO (see `docs/roadmap.md`)
- [ ] Microsoft Graph / connectors (planned, not claimed)

