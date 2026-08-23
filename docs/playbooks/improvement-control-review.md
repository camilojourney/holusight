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

This is a stable local advisory payload for a future consumer. It is not a
No Mistakes or Fleet integration and does not authorize automatic action.
