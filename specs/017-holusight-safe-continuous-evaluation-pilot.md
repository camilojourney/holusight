# Holusight Safe Continuous-Evaluation and Improvement Pilot

**Status:** Phase 1 implemented (bounded direct-PR, unmerged pending review).
**Authorization boundary:** captain-authorized, delegated pilot per
`/Users/camiloslaptop/.treehouse/firstmate-8bf1b0/6/firstmate/data/holusight-eval-safe-pilot-v1/delegated-decisions.md`
(2026-08-23). This spec and its implementation are scoped exactly to that
delegation: a bounded, no-spend, Holusight-only pilot using public,
synthetic, or repository-owned fixtures. It does not authorize deployment,
private/production content, telemetry, paid APIs, external providers,
online self-modification, or autonomous promotion. See
[Non-goals](#14-non-goals-verbatim-boundary-translation).

## 1. Successor-spec provenance and draft custody

This spec formally **supersedes** an earlier, now-unavailable draft
referenced by the delegating decision as `spec-013-draft-custody` /
`draft-custody`. That draft's content could not be located in this
worktree or its history at the time this spec was written, and its
missing text is **not reconstructed or guessed here**. Per the delegated
decision:

> "Any successor must be a new tracked artifact based only on verified
> specs 011/012, current repository evidence, and merged Holusight work."

This spec is built from exactly those three sources:

- **`specs/011-holusight-product-architecture-research.md`** (research
  only, no implementation authorization) — its "Improvement architecture"
  and "Evaluation harness" sections define the general shape (frozen task
  corpus → candidate in shadow → paired comparison → canary → promote or
  rollback; local-by-default telemetry) this pilot draws its vocabulary
  from, narrowed drastically in scope.
- **`specs/012-holusight-overnight-benchmark-continuous-evaluation-research.md`**
  (research only) — its "Continuous-improvement protocol" section (what a
  candidate **may** and **may not** do to its own evaluator) and its
  frozen-task/manifest/result JSON schema sketches are the direct
  ancestor of §4/§5 below, again narrowed by two to three orders of
  magnitude in scope: this pilot ships **4 frozen cases**, not the
  96-task suite spec 012 describes: see [§9](#9-relationship-to-specs-011012-explicitly-not-the-96-task-suite).
- **Merged Holusight work (PRs #16–#20)** — this pilot adds no new
  provider, no new retrieval mechanism, and no new CLI surface under
  `holus`. It is a thin evaluator layered over:
  - `src/codesight/consistency.py` (spec 013, PR #16) — the
    documentation-code consistency engine.
  - `src/codesight/cli_axi.py` / `src/codesight/axi_providers.py`
    (spec 015, PR #18) — the `holus` AXI command surface and its evidence
    providers.
  - `src/codesight/fleet_scorecard.py` (spec 016, PR #19) — the existing
    Fleet v1.2 scorecard-bridge precedent this pilot's own aggregate
    export mirrors.
  - The bounded per-provider display-quota fix (PR #20, `commit
    e516db769f44f0b9b71c23216bc19b04d5219a22`) — the seed reproduced
    usage gap this pilot's frozen case corpus is built around (§4).

**Draft custody going forward:** this spec, once merged, is the canonical
successor. `docs/decisions/0013-eval-pilot-scope-boundaries.md` is the
accompanying decision record.

## 2. Purpose

Turn the fact that Holusight has *already* found and fixed one real
`holus` usage gap (PR #20) into a small, durable, local mechanism that
keeps that gap fixed, and gives this repository a place to add the next
one — without building the general-purpose benchmark platform spec 012
describes, and without granting any process the authority to promote
itself.

The customer-visible job, narrowed from spec 011's framing to this
pilot's actual scope:

> Before trusting that a shipped fix still holds, or that a proposed
> change doesn't quietly regress it, run the smallest frozen, provenance-
> carrying check set that already caught a real problem once — locally,
> for free, and only as advice a human can act on.

## 3. What is and is not built

| Built (this PR) | Not built (explicitly deferred) |
|---|---|
| A frozen JSONL case corpus (4 cases) with mandatory provenance | The 96-task suite, held-out splits, human-annotation manuals (spec 012 §"Frozen private suite") |
| A bounded, deterministic local runner (`src/codesight/eval_pilot.py`) | Inspect AI or any external orchestration substrate |
| Candidate-lineage recording (who/what produced a run) | A trace/training store, central or otherwise |
| One genuine candidate-vs-status-quo comparative case (the PR #20 fix vs. its pre-fix behavior) | A router benchmark, provider ablation matrix, or multi-provider architecture comparison |
| Two Fleet v1.2-shaped, content-free exports (aggregate scorecard + minimal domain-result summary) | Any change to `agentic/manifest.yaml`'s declared `eval_entrypoint` (still `just fleet-smoke`, unchanged) |
| A human-approved case-admission path (playbook) | Any autonomous case-writing tool |
| Documentation of the spec-002 default drift (§10) | Any change to the shipped embedding default |

## 4. The frozen case corpus

`tests/fixtures/holusight_eval_pilot_cases.jsonl`, schema
`holus-eval-pilot-case/v1`, one JSON object per line. Every case is
**read-only input** to `src/codesight/eval_pilot.py`'s runner — the
runner never opens this file for writing (proven by
`tests/test_eval_pilot.py::test_run_pilot_works_when_case_file_is_read_only`,
which chmods the fixture read-only mid-test).

### 4.1 Required shape

```json
{
  "schema_version": "holus-eval-pilot-case/v1",
  "case_id": "...",
  "family": "regression",
  "kind": "regression | comparative",
  "provenance": {
    "origin": "reproduced_usage_gap | spec_documented_finding | spec_documented_contract",
    "description": "...",
    "diagnosis_ref": "... (optional)",
    "fix_ref": "... (optional, null if none)",
    "admitted_by": "who/what approved admission",
    "admitted_at": "YYYY-MM-DD"
  },
  "grader": "name of a registered grader function",
  "fixture": { "...": "grader-specific synthetic input" },
  "expected": { "...": "grader-specific frozen expectation" },
  "requires_index": false,
  "requires_semantic": false,
  "egress_allowed": false,
  "notes": "..."
}
```

`load_cases()` rejects (raises, does not silently skip) any case missing
a required provenance field or naming an unregistered grader — a case
cannot be "half admitted."

### 4.2 The four seed cases

1. **`cli-axi-provider-starvation-display-quota`** (`kind: comparative`) —
   the reproduced, already-fixed provider-starvation bug (§5). This is
   the pilot's one genuine candidate-vs-status-quo demonstration.
2. **`consistency-known-dangling-reference-0006`** (`kind: regression`) —
   protects the exact provider's dangling-reference detection against
   silent regression, using the real, currently-unresolved
   `docs/decisions/0006-two-deployment-modes.md` → `specs/002-deployment-modes.md`
   dangling reference spec 013 §4 item 9 already documented and
   deliberately left unfixed.
3. **`consistency-refresh-then-check-is-up-to-date`** (`kind: regression`) —
   protects the deterministic hash-diffing contract spec 013 §4 item 8
   describes (`refresh()` then immediate `check_consistency()` on
   unchanged content must report `up_to_date`).
4. **`axi-providers-no-egress-by-default`** (`kind: regression`) —
   protects the egress-off-by-default invariant spec 015 §3 describes
   (`axi_providers._no_egress_env()` strips `VOYAGE_API_KEY` unless the
   caller opts in, and restores it afterward).

Case 1 is deliberately synthetic (a fixed provider/item-count fixture,
not live repo content) so it never drifts as prose files are edited —
see spec 012's own mutation-design principle ("Generate them offline from
pinned source snapshots"), applied here in miniature. Cases 2–4 are
deliberately **real, live repository facts** — they exercise the actual
engine against actual current state, which is a stronger and more honest
regression signal than a synthetic mirror would be, at the cost of (by
design) being scoped to facts already known to be stable.

## 5. The seed reproduced usage gap: provider-starvation display quota

**Confirmed, reproduced, and fixed** before this pilot existed (PR #20,
commit `e516db769f44f0b9b71c23216bc19b04d5219a22`), per the read-only
diagnosis at
`/Users/camiloslaptop/.treehouse/firstmate-8bf1b0/6/firstmate/data/holusight-axi-evidence-routing-diagnosis/report.md`:
`holus evidence --mode auto` concatenated all four providers' items in
fixed order and sliced the first 20 for display, with no per-provider
quota. Because `exact_provider`'s own 30-match scan budget has no
per-file cap, a single early-scanned file could by itself exhaust the
entire display cap, silently pushing out every item from
already-successful providers.

The fix (`cli_axi._select_display_items`) replaced the concatenate-then-
slice merge with a bounded, deterministic round-robin over providers in
their existing fixed order. `tests/test_cli_axi.py` already carries six
unit tests proving `_select_display_items`'s correctness in isolation
(added alongside the fix itself).

**What this pilot adds that those unit tests do not**: a genuine
candidate-vs-status-quo-control comparison, with lineage and provenance,
inside the eval-pilot framework. `eval_pilot.py` reimplements the
pre-fix merge strategy as `_naive_concatenate_then_slice` — a function
kept *only* as a frozen comparator, never imported by production code
(`tests/test_eval_pilot.py::test_naive_status_quo_comparator_is_not_imported_by_production_cli`
asserts this directly by scanning `cli_axi.py`'s own source). The
`cli-axi-provider-starvation-display-quota` case runs both the shipped
candidate (`cli_axi._select_display_items`) and the frozen status-quo
comparator against the same synthetic fixture (one provider with 30
items, three others with 1–5 items each, cap 20) and asserts:

- the **candidate** must surface items from ≥3 distinct providers, and
- the **status-quo comparator** must still reproduce the historical
  starvation (≤1 distinct provider) —

so the case fails loudly if either the fix regresses *or* the frozen
comparator itself is ever edited to stop being a meaningful control.

## 6. Runner, lineage, and status-quo control

`src/codesight/eval_pilot.py::run_pilot()` is the entire runner. For each
case: look up its named grader, run it, catch any exception as a
retained `"error"` verdict (never an unhandled crash), and accumulate
results. No case can affect another case's grading.

### 6.1 Candidate lineage

Every run records a `CandidateLineage`: `candidate_id`, `repo_commit`,
`workflow`, `tool`, `model` (optional), `recorded_at`. Deliberately
**no** free-text prompt/transcript/content field —
`tests/test_eval_pilot.py::test_candidate_lineage_has_no_free_text_content_field`
pins the exact field set. This satisfies the delegated requirement to
"record workflow/model/tool context and candidate lineage without raw
prompts, private content, paths, or a central training lake": lineage is
identity metadata only, stored nowhere but the local run result the
caller chose to write (`--output`, or stdout — never auto-uploaded
anywhere).

### 6.2 Status-quo control

`kind: "comparative"` cases (currently just the one seed case) always
produce **both** a candidate verdict and a `status_quo_verdict` — never
just one. `PilotRunResult.status_quo_control` is `"included"` whenever
at least one comparative case ran in that batch, and `"not_applicable"`
when the batch contains none — so "status quo is mandatory" is a
structural, testable property (`test_status_quo_control_is_included_whenever_comparative_cases_exist`,
`test_status_quo_control_not_applicable_when_no_comparative_cases`),
never a silently-omitted comparison.

`kind: "regression"` cases have no separate live status-quo run because
there is no alternate implementation worth comparing against — their
frozen `expected` block **is** the human-approved definition of
status-quo-correct behavior (see §7 for how that gets admitted). This
matches spec 011/012's framing that "status quo composition" is always
the mandatory control condition; in a pilot this small, for cases without
a genuine second implementation, the control **is** the frozen
expectation itself, not a fabricated second code path.

### 6.3 Evaluator isolation ("candidates cannot modify their evaluator")

This pilot has no autonomous, untrusted candidate executor (explicitly
out of scope — see §14). "Candidates cannot modify their evaluator" is
therefore enforced the same way every other change to this repository
is: the frozen case file and the grader registry in `eval_pilot.py` are
ordinary version-controlled files requiring a human-reviewed PR, exactly
like any other source change (see the Agent Authority Matrix in
`AGENTS.md`). Three properties make this a testable invariant rather
than an assertion:

1. **Structural read-only access**: the runner never opens the case file
   for writing — proven, not just asserted, by running it against a
   `chmod 0o444` copy (§4).
2. **Content-hash pinning per run**: every `PilotRunResult` records
   `cases_file_hash` (`sha256` of the case file's exact bytes at run
   time). A silent edit to the frozen corpus changes this hash, making
   the tamper visible in any results diff
   (`test_cases_file_hash_recorded_and_detects_edits`).
3. **Failed runs never rewrite frozen truth**: a run that fails cases —
   even when forced to fail via a monkeypatched grader in a test — never
   touches the case file's bytes
   (`test_a_failing_run_does_not_mutate_the_frozen_case_expected_values`).

## 7. Human-approved case admission

See `docs/playbooks/eval-pilot-case-admission.md` for the full,
step-by-step path. Summary: a new case is added via an ordinary PR that
(a) appends one line to
`tests/fixtures/holusight_eval_pilot_cases.jsonl` with full provenance
(`origin`, `description`, `admitted_by`, `admitted_at`, and either
`diagnosis_ref`/`fix_ref` for a reproduced gap or a spec/ADR anchor for a
documented contract), (b) if the case needs a new grading strategy, adds
a grader function to `src/codesight/eval_pilot.py` and registers it in
`GRADERS`, and (c) passes the same human PR review every other change in
this repository requires — there is no separate, lower-friction, or
automated admission path. No agent process in this repository is
authorized to add a case to the frozen corpus without that review.

## 8. Failed-candidate retention without becoming evaluator truth

A run's `grades` list always includes every case's outcome — pass, fail,
or error — never filtered down to only the passing subset
(`test_failing_grade_is_retained_in_run_result_not_dropped`,
`test_erroring_grader_is_retained_as_error_not_raised`). A caller who
writes `--output` gets an append-friendly JSON result file per run;
nothing in this module deletes, overwrites in place, or "cleans up" a
prior run's result. A failing run is retained evidence about the
candidate that produced it — it never rewrites the frozen case's
`expected` block, which stays the sole source of "what counts as
correct" until a new human-reviewed case-admission PR changes it (§7).
This is the practical meaning of "failed candidates remain retained
evidence without becoming evaluator truth": the failure is kept, but it
has zero authority over the evaluator itself.

## 9. Relationship to specs 011/012 — explicitly not the 96-task suite

Spec 012 designs a 96-task frozen private suite with held-out splits,
two-annotator human labeling, a router benchmark across 17 provider
variants, statistical significance testing, and a multi-stage experiment
ladder up to a "first authorized one-night run" with an owner-set paid
API cap. **None of that is built here.** This pilot is deliberately the
smallest rung of spec 012's own "experiment ladder" — narrower even than
its "Free smoke" stage (12–20 tasks; $0): 4 cases, all deterministic, all
local, no held-out split (there is no untrusted candidate to hide
anything from yet — see §6.3), no statistical apparatus (4 deterministic
cases need none). Building toward spec 012's fuller design is explicitly
**not authorized** by this pilot; the delegated decision's
`second-repo-authorization` and `paid-api-benchmark-authorization` items
defer exactly that kind of expansion until this pilot produces evidence
of its own value.

## 10. Baseline note: spec 002's shipped-default drift (documented, not changed)

Per the delegated decision's `spec002-default-drift` item: "Use current
tested shipped behavior as the provisional implementation baseline. Make
the tracked specification explicitly match it or explain it... Do not
silently change the production default."

`specs/002-embedding-model-config.md`'s "Key Parameters" table states the
default embedding model is `nomic-embed-text-v1.5`. The actual shipped
default, unchanged by this pilot, is (`src/codesight/config.py`):

```python
DEFAULT_EMBEDDING_MODEL = os.environ.get(
    "CODESIGHT_EMBEDDING_MODEL",
    "voyage-code-3" if VOYAGE_API_KEY else "sentence-transformers/all-MiniLM-L6-v2",
)
```

i.e. `all-MiniLM-L6-v2` with no API key present, or `voyage-code-3` when
`VOYAGE_API_KEY` is set — **never** `nomic-embed-text-v1.5`. This is a
genuine, pre-existing spec/code drift (confirmed by reading the config
module directly, not asserted). Spec 002 now carries an explicit "Status
note" documenting this (see that file). This pilot does **not** change
`DEFAULT_EMBEDDING_MODEL`, `EMBEDDING_MODEL_REGISTRY`, or any production
default — per the delegated boundary and per this pilot's own "remain
usable without embeddings or external providers" requirement, none of
its 4 seed cases touch the embedding layer at all.

## 11. Local usage

```bash
# Run the frozen corpus once, advisory only
python -m codesight.eval_pilot run

# Also print the Fleet v1.2 aggregate scorecard preview
python -m codesight.eval_pilot run --scorecard

# Record explicit candidate lineage
python -m codesight.eval_pilot run \
  --candidate-id my-change-42 --workflow crewmate --tool holus-cli --model claude-sonnet-5

# just recipe
just eval-pilot
```

Exit code `0` means every case passed; `1` means at least one case
failed or errored. Nothing in this repository reads that exit code and
takes an automatic action — it is advisory input for a human, matching
`eval-release-gates`'s "Pilot results are advisory only."

## 12. Fleet v1.2 export (additive, not the declared entrypoint)

`eval_pilot.build_pilot_aggregate_scorecard()` produces a
`fleet.eval_scorecard.v1.2`-shaped document containing **only** counts,
rates, hashes, and a gate decision — no case questions, no excerpts, no
file paths beyond this repository's own identity
(`test_aggregate_scorecard_contains_no_raw_case_content` asserts no
synthetic-fixture marker string or file path leaks into it).
`eval_pilot.pilot_domain_result_summary()` mirrors
`fleet_scorecard.domain_result_summary()`'s exact minimal shape.

**Neither function changes `agentic/manifest.yaml`'s declared
`eval_entrypoint`**, which stays `just fleet-smoke` (the consistency
evaluator, spec 016), unchanged
(`test_fleet_manifest_entrypoint_is_unchanged_by_this_pilot`). This
pilot's Fleet export is a second, independent, additive preview — not a
replacement for the landed spec 016 wiring, and not itself wired as
anything Fleet's runner would currently invoke.

## 13. Testing

`tests/test_eval_pilot.py` (30 tests) covers, per the launch checklist:
frozen-case provenance (§4), evaluator isolation (§6.3), status-quo
comparison (§6.2), no-egress/no-key defaults, aggregate-only Fleet
export (§12), candidate lineage with no raw content (§6.1),
failed-candidate retention (§8), and derived-state delete/rebuild
equivalence (mirroring `tests/test_fleet_smoke.py` task 18's pattern).
Full suite: `uv run --extra dev pytest tests/ -x -v`. Lint:
`uv run --extra dev ruff check src/ tests/`.

## 14. Non-goals (verbatim boundary translation)

Directly from the delegated decision, translated into this pilot's
concrete implementation:

- **No deployment of any kind.** This pilot is a local Python module and
  a JSONL fixture file; nothing here starts a server or ships anywhere.
- **No private/production content.** All 4 seed cases use synthetic
  fixtures or this repository's own already-public tracked files —
  never a customer-indexed folder (the read-only invariant already
  forbids that at the engine level regardless).
- **No telemetry.** Results are local Python objects / stdout / an
  explicit `--output` file the caller chooses. Nothing is sent anywhere
  automatically.
- **No paid APIs, no external providers.** All 4 seed cases run with
  `requires_semantic: false`; the runner's default `allow_semantic=False`
  additionally refuses any case that does request it
  (`test_run_pilot_skips_semantic_required_cases_without_opt_in`). No
  case in this pilot calls Voyage, OpenAI, or any network endpoint.
- **No change to a production embedding default.** Confirmed unchanged;
  see §10.
- **No online self-modification or autonomous promotion.** The runner
  never writes to its own case file or grader registry (§6.3); nothing
  in this repository reads a verdict from this module and takes an
  automatic action (§11); `provenance_policy.default_training_eligibility`
  in `agentic/manifest.yaml` remains schema-fixed `false`, untouched by
  this pilot.
- **No nested `/code` invocation.** Not used anywhere in this change.
- **No merge.** This PR is opened and left unmerged; the configured
  merge authority decides.
