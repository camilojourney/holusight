# Holusight ↔ Graphify Integration: Actual State and Highest-Leverage Work

> Audit performed 2026-09-29 against worktree
> `/Users/camiloslaptop/.treehouse/firstmate-7bab20/5/firstmate/projects/holusight`
> at `HEAD = c51870c3b0c058ca8ed756ee3fbb9d0a78afe4c0` ("Add project-local holusight skill bootstrap (#69)"),
> worktree dirty (`M .gitignore` only).
> Every claim below is from source code read directly or from command output reproduced verbatim.
> Where a repo document asserts something the code does not do, both are cited and the conflict is called out.

## Headline

The integration is **real but degenerate**. The graph file is present, tracked, and rich (6,214 edges including 1,494 symbol-level `calls` edges with line numbers). Holusight's `structural` provider **never reads a single edge** — it substring-matches query tokens against node-ID strings. It is a fuzzy filename/symbol grep wearing the word "structural." Separately, the graph is **permanently and unfixably stale by construction** (squash-merge guarantees `built_at_commit` can never equal `HEAD`), and the project's own agent instruction says never to trust a `stale` provider — so agents are told to discard 100% of structural output. Finally, the one harness that could measure structural value has been **silently scoring 0 on all 60 code queries since the codesight→holusight rename**, because its ground-truth paths still say `src/codesight/`.

---

## Q1. How does Holusight's structural provider actually consume the graph?

### Takeaway
`_load_structural_index` loads only `id → source_file` maps plus the raw `links` list; `structural_edges_for` (used by the consistency engine) collapses symbol-level edges to **file-to-file** and **discards direction**; and the `holus`-facing `structural_provider` **ignores `links` entirely**, doing substring token matching over node-ID strings. Nodes, symbols, and call relationships are all present in the data and essentially unused.

### Cited Findings

- `_load_structural_index` at `src/holusight/consistency.py:436-460` reads `graphify-out/graph.json` and builds exactly three things: `node_file: dict[node_id -> source_file]`, `file_nodes: dict[source_file -> [node_id]]`, and `links` (the raw list). It keeps `built_at_commit`. It **stores no node labels, no node types, no line numbers** — `_StructuralIndex.__slots__` is `("available", "built_at_commit", "node_file", "file_nodes", "links")` (`consistency.py:419`).
- Expected `graph.json` shape, verified by loading the real file: top-level keys `['directed', 'multigraph', 'graph', 'nodes', 'links', 'hyperedges', 'built_at_commit']`. `directed = False`. `nodes` = 3,858. `links` = 6,214. `hyperedges` = 0. `built_at_commit = '292e35f7729f548829af08d240df13254a5ab4f5'`. — command output, `python3 -c "import json; d=json.load(open('graphify-out/graph.json'))..."`
- Node records carry far more than the loader keeps. Real sample:
  `{"label": "CandidateLineage", "file_type": "code", "source_file": "src/holusight/eval_pilot.py", "source_location": "L127", "_callable": true, "_callable_class": true, "_origin": "ast", "id": "src_holusight_eval_pilot_candidatelineage", "community": 1, "community_name": "eval_pilot.py", "norm_label": "candidatelineage"}`. `type` is present on only 1 of 3,858 nodes (`'package'`); the other 3,857 have `type: None`. — command output
- Link records are directed in payload and carry call sites. Real sample:
  `{"relation": "calls", "context": "call", "confidence": "EXTRACTED", "source_file": "src/holusight/agent_focus.py", "source_location": "L377", "weight": 1.0, "_origin": "ast", "source": "src_holusight_agent_focus_build_context_pack", "target": "src_holusight_agent_focus_read", "confidence_score": 1.0}` — command output
