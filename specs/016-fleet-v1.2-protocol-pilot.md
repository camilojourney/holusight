# Fleet v1.2 Protocol Pilot

## 1. Purpose

Wire Holusight's repository manifest and its existing Phase 1
documentation-code consistency evaluator (`src/codesight/consistency.py`,
spec 013) to Fleet's canonical, now-landed `v1.2` agentic contracts —
without reconstructing, forking, or vendoring those contracts into this
repository. This is a bounded pilot: it wires two contract-required
touchpoints (a repo manifest and a scorecard producer), adds a local
no-spend smoke suite, and stops there.

See `docs/decisions/0012-fleet-v1.2-protocol-wiring.md` for the decision
record this spec implements.

## 2. Contract provenance

The canonical source for everything this pilot wires against:

```
Repository: github.com/camilojourney/fleet-system
Commit:     7d396b30f0250a414f9115964c945e29b7afb267 (origin/main)
PR:         https://github.com/camilojourney/fleet-system/pull/58
            "feat: extend agentic contracts to v1.2 with provenance boundary ADR"
```

Files read (never copied) from that commit:

| File | What it defines |
|---|---|
| `system/shared/contracts/agentic/repo-agent-manifest.schema.json` | `fleet.repo_agent_manifest.v1.2` — required `eval_entrypoint`, `privacy`, `provenance_policy`. |
| `system/shared/contracts/agentic/memory-policy.schema.json` | `fleet.memory_policy.v1.1` — required `fleet_visibility` (unchanged by the v1.1→v1.2 transition). |
| `system/shared/contracts/agentic/eval-scorecard.schema.json` | `fleet.eval_scorecard.v1.2` — required `cross_project_metrics`, `artifacts`; the non-negotiable `gate_decision: pass` ⇒ `hidden_correctness.status: pass` conditional. |
| `system/shared/contracts/agentic/agent-trace.schema.json` | `fleet.agent_trace.v1.2` — referenced for context; this pilot does not emit trace documents (see §4). |
| `system/shared/contracts/agentic/ADR-001-fleet-responsibility-boundary.md` | The ownership boundary: Fleet owns contracts/runner/skills; repos own domain evaluators, `scores`, and release authority; Holusight/Graphify own rebuildable derived understanding, never canonical truth. |
| `system/shared/contracts/agentic/VERSIONING.md` | The `v1 → v1.1 → v1.2` additive migration policy this pilot follows. |
| `system/shared/scripts/run_repo_eval.py` | The canonical runner: how `eval_entrypoint.command` is invoked, and the exact `parse_domain_result()` contract for its stdout (§4). |
| `system/shared/scripts/eval_privacy_boundary.py` | The five required exclusion categories (`REQUIRED_EXCLUSION_CATEGORIES`) `not_exported_to_fleet` must cover. |

