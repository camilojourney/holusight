# Holusight Evidence Subject Binding v1

**Status:** Implemented.

## Purpose and boundary

This closes gap G1 from the captain-authorized completeness gap-map review
of the existing eval-pilot and improvement-control contracts (specs
017-020): a repository-relative link path in a `holus-improvement-change/v1`
manifest was a locator, but pre-promotion review never proved that the
linked implementation, tests, documentation, and evaluation case were the
exact bytes a linked `holus-eval-pilot-result/v1` was actually evaluated
against. A candidate could change implementation and update only the
manifest's own hash, without rerunning evaluation, and reach
`human_promotion_review` on stale evidence.

This is a small additive closure, not a new system. It adds one new
required field to the existing pilot result schema, and one new
recomputation pass inside the existing `_review_links` review path. It adds
no new manifest field, link role, storage layer, evidence lake, universal
repository tree, evaluator self-grading, autonomous promotion, deployment,
or external integration. `.holusight/` remains derived, non-canonical state.

## The immutable Git subject

Every `PilotRunResult` (`src/codesight/eval_pilot.py`) now carries a
`subject: EvaluationSubject`, computed fresh by `run_pilot` from the real
repository state at evaluation time — never trusted from caller input:

```json
{
  "repository_id": "https://github.com/camilojourney/holusight.git",
  "commit": "<full Git commit oid>",
  "tree": "<full Git tree oid>",
  "clean": true,
  "branch": "fm/holusight-subject-binding-v1"
}
```

- `repository_id` is the canonicalized configured `origin` remote URL with
  userinfo, query, and fragment removed. Machine-local or malformed remotes,
  and repositories with no remote, use the fixed `"local-no-remote"`
  sentinel. Credentials and filesystem paths are never persisted.
- `commit` and `tree` are full Git object ids resolved from `HEAD` /
  `HEAD^{tree}` at evaluation time. Both 40-hex SHA-1 and 64-hex SHA-256
  repositories are supported; an unresolvable object is `null`.
- `clean` is `true` only when both `commit` and `tree` resolve, `git status`
  succeeds with no uncommitted changes, and a second subject capture after
  grading has the same repository identity, commit, tree, and clean state.
  Git command failure and concurrent repository changes fail closed.
- `branch` is recorded only as an annotation. Nothing in the applicability
  recomputation below reads it — a mutable branch name is never identity.

`_validate_result` additionally rejects any result whose subject is not
`clean` (with a resolved `commit` and `tree`) as promotion-relevant
evidence, alongside its existing `corpus_trust`/`repo_dirty` check. The
aggregate scorecard derives promotion relevance and `repo_commit` from this
subject and rejects a caller-supplied commit that does not match it.

## Review-time applicability recomputation

`improvement_control._review_links` reuses the existing six link roles as
typed relations — no new role. For a manifest at `classification: evaluated`
whose linked evaluation result is a pilot result, review now recomputes
applicability against that result's subject
(`improvement_control._subject_applicability_blockers`) before the manifest
can reach `evaluated` stage:

1. The subject itself must be `clean` with a resolvable `commit`/`tree`, or
   the result is `dangling_evaluation_subject`.
2. The current repository's identity must match `subject.repository_id`, or
   `wrong_repository_subject`.
3. `subject.commit^{tree}` must still resolve (the commit must still exist),
   or the subject is `stale_evaluation_subject`.
4. The resolved tree must equal `subject.tree`, or `wrong_tree_oid`.
5. The current `HEAD` must descend from the evaluated commit, or the subject
   is stale after rewritten/rebased history.
6. For every path linked under `implementation`, `tests`, `documentation`,
   and `evaluation_case` — the **consequential** roles whose bytes the
   result actually depended on (`governing` and `evaluation_result` are
   excluded: one governs, the other is the anchor itself) — the path must
   resolve to a Git blob at the evaluated commit
   (`git rev-parse <commit>:<path>`), or it is
   `dangling_consequential_artifact` (this is also the rebase/rename case: a
   path is a locator, never identity, so a renamed file that never existed
   at that path in the evaluated commit is indeterminate, never silently
   accepted because its current bytes happen to hash-match the manifest).
7. That evaluated blob must equal both the current tracked `HEAD:<path>` blob
   and the current worktree blob. The path must also be clean in the index and
   worktree. A tracked mismatch is `changed_consequential_artifact`; staged,
   unstaged, or untracked path state is `dirty_consequential_artifact`.
   Current bytes matching the manifest hash cannot hide a different tracked
   `HEAD` blob.

Every one of these blocker codes shares a prefix (`dangling_`, `stale_`,
`wrong_`, `changed_`, or `dirty_`) that `_stage()` treats as
disqualifying — so a manifest with any of them can never reach `evaluated`
stage, and `pre_promotion` review can never return
`human_promotion_review` for it. This preserves the existing promotion
boundary rather than adding a new one: promotion was always
`allowed: false`, and remains so.

A later manifest-only descendant commit - one that touches nothing
consequential - remains applicable because every consequential `HEAD` blob
and clean worktree path still matches the evaluated subject. Commit recency
and the manifest's own branch play no part.

## Explicitly out of scope

- No change to the `retrieval_variation.py` result schema or its own
  applicability check, which already fully recomputes its result by
  re-executing `run_program` against current tracked `HEAD` bytes
  (`retrieval_variation.validate_result`) — a different, already-adequate
  mechanism for that subsystem. G1 only closes the gap for pilot results.
- No new manifest field or link role (`holus-improvement-change/v1`'s six
  roles are unchanged).
- No evaluator-subject pinning (G2), comparison packet (G3), or normative
  `pass | block | indeterminate` integration outcome (G4) — later,
  independent corrections in the same dependency-ordered queue.

## Evidence and verification

`tests/test_evidence_subject_binding.py` covers, per the acceptance
criteria in the originating gap-map review: a clean evaluated result
reaching `human_promotion_review`; a later unrelated commit with identical
consequential blobs staying applicable; a changed implementation with only
the manifest hash updated (never rerun) becoming indeterminate; a tampered
tree OID; an unknown/rewritten evaluated commit; a dirty-worktree
evaluation; and a renamed/rebased path whose current bytes hash-match but
never existed at the evaluated commit. `tests/test_improvement_control.py`
and `tests/test_control_plane_adversarial_e2e.py` continue to prove the
unchanged parts of the review contract, now against real committed Git
fixtures (a genuinely evaluated result can only ever have a real subject).

Graphify was checked first. `graphify-out/graph.json` existed but
`built_at_commit` (`923af1f`) predated this repository's current `HEAD`
(`6e868df`, merged PR #28), and neither the `graphify` CLI nor the
`fleet_graphify.py` wrapper this repository's own `AGENTS.md` names was
present on this execution host. Direct source and Git history evidence was
used instead, per the same fallback already recorded in spec 019. The stale
graph was not modified.
