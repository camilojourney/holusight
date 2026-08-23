# Holusight Continuous-Improvement Loop v1

**Status:** Phase 1 implemented (bounded direct-PR).
**Authorization boundary:** captain-authorized direct-PR under Holusight's
registered `direct-PR +yolo` posture (see the launch brief this PR
implements). Scoped to: no nested `/code`, no deploy, no paid APIs or
external egress by default, no central trace/training store, no private or
production data, no online self-modification, no autonomous promotion, no
auto-merge based only on evaluation, no merge. See
[Non-goals](#8-non-goals).

## 1. Relationship to specs 011-017

This spec adds no new provider, no new retrieval mechanism, and does not
duplicate any Fleet contract. It is the smallest coherent lifecycle wrapper
around already-shipped Holusight-AXI work:

- **`src/codesight/eval_pilot.py`** (spec 017, PR #21) — the frozen case
  corpus, deterministic runner (`run_pilot`), candidate lineage, status-quo
  comparator pattern, and Fleet v1.2-shaped aggregate export. This spec
  extends that module with two additive functions
  (`build_intake_proposal`, `evaluate_progress`) and does not change any
  existing function's behavior or signature.
- **`src/codesight/cli_axi.py` / `src/codesight/axi_schema.py`**
  (spec 015, PR #18) — the schema-generated `holus` command surface. This
  spec adds four commands to the same `AXI_COMMANDS` tuple rather than
  creating a second CLI.
- **`src/codesight/consistency.py`** (spec 013, PR #16) and
  **`.claude/rules/structure.md`** — the structural placement guard reads
  the same structure contract `consistency.py`'s classifier already relies
  on; it adds no new classification logic of its own.
- **`src/codesight/fleet_scorecard.py`** (spec 016, PR #19) — unchanged.
  `agentic/manifest.yaml`'s `eval_entrypoint` stays `just fleet-smoke`.

The full lifecycle this spec ships:

```text
explicit observed gap                    (holus improve-intake, opt-in)
  -> sanitized reproducible case            (content-minimized proposal, no write)
  -> human-reviewed frozen-case admission    (ordinary PR against tests/fixtures/*.jsonl)
  -> status-quo baseline + candidate eval    (holus improve-run, reuses eval_pilot.run_pilot)
  -> deterministic scorecard and lineage     (build_pilot_aggregate_scorecard, CandidateLineage)
  -> stagnation / research-needed signal     (evaluate_progress -- structured, never launched)
  -> human-controlled promotion or rollback  (lifecycle.promotion.allowed is always false)
  -> retained regression case                (frozen corpus keeps growing, one PR at a time)
```

Placement compliance (`holus improve-placement`) is a parallel, standalone
concern in the same command family: before *any* proposed repository
artifact is created (a case, a spec, a test, a doc), check it against
`.claude/rules/structure.md` and existing files first.

## 2. `holus improve-*` command family

Four commands, added to the same schema `axi_skill_gen.py` renders into
`.claude/skills/holus/SKILL.md` (`AXI_SCHEMA_VERSION` bumped `0.1.0` ->
`0.2.0`):

| Command | Job |
|---|---|
| `holus improve-status` | Frozen-case corpus summary, status-quo coverage, placement-guard capability advertisement. Read-only. |
| `holus improve-intake "<summary>"` | Explicit, opt-in, content-minimized proposed regression case for human review. Never writes a file. |
| `holus improve-run` | Runs the frozen corpus (wraps `eval_pilot.run_pilot`), records lineage, reports `research_needed`/`stagnated`/`improved` progress against an optional prior run, always reports `promotion.allowed: false`. |
| `holus improve-placement` | Validates a proposed artifact path against structure/canonical-location/duplicate-name evidence. Never edits files. |

None of the four introduces a write path. `improve-run --output <path>`
writes only the caller-specified *output* artifact (a run result the
caller asked for), never anything inside the tracked repository.

## 3. Intake: opt-in, content-minimized, no silent capture

`holus improve-intake "<summary>"` (`eval_pilot.build_intake_proposal`):

- **Opt-in only.** Nothing in this repository calls it automatically —
  it is a command a human or agent runs deliberately, with a plain-text
  summary they chose to type, exactly like every other `holus` command.
  There is no hook, no wrapper, no background capture of prompts, tool
  transcripts, file content, credentials, or telemetry.
- **Content-minimized.** The summary is trimmed to 240 characters before
  it is echoed back as `provenance.description`. This is not a secrets
  scanner — it is a bound on how much free text the loop will ever carry
  forward, consistent with `CandidateLineage`'s existing no-free-text-field
  contract (spec 017 §4.6).
- **No write.** `build_intake_proposal` returns a proposal object; it
  never opens `tests/fixtures/holusight_eval_pilot_cases.jsonl` (or any
  file) for writing. Duplicate-`case_id` detection is advisory (reads the
  corpus if `--cases` is given, to warn before the human pastes a
  colliding id into a PR).
- **Admission is unchanged.** Turning a proposal into a real frozen case
  is still exactly the process `docs/playbooks/eval-pilot-case-admission.md`
  already documents: paste the proposal's fields into one JSONL line, open
  an ordinary PR, get ordinary review. `holus improve-intake` only
  produces the paste-ready skeleton — it has no more authority over the
  frozen corpus than a human typing the JSON by hand did before this spec.

## 4. Run: candidate vs. mandatory status-quo, immutable lineage

`holus improve-run` is a thin CLI wrapper over `eval_pilot.run_pilot` —
see spec 017 §4 for the underlying guarantees this inherits unchanged:
never opens the case file for writing, records `CandidateLineage`
(`candidate_id`, `repo_commit`, `workflow`, `tool`, `model` — no free-text
content field), retains failed/errored grades as evidence, and strips
`VOYAGE_API_KEY` from its own process environment unless `--allow-egress`
is passed.

This spec adds two things on top:

1. **`--compare-result <path>` and `evaluate_progress`.** Given a prior
   run's JSON output (loaded via `load_prior_run`, which validates the
   shape and raises rather than silently guessing on a malformed path),
   the current run's `counts` are compared to the prior run's `counts`
   only — no case content, no prompts. The result is one of four
   machine-readable outcomes:

   | `outcome` | Meaning | `recommended_research` |
   |---|---|---|
   | `improved` | Pass rate increased. | `null` |
   | `research_needed` | No prior run, or errored-case count increased (instability, not simple regression). | `normal_review` |
   | `stagnated` | Pass rate decreased, or unchanged from the prior run. | `gpt_deep_research` |

   `recommended_research` is a **string label only** — `normal_review` or
   `gpt_deep_research`. Nothing in this repository reads that string and
   launches anything; see `~/.claude/skills/gpt-deep-research/SKILL.md`
   for the (separately human-triggered) tool this label would point a
   human at.

2. **Explicit non-promotion.** Every `improve-run` payload carries
   `lifecycle.promotion = {"allowed": false, "status":
   "human_review_required", "reason": "no automatic promotion or
   rollback"}` unconditionally — this is not conditioned on the run's
   outcome. See `tests/test_improve_loop.py::test_refuses_automatic_
   promotion_regardless_of_outcome`.

### 4.1 Proof: the already-reproduced regression, end to end

`holus improve-run` reproduces the `cli-axi-provider-starvation-display-
quota` frozen case (spec 017 §4, the real PR #20 fix) through the new CLI
surface: the candidate (`cli_axi._select_display_items`) passes, and the
frozen pre-fix status-quo comparator (`eval_pilot.
_naive_concatenate_then_slice`) still reproduces the historical starvation
on the same synthetic fixture. See
`tests/test_improve_loop.py::test_improve_run_reproduces_the_display_
quota_regression_via_cli`.

## 5. Aggregate export: Fleet v1.2-shaped, content-free

`--scorecard` on `improve-run` calls the already-shipped
`eval_pilot.build_pilot_aggregate_scorecard` unchanged (spec 017 §6) — no
new export format, no new Fleet contract surface. `scores` stays counts/
rates/hashes only; see `tests/test_improve_loop.py::test_refuses_private_
or_raw_content_export_in_scorecard`.

## 6. Repository-placement compliance

`holus improve-placement --artifact-type <type> --proposed-path <path>`
(`cli_axi._placement_recommendation`) checks a proposed artifact path
against `.claude/rules/structure.md` before it exists, using three signals:

1. **Canonical-location membership** — is the proposed path inside the
   root(s) `.claude/rules/structure.md` documents for that artifact type
   (`specs/` for `spec`, `docs/decisions/` for `adr`, `tests/fixtures/`
   for `case`/`fixture`, ...)?
2. **Structural fine print**, applied per artifact type rather than as one
   universal rule (deliberately narrow — see [§8](#8-non-goals)):
   - `spec`: `specs/` is flat — a proposed path in a subdirectory is
     rejected (`.claude/rules/structure.md`: "Flat structure only. No
     subdirectories.").
   - `docs` (the generic top-level type, distinct from `adr`/`playbook`
     which already have their own subdirectories): only the three fixed
     files `docs/README.md`, `docs/vision.md`, `docs/roadmap.md` are
     canonical — anything else under `docs/` is exactly the
     `docs/RESEARCH.md`/`docs/MARKET.md`-shaped "legacy violation"
     `AGENTS.md` already calls out by name, so it is refused with
     `guidance` pointing at `adr`/`playbook`/`spec` instead, and
     `recommended_path` is `null` (there is no safe auto-generated
     fallback path for an ad-hoc docs/ file — the caller must pick a
     different artifact type).
   - `test`: must be `test_*.py` directly under `tests/` (not nested, and
     not confused with `tests/fixtures/`, which is the separate
     `case`/`fixture` type).
3. **Duplicate-name detection** — `rglob`s the artifact type's canonical
   root(s) for an existing file with the same basename, so a caller
   proposing `tests/test_eval_pilot.py` when that file already exists is
   told so, rather than silently allowed to shadow it.

**Never edits files.** `_placement_recommendation` and its
`_recommended_new_path` helper only call `.exists()` / `.is_dir()` /
`.rglob()` — read-only filesystem operations. (A prior draft of this
change called `.mkdir(parents=True, exist_ok=True)` on the fallback root
before checking name collisions; that write path was removed before this
PR, and `tests/test_improve_loop.py::test_placement_never_creates_a_
directory_on_disk` proves the read-only property directly, independent of
whether every schema-declared artifact type's root happens to already
exist in this repository.)

**Path-traversal / absolute-path safe.** An absolute or `..`-escaping
`--proposed-path` never reaches a filesystem check against anything
outside this repository — `cli_axi._safe_repo_relative_path` resolves and
bounds-checks the path before any `.exists()`/`.is_dir()` call is made
against it; an unsafe path is reported as simply not-canonical, with no
information about the host filesystem leaked into the response.

### 6.1 Proof: the duplicate-artifact case

`holus improve-placement --artifact-type test --proposed-path
tests/test_eval_pilot.py` (a real, already-existing file) reports
`status: blocked`, `duplicate_hits: ["tests/test_eval_pilot.py"]`,
`recommended_action: adjust_path_and_retry`. See
`tests/test_improve_loop.py::test_placement_blocks_duplicate_artifact_
name`.

## 7. Negative tests (the launch checklist's explicit refusals)

All in `tests/test_improve_loop.py`, section 5:

| Refusal | Proof |
|---|---|
| Evaluator mutation | `test_refuses_evaluator_mutation_via_intake_or_run` — case file bytes unchanged after `improve-intake` and `improve-run`. |
| Private/raw-content export | `test_refuses_private_or_raw_content_export_in_scorecard`, `test_refuses_private_or_raw_content_export_via_intake_summary_truncation`. |
| Automatic promotion | `test_refuses_automatic_promotion_regardless_of_outcome`. |
| External egress | `test_refuses_external_egress_by_default` — a real `VOYAGE_API_KEY` set in the test process never appears in `improve-run`'s output, and `egress_allowed`/`semantic_allowed` stay `false` without `--allow-egress`/`--allow-semantic`. |
| Unsupported placement | `test_refuses_unsupported_placement_artifact_type_as_usage_error` (schema-level `choices` rejection, exit 2), `test_e2e_unsupported_placement_type_exits_2` (real subprocess), plus the canonical-location/duplicate/docs-root/subdirectory refusals in section 4. |

## 8. Non-goals

Verbatim from the launch brief, unchanged by this implementation:

- No nested `/code` invocation, no deploy, no paid APIs, no external
  egress by default.
- No central Fleet trace/training store — `improve-intake` proposals and
  `improve-run` results are local values returned to the caller; nothing
  is written to a shared store by this loop.
- No private or production data — intake is opt-in plain text the caller
  chose to type; the frozen corpus stays synthetic/repository-owned per
  spec 017 §4.2/§14.
- No online self-modification — this loop does not alter its own code,
  evaluator, or the `holus` schema at runtime.
- No autonomous promotion, auto-merge based only on evaluation, or merge.
- No universal directory migration — placement compliance is additive
  evidence over the existing `.claude/rules/structure.md` contract, not a
  rewrite of it.
- No claim of evaluation quality beyond the frozen cases actually run —
  unchanged from spec 017 §14.

## 9. Files changed

- `src/codesight/axi_schema.py` — four new `AxiCommand` entries,
  `AXI_SCHEMA_VERSION` `0.1.0` -> `0.2.0`.
- `src/codesight/cli_axi.py` — four new handlers, the placement-guard
  helpers (`_placement_recommendation`, `_safe_repo_relative_path`,
  `_recommended_new_path`, `_find_duplicate_artifacts`).
- `src/codesight/eval_pilot.py` — `build_intake_proposal`,
  `load_prior_run`, `evaluate_progress` (additive; no changes to any
  spec-017 function's behavior).
- `.claude/skills/holus/SKILL.md` — regenerated via
  `python -m codesight.axi_skill_gen`.
- `.claude/rules/structure.md`, `AGENTS.md` — documented
  `tests/fixtures/*.jsonl` as the canonical case-corpus location.
- `ARCHITECTURE.md` — new "Continuous-Improvement Loop v1" section.
- `docs/decisions/0014-continuous-improvement-loop-placement-guard.md` —
  decision record for the placement-guard scope boundary (evidence-only,
  never auto-edits; fixed `docs/` allowlist; per-type structural rules
  rather than a universal migration).
- `docs/playbooks/eval-pilot-case-admission.md` — step 2 now points at
  `holus improve-intake` as the recommended way to generate the
  paste-ready proposal skeleton.
- `tests/test_improve_loop.py` — new, 29 tests.
