# 029 — Deterministic duplication and explicit alignment

Status: implemented; local behavioral validation passed, independent shipping validation remains held on owner-supported authentication/final review. Earlier Review lifecycle failures and the subsequent auth failure are preserved separately. Follows the user's expanded request (code/code, docs/code, docs/docs duplication/alignment and proof after changes). Extends spec 028; does not restore retrieval, embeddings, or LLMs. Source findings are independent of graph provenance: a stale graph remains stale, even when a new source scan completes.

## Research and bounded conclusions

Research performed 2026-10-01 using primary project documentation. No subagent tool is available in this worker session; research was performed directly, not delegated. No researched package was installed or executed.

1. **NiCad 7.0**, [official README](https://raw.githubusercontent.com/CordyJ/Open-NiCad/main/README.txt), distinguishes files/functions/blocks and exact, consistent-renaming, blind-renaming, and near-miss configurations. Its difference thresholds measure pretty-printed lines, not semantic equivalence. It needs OpenTxl/compiler tooling. Adopt the distinction between exact structure and renamed candidates, not its dependency stack or arbitrary 30% threshold. Use Python's built-in AST for a bounded Python-only slice.
2. **jscpd**, [official README](https://raw.githubusercontent.com/kucherenko/jscpd/master/README.md), uses language tokenization and rolling Rabin-Karp hashes; identifier/literal normalization and near-miss passes are separate opt-ins. Its semantic mode requires an embedding model and is explicitly experimental; related client/server code may be misidentified as mergeable duplicates. Keep literal values, external identifiers, operators, decorators and attributes in AST fingerprints. Renaming local variables is advisory, never proof of behavioral equivalence. Minimum-size filters reduce boilerplate noise. The fetched rolling main README is a research observation, not a pinned dependency or independent benchmark.
3. **Python ast**, [official documentation](https://docs.python.org/3/library/ast.html), provides parsing, AST walking/dumps and source positions without importing or executing project modules. AST shapes can change between Python versions. `literal_eval` is not safe against resource exhaustion; parsing itself has stack/memory limits. Do not execute doctests or call eval; accept only scalar literal AST nodes, bounded file sizes and AST sizes. Bind receipts to analyzer/Python version. Python AST support is not a claim of cross-language coverage.
4. **Python doctest**, [official documentation](https://docs.python.org/3/library/doctest.html), verifies explicitly executable examples rather than arbitrary documentation prose. It executes code, incompatible with this read-only no-egress checker. Borrow explicit linkage, not execution: documentation scalar facts and code scalar declarations share an explicit key.
5. **Bazel remote caching**, [official documentation](https://bazel.build/remote/caching), describes action hashes and content-addressed outputs, and warns about changing inputs during a build. Borrow input/rule fingerprints and before/after change detection. Do not add a cache or service: full bounded rescans are simpler and eliminate stale-record invalidation. A future incremental cache must include deletion, analyzer-version and dependency invalidation; not part of this slice.

These sources support the mechanisms, not a promise of semantic understanding, measured agent productivity, or general-purpose equivalence checking. Duplicate appearance can be intentional; errors require explicit alignment contracts.

## Product contract

`holus align [repo] [--scope <relative-file-or-directory>] [--docs] [--against <repo-relative-report.json>]` is read-only and deterministic. It inventories current Git tracked/unignored Python and Markdown files; non-Git directories use a bounded walk. Derived/build/dependency directories are excluded. Symlinks and escapes are refused. Graphify is never invoked. When available, existing graph node IDs are attached as navigation hints; graph status/hash are reported separately. The scan does not require a current graph to inspect source, and does not claim to refresh Graphify.

Coverage: Python function AST fingerprints (exact structure excluding docstrings/function name; conservative local renaming as a separate candidate), substantive Markdown paragraphs (exact whitespace-normalized duplicates plus high five-word-shingle overlap candidates), and explicitly linked scalar declarations. Candidate similarity does not assert common ownership or recommend deletion without agent review. Unsupported languages, unlinked arbitrary prose, dynamic values and runtime behavior are outside scope.

Example explicit facts:

```python
MAX_RETRIES = 3
# holus:fact retry-limit = MAX_RETRIES
```

```markdown
Retries are limited to five.
<!-- holus:fact retry-limit = 5 -->
```

All declarations of a key intentionally refer to the same fact. Two linked docs with different values produce docs/docs alignment evidence. Two linked Python declarations with different values produce code/code alignment evidence. Same symbol name in unrelated modules alone is NOT a contradiction. Markers are explicit contracts, not inferred from prose; prose that disagrees with its own marker is NOT verified by this tool. JSON scalar values only; nonliteral or ambiguous Python declarations are unverified rather than executed.

## Updates and receipts

Every run reads current source bytes. Source manifest SHA-256s plus scope, rules version and Python version bind the result. At the end, source inventory/bytes are rechecked; concurrent changes return unknown rather than a valid receipt. Findings cite source ranges/hashes, not full contents. No source, graph or cache is written. An agent can explicitly save stdout by shell redirection to `.holusight/`, then pass `--against` on the next run. Baselines must be matching complete, comparable reports from the same repository, scope and analyzer, with valid source/finding identities. Delta reports list new/persisting/resolved finding IDs; 'resolved' means no longer detected by these rules, NOT proof that the agent's repair is behaviorally correct. Deleted source is visible in the input delta.

Budgets and skipped/unsafe/unreadable sources are explicit. Incomplete scans cannot claim all previous findings resolved. Duplicates are advisory; explicit mismatches fail. A missing or stale graph is reported separately from source scan coverage. There is no watch daemon: rerun after edits, or call from an agent's existing validation workflow.

## Bounded terminal-review corrections (R1–R5)

The supervisor authorized between-terminal-run corrections, not a raw JSON gate approval. Syntactic module bindings now reject unsupported rebinding (including assignment RHS/definition headers, deletion, exception/pattern captures and wildcard imports); non-module fact markers are unverified. Module markers stand at column zero or inline with a top-level declaration. Ordinary module literals and function-local shadowing without a local marker remain supported. No analyzed code or runtime data-flow is executed.

The two existing scanners share Markdown fenced/indented-example filtering. Closing fences must match character and minimum opening length, with valid ASCII space/tab-only suffix; mismatched/short/trailing-text closes do not release example contents into prose. Invalid backtick info strings do not hide live prose. Indented example lines are excluded; this is not a full renderer.

Provenance brackets Git status with HEAD samples. The graph checker resamples read source hashes, path resolution/existence, graph and revision evidence at completion; the source scanner also carries end-of-run graph state instead of a falsely current initial state. Detected instability is unknown/non-current. No global locks, watch service or atomicity guarantee. Empty source fields are informational unavailable evidence, not path escapes. Resolution failures, including the documented Python 3.11 RuntimeError boundary, are contained without relaxing path restrictions.

The corrected fact/example behavior changes receipt comparability: rule identity is now `holus-alignment/v2`, and complete v1 receipts are rejected as incompatible rather than silently claiming findings resolved. R6's optional refresh simplification remains unimplemented by supervisor decision; the explicit no-write refresh refusal remains.

Executable regressions in `tests/test_review_regressions.py` were replayed against immutable baseline `71e8712`: 28 behavior assertions failed, plus the changed rule-identity guard; five valid controls passed. After corrections, the complete suite passed **94 tests**, both from the local source and from a privately installed offline wheel (using existing dev test tooling, not added runtime dependencies). Ruff passed. Actual runtime was Python 3.13.14. Python 3.11-style resolver RuntimeError handling was dependency-boundary emulation, not an actual Python 3.11 run; native 3.13 symlink-loop controls were already safe in the baseline and remained so. No claim of all-version, arbitrary-concurrency or semantic completeness is made. Durable immutable-head command/receipt paths are handed to Firstmate separately. Shipping remains blocked until supported independent Review completes.

## Focused agent entry points

`check` and `align` accept normalized repository-relative file or directory scopes. Directory matching uses path components, so `specs/` never includes `specs-other/`. `--docs` selects supported Markdown anywhere in the existing safe enumeration, without opening ignored/private derived archives. Both flags intersect. Source symlinks and escaping scopes remain refused; no extra app flag or new enumeration surface is introduced. Status remains whole-graph provenance and rejects selectors with actionable check/align guidance.

Graph checks select scoped source items and incident links, explicitly declaring `coverage.global_integrity=false`; unrelated graph corruption is not silently certified. `align` retains cross-focus comparison partners and emits only findings with a selected location, prioritizing that anchor before bounded partner projection. Scan-file and focused-file coverage are separate. Empty focus is unknown/partial. Unsupported comparison partners can still make a receipt incomplete: narrowing findings is not permission to invent a complete equivalence result.

Selector identity includes Markdown mode and normalized scope/kind. Slash-equivalent folder receipts compare; switching selectors or a file becoming a directory is incompatible. Existing complete v2 default/file baselines remain comparable where analysis and scope are unchanged. The analyzer itself remains v2; v1 is still rejected. Tests exercise console/module/API selectors, safe enumeration, cross-focus facts/copies, scope boundaries, partial partners, bounded anchor retention, and justified focused repairs while unrelated global issues remain. Local focused-versus-full output reduction demonstrates navigation relevance, not causal productivity or token savings. No paired model trial, frozen benchmark modification or Graphify refresh is part of this feature.

## Proof requirements

Public-command fixtures must demonstrate duplicates with renamed locals, changed-literal negative controls, related-but-not-duplicate docs, explicit doc/code, code/code and docs/docs contradictions, safe unknown for dynamic declarations, no import/network execution, unchanged input hashes, edits/repairs/deletions reflected on subsequent runs, honest partial coverage and baseline compatibility checks. Real repository output must be labeled advisory and source-backed; synthetic fixtures must not be called actual Graphify generation. Current source-backed tests do not prove improved agent productivity; that needs a later paired human-reviewed task study.

## Observed proof (isolated worker, 2026-10-01)

The full suite passed **55 tests**, including public Python-module commands for each of the three fact-pair families, baseline comparison after edits/deletions, changed-literal/default/external-call negative controls, ignored/private derived inputs, ambiguous values and concurrent-edit invalidation. Ruff lint and formatting passed. Reproduce the portable checks with `uv run --offline --extra dev pytest tests/test_alignment.py -q` (and the full `tests/` suite for graph and CLI regressions).

A separate five-source synthetic repository exercised the installed `holus` console command with operating-system network and filesystem-write denial (except `/dev/null` for Git). The parent proof script created the fixture and applied repairs; the checker never edited it. Every command preserved input hashes:

| Phase | Public result | Evidence |
|---|---|---|
| Before | `mismatch`, exit 1 | docs/code retries 5 vs 3; code/code timeout 10 vs 8; docs/docs protocol http vs https; one renamed-code and one exact-doc duplicate candidate |
| Inspect | cited source lines read | each fact key/value and duplicate location checked, not an invented prose contradiction |
| Manual repair then `--against` | `ok`, exit 0 | all five IDs resolved; exactly the three edited source paths changed; duplicate consumers replaced with canonical references |
| New uncommitted edit | `mismatch`, exit 1 | retries changed to 9; one newly detected ID without restarting anything |
| Repair again and repeat | `ok`, exit 0 | three repeated scans had identical source snapshots |

These local runs took about **0.40–0.45 seconds** on this host; they are not general performance or productivity benchmarks. The fixture graph was Graphify-shaped, **not generated by Graphify**. Graph state changed from current before edits to stale after repairs and stayed stale: fixing source does not prove graph freshness. Durable local receipts under `.holusight/alignment-proof-*/` include command arguments, full reports, inspection evidence, input identities and implementation HEAD; Firstmate receives the final immutable-head receipt path separately.

A real repository scan also found a substantive shared onboarding paragraph in `business/playbooks/client-onboarding.md` and `docs/playbooks/client-onboarding.md`, with both cited locations and graph node hints. This is an advisory consolidation lead, not proof that both guides should be merged. There were **no explicit fact contracts in that real scan**, so it did not verify arbitrary documentation claims. Do not present zero explicit errors as semantic consistency.

A separately authorized Graphify counterfactual used the installed `graphify update src/holusight`, documented `GRAPHIFY_OUT` override and a network-denied, write-contained sandbox. It produced a separate **75-node/150-link source-only graph** with zero dangling endpoints and a successful query. Historical graph SHA-256 `3aa6c212a5e4034045c8f1b4ae9c0e5e8c47cdf13895555fd6184201912306fa` and source bytes were unchanged. The root update had refused traversal into sandbox-denied `tasks/`; narrowing the input succeeded. That distinguishes a privacy-boundary refusal from an updater algorithm failure. The source-only output was built from dirty sources and is NOT a replacement for the whole-repository semantic graph. No docs/models/providers were invoked; the final checker never executes Graphify.

Remaining evidence gap: paired real-agent repair tasks, arbitrary prose contradictions, runtime equivalence, non-Python/Markdown coverage, and verified whole-repository graph refresh. Those earlier Review attempts timed out after emitting findings but not exiting. A later owner-authorized private-profile attempt returned an OAuth authentication failure, with no findings/gate/push/PR. This lane has no shipped PR or green CI claim; fresh validation requires the existing owner's authentication handoff. The focused-selector build is separately authorized between terminal runs and does not waive those failures.