**How this was located:** `graphify` and `fleet_graphify.py` were
unavailable in this execution environment (confirmed by direct invocation
attempt — see the worker's status log). Per this repo's own documented
degrade pattern (`AGENTS.md`, "the eval harness's Graphify baseline,
`consistency.py`'s structural provider — must degrade to an explicit
'unavailable' result rather than fail, and does"), discovery fell back to
inspecting the `fleet-system` repository directly: its git log,
`system/shared/contracts/agentic/` tree, and the commit that introduced
`v1.2` (`7d396b3`, merged as PR #58 the same day this pilot started).

## 3. What is wired, and where

| Fleet requirement | Holusight artifact |
|---|---|
| A repo declares one `eval_entrypoint` | `agentic/manifest.yaml`: `command: just fleet-smoke` |
| A repo declares a `privacy` boundary that `agentic/memory.yaml`'s `fleet_visibility` must agree with exactly | `agentic/manifest.yaml` + `agentic/memory.yaml`, byte-identical `exported_to_fleet` / `not_exported_to_fleet` lists |
| `fleet.repo_agent_manifest.v1.2` requires `provenance_policy` with `default_training_eligibility: false` | `agentic/manifest.yaml`'s `provenance_policy` block |
| The runner's `parse_domain_result()` reads a JSON object from the entrypoint's last stdout line | `src/codesight/fleet_scorecard.py::main()` — printed by `just fleet-smoke` |
| A domain evaluator's four outcomes, honestly shaped into `fleet.eval_scorecard.v1.2` | `src/codesight/fleet_scorecard.py::build_eval_scorecard()`, exercised for all four outcomes in `tests/test_fleet_smoke.py` (tasks 7–10) |

`src/codesight/consistency.py` itself is **not modified** by this pilot.
`fleet_scorecard.py` reads its output (`ConsistencyReport`); it does not
change how consistency is computed.

## 4. Two outputs, not one — and why

Fleet's `run_repo_eval.py` does the heavy lifting of assembling a full
`eval-scorecard`/`agent-trace` envelope itself (identity hashes,
`repo_commit`, `environment`, retry semantics) around whatever a repo's
`eval_entrypoint` reports. The entrypoint's own contract, read directly
from `parse_domain_result()`'s docstring, is minimal: its stdout's last
non-blank line, if present, must be one JSON object with an optional
`hidden_correctness`, an optional `scores`, and any of
`human_correction_burden`/`regressions`/`total_cost_usd`/`handoff_loss`.

So `fleet_scorecard.py` produces two different things for two different
consumers:

1. **`domain_result_summary()`** — the minimal dict above. This is what
   `just fleet-smoke` actually prints as its last line, and it is what a
   real invocation of Fleet's `run_repo_eval.py` (if Fleet ever points its
   runner at this repository) would actually consume.
2. **`build_eval_scorecard()`** — a full `fleet.eval_scorecard.v1.2`
   document. This is Holusight's own local, honest *preview* of what one
   `ConsistencyReport` looks like normalized into Fleet's envelope shape —
   used by the smoke suite to prove the shaping logic is correct, and
   available for inspection. It is not a claim that Fleet's runner already
   emits this: see §6.

## 5. The four consistency outcomes, mapped honestly

`consistency.check_consistency()` is explicit in its own docstring that it
performs "deterministic hash-diffing, not semantic value comparison": it
reports *that* something changed since the cache's last refresh, not
*whether* the content is still semantically consistent. The mapping in
`fleet_scorecard.py` reflects exactly that limit — it does not claim more
correctness knowledge than the evaluator has:

| `ConsistencyStatus` | `gate_decision` | `hidden_correctness.status` | Why |
|---|---|---|---|
| `up_to_date` | `pass` | `pass` | The one claim this evaluator can actually stand behind: nothing changed, cache still matches disk. |
| `spec_changed_awaiting_implementation` | `hold` | `unknown` | A change happened; this evaluator has no semantic power to confirm the result is still consistent. |
| `possible_undocumented_drift` | `fail` | `fail` | The one outcome this evaluator exists specifically to catch. |
| `coordinated_change` | `hold` | `unknown` | Both sides changed together; still no semantic confirmation available. |
| `unknown_concept` | — (no scorecard) | — | Not one of the four outcomes — nothing was evaluated, so `build_eval_scorecard()` raises `ValueError` rather than fabricating a verdict. |

`hidden_correctness.source` is always `"domain_evaluator"` — never
`self_reported_success`/`completion`/`pr_created`/`output_bytes`, which
Fleet's schema deliberately excludes from
`cross_project_metrics.hidden_correctness.source`'s enum and this pilot
never sets. `tests/test_fleet_smoke.py` task 17 proves the schema's own
non-negotiable clause (`gate_decision: pass` ⇒
`hidden_correctness.status: pass`) holds for all four outcomes by
construction, not just the one case exercised in a single run.

## 6. Scorecard truth and limitations

- `build_eval_scorecard()`'s output is **not** what Fleet's
  `run_repo_eval.py` currently emits. As read directly from
  `run_repo_eval.py` at commit `7d396b3`: it accepts a
  `fleet.repo_agent_manifest.v1.2` manifest as valid input (a v1.2
  manifest is a strict superset of v1.1's requirements), but its own
  emitted scorecard still hardcodes `"schema":
  "fleet.eval_scorecard.v1.1"` and has no `artifacts` key. v1.2 *output*
  emission is listed in PR #58's own commit message as deferred Fleet-side
  work, not yet landed. `build_eval_scorecard()` is Holusight's own,
  independently correct v1.2-shaped document — useful to prove the
  mapping and prepare for when Fleet's runner does emit v1.2, but not
  itself proof that integration has happened.
- The JSON Schema files themselves are not vendored into this repository
  (per ADR-0012), so nothing in `tests/test_fleet_smoke.py` runs
  `jsonschema.validate()` against the real schema. Tests instead assert
  the specific shape constraints the schema enforces (hash regex,
  required fields, the gate/hidden-correctness invariant) as a proxy. A
  future schema change on Fleet's side would not be caught here until
  someone re-reads the canonical source and updates this pilot to match.
- `input_hash`/`fixture_set_hash`/`result_hash` are genuine SHA-256
  digests of this evaluator's own concept id, commit, and linked-artifact
  set — not placeholders — but they are **not** the same hashes
  `run_repo_eval.py` would compute (it hashes `input_payload`/a fixture
  directory the caller supplies, which this pilot does not define, since
  there is no separate frozen task corpus for a documentation-consistency
  check the way there is for a coding-task evaluator).
- `repo_commit` in every scorecard this pilot builds is supplied by the
  caller, not auto-derived inside `build_eval_scorecard()` — this keeps
  the function pure and testable with synthetic commits; real callers
  (the smoke suite's own aggregate line, or any future direct use) are
  responsible for passing this repository's actual `git_utils.current_commit()`.
- `total_cost_usd: 0.0` is a genuine, verifiable claim: the `exact` and
  `structural` providers make zero API calls (no embeddings, no LLM
  calls), and nothing in this pilot's code path touches the network — see
  §7.

## 7. No-spend, no-telemetry, no-promotion boundaries

- **No spend:** `tests/test_fleet_smoke.py` and `fleet_scorecard.py` only
  call `consistency.refresh()`/`check_consistency()` with the default
  `run_semantic=False` — the semantic provider (the only one that could
  call an embedding model) is never invoked anywhere in this pilot. Tasks
  5 and 6 assert this directly.
- **No telemetry:** nothing in this pilot makes a network call, writes
  outside `.holusight/` (already-gitignored derived state) or `agentic/`
  (committed, inert YAML/Markdown), or contacts Fleet in any way. The
  scorecards this pilot builds are local Python dicts / stdout JSON —
  there is no export step in this PR.
- **No autonomous promotion:** `gate_decision` and `hidden_correctness`
  are informational output only. Nothing in this repository — not this
  pilot's code, not any CI hook, not `just fleet-smoke` — reads a
  `gate_decision` and takes an action (merge, deploy, retrain) based on
  it. `provenance_policy.default_training_eligibility` is schema-fixed to
  `false`, and nothing in this pilot sets any trace's per-payload
  `training_eligibility` to `true` (this pilot emits no `agent-trace`
  documents at all — see §4).
- **Semantic-provider default unchanged:** `consistency.refresh()`'s
  `run_semantic` parameter still defaults to `False`; this pilot adds no
  code path that changes that default or calls it with `run_semantic=True`.

## 8. Non-goals

Matching the launch instructions exactly:

- No nested `/code` invocation.
- No deployment of any kind.
- No exposure of private or customer content (the `not_exported_to_fleet`
  boundary in `agentic/manifest.yaml` / `agentic/memory.yaml` explicitly
  covers this, per §7 of `eval_privacy_boundary.py`'s required
  categories).
- No new root-level `fleet` CLI path — `fleet_scorecard.py` is a library
  module plus a `python -m codesight.fleet_scorecard smoke` entrypoint,
  not a new subcommand under `python -m codesight` or `holus`.
- No duplication of the `holus`/AXI command surface (PR #18): this pilot
  calls `consistency.check_consistency()` directly (the same function
  `holus check` calls), rather than adding a second CLI wrapper around
  the same job.
- No CI enforcement or merge blocking based on any scorecard this pilot
  produces.

## 9. Relationship to other in-flight/landed work

- **Spec 013** (`consistency.py`, PR #16) — the evaluator this pilot
  wires to. Unmodified.
- **Spec 014** (retrieval evaluation harness, PR #17) — unrelated
  surface (`tests/eval_holusight.py`); not touched.
- **Spec 015** (`holus` AXI command surface, PR #18) — landed on
  `origin/master` mid-pilot (merged as this pilot's branch was created).
  This pilot rebased onto it and deliberately reuses
  `consistency.check_consistency()` rather than adding a parallel CLI —
  see §8 and ADR-0012's alternatives table.
- **`fm/holusight-axi-consistency-phase1`** (a separate, still-unmerged
  remote branch, diverged from the version of Phase 1 that actually
  landed as PR #16) — untouched by this pilot; this pilot branches from
  `origin/master` after PR #16/#17/#18, not from that branch, and shares
  no commits or files with it.

## 10. Local no-spend smoke suite

`tests/test_fleet_smoke.py` — 20 independently-runnable tasks, exact and
structural providers only, no network, no `.env`/API-key dependency. Also
serves as `agentic/manifest.yaml`'s declared `eval_entrypoint`'s test
surface (run via `just fleet-smoke`). See that file's module docstring for
the full task list; summary:

- Tasks 1–2: exact provider (reference resolution, dangling-reference
  detection).
- Tasks 3–4: **partial-result survival** — a missing or corrupt
  `graphify-out/graph.json` degrades the structural provider to
  `unavailable` without raising, and `refresh()` still completes using
  exact-provider results alone.
- Tasks 5–6: provider-scope discipline (semantic never runs by default).
- Tasks 7–11: the four consistency outcomes map to the table in §5;
  `unknown_concept` correctly has no scorecard.
- Tasks 12–17: scorecard shape (schema string, hash patterns, commit
  pattern, zero cost, honestly-empty `artifacts`, the
  gate/hidden-correctness invariant across all four outcomes).
- Task 18: **`.holusight/` delete/rebuild equivalence** — deleting the
  cache directory entirely and re-running `refresh()` reproduces the same
  `gate_decision`, `hidden_correctness`, `scores`, and content-derived
  hashes for the same on-disk content. (Generic artifact-count rebuild
  equivalence is already covered by `tests/test_cli_axi.py` from PR #18;
  this task specifically proves the *Fleet-shaped* result a caller would
  act on survives a rebuild, which is new coverage.)
- Tasks 19–20: the entrypoint's own `domain_result_summary()` output
  satisfies `run_repo_eval.py`'s `parse_domain_result()` contract exactly.
