# Holusight Research-to-Improvement Control Plane v1

**Status:** Phase 1 implemented.

## Purpose and boundary

This is the deterministic review layer over the existing `holus improve-*`
commands, eval pilot, and placement guard from specs 017 and 018. It does not
add a provider, Fleet contract, training store, command-line control plane, or
promotion mechanism. It gives a later human or local consumer one stable JSON
answer for a tracked change: its classification and stage, missing evidence,
next permitted action, promotion blockers, and any narrowly justified
`research_needed` packet.

All decisions are derived from an explicit tracked JSON change manifest,
structured `**Status:**` markers in governing Markdown, repository-relative
links, and byte hashes. No language model classifies authority or evidence.
The command never launches research, makes a network request, accesses
credentials/private/customer/production data, modifies canonical artifacts,
merges, releases, or promotes.

## Command contract

Schema version `0.3.0` adds three commands to the existing generated `holus`
surface:

```text
holus improve-review <change-manifest.json> [--phase before_change|after_implementation|after_test|pre_promotion] [--record]
holus improve-history <change-id>
holus improve-integration <change-manifest.json> [--phase ...]
```

`improve-review --format json` is the lossless canonical control result. Its
`review` object always has `classification`, `stage`, `missing_evidence`,
`blockers`, `next_permitted_action`, and `promotion`. Promotion is always
`allowed: false`; even a complete pre-promotion review ends at
`human_promotion_review`.

`improve-integration` emits the same review with
`integration_contract: "holus-improvement-integration/v1"`,
`consumer: "local_advisory_only"`, and `integration_complete: false`. It is a
stable local handoff shape for a future No Mistakes or Fleet consumer. No other
repository is changed and no integration is claimed complete.

## Tracked manifest

A change manifest is repository-relative JSON with schema
`holus-improvement-change/v1`:

```json
{
  "schema_version": "holus-improvement-change/v1",
  "change_id": "example-change",
  "classification": "accepted",
  "structured_sections": ["context", "evidence", "decision"],
  "links": {
    "governing": ["specs/019-research-to-improvement-control-plane.md"],
    "implementation": ["src/codesight/improvement_control.py"],
    "tests": ["tests/test_improvement_control.py"],
    "documentation": ["docs/playbooks/improvement-control-review.md"],
    "evaluation_case": ["tests/fixtures/example-cases.jsonl"],
    "evaluation_result": ["tests/fixtures/example-result.json"]
  },
  "link_hashes": {"path": "sha256:<current-bytes-hash>"},
  "lineage": {"candidate_id": "candidate-42", "workflow": "local", "tool": "holus"}
}
```

The manifest is tracked metadata, not a free-form prompt. Its top-level and
structured-section vocabulary is closed; lineage accepts only bounded identifier
fields. It rejects fields that could carry raw prompts/source content,
private/customer data, credentials, or telemetry. `evidence_state` is exactly
`familiar` or `unfamiliar`. Paths must stay inside the repository. The fixed
link roles are canonical only at these locations: governing specs/ADRs,
implementation under `src/`, `tests/test_*.py`, explanatory documentation in
`docs/` or `ARCHITECTURE.md`, evaluation cases under `tests/fixtures/*.jsonl`,
and evaluation results under `tests/fixtures/` or derived improvement-run
state.

## Classification, stages, and evidence checks

The only classifications are `research_only`, `proposed`, `accepted`,
`implemented`, `evaluated`, `rejected`, and `superseded`. The explicit manifest
value is authoritative only after exact validation against any structured
`**Status:**` marker. Contradictory metadata, invalid role placement, duplicate
links, dangling links, missing hashes, and hash mismatch are blockers.

`accepted`, `implemented`, and `evaluated` require every fixed link role and
current hashes. The derived stage advances only from verified link presence:
`accepted` -> `implemented` -> `evaluated`. `research_only`, `rejected`, and
`superseded` remain non-authoritative records and never require implementation,
tests, or evaluation evidence.

Before change, `proposed_artifacts` are checked using the existing canonical
placement rules. Existing duplicate paths/names and wrong roots are blocked
before any artifact is created. Any proposed evaluator source or frozen pilot
case mutation is a distinct `evaluator_mutation` blocker. The control plane
never edits an evaluator or case corpus.

## Stepwise operation and research signals

- `before_change`: resolve placement, then `implement_change`.
- `after_implementation`: complete deterministic links, then
  `run_deterministic_tests`.
- `after_test`: retain the result and run `pre_promotion` review.
- `pre_promotion`: only a blocker-free result permits
  `human_promotion_review`, never automatic promotion.

`research_needed` is `null` unless evidence is contradictory, materially
incomplete, explicitly marked `unfamiliar`, or two retained records show the
same blocked stage. The packet gives either `normal_review` or a precise
`gpt_deep_research` question with `external_action: "not_launched"`. It does
not invoke external, paid, or egress-capable research.

## Derived records and rebuild

`--record` is opt-in and writes only to the gitignored
`.holusight/improvement-runs/<change-id>/` directory. Records contain stage,
outcome, metadata and link hashes, repository references, bounded lineage, and
blocker codes. They do not store raw prompts/source content, private/customer
data, credentials, or production telemetry. `improve-history` exposes only
this minimized history.

The directory is derived state, never canonical truth. It is safe to delete;
running the same review with `--record` rebuilds it from the unchanged tracked
manifest and repository evidence. Failed candidates remain inspectable and
rerunnable, but cannot rewrite their evaluator or become promotion authority.

## Evidence and verification

The required end-to-end coverage is in
`tests/test_improvement_control.py`: complete and incomplete accepted links,
non-authoritative classifications, duplicate/misplaced pre-creation blocking,
all link integrity failures, retained history/rebuild, constrained research
packets, safety refusals, and the local integration payload. Existing
`tests/test_eval_pilot.py` and `tests/test_improve_loop.py` continue to prove
frozen-evaluator and regression-loop behavior.

Graphify was unavailable while this implementation was scoped. The exact
attempted command was:

```text
python3 /Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py query "Holus AXI schema cli generated skill continuous improvement evaluation pilot control commands traceability record linked evidence"
```

It failed because that wrapper path was absent on this execution host. Source
inspection was used instead; no external research was needed because the
architecture was determined by merged specs 011-018 and existing code.
