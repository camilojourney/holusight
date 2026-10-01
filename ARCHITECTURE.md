# Holusight architecture — Graphify consistency helper

Holusight helps agents inspect Graphify/source integrity plus duplication and explicit alignment. It is not a search/index/LLM application. `src/holusight/consistency.py` checks the graph; `alignment.py` detects source duplication candidates and shared-fact contradictions. `api.py` exposes `Holusight.check/status/align`; `__main__.py` plus `cli_axi.py` expose the same operations as `python -m holusight` and `holus`.

## Data and trust boundary

Input is `<repo>/graphify-out/graph.json`, Graphify's v1.2-style `nodes` and `links`. It must remain inside the resolved repository (symlinks escaping the root are refused); source paths in nodes/edges are similarly resolved and confined. No Graphify subprocess, model, embedding daemon, network client, index, or SQLite cache is invoked. The checker has a 100 MB graph limit and caps displayed findings at 100 while retaining complete error counts. It reads source files only, never writes checked repositories. Source files over 2 MB or unreadable lines are counted as unverified, preventing a clean verdict.

`built_at_commit` is not trusted as an assertion: it must be a 40-character SHA equal to `git rev-parse HEAD`, with a clean working tree from `git status --porcelain`. A missing/invalid value or unverifiable Git state is `unknown`; mismatch or dirty source is `stale`; missing/malformed graph is `unavailable`. Stale graph findings describe contradictions with **current** source but cannot certify current Graphify output. A tracked graph committed after its build can legitimately be stale; no automatic rebuild happens here.

For each graph node and edge, the checker verifies cited source paths exist and line locations do not exceed current files. Each link endpoint must identify a graph node. It checks explicit root-relative `src/`, `tests/`, `specs/`, `docs/`, `business/`, `.claude/`, `.github/`, and named root Markdown path claims in graph-backed Markdown, reporting a missing path with the claim's source file and line. A missing safe path immediately followed by the literal `(not created yet)` annotation is reported as informational `planned_path_reference` and unverified, not `missing_path_claim` error. The annotation applies only to that path; other absent references on the same line and unsafe paths still error. A proposal-only scope is `unknown`. Generic proposed/future prose is not classified. It does **not** infer symbol resolution from substring matches, interpret prose as truth, or treat graph edges as source proof. Findings have type, source path, line when available, message, and graph/line evidence. A stale/unknown graph never returns a clean/current verdict.

## Public contract

- `holus check [repo] [--scope <relative-source-path>]` / `python -m holusight check`: JSON report; exit 0 only for current and no errors.
- `holus status [repo]`: JSON provenance/counts, no mutation.
- `Holusight(repo).check(scope=None)` and `.status()` return the same data.
- `holus align [repo] [--scope <file>] [--against <repo-relative-report>]` and `Holusight(repo).align()` rescan current source and compare explicit declarations/duplicate candidates.

## Deterministic source checks and refresh

The scanner inventories Git tracked/unignored `.py`/`.md` files (or walks a non-Git directory), excluding derived/dependency and private runtime directories. Source symlinks are refused. Python functions with at least three statements and 20 AST nodes are fingerprinted without docstrings/function name; optional local-renaming candidates preserve literals, operators, external identifiers, defaults, decorators and annotations. These are structural candidates, not proven behavioral equivalence. Markdown paragraphs need 30 words; exact whitespace-normalized duplicates and >=0.85 five-word-shingle Jaccard matches are advisory. A shingle index avoids comparing unrelated paragraphs. Graph IDs are attached as navigation hints only, with independent graph snapshot/provenance.

Explicit `holus:fact` markers link JSON scalar declarations in Markdown to unambiguous top-level Python scalar literal declarations by a shared key. Disagreeing values produce code/code, docs/docs or docs/code mismatch evidence. Dynamic declarations, malformed markers and ambiguous bindings prevent a complete verdict. Imports/eval/doctests/project functions are never executed; markers inside Python strings or Markdown code examples are not contracts. This does not validate arbitrary prose or runtime behavior.

Every run re-reads source; SHA-256 manifests, rule/Python version and scope bind the report. Rechecking bytes/inventory/graph at completion detects concurrent edits. No cache invalidation or watch service is needed. Matching complete saved reports produce new/persisting/resolved IDs and changed/deleted source paths, without interpreting resolution as functional correctness. Limits: 500 files, 256 KB/file, 10 MB total bytes, 2000 units, 1000 facts and 5000 candidate paragraph comparisons. Truncation and unverified coverage are explicit; incomplete scans cannot establish resolved findings. Receipt/source/graph files are never written by the tool.

`--scope` accepts only paths contained inside the repository. The old index/search/ask/serve/demo, semantic evidence, web UI, embedding daemon, and autonomous evaluation surfaces are retired. Historical specs/ADRs remain as provenance; `specs/028-graphify-consistency-helper.md` supersedes their operational contracts.