- Edge relation inventory (all 6,214): `contains` 2,502 · `calls` 1,494 · `references` 644 · `rationale_for` 532 · `method` 434 · `uses` 200 · `imports_from` 139 · `imports` 124 · `inherits` 82 · `indirect_call` 60 · `re_exports` 3. Confidence labels: `EXTRACTED` 5,920, `INFERRED` 294. — command output
- `structural_edges_for` (`consistency.py:474-521`) is **direction-blind**: `if source in node_ids: other_file = index.node_file.get(target)` / `elif target in node_ids: other_file = index.node_file.get(source)` (`consistency.py:488-493`). Caller and callee are treated identically. It then emits `Edge(from_ref=f"artifact:{artifact_path}", to_ref=f"artifact:{other_file}", ...)` (`consistency.py:506-507`) — **file granularity**, deduped by `key = (other_file, relation)` (`consistency.py:499`), so all 1,494 individual call sites between two files collapse to one edge with no symbol and no line.
- The `holus`-facing provider is worse: `structural_provider` at `src/holusight/axi_providers.py:227-307` calls `_load_structural_index` and `structural_graph_freshness`, then iterates **`index.file_nodes` only** — `haystack = path.lower() + " " + " ".join(node_ids).lower()` / `if not any(tok in haystack for tok in tokens): continue` (`axi_providers.py:253-256`). `index.links` is **never referenced anywhere in the function**. Every item it emits has `relation="graphify:node_match"` and hardcoded `confidence=0.5` (`axi_providers.py:273-274`).
- Real behavior, verbatim from `holus evidence "who calls hybrid_search" --provider structural --format json`: the top four results are `tests/test_indexer.py`, `tests/test_eval_baselines.py`, `tests/test_eval_variants.py`, `tests/test_eval_harness.py`, with excerpts like `tests_test_indexer_test_index_repeated_calls_close_only_owned_store_and_preserve_stats`. `src/holusight/search.py` ranks **fifth**. The provider matched the English word "calls" inside test function names. It did not answer the question.
- The same question answered directly from `graph.json` in 14 lines of Python returns the correct, precise answer: callers of `hybrid_search` are `src/holusight/api.py` `.search()` at `L161` and `tests/eval_harness.py` `_default_search_fn()` at `L123`; callees are `get_embedder()` (`embeddings.py`), `rrf_merge()`, `vprf_enhance_query()`, `_cnfb_boost()`, `_reorder_by_filename_match()`, `_rerank()` (all `search.py`), plus eval-harness symbols. — command output
- The eval baseline is a third, separate re-implementation of the same substring trick: `tests/eval_baselines.py:221-300`, `graphify_structural_search_fn_factory`, scores files by "the number of distinct query tokens that appear as a substring of any node's ... node_id itself" and returns every result with `start_line=1, end_line=1` (`eval_baselines.py:277-278`). Its own comment concedes the limitation: `"_StructuralIndex (consistency.py) exposes only node_file/file_nodes/links, not full node records — match against each node_id itself"` (`eval_baselines.py:252-255`).
- `ARCHITECTURE.md` describes the structural provider as `"sourced from the tracked graphify-out/graph.json, with an explicit staleness flag"` and `specs/013-holusight-axi-consistency-architecture.md:56` describes its method as `"Graph node/edge lookups keyed by source_file, carrying the graph's own confidence_score"`. That is accurate for `structural_edges_for` (which does read edges, at file granularity) but **not** for the `holus` `structural_provider`, which performs no edge lookup at all.

### Inferences
- The project has three independent consumers of the graph (`consistency.structural_edges_for`, `axi_providers.structural_provider`, `eval_baselines.graphify_structural_search_fn_factory`) and **none of them uses the graph as a graph**. The richest asset in the file — 1,494 AST-extracted `calls` edges with file+symbol+line on both ends and `confidence: EXTRACTED` — is loaded into memory on every call and then thrown away.
- Because `_StructuralIndex` deliberately drops `label`, `source_location`, and `file_type`, every downstream consumer is *forced* into node-ID substring matching. The bottleneck is a 5-field `__slots__` declaration at `consistency.py:419`, not the graph.
- `directed: False` at the graph's top level is cosmetic/NetworkX-export metadata, not a data limitation: `source`/`target` on each link plus `relation: "calls"` fully determine direction. Direction is lost by Holusight's code (`consistency.py:488-493`), not by Graphify.

### Gaps
- Whether Graphify's own `query`/`path`/`explain` commands would have returned better answers cannot be tested — the CLI is not installed (see Q4).

---

## Q2. How is staleness detected, and what happens on stale?

### Takeaway
Staleness is a bare string equality between the graph's recorded `built_at_commit` and current `HEAD`. Because this repo squash-merges, the recorded commit is a discarded PR-branch commit that is **not an ancestor of HEAD and never will be**, so the graph reports `stale` permanently — and it did so from the moment it was committed. Every consumer warns and proceeds; nothing refuses. The generated agent skill, meanwhile, says never to trust a `stale` provider.

### Cited Findings

- The whole detector, `consistency.py:463-471`:
  ```python
  def structural_graph_freshness(index, repo_root) -> tuple[bool, str | None]:
      """Return (stale, built_at_commit). Unavailable graph counts as stale."""
      if not index.available:
          return True, None
      head = current_commit(repo_root)
      stale = head is None or index.built_at_commit is None or head != index.built_at_commit
      return stale, index.built_at_commit
  ```
  It is exact string equality against `HEAD`. There is no ancestry check, no per-file mtime or blob comparison, no tolerance window.
- The recorded commit is not in the repo's first-parent history. `git merge-base --is-ancestor 292e35f HEAD` → **`NO_not_ancestor`**. `git merge-base --is-ancestor 292e35f a73f76c` → **`NO`**. `git show -s 292e35f` → `Tue Sep 22 09:26:15 2026 · "Rename the codesight package to holusight" · parents: 70451b0`. The commit that actually landed the graph, `a73f76c` ("Complete Holusight rename and refresh Graphify output (#57)", `Tue Sep 22 12:11:53 2026`), has the **same parent `70451b0`** — i.e. `292e35f` is a sibling PR-branch commit that the squash-merge discarded. — command output
- Consequence: the graph was already `stale` at the instant it was committed, and no amount of "refresh the graph" fixes it while the repo squash-merges, because the commit the graph is built at is always destroyed by the merge that lands it.
- Verified live, `holus providers --format json`:
  ```json
  { "name": "structural", "available": true,
    "version": "graphify@292e35f7729f548829af08d240df13254a5ab4f5",
    "freshness": "stale", "egress": "none",
    "detail": "224 file(s) with graph nodes" }
  ```
