# Retrieval Evaluation Harness Expansion

**Status:** Vertical slice implemented (bounded direct-PR). This spec narrows
`specs/012-holusight-overnight-benchmark-continuous-evaluation-research.md`'s
research (a much larger, multi-night, multi-repository benchmark
architecture) down to what is actually built here: an expansion of the
existing local retrieval eval harness, not the full spec 012 platform.

**Authorization boundary:** this is the captain-authorized direct-PR
expansion described in spec 012's experiment ladder as **Stage 0/1** ("free
smoke" / "local private core" — $0 external spend, local-only, no downloads).
It does not authorize spec 012's Stage 2+ (paid one-night runs, public
benchmark corpora, a router benchmark, or an independent holus-axi
interface study). It does not change `codesight.config.DEFAULT_EMBEDDING_MODEL`,
does not deploy anything, and does not alter external links.

## 1. Purpose

`tests/eval_harness.py` already scored one retrieval arm (production
`hybrid_search`) against 20 hand-written queries. That answers "did this
change regress hybrid search?" but not "how does hybrid search compare to
its own sparse/exact/structural components?", "how does the eval taxonomy
break down by query type?", or "what would a different embedding model cost
to try?" This expansion adds those without replacing the original harness or
its default behavior — `just eval` still runs exactly what it ran before.

## 2. What changed

| File | Change |
|---|---|
| `tests/eval_harness.py` | `run_eval()` gained an optional `search_fn` parameter (defaults to `hybrid_search`, so all 13 pre-existing tests pass unchanged) and new deterministic metrics: `recall_at_k`, `ndcg_at_10`, `evidence_completeness`, `avg_latency_ms`. `EvalQuery` gained `family`, `split`, `expected_evidence` (all optional, default-compatible). |
| `tests/eval_baselines.py` | **New.** Three `SearchFn` baselines sharing `hybrid_search`'s call signature: `exact_search_fn_factory` (literal substring grep), `bm25_search_fn` (FTS5 sparse-only, bypasses vector/RRF/rerank), `graphify_structural_search_fn_factory` (Graphify symbol-graph baseline). |
| `tests/eval_variants.py` | **New.** Opt-in embedding-model variant runner — never invoked by default, never changes the process default model. See §5. |
| `tests/eval_holusight.py` | CLI gained `--baselines` (comma-separated, default `hybrid` — unchanged behavior) and now defaults `--queries` handling to load the expanded fixture's `family`/`split`/`expected_evidence` fields when present. |
| `tests/fixtures/holusight_eval_taxonomy.json` | **New.** 85 queries across 7 families (§3), grounded in this repo's own tracked source/docs. The original `tests/fixtures/holusight_eval_20q.json` is untouched and remains the `just eval` default. |
| `tests/test_eval_harness.py`, `tests/test_eval_baselines.py`, `tests/test_eval_variants.py` | New/expanded test coverage (§7). |

## 3. Query taxonomy and corpus provenance

All 85 queries in `holusight_eval_taxonomy.json` target this repository's own
tracked, public source files, specs, ADRs, and tests — the same corpus
`just eval` already indexes. **No customer data, no indexed-folder content
from any Holusight deployment, and no content outside this git repository is
used anywhere in this harness.** This satisfies the read-only/no-private-data
invariant in `AGENTS.md` by construction: the corpus *is* the codebase, which
is exactly what the engine is designed to search, and the fixture is
reproducible by any developer with a checkout of this repo — no download, no
credential, no external fetch.

Every `exact_lookup` and `config_lookup` entry's `exact_string` was verified
at fixture-build time (a one-off script, not shipped, asserted the literal
string exists in the named file before writing the JSON) — none of these
targets are hand-guessed.

