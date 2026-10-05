# Holusight

Holusight is a small **read-only consistency helper for agents**. Graphify supplies the map; Holusight checks graph references and rescans current source for code/code and docs/docs duplication candidates and explicitly linked code/docs/code facts. It does **not** index documents, synthesize answers, infer arbitrary prose truth, call models/network services, edit source, or silently rebuild Graphify.

## Install

Requires Python 3.11+; Git is needed to verify graph provenance. From a checkout, run `uv sync` (or `pip install -e .`). The runtime has no Python dependencies. Development tooling uses `uv sync --extra dev`. Offline commands below require an already provisioned environment. The installed console entry point is `holus`; the former skill installer and retrieval commands are retired.

## Run

Replace `[repo-path]` with the repository root or omit it for the current directory.

```sh
uv run --offline python -m holusight check [repo-path]
uv run --offline python -m holusight check [repo-path] --scope specs/
uv run --offline holus check [repo-path] --docs
uv run --offline python -m holusight status [repo-path]
uv run --offline holus align [repo-path]
# after installation: holus check [repo-path] / holus align [repo-path]
```

Output is JSON. `status` reports whole-graph provenance, not integrity; use `check` for errors. A current graph requires a matching build commit, clean Git tree and graph-backed source bytes verified against that snapshot. Unverifiable sources are `unknown`, not fresh. See [the provenance contract](ARCHITECTURE.md#data-and-trust-boundary) for exact conditions. The historical graph here is intentionally **not refreshed** during checks; expect `stale` until an operator rebuilds it independently. For `check`, exit 0 requires current provenance with no errors/unverified checks in declared coverage; exit 1 covers errors, stale, unknown or unavailable. Error findings in non-current graphs are leads, not a current clean bill of health.

Graph integrity and literal source/path evidence are bounded checks, not semantic doc/code verification. A missing path immediately annotated `(not created yet)` (for example, `` `src/future.py` (not created yet) ``) is an informational `planned_path_reference`, not a confirmed current-reference error. It counts as unverified: a proposal-only scope returns `unknown`, not a clean semantic verdict. This literal path-local annotation does not infer intent from words like “future” elsewhere or exempt unsafe paths. Agents should inspect cited source lines and use Graphify directly for traversal. No source or graph files are written by `check` or `align`.

## Duplication, explicit alignment, and updates

`holus align` rescans current Python and Markdown files with no cache or daemon. It reports Python function AST copies/renamed-local candidates and substantive duplicate/overlapping Markdown paragraphs. Candidates require agent judgment: similar code may be intentionally separate. It preserves literals, operators and external identifiers; unsupported languages and arbitrary prose meaning are not verified.

Check `coverage.extensions`, `unsupported_files` and `focused_unsupported_files` before interpreting results. Recognized unsupported application sources (including TypeScript and Swift) are inventoried by path metadata only, not parsed or hashed by the source scanner. If selected, they make the report `partial`, `complete: false`, exit 1, even when useful Python candidates remain. An empty inventory is never complete. The extension list is not exhaustive; `ok` means only the declared supported checks completed, not that the repository has no bad code. A Python-only scope or `--docs` can finish its narrower checks while explicitly retaining whole-inventory unsupported counts. Graph provenance is separate and may inspect graph-backed source files.

Use this as a **limited candidate-navigation helper**, not a general clone detector, architectural-quality gate or automatic refactoring tool. Public semantic-clone subsets had very low recall; see [evaluation scope and results](specs/030-source-evaluation.md).

For a fact that must agree across consumers, explicitly give it the same key:

```python
MAX_RETRIES = 3
# holus:fact retry-limit = MAX_RETRIES
```

```markdown
<!-- holus:fact retry-limit = 5 -->
```

Different declarations of that key produce a mismatch with source hashes and locations across code/code, docs/docs or docs/code. Markers compare declarations, not surrounding prose. Python markers must be module-level; unsupported or malformed declarations are unverified, not executed. Source scans and graph freshness are separate: alignment can finish while the graph remains stale. See [the deterministic source contract](ARCHITECTURE.md#deterministic-source-checks-and-refresh) for binding, example-filtering and concurrent-edit limits.

Agents can inspect findings, edit the cited source, and rerun:

```sh
mkdir -p .holusight
holus align . > .holusight/before.json  # exit 1 for explicit mismatch/incomplete scan
# inspect cited files/lines and repair them (Holusight never edits them)
holus align . --against .holusight/before.json > .holusight/after.json
```

Focus the agent's findings, without losing comparison partners:

```sh
holus check . --docs                  # supported Markdown anywhere in safe enumeration
holus align . --scope specs/          # findings involving specs and relevant outside partners
holus align . --scope src/holusight/  # application code and relevant documentation
holus align . --docs --scope specs/  # intersection: Markdown beneath specs
```

The positional path stays the repository root, not the focus folder. File/directory scopes normalize trailing slashes and use path-component boundaries. `status` stays whole-graph provenance and rejects targeting flags. `--docs` does not enter ignored/private archives or follow source symlinks. `check` restricts source checks and graph integrity to selected items/incident links; its coverage explicitly says global integrity is not checked. `align` limits emitted findings, not comparison inventory: partners elsewhere and unverified partner evidence still matter. Reports expose the normalized selector and focused-file coverage. Empty/unrepresented selections are unknown/partial, never a clean pass. Focus reduces irrelevant findings the agent sees; it does not prove fewer scanner reads or improved productivity. **Scope is not a privacy boundary.** For a mixed private vault, first make an independently allowlisted, regular-file, code-only snapshot outside the vault, then scan that snapshot locally with egress disabled. Do not point the scanner at the whole vault, even with `--scope`.

Reports include content hashes and `delta.new/resolved/persisting` IDs plus changed/deleted source paths. Resolved means no longer detected, not behaviorally correct. Analyzer rules are `holus-alignment/v3`; v1/v2 receipts must be regenerated and cannot establish resolution under corrected normalization/coverage. Comparison refuses incompatible or incomplete baselines; see [receipt compatibility](ARCHITECTURE.md#public-contract) and [scan limits](ARCHITECTURE.md#deterministic-source-checks-and-refresh). Duplicate-only `review` is advisory (exit 0); `mismatch`, `partial`, `unknown` and `unavailable` exit 1. There is no automatic skill selection or background Graphify refresh.

## Development

See [the development playbook](docs/playbooks/development.md) for setup, tests and lint commands.

See `ARCHITECTURE.md`, `specs/028-graphify-consistency-helper.md` and `specs/029-deterministic-duplication-alignment.md` for the supported contracts, research and migration disposition. Earlier numbered specs and accepted decisions are historical context for the retired retrieval product, not current interfaces.