- Every one of the five archived dated snapshots has the same structural problem — each records a commit, and none records the commit it was committed under: `2026-08-12 → a0c27823`, `2026-08-13 → 25a3bc3e`, `2026-08-14 → f8ef150f`, `2026-08-20 → 1e99ecac`, `2026-08-23 → 67bfb81c`. — command output
- What consumers do on `stale` — three sites, all warn-and-proceed, none refuse:
  1. **Consistency engine**: emits a health flag with `severity="info"` and `evidence_class=EvidenceClass.INFERRED`, detail `f"graphify-out/graph.json built_at_commit={structural_commit!r} does not match current HEAD; run \`graphify update .\`"` (`consistency.py:798-812`). Edges are still generated, each stamped `"graph_stale": stale` in its evidence payload (`consistency.py:515`). `refresh` calls `structural_edges_for(structural_index, path, structural_stale)` unconditionally for every implementation artifact (`consistency.py:1028-1032`).
  2. **`holus` provider**: returns `state=ProviderState.STALE if stale else ProviderState.OK` but **with the full item list attached** (`axi_providers.py:301-307`). When there are no matches it returns `STALE` instead of `NO_EVIDENCE` (`axi_providers.py:295`) — so `stale` conflates "graph is old" with "found nothing."
  3. **Eval harness**: prints to stderr and runs anyway. Verbatim: `warning: graphify-out/graph.json is stale (built_at=292e35f7729f548829af08d240df13254a5ab4f5, HEAD=c51870c3b0c058ca8ed756ee3fbb9d0a78afe4c0) — run \`graphify update .\` for a current graph`. `specs/014-...md:129-134` confirms the intent: a stale graph "is available but is stale" is surfaced rather than refused, and an absent graph degrades to "0 hits" "rather than raising."
- The governing agent instruction contradicts all of that. The generated skill, `.claude/skills/holus/SKILL.md:20`: `"Never treat a stale, partial, or unavailable provider state as if it were current, authoritative evidence - surface the state to the user instead of a confident answer."` The identical rule appears in the machine-wide `CLAUDE.md` holusight block.
- Real evidence output confirms the label reaches the agent: `holus evidence "chunk_file_ast" --provider structural --format json` → `"providers_checked": [{"provider": "structural", "state": "stale", "detail": "1 file(s) matched (graph built_at_commit='292e35f...', stale)"}]`, yet `"coverage": "sufficient"` and `"answerable": true`.

### Inferences
- The staleness signal is **100% false-positive by construction**, which makes it worthless as a signal. A permanently-red light is the same as no light. And because the rule says to distrust `stale`, a compliant agent must discard every structural result — meaning the provider ships, runs, costs 1.59 ms/query, and contributes nothing an obedient agent is allowed to use.
- The correct freshness test for a committed derived artifact is not commit equality. It is: does every file the graph covers still have the same Git blob as when the graph was built? That is per-file, survives squash-merge and unrelated commits, and is exactly the test `retrieval_variation.py` and spec 021's `EvaluationSubject` already apply elsewhere in this same repo (`ARCHITECTURE.md` "Evidence Subject Binding v1": "every linked path has the same Git blob at the evaluated commit, current HEAD, and clean worktree"). The mechanism already exists in-repo; the structural provider just doesn't use it.
- Because `refresh` generates structural edges even when stale and stamps them `INFERRED`, the consistency cache is currently seeded with file-level edges derived from a graph that predates 15 source-file changes — silently mixing week-old structure into current evidence.

### Gaps
- The health flag's `severity="info"` means it does not surface in the `warning`/`high` counts an operator would notice. `holus status` reported `"health_flags": {"info": 19, "warning": 84, "high": 0, "total": 103}` — the stale-graph flag is one of 19 infos among 103 flags. I did not enumerate all 103 to confirm which info is which; `holus check --format json` truncated its output (`"23 more concept(s) not shown"`).

---

## Q3. Does `graphify-out/` exist and is it current?

### Takeaway
It exists and is tracked, `graph.json` is 4.01 MB and last refreshed 2026-09-22. Since then 12 commits and 15 source files have landed, and **5 tracked `.py` files — including two shipped production modules — are entirely absent from the graph**. The wiki and top-level `GRAPH_REPORT.md` that agent instructions point at do not exist.

### Cited Findings

- `ls -la graphify-out/` (verbatim, trimmed):
  ```
  -rw-r--r--  6289      Sep 28 00:59 .graphify_labels.json.sig
  drwxr-xr-x            Sep 28 00:59 2026-08-12/ 2026-08-13/ 2026-08-14/ 2026-08-20/ 2026-08-23/
  -rw-r--r--  4013085   Sep 28 00:59 graph.json
  ```
  (All mtimes are `Sep 28 00:59` because that is when this worktree was created, not when the graph was built.)
