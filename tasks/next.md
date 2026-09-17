# Next Tasks — codesight

_Tasks for Juan + Fruco to complete. Check off when done._

---

## Evaluation (local/advisory) — accepted finish line (2026-09-16 / extended 2026-09-17)

Per [ADR-0019](../docs/decisions/0019-local-advisory-evaluator-promotion-denied.md):

- [x] Local Fleet smoke (`just fleet-smoke`) — pilot on `master`
- [x] Local eval pilot (`just eval-pilot`) — 4 frozen cases on `master`
- [x] Advisory named-suite orchestration (`just proper-eval`) — suite identity + subject binding + visible surfaces; promotion denied
- [x] Promotion denied (no autonomous promote/merge/deploy from gates)
- [ ] Overnight AVO / G2 external acceptance — **deferred**, not blocking

See [docs/playbooks/run-proper-eval.md](../docs/playbooks/run-proper-eval.md).

## Product (still open beyond eval)

- [ ] v0.6 ACL / SSO (see `docs/roadmap.md`)
- [ ] Microsoft Graph / connectors (planned, not claimed)
