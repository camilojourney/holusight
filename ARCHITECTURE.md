# Holusight architecture — Graphify consistency helper

Holusight now has one job: read an existing Graphify graph and compare verifiable graph claims with repository source. It is not a search/index/LLM application. `src/holusight/consistency.py` is the checker, `api.py` exposes `Holusight.check/status`, and `__main__.py` plus `cli_axi.py` expose the same command as `python -m holusight` and `holus`.

## Data and trust boundary

Input is `<repo>/graphify-out/graph.json`, Graphify's v1.2-style `nodes` and `links`. It must remain inside the resolved repository (symlinks escaping the root are refused); source paths in nodes/edges are similarly resolved and confined. No Graphify subprocess, model, embedding daemon, network client, index, or SQLite cache is invoked. The checker has a 100 MB graph limit and caps displayed findings at 100 while retaining complete error counts. It reads source files only, never writes checked repositories. Source files over 2 MB or unreadable lines are counted as unverified, preventing a clean verdict.

`built_at_commit` is not trusted as an assertion: it must be a 40-character SHA equal to `git rev-parse HEAD`, with a clean working tree from `git status --porcelain`. A missing/invalid value or unverifiable Git state is `unknown`; mismatch or dirty source is `stale`; missing/malformed graph is `unavailable`. Stale graph findings describe contradictions with **current** source but cannot certify current Graphify output. A tracked graph committed after its build can legitimately be stale; no automatic rebuild happens here.

For each graph node and edge, the checker verifies cited source paths exist and line locations do not exceed current files. Each link endpoint must identify a graph node. It checks explicit root-relative `src/`, `tests/`, `specs/`, and `docs/` path claims in graph-backed Markdown, reporting a missing path with the claim's source file and line. It does **not** infer symbol resolution from substring matches, interpret prose as truth, or treat graph edges as source proof. Findings have type, source path, line when available, message, and graph/line evidence. A stale/unknown graph never returns a clean/current verdict.

## Public contract

- `holus check [repo] [--scope <relative-source-path>]` / `python -m holusight check`: JSON report; exit 0 only for current and no errors.
- `holus status [repo]`: JSON provenance/counts, no mutation.
- `Holusight(repo).check(scope=None)` and `.status()` return the same data.

`--scope` accepts only paths contained inside the repository. The old index/search/ask/serve/demo, semantic evidence, web UI, embedding daemon, and autonomous evaluation surfaces are retired. Historical specs/ADRs remain as provenance; `specs/028-graphify-consistency-helper.md` supersedes their operational contracts.
