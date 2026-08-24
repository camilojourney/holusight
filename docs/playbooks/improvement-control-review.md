# Playbook: Review a research-to-improvement change

Use this after specs 017 and 018 when a tracked conclusion needs a deterministic
stage and traceability review. The commands are local and advisory. They never
promote, merge, deploy, launch research, or edit a canonical artifact.

## 1. Prepare tracked evidence

Create a repository-relative `holus-improvement-change/v1` JSON manifest near
its governing spec or ADR. Use the exact schema and canonical locations in
`specs/019-research-to-improvement-control-plane.md`.

Before creating a new linked artifact, run the existing placement guard:

```bash
holus improve-placement --artifact-type test --proposed-path tests/test_example.py
```

Do not put prompts, source text, customer/private data, credentials, or
production telemetry in the manifest. Use references and hashes only.

## 2. Review each step

```bash
# Verify intent, placement, and the next permitted action.
holus improve-review specs/019-example.change.json --phase before_change --format json

# Verify implementation links after code exists.
holus improve-review specs/019-example.change.json --phase after_implementation --format json

# Retain a minimized local record after deterministic tests.
holus improve-review specs/019-example.change.json --phase after_test --record --format json

# Ask whether human promotion review is permitted.
holus improve-review specs/019-example.change.json --phase pre_promotion --format json
```

Resolve every `review.blockers` entry using repository evidence. A complete
pre-promotion result still returns `promotion.allowed: false` and
`next_permitted_action: human_promotion_review`.

## 3. Handle non-authoritative material and research signals

Set `classification` exactly to `research_only`, `rejected`, or `superseded`
when that is the tracked conclusion. Those records should remain inspectable
but must not be padded with invented implementation or test links.

Read `research_needed` only when it is present. It appears for contradictory,
materially incomplete/unfamiliar, or repeatedly stagnant evidence. A
`gpt_deep_research` recommendation is a question only: it has
`external_action: "not_launched"`. Do not start external research from this
command.

## 4. Inspect and rebuild local history

```bash
holus improve-history example-change --format json
rm -rf .holusight/improvement-runs/example-change
holus improve-review specs/019-example.change.json --phase after_test --record --format json
```

The record directory is gitignored derived state. Deleting it and rebuilding it
cannot change specs, ADRs, source, tests, frozen cases, or evaluation truth.

## 5. Hand off locally

```bash
holus improve-integration specs/019-example.change.json --phase pre_promotion --format json
```

## 6. Immutable Git subject and recomputed applicability

A promotion-eligible eval-pilot `evaluation_result` must be produced against a
real, committed Git repository, and its evaluated case corpus must match the
blob committed at that subject. A pilot result now carries `subject` with
`repository_id`, `commit`, `tree`, `clean`, and an inert `branch` annotation,
computed from real Git state when the result is produced, never from caller
input (spec 021,
`docs/decisions/0017-immutable-evaluation-subject-binding.md`).

At `--phase pre_promotion`, review recomputes applicability against that
subject for every `implementation`, `tests`, `documentation`, and
`evaluation_case` link. Current `HEAD` must descend from the evaluated commit,
and each path must have the same blob at the evaluated commit and current
`HEAD`, with a clean matching worktree path. If you see any of these blockers,
the fix is always to rerun evaluation against current code, never to hand-edit
`link_hashes`:

| Blocker | Meaning |
|---|---|
| `dangling_evaluation_subject` | The result has no resolvable commit/tree, was produced outside Git, or has an unborn branch. |
| `dirty_evaluation_subject` | The result records an unclean evaluation subject or dirty lineage. |
| `wrong_repository_subject` | The result was evaluated in a different repository identity. |
| `stale_evaluation_subject` | The evaluated commit no longer resolves, or current `HEAD` does not descend from it after rewritten/rebased history. |
| `wrong_tree_oid` | The evaluated commit exists, but its tree does not match the recorded one. |
| `dangling_consequential_artifact` | The linked path did not exist at the evaluated commit - including a rename/rebase where the current path is new. |
| `changed_consequential_artifact` | The path's evaluated blob differs from current tracked `HEAD` or worktree bytes, including when only the manifest hash was updated. |
| `dirty_consequential_artifact` | The linked path has staged, unstaged, or untracked state, or Git cannot prove it clean. |

Every one of these blocks `evaluated` stage and therefore
`human_promotion_review`, the same way `dangling_`/`stale_`/`wrong_` link
blockers already did. A later commit that changes nothing consequential
(unlinked docs or other unrelated files) does not invalidate an
already-evaluated result.
Every consequential tracked and worktree blob must remain identical, while
commit recency and branch name remain irrelevant.

This is a stable local advisory payload for a future consumer. It is not a
No Mistakes or Fleet integration and does not authorize automatic action.
