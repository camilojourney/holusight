# Holusight

Holusight is a small **read-only consistency helper for agents**. Graphify supplies the map; Holusight checks graph references and rescans current source for code/code and docs/docs duplication candidates and explicitly linked code/docs/code facts. It does **not** index documents, synthesize answers, infer arbitrary prose truth, call models/network services, edit source, or silently rebuild Graphify.

## Run

```sh
uv run --offline python -m holusight check [repo-path]
uv run --offline python -m holusight check [repo-path] --scope docs/guide.md
uv run --offline python -m holusight status [repo-path]
uv run --offline holus align [repo-path]
# after installation: holus check [repo-path] / holus align [repo-path]
```

Output is JSON. `status` is `current` only when `built_at_commit` is a full SHA equal to Git HEAD **and** the working tree is clean. A missing or invalid commit is `unknown`, a mismatch or dirty tree is `stale`, and missing/malformed graph data is `unavailable`. Graphify's historical graph in this repository is intentionally **not refreshed** during checks; expect `stale` until an operator rebuilds it independently and proves its provenance. A scope not represented by graph-backed source evidence is `unknown`, not a clean pass. Exit code 0 means a current graph with no detected errors or unverified checks; exit code 1 covers errors, stale, unknown, or unavailable. Error findings in stale graphs are useful leads, not a current clean bill of health.

Graph integrity and literal source/path evidence are bounded checks, not semantic doc/code verification. A missing path immediately annotated `(not created yet)` (for example, `` `src/future.py` (not created yet) ``) is an informational `planned_path_reference`, not a confirmed current-reference error. It counts as unverified: a proposal-only scope returns `unknown`, not a clean semantic verdict. This literal path-local annotation does not infer intent from words like “future” elsewhere or exempt unsafe paths. Agents should inspect cited source lines and use Graphify directly for traversal. No source or graph files are written by `check` or `align`.

## Duplication, explicit alignment, and updates

`holus align` rescans current Python and Markdown files with no cache or daemon. It reports Python function AST copies/renamed-local candidates and substantive duplicate/overlapping Markdown paragraphs. Candidates require agent judgment: similar code may be intentionally separate. It preserves literals, operators and external identifiers; unsupported languages and arbitrary prose meaning are not verified.

For a fact that must agree across consumers, explicitly give it the same key:

```python
MAX_RETRIES = 3
# holus:fact retry-limit = MAX_RETRIES
```

```markdown
<!-- holus:fact retry-limit = 5 -->
```

Different declarations of that key produce a mismatch with source hashes and locations. This works for code/code, docs/docs, and docs/code. It compares declarations, not the surrounding prose; nonliteral/ambiguous Python values are unverified rather than executed. Source results and Graphify freshness are separate: a source scan can finish while the graph remains stale.

Agents can inspect findings, edit the cited source, and rerun:

```sh
mkdir -p .holusight
holus align . > .holusight/before.json  # exit 1 for explicit mismatch/incomplete scan
# inspect cited files/lines and repair them (Holusight never edits them)
holus align . --against .holusight/before.json > .holusight/after.json
```

Reports include content hashes and `delta.new/resolved/persisting` IDs plus changed/deleted source paths. A resolved ID means no longer detected by these rules, not that a refactor is behaviorally correct. Comparison refuses incompatible or incomplete baselines. `--scope <file>` focuses findings involving that file while still scanning comparison partners. Duplicate-only `review` is advisory (exit 0); `mismatch`, `partial`, `unknown` and `unavailable` exit 1. Budgets/coverage are explicit. There is no automatic skill selection or background Graphify refresh.

## Development

```sh
uv run --offline --extra dev pytest tests/ -q
uv run --offline --extra dev ruff check src/ tests/
```

See `ARCHITECTURE.md`, `specs/028-graphify-consistency-helper.md` and `specs/029-deterministic-duplication-alignment.md` for the supported contracts, research and migration disposition. Earlier numbered specs and accepted decisions are historical context for the retired retrieval product, not current interfaces.
