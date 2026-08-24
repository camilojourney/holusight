# ADR-0017: Bind pilot evaluation results to an immutable Git subject

**Date:** 2026-08-24
**Status:** Accepted

## Decision

Add one required `subject` field (`repository_id`, `commit`, `tree`, `clean`,
and an inert `branch` annotation) to `holus-eval-pilot-result/v1`, computed
by `run_pilot` from real Git state, never from caller input. At review time,
recompute every consequential linked artifact (`implementation`, `tests`,
`documentation`, `evaluation_case`) against that subject by resolving each
repository-relative path to a Git blob at the evaluated commit and comparing
it to the clean current `HEAD` and worktree blobs. Require current `HEAD` to
descend from the evaluated commit. Reuse the existing six manifest link roles
unchanged; add no new role, manifest field, storage layer, or promotion
mechanism.

## Consequences

- A repository-relative link path is now proven to be a locator, not
  identity: a candidate cannot change implementation and update only a
  manifest hash to reach `evaluated` stage without rerunning evaluation.
- A stale, dirty, wrong-tree, unknown/rewritten-commit, renamed/rebased, or
  changed consequential artifact is indeterminate — it demotes stage away
  from `evaluated` via the existing blocker-prefix mechanism in `_stage()`,
  so it can never reach `pre_promotion`'s `human_promotion_review`. No new
  top-level outcome vocabulary was introduced; the existing blocker/stage
  machinery already does this correctly once fed the right blockers.
- A previously silent loophole is closed: a non-Git directory used to read
  as "not dirty" (because `git status` simply fails there), so an eval-pilot
  result produced outside a real Git repository could still become
  promotion-relevant evidence. `EvaluationSubject.clean` now requires a
  resolvable commit and tree, successful clean status checks, and the same
  subject before and after grading. Git failures and concurrent changes fail
  closed.
- A later manifest-only descendant commit remains applicable exactly when
  every consequential tracked `HEAD` blob and clean worktree path is unchanged.
  Commit recency does not invalidate an already-evaluated result.
- Repository identities are sanitized before persistence, SHA-1 and SHA-256
  object formats are accepted, and aggregate scorecards derive their commit
  and promotion relevance from the bound subject.
- Mutable branch names are recorded only as an annotation
  (`EvaluationSubject.branch`); nothing in the applicability recomputation
  reads it.
- `retrieval_variation.py`'s own result schema and applicability check are
  untouched — it already fully re-executes and byte-compares against
  current tracked `HEAD` on every load, which is a different, already
  adequate mechanism for that subsystem (see ADR-0016).

An evaluator-subject pin (G2), a frozen comparison packet (G3), and a
normative `pass | block | indeterminate` integration outcome (G4) remain
separate, later corrections in the same dependency-ordered queue — adding
them here would widen this change beyond the one gap it closes.