| Family | Count | What it tests | Gold |
|---|---:|---|---|
| `exact_lookup` | 20 | Literal symbol/string retrieval (the ripgrep-favorable case) | Exact file, verified literal substring |
| `conceptual_localization` | 20 | Natural-language description of behavior | Expected file (original 20q style) |
| `symbol_reference` | 10 | Cross-file linkage ("how does A call B") | Primary file, optional `expected_evidence` multi-file gold |
| `doc_synthesis` | 15 | Broad spec/ADR/architecture questions | Expected doc file |
| `config_lookup` | 10 | Env var / constant name lookup | Expected file, verified literal substring |
| `test_coverage` | 5 | "Which test covers X" | Expected test file |
| `contradiction_no_answer` | 5 | Query for a capability that does not exist in this repo | `NO_MATCH_SENTINEL` — diagnostic-only, see §4 |

85 sits inside spec 012's frozen-suite target range (80–100) while staying a
**vertical slice**: this is not spec 012's full 96-task private suite with
mutation families, held-out splits, human-labeled impact/compliance
adjudication, or hidden qrels. Every gold label here is directly
inspectable in the fixture file — nothing is hidden, because nothing here
claims to be tamper-resistant promotion evidence. `split` is currently `dev`
for all 85 entries (no calibration/held-out separation yet); that
distinction is deferred, see §8.

## 4. Diagnostic probes are not scored as pass/fail

The five `contradiction_no_answer` queries ask about capabilities this
codebase does not have (Kubernetes, GraphQL, OAuth device-code flow, Rust
bindings, distributed consensus). CodeSight's retrieval engine has no
abstention mechanism — `hybrid_search` always returns its best-effort top-K,
even when nothing is actually relevant. Scoring these queries pass/fail
against a fabricated "should abstain" rule would invent ground truth the
system cannot currently produce.

Instead, `run_eval()` runs these queries normally, records the top result's
file/score/latency in `per_query` with `"diagnostic_only": true`, and
**excludes them from `hit_rate`, `recall_at_k`, `mrr_at_10`, `ndcg_at_10`,
and `evidence_completeness`** (`num_graded` vs. `num_diagnostic_probes` in
`EvalResult` makes the split explicit). This keeps the harness's aggregate
metrics deterministic and truthful rather than silently inflating or
deflating them with an invented abstention rule. Building real abstention
is out of scope here — see §8.

## 5. Baselines

All three new baselines share `hybrid_search`'s exact call signature —
`(store, embedder, query, top_k, config) -> list[SearchResult]` — so
`run_eval()` scores any of them identically and results are directly
comparable in the same run.

- **`exact_search_fn_factory(repo_root)`** — literal, case-insensitive
  substring match over every file `codesight.indexer.walk_repo_files` would
  index (the same gitignore-aware corpus the production index uses). No
  index structure, no embeddings. The ripgrep/grep-style control from spec
  012's variant matrix.
- **`bm25_search_fn`** — calls `store.bm25_search()` directly and skips
  vector search, RRF merge, CNFB, and reranking. Isolates the sparse arm.
- **`graphify_structural_search_fn_factory(repo_root)`** — matches query
  tokens against Graphify node IDs (`graphify-out/graph.json`) and ranks
  files by distinct matched symbols. **Deliberately reuses
  `codesight.consistency._load_structural_index` and
  `structural_graph_freshness`** (the already-landed Phase 1 consistency
  system, spec 013) instead of re-parsing the graph a second way, so the
  eval harness and the consistency engine agree on what "available" and
  "stale" mean for the same file.

### Graphify availability/staleness handling

`tests.eval_baselines.graphify_availability(repo_root)` reports, without
running any query:

```python
GraphifyAvailability(available: bool, stale: bool, built_at_commit: str | None, current_commit: str | None)
```