- `git log --oneline -- graphify-out/` most recent: `a73f76c Complete Holusight rename and refresh Graphify output (#57)`, dated `Tue Sep 22 12:11:53 2026`. Prior touches: `6e868df`, `67ff510`, `5aa41bb`, `1e99eca`, `24f7c64`, `198a6c7`, `3175ea0`, `07f8944`.
- Drift since that refresh: `git rev-list --count a73f76c..HEAD` → **12** commits. `git diff --name-only a73f76c..HEAD` → **30** files, of which **15** are under `src/`: `api.py`, `axi_providers.py`, `axi_schema.py`, `axi_skill_gen.py`, `chunker.py`, `cli_axi.py`, `config.py`, `consistency.py`, `consistency_store.py`, `embeddings.py`, `indexer.py`, `local_usage_trace.py`, `public_research.py`, `search.py`, `skill_installer.py`.
- Concrete coverage drift, measured: the graph covers **224** source files; **0** graph files have been deleted; but **5 tracked `.py` files are absent from the graph entirely** — `src/holusight/local_usage_trace.py`, `src/holusight/public_research.py`, `tests/test_config.py`, `tests/test_local_usage_trace.py`, `tests/test_public_research.py`. — command output
- Those two missing `src/` modules are recent shipped features: `caae73b Add local usage trace quality summary (#65)` and `9980904 Add opt-in public URL research with verified excerpt receipts (#68)`. An agent asking the structural provider anything about them gets zero evidence with no indication that the file simply isn't in the graph.
- The top-level `graph.json` is **not** a copy of the newest dated snapshot: `shasum` gives `aca73375...  graphify-out/graph.json` vs `fcead988...  graphify-out/2026-08-23/graph.json`, and their `built_at_commit` values differ (`292e35f` vs `67bfb81c`).
- `graphify-out/wiki/` → `ls: No such file or directory`. `graphify-out/GRAPH_REPORT.md` → `ls: No such file or directory`. Both are gitignored (`.gitignore:64-65`). Dated snapshot dirs do contain `GRAPH_REPORT.md`.
- Graph composition: `file_type` counts are `code` 1,698 · `document` 1,628 · `rationale` 532. 137 `.md` files appear as document nodes, headed by `business/specs/005-money-model.md` (53 nodes), `specs/012-...md` (51), `docs/research/gpt-deep-research/2026-08-14-holusight-infrastructure-graphify-architecture.md` (42), `AGENTS.md` (40). — command output

### Inferences
- The graph is roughly one week and 15 source files behind, and its most consequential drift is *silent absence* rather than wrong data: two production modules are invisible to structure. Absence is the failure mode that "0 hits" cannot distinguish from "no such relationship," which is precisely the ambiguity `ProviderState` was designed to eliminate.
- `AGENTS.md`'s instruction "If `graphify-out/wiki/index.md` exists, use it for broad navigation instead of raw file browsing" and "Read `graphify-out/GRAPH_REPORT.md` only for broad architecture review" both target paths that are gitignored and absent. An agent following them wastes two tool calls discovering nothing.

---

## Q4. Does the `fleet_graphify.py` path in AGENTS.md exist on this machine?

### Takeaway
**No — the exact path is dead, because `/Users/mini` does not exist on this machine.** But the wrapper script itself *does* exist under this user's home at a different path. So the instructions are broken by a hardcoded username, not by a missing tool. The `graphify` CLI itself is genuinely not installed. Spec 014 already documented this and it was never fixed.

### Cited Findings

- `ls -la "/Users/mini/.openclaw/workspace/github/~fleet-system/system/shared/scripts/fleet_graphify.py"` → **`No such file or directory`**, exit 1.
- Root cause: `ls -la /Users/` lists only `camiloslaptop`, `Shared`, `tempadmin`, `.localized`. **There is no `mini` user on this machine.** The instruction was written on a different host.
- The script exists at a corrected path: `find /Users/camiloslaptop -name "fleet_graphify.py"` →
  ```
  /Users/camiloslaptop/github/fleet-system/.graphify-build-mirror/fleet_graphify.py
  /Users/camiloslaptop/github/fleet-system/system/shared/scripts/fleet_graphify.py
  ```
  The second is the exact same relative path (`system/shared/scripts/fleet_graphify.py`) under a different home — a one-token fix.
- The `graphify` CLI is not installed: `which graphify` → `graphify not found`, exit 1. `which agy` → `/opt/homebrew/bin/agy` (the semantic runner *is* installed).
- The dead path appears in agent instructions **six times** across the loaded instruction surface for this repo: three times in `projects/holusight/AGENTS.md`'s repeated graphify blocks and again in the duplicated `CLAUDE.md` sections, each with the same six bullet rules ("first run `python3 /Users/mini/...` query", "Before editing a source file, run the traceable ... wrapper", "After modifying code files ... run `... update .`").
- This was already known and documented, unfixed, five-plus weeks ago. `specs/014-retrieval-evaluation-harness-expansion.md:137-144`: `"per this task's instructions, graphify query/graphify explain/graphify path were attempted first. The graphify CLI and the fleet_graphify.py wrapper referenced in this repo's AGENTS.md are both unavailable in this task's execution environment (graphify not ...)"` and `"graphify update . was likewise not run after this"`.
- `projects/holusight/AGENTS.md` also self-documents the consequence in its Commands section: `"The graphify/fleet_graphify.py/agy tooling this file references elsewhere is not present on every execution host — code that depends on it ... must degrade to an explicit 'unavailable' result rather than fail, and does."`

### Inferences
- Every instruction telling an agent to query or refresh the graph is currently a **guaranteed failed tool call** followed by a fallback to raw file reading — i.e. the instructions actively cost tokens and latency while delivering nothing. Worse, the "before editing a source file, run the wrapper to surface dependents/callers" rule is the single most valuable instruction in the block, and it is the one that fails.
- The graph can, in fact, be refreshed on this machine — the wrapper is present at `/Users/camiloslaptop/github/fleet-system/system/shared/scripts/fleet_graphify.py`. This is a **path-correction bug, not a missing-capability bug**, which makes it the cheapest fix in this entire audit. (Whether that wrapper runs successfully was not tested — see Gaps.)
- The repeated-three-times graphify block in the instruction surface is itself pure token tax: identical six-bullet text loaded three times per session, all pointing at a dead path.

