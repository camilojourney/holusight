# Playbook: Admitting a case to the eval-pilot frozen corpus

See `specs/017-holusight-safe-continuous-evaluation-pilot.md` for the full
design record. This playbook is the step-by-step admission flow for
`tests/fixtures/holusight_eval_pilot_cases.jsonl` only.

**There is exactly one admission path: an ordinary, human-reviewed PR.**
No agent process in this repository is authorized to add or edit a frozen
case without that review — this is the same authority boundary every
other change to this repository already has (see `AGENTS.md`'s Agent
Authority Matrix), applied here without exception.

## 1. When to admit a case

Admit a case when either is true:

- **A reproduced usage gap was found and fixed.** You (or an agent) found
  a real, reproducible problem in `holus`/`consistency`/related
  Holusight-AXI surfaces, fixed it, and want to make sure it stays fixed.
  This is the strongest, most valuable kind of case — it protects
  something that was actually broken once. See the seed example,
  `cli-axi-provider-starvation-display-quota`.
- **A spec already documents a deterministic contract worth protecting.**
  A spec/ADR states an invariant in prose (e.g. "X must always Y") that
  has no existing frozen regression coverage. Point `diagnosis_ref` at
  the exact spec section.

Do **not** admit a case for:

- Anything requiring private, customer, or production content — this
  pilot's fixtures must be synthetic or already-public repository
  content only (delegated policy `eval-private-retention`).
- Anything requiring a paid API or external provider by default —
  `requires_semantic: true` cases are refused unless the caller passes
  `--allow-semantic`, and none of this pilot's own cases should need it
  without a strong, separately-justified reason.
- A vague "this seems important" hunch with no reproduction and no spec
  anchor — see spec 017 §4.1's required `provenance` fields; a case
  without a real `diagnosis_ref` or spec anchor will not pass review.

## 2. Write the case

Optionally generate a paste-ready skeleton first with
`holus improve-intake "<one-sentence summary>" --origin
reproduced_usage_gap --admitted-by "<you>"` (spec 018 §3). This is purely a
convenience - it never writes to the corpus file, and it has no more
authority over admission than typing the JSON by hand. It rejects
credential-like, private, and raw-prompt text before echoing or retaining it;
this is not merely truncation. It is strictly opt-in: nothing in this
repository calls it automatically.

Append **one line** of valid JSON to
`tests/fixtures/holusight_eval_pilot_cases.jsonl` (never reformat or
reorder existing lines in the same PR — keep diffs reviewable):

```json
{"schema_version": "holus-eval-pilot-case/v1", "case_id": "your-unique-id", "family": "regression", "kind": "regression", "provenance": {"origin": "reproduced_usage_gap", "description": "one sentence: what was broken and how this case protects it", "diagnosis_ref": "path/to/report/or/spec#anchor", "fix_ref": "commit:<sha> (PR #NN)", "admitted_by": "your name or team", "admitted_at": "YYYY-MM-DD"}, "grader": "grade_your_new_thing", "fixture": {}, "expected": {}, "requires_index": false, "requires_semantic": false, "egress_allowed": false, "notes": "why this case exists, for a future reader"}
```

Required `provenance` fields (validated at load time —
`eval_pilot.load_cases()` raises, not skips, on any case missing one):
`origin`, `description`, `admitted_by`, `admitted_at`. `origin` must be
one of `reproduced_usage_gap`, `spec_documented_finding`,
`spec_documented_contract`.

`kind` is `"regression"` unless you are demonstrating a genuine
candidate-vs-alternate-implementation comparison, in which case use
`"comparative"` and see step 4.

## 3. Write (or reuse) a grader

If an existing grader in `src/codesight/eval_pilot.py`'s `GRADERS`
registry already fits (e.g. another dangling-reference case can reuse
`grade_known_dangling_reference_case` with a different `fixture.doc_path`),
just point your case's `"grader"` field at it — no code change needed.

Otherwise, add a new `grade_*(case: dict, repo_root: Path, ctx: RunContext) -> CaseGrade`
function and register it in `GRADERS`. Requirements for a new grader:

- **Deterministic by default.** No embedding calls, no network calls,
  unless the case explicitly sets `requires_semantic: true` (and even
  then the runner refuses to run it without `--allow-semantic`).
- **Never raises for an ordinary fail.** Return a `CaseGrade` with
  `verdict="fail"` for a normal mismatch. Let genuine programming/fixture
  errors propagate — `run_pilot()` catches them and records
  `verdict="error"` so a broken fixture never crashes the whole run.
- **Never writes to the repository, the case file, or any real
  `.holusight/` cache this worktree owns.** Consistency-engine-backed
  graders must operate on a `tempfile.TemporaryDirectory()` synthetic
  repo, exactly like `grade_refresh_then_check_up_to_date` does.
- **`detail` strings must stay free of absolute host paths** — use
  repo-relative paths or values only (this pilot's own tests assert this;
  see `test_grade_detail_never_contains_an_absolute_host_path`).

## 4. Comparative cases: adding a status-quo comparator

A `"comparative"` case must also provide a frozen, pinned alternate
implementation to compare the candidate against - kept purely as an
eval-pilot fixture, **never imported by production code**. Follow the
pattern in `eval_pilot._naive_concatenate_then_slice`: a small, clearly
commented pure function whose only job is to reproduce the historical
"before" behavior, plus a test proving production code never imports it
(mirror `test_naive_status_quo_comparator_is_not_imported_by_production_cli`).

## 5. Verify locally before opening the PR

```bash
uv run --extra dev pytest tests/test_eval_pilot.py -x -v
uv run --extra dev ruff check src/ tests/
python -m codesight.eval_pilot run --scorecard
```

Confirm your new case appears in the run output with the verdict you
expect, and that the full suite (`just check`) still passes.
`holus improve-run --scorecard` is the schema-generated CLI equivalent of
`python -m codesight.eval_pilot run --scorecard` (spec 018 §4) — either
works.

If your case needs a new fixture file (not a JSONL line — an actual new
file under `tests/fixtures/`), check its path first with
`holus improve-placement --artifact-type fixture --proposed-path
<path>` (spec 018 §6) to catch a wrong-directory or duplicate-name mistake
before you write it.

## 6. Open the PR

Ordinary PR, ordinary review — the same bar as any other change in this
repository. The reviewer should specifically confirm:

- The case's `provenance` is real and verifiable (a real commit/PR
  reference, or a real spec/ADR section — not a fabricated citation).
- The grader is deterministic and side-effect-free per step 3.
- If `kind: "comparative"`, the status-quo comparator is genuinely frozen,
  registered by the evaluator, and demonstrably not imported by production code.
- Any temporary or external corpus is untrusted advisory input: it cannot
  produce a passing promotion scorecard or pre-promotion evidence.

## 7. What happens to a case that starts failing later

A case that starts failing (because behavior genuinely regressed) is a
signal, not an emergency stop — this pilot is advisory only (spec 017
§14: no autonomous promotion, nothing acts on a verdict automatically).
The failing result is retained as evidence; it does not get silently
edited away. If the failure reveals the *case* itself was wrong (not the
code), fix the case in a new, separately reviewed PR with an updated
`notes` field explaining why — never quietly loosen `expected` without
explanation.