`eval_holusight.py`'s CLI calls this once per run (when `graphify` is in
`--baselines`) and prints a `warning:` to stderr plus a `graphify_status`
block at the top level of the JSON output — never buried only inside
per-result text. On this repository, at the time of writing,
`graphify-out/graph.json` **is** available but **is stale**
(`built_at_commit` is PR #13's commit; current `HEAD` is PR #16's) — the CLI
correctly surfaces this rather than silently scoring against a stale graph
as if it were current. If `graphify-out/graph.json` is absent or
unparsable, the baseline's `SearchFn` returns `[]` for every query rather
than raising, so a run with `--baselines graphify` degrades to "0 hits,
clearly flagged as unavailable" instead of crashing the whole eval run.

**Graphify CLI note:** per this task's instructions, `graphify query`/
`graphify explain`/`graphify path` were attempted first. The `graphify` CLI
and the `fleet_graphify.py` wrapper referenced in this repo's `AGENTS.md`
are both unavailable in this task's execution environment (`graphify not
found`; wrapper script path does not exist on this host). The tracked
`graphify-out/graph.json` and `graphify-out/*/GRAPH_REPORT.md` artifacts
were inspected directly instead (see the git history of this PR for the
exact commands run). `graphify update .` was likewise not run after this
PR's code changes, for the same reason — the graph's staleness relative to
this PR is expected and is exactly what the CLI's own availability check
above reports.

## 6. Metrics (all deterministic)

Every metric `run_eval()` computes is derived from exact string/rank
matching against hand-verified `expected_file`/`expected_evidence` fields —
**no LLM judge is used anywhere in this harness.** This follows spec 012's
priority order (executable/deterministic truth over calibrated judges) and
the project's existing instruction to keep model-inferred evaluation
(Graphify's own `semantic` provider, `consistency.py`'s opt-in embedding
similarity) clearly separated from deterministic truth.

| Metric | Definition |
|---|---|
| `hit_rate` | Fraction of graded queries where `expected_file` appears anywhere in the returned results |
| `recall_at_k[K]` | Fraction of graded queries whose first matching result ranks ≤ K, for each `K` in `k_values` (default `1, 5, 10`) |
| `mrr_at_10` | Mean reciprocal rank of the first matching result |
| `ndcg_at_10` | `1/log2(rank+1)` for the first matching result (single-relevant-item nDCG; 1.0 for a rank-1 hit, 0.0 on a miss) |
| `evidence_completeness` | Mean fraction of `expected_evidence` files found anywhere in the results (defaults to `[expected_file]` when no multi-file gold is set — so single-file queries reduce to a 0/1 hit indicator) |
| `avg_latency_ms` | Mean wall-clock time per query's `search_fn` call |
| `tokens_per_correct_answer` / `total_tokens` | Unchanged from the original harness |

`family_breakdown` (computed in `eval_holusight.py`, not the core harness)
rolls `hit_rate` up per query family so a run's output is directly readable
without a spreadsheet — see §9 for a real example.

## 7. Model-pluggability guardrail (`tests/eval_variants.py`)

`tests/eval_variants.py` is a **separate, opt-in module** — it is never
imported or invoked by `eval_holusight.py`'s default flow, and running
`just eval` never touches it.

Because a different embedding model produces vectors in a different space
than whatever is already indexed at `~/.codesight/data/<hash>/`, a variant
run **cannot** reuse the default store. It:

1. Requires the caller to explicitly pass `--variant-model` and
   `--variant-backend` (no default variant; `EmbeddingVariantSpec` has no
   default constructor for either field).
2. Sets `CODESIGHT_DATA_DIR` to a fresh `tempfile.mkdtemp()` **before**
   `codesight` is imported anywhere in the process (config.py reads
   `DATA_DIR` from the environment once, at import time), builds a small,
   disposable, local-only index there, and `shutil.rmtree`s it in a
   `finally` block. The default `~/.codesight/data/` store is never opened.
3. If the requested backend needs an API key (`voyage`, `api`) and it's
   absent, `codesight.embeddings.get_embedder` raises immediately — no
   fallback, no silent network call, no silent downgrade to another model.
4. Reports, explicitly, every run: `provider` (backend/model/dimensions),
   `index` (files indexed, chunks created, build wall time), `usage`
   (embedding call counts and an **estimated** token count — `len(text)//4`,
   the same fallback tokenizer `eval_harness.py` already uses for snippets,
   explicitly labeled as an estimate, not a provider-billed count), `cost`
   (`null` with an explicit "unknown, not assumed zero" note unless the
   caller supplies `--price-per-1k-input`; **never** guessed from a
   hardcoded price table, because provider prices change — this mirrors
   spec 012's cost-model warning about pinning a price snapshot rather than
   assuming an old rate still holds), and a `guardrail` block asserting
   `variant_changed_process_default: false` alongside the actual
   `codesight.config.DEFAULT_EMBEDDING_MODEL` value at run time.

`tests/test_eval_variants.py` asserts this guardrail directly: after a
variant run using an explicit model/backend, `codesight.config`'s
`DEFAULT_EMBEDDING_MODEL` is re-imported and checked unchanged, and the
payload's own `guardrail` block is asserted.

## 8. Limitations (do not over-claim this)

This is a **vertical slice**, not spec 012's overnight benchmark and not a
production readiness claim:

- **85 queries, all `split: "dev"`.** No calibration/held-out split, no
  mutation families, no adjudicated human labels. A ~2-percentage-point
  quality claim cannot be resolved at this sample size (spec 012 §"What one
  night can establish" applies at even smaller scale here).
- **No abstention.** `contradiction_no_answer` queries are diagnostic-only
  (§4), not a scored safety gate — this harness does not implement or claim
  to test engine-side ACL/abstention behavior.
- **Graphify structural baseline is coarse.** It matches query tokens
  against Graphify node IDs (derived symbol identifiers), not full node
  metadata (the tracked `_StructuralIndex` in `consistency.py` does not
  expose node labels, only `node_file`/`file_nodes`/`links`) — it is a
  meaningful structural signal, not a tuned retrieval system, and it
  currently under/over-matches on prose-heavy documentation nodes.
- **BM25 baseline score is rank-derived (`1/rank`), not a normalized `bm25()`
  value** — the FTS5 query path used here (`ChunkStore.bm25_search`) returns
  ranked IDs, not raw scores; rank position is the deterministic signal
  actually available.
- **Single-repository corpus.** Every query targets this one repository.
  Spec 012's transfer-across-repositories caveat applies unchanged.
- **No statistical testing.** No bootstrap confidence intervals, no
  Holm correction, no paired significance test — every number here is a
  point estimate over 80 graded queries, meant for fast local iteration
  and regression-catching, not for a promotion decision.
- **Not a production benchmark.** Nothing in this harness's output should
  be cited as evidence of production retrieval quality without the
  sample-size, split, and statistical caveats above attached.

## 9. Command flow

```bash
# Default — unchanged from before this PR (20 queries, hybrid only)
just eval

# Expanded taxonomy across all local baselines
uv run python tests/eval_holusight.py \
    --queries tests/fixtures/holusight_eval_taxonomy.json \
    --baselines hybrid,bm25,exact,graphify --top-k 10

# One baseline only, writing JSON for later diffing
uv run python tests/eval_holusight.py \
    --queries tests/fixtures/holusight_eval_taxonomy.json \
    --baselines bm25 --output /tmp/bm25_eval.json

# Opt-in embedding-model variant (never run automatically; requires an
# explicit model + backend; local-only unless you pass --variant-backend
# voyage/api with the matching API key already set)
uv run python tests/eval_variants.py \
    --variant-model sentence-transformers/all-MiniLM-L6-v2 \
    --variant-backend local \
    --queries tests/fixtures/holusight_eval_taxonomy.json
```

See `docs/playbooks/run-retrieval-eval.md` for a walkthrough including how
to read `family_breakdown` and the Graphify availability warning.

## 10. Non-goals for this PR

Everything in spec 012 not listed in §2 above: paid API runs, public
benchmark dataset imports (BEIR/MTEB/CoIR/SWE-bench/LongMemEval/etc.), the
96-task private suite with mutation families and held-out splits, human
annotation/adjudication, the router benchmark, the independent holus-axi
interface study, the unattended overnight runner state machine, and any
production promotion mechanism. All remain future work gated by their own
explicit authorization, per spec 012's experiment ladder.