### Gaps
- I did not execute `/Users/camiloslaptop/github/fleet-system/system/shared/scripts/fleet_graphify.py query "..."` against this worktree. Existence is proven; that it runs and produces a current graph here is **assumed, not verified**. This should be the first thing confirmed before recommending the path fix as complete.

---

## Q5. Is `graphify-out/` tracked or gitignored?

### Takeaway
Deliberately both: `graph.json` is force-tracked while every other generated output is ignored. That makes the stale graph a **tracked, committed, doc-code-consistency defect of exactly the category this project exists to detect — and Holusight does not detect it.**

### Cited Findings

- `git check-ignore -v graphify-out/` → exit **1** (not ignored). `git ls-files graphify-out/ | wc -l` → **22** tracked files.
- `.gitignore:57-70` encodes the intent explicitly:
  ```
  # graphify - commit graph.json; ignore generated outputs and local state
  graphify-out/*.html
  graphify-out/*.svg
  graphify-out/*.graphml
  graphify-out/.graphify_labels.json
  graphify-out/.graphify_root
  graphify-out/cache/
  graphify-out/wiki/
  graphify-out/GRAPH_REPORT.md
  graphify-out/cypher.txt
  graphify-out/manifest.json
  !graphify-out/graph.json
  graphify-out/.vocab.txt
  ```
- Tracked set: `graphify-out/graph.json`, `graphify-out/.graphify_labels_json.sig`, and full `graph.json` + `GRAPH_REPORT.md` + `manifest.json` + `.graphify_labels.json` for each of the five dated snapshots (the per-directory ignores don't match nested paths). — `git ls-files graphify-out/`
- The irony is doubled by `.claude/rules/structure.md`, which classifies `.holusight/` as `"Gitignored derived state, never canonical truth"` — while the analogous Graphify derived state is committed and therefore behaves as canonical truth to every reader.
- Holusight's own detectors do not catch it. `holus check --format json` reports `{"concepts_checked": 43, "summary": {"possible_undocumented_drift": 5, "up_to_date": 38}}` — the stale graph is not among the drift findings, because the graph is not a registered concept and the only signal is the `severity="info"` health flag from `consistency.py:798-812`.

### Inferences
- A committed derived artifact with no freshness enforcement is the textbook doc-code drift this repo's entire consistency layer targets — and it is sitting in the repo, one directory away from the engine that would catch it if it checked. This is the single most rhetorically useful finding for the thesis: **Holusight cannot currently keep its own structural graph honest.**
- Committing `graph.json` is still the right call for agent efficiency (it makes structure available with zero setup on any clone, no CLI install, no egress). The fix is not to un-track it; it is to make staleness *per-file and enforced* so the tracked copy has to stay honest.

---

## Q6. ADR-0010 vs the fact that the structural provider ships

### Takeaway
ADR-0010 said "do not integrate Graphify into the retrieval pipeline for v1," specified an extension contract behind `HOLUSIGHT_GRAPHIFY_PATH`, and forbade marketing the capability. The env var was never implemented; `pilot-offer.md` correctly still excludes it. But a `structural` provider shipped anyway on the *consistency/evidence* surface, and agent instructions were made to depend on it — so the ADR was honored on the letter (retrieval ranking is untouched) and bypassed in spirit (agent-facing evidence now depends on the graph).

### Cited Findings

- `docs/decisions/0010-graphify-extension-contract.md`, status `accepted`, dated `2026-08-13`, titled "Graphify Extension Contract (**Not Integrated in v1**)". Decision, verbatim: `"**Do not integrate Graphify into the retrieval pipeline for v1.** Document an extension contract and keep ordinary document/code search working without any graph artifact."`
- Its evaluation table gives the reasons: small/testable integration path → `"No — importing graph artifacts would touch indexer, search ranking, and deployment images"`; failure isolation → `"Hard — bad graph data could affect ranking if fused naively"`; required for document search → `"No — hybrid BM25 + vector + RRF is sufficient for pilot"`.
- The specified contract, item 2, is display-only enrichment: `"when a query returns code chunks, attach related_symbols: [{file, symbol, relation}] from the graph — display only, no ranking change in v1 experiment"`. Item 3: `"if graph missing or stale, log warning and return search results unchanged"`.
- The contract's own trigger is unimplemented: `grep -rn "HOLUSIGHT_GRAPHIFY_PATH\|GRAPHIFY_PATH" src/` → **no matches**.
- ADR-0010's marketing rule: `"Do not claim 'Graphify-powered' or 'code graph search' on holusight.com until the extension contract is implemented and tested."` Consistent with that, `specs/010-capability-inventory.md:98` still lists `| Graphify code-graph integration | **Planned** | see docs/decisions/0010-graphify-extension-contract.md |`, and `business/pilot-offer.md:61` lists `- Graphify graph integration (see ADR 0010)` under exclusions, with `:69` offering it as a separately-quoted `"Graphify experiment"` SOW.
- Yet `structural` is a first-class, always-on provider on the agent surface: `axi_providers.py:518` registers `"structural": structural_provider`; `axi_providers.py:530-531` routes `"structure": ["structural"]` and puts it second in `"auto": ["exact", "structural", "consistency", "semantic"]`; `holus providers` reports it `"available": true`.
- And agent instructions were written to depend on it — `.claude/skills/holus/SKILL.md:8` advertises `"is the structural graph stale"` as a supported question, and `AGENTS.md`'s graphify block mandates querying structure before editing any source file.

### Inferences
- Nothing here is literally violated: ADR-0010 scoped its prohibition to *retrieval ranking*, and retrieval ranking genuinely never touches the graph (the eval `graphify` baseline is a standalone comparison `SearchFn`, not a fused signal). The ADR aged out of its own scope instead: it was written before the consistency/evidence surface existed, so the surface where Graphify *did* get integrated is unaddressed by it.
- The practical inconsistency is in expectations, not architecture: the product excludes the capability and the marketing rule forbids claiming it, while the internal agent contract *requires* it and the generated skill advertises it. Those two audiences disagree about whether this feature exists.
- The cleanest reconciliation is also the smallest: ADR-0010's item 2 — `related_symbols: [{file, symbol, relation}]`, display-only, no ranking change — is **exactly the missing capability identified in Q1**, is already the agreed-and-accepted design, and requires no new decision. It just needs to be built on the evidence surface rather than the retrieval surface.

---

## Q7. What does the eval harness's "graphify" baseline measure, and is there real evidence?

### Takeaway
**There is no valid measurement of structural retrieval value on this repo, and the reason is itself a live doc-code drift bug.** 61 of 85 ground-truth paths in the taxonomy fixture do not exist — 60 of them still say `src/codesight/`, the package name abandoned in the same commit that refreshed the graph. Both baselines have been silently scoring near-zero on all code queries for a week. Neither CI nor the consistency engine caught it.

### Cited Findings

- I ran the harness. Verbatim output of
  `uv run --extra dev python tests/eval_holusight.py --queries tests/fixtures/holusight_eval_taxonomy.json --baselines exact,graphify --top-k 10 --no-index`:
  ```
  warning: graphify-out/graph.json is stale (built_at=292e35f7729f548829af08d240df13254a5ab4f5, HEAD=c51870c3b0c058ca8ed756ee3fbb9d0a78afe4c0) — run `graphify update .` for a current graph
  exact: hit_rate=1.2% mrr@10=0.003 ndcg@10=0.005  graphify: hit_rate=26.2% mrr@10=0.252 ndcg@10=0.254
  ```
- Full metrics from the result JSON (`schema_version: "holus-eval-report/v2"`, 85 queries, 80 graded, 5 diagnostic probes):
  | baseline | hit_rate | mrr@10 | ndcg@10 | recall@1 / @5 / @10 | evidence_completeness | avg_latency_ms |
  |---|---|---|---|---|---|---|
  | exact | 0.0125 | 0.0025 | 0.0048 | 0.0 / 0.0125 / 0.0125 | 0.0125 | 21.0 |
  | graphify | 0.2625 | 0.2518 | 0.2542 | 0.25 / 0.25 / 0.2625 | 0.2687 | 1.59 |
- **These numbers are invalid.** Ground truth is broken: of 85 `expected_file` values, **61 do not exist on disk**. The non-existent set is `__NO_MATCH__` (the 5 intentional diagnostic probes) plus 16 distinct `src/codesight/*` paths: `__main__.py, api.py, chunker.py, config.py, consistency.py, consistency_store.py, embeddings.py, git_utils.py, holus.py, indexer.py, llm.py, parsers.py, search.py, store.py, types.py, web/server.py`. `ls src/` → `holusight` only. `grep -c "src/codesight/" tests/fixtures/holusight_eval_taxonomy.json` → **66**; `grep -c "src/holusight/"` → **0**. — command output
- Real per-query records showing the dead ground truth verbatim:
  `{"query": "rrf_merge", "family": "exact_lookup", "expected_file": "src/codesight/search.py", "hit": false, ...}`
  `{"query": "_sanitize_fts_query", "family": "exact_lookup", "expected_file": "src/codesight/store.py", "hit": false, ...}`
- The 24 `expected_file` paths that *do* exist are all docs, specs, ADRs, `AGENTS.md`, `ARCHITECTURE.md`, and two test files — every code path is dead.
- Family breakdown makes the artifact obvious. `graphify`: `doc_synthesis` 15/15 = **1.00**, `test_coverage` 5/5 = **1.00**, `config_lookup` 1/10 = 0.10, and **`exact_lookup` 0/20, `symbol_reference` 0/10, `conceptual_localization` 0/20 — all 0.00**. `exact`: 1/20 on `exact_lookup`, **0.00 on every other family**. The graphify baseline's entire 26.2% comes from the doc/test families whose paths survived the rename; it scored zero on every family whose ground truth points at `src/codesight/`.
- Importantly, **`symbol_reference` 0/10 is not evidence that structure failed.** All 10 of those queries have `expected_file` under `src/codesight/` and are therefore ungradeable. Their query text is genuinely structural — e.g. `"how does hybrid_search call bm25_search and vector_search together"`, `"where does the indexer call get_embedder to build the embedding backend"`, `"how does the web server call require_auth before search"`. These are the exact questions a working structural provider should own, and the harness currently cannot score them.
- The rename landed in the same commit pair as the graph refresh (`292e35f` / `a73f76c`, 2026-09-22), so the fixture has been broken for the full 12 commits since.
- `specs/014-...md:224-225` already concedes the baseline is coarse: `"Graphify structural baseline is coarse. It matches query tokens against Graphify node IDs (derived symbol identifiers), not full node ..."`. Spec 014 also frames its own numbers as `"a bounded local vertical slice, not a production benchmark"` (`ARCHITECTURE.md`).
- The only structural-vs-hybrid comparison numbers anywhere in the repo are aspirational, not measured. `specs/012-...md:654`: `"if **Holusight+Graphify** is statistically and operationally indistinguishable from Holusight alone, Graphify should not remain merely because graphs are theoretically attractive. Conversely, if Graphify uniquely recovers high-severity transitive impacts, that can justify its cost"` — a stated research question, explicitly unanswered.
- `ARCHITECTURE.md`'s performance table (Baseline 52.5%/0.352 → VPRF+reranker 100%/0.599 → AST chunking 100%/0.823 → voyage 100%/0.793) contains **no Graphify row at all**. No stored eval artifact contains graphify results either: the four JSONs under `tasks/2026-04-03/PLAN-.../results/` have keys `timestamp, phase, eval_type, baseline_phase1/2, comparison_table, best_config, key_insights` and none mention graphify.
- Hybrid could not be run for comparison: `holus providers` reports `{"name": "semantic", "available": false, "freshness": "unavailable", "detail": "repository not indexed; run \`python -m holusight index .\`"}`.
- One more live rename-drift artifact, in the **generated agent-facing skill** — `.claude/skills/holus/SKILL.md:172` contains a mangled command produced by a blind `codesight→holusight` string replace:
  ```
  python -m python -m holusight.cli_axiight.cli_axi improve-intake "structural graph stale case" ...
  ```
  (`grep -rn "cli_axiight\|python -m python" src/ .claude/skills/` matches only this line, so the corruption is in the committed generated artifact, not in `axi_skill_gen.py`.) An agent copying that line gets an immediate failure. `tests/test_axi_skill_drift.py` is documented as failing `pytest` when schema and skill diverge — it evidently does not check command-string well-formedness.

### Inferences
- **Measured vs assumed, stated plainly:** the value of structural retrieval on this repo is **entirely assumed**. The 26.2% figure is an artifact of file-level results matching file-level doc ground truth, measured against a fixture that is 72% dead. Nothing in this repository measures whether structure beats or complements hybrid retrieval, and the one place designed to answer it is broken.
- The rename bug is the most valuable finding for the user's thesis, because it is a *perfect* instance of the problem Holusight exists to solve: a tracked artifact (`holusight_eval_taxonomy.json`) silently contradicting the code it governs for 12 commits, degrading a quality gate to a no-op, undetected. The consistency engine missed it because `extract_exact_references` only scans `_REFERABLE_KINDS` (spec/ADR/architecture prose), not JSON fixtures — so dangling-path detection, the engine's strongest capability, is not pointed at the file where it would have mattered most.
- The 1.59 ms average latency for graphify vs 21.0 ms for exact is real and notable: graph lookups are ~13× cheaper than filesystem scanning. Whatever structure is worth, it is worth it cheaply.

### Gaps
- No hybrid or BM25 comparison was obtainable (repo not indexed; indexing with `Qwen/Qwen3-Embedding-8B` locally was out of budget for this audit). So even after the fixture is fixed, the structural-vs-hybrid question remains open until someone indexes and reruns.
- Whether the harness's `doc_synthesis`/`test_coverage` families would still favor graphify after the fixture fix is unknown — plausibly the 1.00 scores partly reflect graphify returning whole files at `start_line=1`, which trivially matches file-level ground truth.

---

## Q8. What would structure genuinely add that BM25+vector cannot, and what is cheap?

### Takeaway
Three agent questions are **impossible** for BM25+vector in principle and already fully answerable from the bytes in `graph.json` today: "who calls this," "what breaks if I change this," and "does this doc's described call path still exist." The first two are each a few dozen lines over data already loaded into memory on every provider call. The third is the thesis-critical one and needs a small new edge join, because **there are currently zero doc→code edges in the graph**.

### Cited Findings — what is impossible today vs cheap

- **"Who calls this function" — impossible via retrieval, trivial via graph.** BM25 and vector search rank *text similarity*; neither can distinguish a definition from a call site from a docstring mention. Demonstrated failure: `holus evidence "who calls hybrid_search" --provider structural` returns four test files matched on the word "calls," with `search.py` fifth. Demonstrated success from the same file in 14 lines: callers are `src/holusight/api.py .search() L161` and `tests/eval_harness.py _default_search_fn() L123`; 10 callees resolved with file+symbol. The data needed — `relation: "calls"`, directed `source`/`target`, `source_location: "L161"`, `confidence: "EXTRACTED"` — is on all 1,494 `calls` edges plus 60 `indirect_call`. — command output
- **"What breaks if I change this" — impossible via retrieval, near-free via graph.** This is reverse-reachability over `calls` + `imports_from` + `inherits` + `method`, a total of **2,249 directed edges** (1,494 + 139 + 82 + 434 + 60 indirect). Retrieval cannot compute transitive impact at any k, because relevance is not reachability. `specs/012-...md:654` names exactly this as the case that could justify the graph's cost: `"if Graphify uniquely recovers high-severity transitive impacts, that can justify its cost even if aggregate retrieval nDCG barely moves."`
- **"Is this doc's described call path still real" — the thesis question, and the genuine gap.** Measured: **md→py edges = 0**. The graph has 137 `.md` files and 1,628 `document` nodes, but not one edge connects a document node to a code node. `rationale_for` (532 edges) sounded promising but is docstring→symbol *within the same file* — all 532 are intra-file (verified: `cross-file_type edges: 532`, i.e. rationale→code, every one same `source_file`, e.g. `src/holusight/agent_focus.py` docstring → `build_context_pack()`). So Graphify supplies symbol-accurate code structure and Holusight's `exact` provider supplies doc→path references (`consistency.py:374-408`, `relation="references"`, `evidence={"pattern": "path-token"}`), and **nothing joins them at symbol level.** A doc can say "`hybrid_search` calls `rrf_merge`" and no component in the system can check that claim, even though both facts are one hop apart in two datasets already loaded in the same process.
- **What structure cannot do, honestly:** all of `conceptual_localization` (20 taxonomy queries) and `doc_synthesis` (15) are semantic-similarity work. The `exact` provider's 21.0 ms full-text scan beats node-ID matching for literal identifier lookup once ground truth is fixed. Structure is a *complement*, not a replacement — which is precisely ADR-0010's already-accepted framing (`"hybrid BM25 + vector + RRF is sufficient"` for search; graph as display-only enrichment).

### Inferences — the concrete small additions, ordered by payoff per line changed

1. **Fix the dead path in the instruction surface** (`/Users/mini/…` → `/Users/camiloslaptop/github/fleet-system/system/shared/scripts/fleet_graphify.py`), and collapse the block from three duplicated copies to one. Payoff: the "surface callers before editing" rule stops being a guaranteed failed tool call, and the graph becomes refreshable here. Cheapest item in this audit; verify the wrapper actually runs first (Q4 Gaps).
2. **Fix `tests/fixtures/holusight_eval_taxonomy.json`: `src/codesight/` → `src/holusight/` (66 occurrences).** Payoff: restores a quality gate that has been a no-op for 12 commits, and is a precondition for *any* honest claim about structural value. Add a test that asserts every `expected_file` in every eval fixture exists on disk — that one assertion would have caught this on day one, and it is the same class of check `consistency.py`'s `DANGLING_REFERENCE` already performs, just pointed at fixtures. Also fix the mangled `SKILL.md:172` command and extend `test_axi_skill_drift.py` to reject `python -m python`-shaped garbage.
3. **Widen `_StructuralIndex` by three fields and add two symbol-level queries.** Keep `label`, `source_location`, and `file_type` per node (`consistency.py:419`, `436-460`) — data already parsed and discarded. Then expose `holus evidence --provider structural` handling of "who calls X" / "what calls X" / "impact of X" by reading `index.links`, returning `{file, symbol, line, relation, confidence}` per hit. This is ADR-0010's already-accepted `related_symbols: [{file, symbol, relation}]` contract, display-only, no ranking change — so it needs no new decision, only implementation. Payoff: the single clearest agent-visible win in the repo, turning a provider that answers nothing into one that answers two questions retrieval cannot.
4. **Replace commit-equality staleness with per-file blob staleness.** Instead of `head != index.built_at_commit` (`consistency.py:470`), compare each covered `source_file`'s current Git blob against the blob at `built_at_commit`, and report coverage gaps (the 5 absent `.py` files) separately from staleness. Report `stale` per answer, not globally: an answer about `search.py` is current if `search.py` is unchanged, regardless of 12 unrelated commits. Payoff: turns a permanently-red, therefore ignored, flag into a signal an agent can act on — and ends the "always stale, so never trust it" deadlock created by `SKILL.md:20`. Reuse spec 021's existing blob-comparison mechanism rather than writing a new one.
5. **The thesis feature, and the one genuinely new thing: a doc-claim structural check.** Join Holusight's `exact` doc→path references to Graphify's symbol edges. Concretely: when a spec or ADR names two symbols in proximity, verify the asserted relationship exists in `links`. This is the only item here that creates capability rather than exposing existing data, and it is the only one that directly serves "keep docs honest about code." Scope it to the 6 already-registered named claims in the claim registry first (RRF `k`, AST `min_lines`, hash length, data dir) rather than building a general NL claim extractor — `specs/013` explicitly warns that general extraction is out of scope.

**What to avoid, given the user's stated preference and closed infrastructure-only PRs:** do not build a graph service, a query DSL, a fused ranking signal (ADR-0010 explicitly rejected fusion: `"bad graph data could affect ranking if fused naively"`), or a fourth re-implementation of node matching. Items 1–3 are the direct path: two path/string fixes and three fields plus two query functions over data already in memory. Items 4–5 follow only once item 2 makes their value measurable.

### Gaps
- **Unmeasured and must be stated as such:** no number in this repo supports "structure improves agent context speed." The 1.59 ms vs 21.0 ms latency gap is real but measures lookup cost, not answer quality. The 26.2% hit rate is invalid. Item 2 must land before any claim of structural value is defensible, and then hybrid must be indexed and rerun for a genuine three-way comparison.
- Whether `fleet_graphify.py` at the corrected path successfully regenerates a graph for this worktree is unverified (see Q4).
- I did not determine why `holus providers` reports the `consistency` provider `"freshness": "stale"` while its own detail line shows `cached head` **equal to** `current head` (`c51870c3...` both). That looks like a second, independent false-stale bug on the consistency provider — worth a follow-up, since it means two of three available providers report `stale` unconditionally, and the same `SKILL.md:20` rule tells agents to distrust both.
