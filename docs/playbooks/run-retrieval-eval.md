# Playbook: Run the Retrieval Evaluation Harness

See `specs/014-retrieval-evaluation-harness-expansion.md` for the full
design, taxonomy, and limitations. This playbook is the command flow only.

## 1. Quick regression check (unchanged default)

```bash
just eval
# equivalent to:
uv run --extra dev python tests/eval_holusight.py --top-k 10
```

Indexes the repo, runs the original 20-query fixture through production
`hybrid_search` only, and prints `hit_rate` / `mrr@10` to stderr.

## 2. Compare baselines on the expanded taxonomy

```bash
uv run --extra dev python tests/eval_holusight.py \
    --queries tests/fixtures/holusight_eval_taxonomy.json \
    --baselines hybrid,bm25,exact,graphify \
    --top-k 10 \
    --output /tmp/eval_taxonomy.json
```

Stderr prints one summary line per baseline. The JSON has a
`results.<baseline>.family_breakdown` block per baseline — read that first:
it tells you *which query family* a baseline is winning or losing on, which
is more actionable than the aggregate `hit_rate` alone. For example, the
`exact` baseline should score ~0 on `conceptual_localization` (expected — a
literal substring match can't find a sentence-length paraphrase) and well on
`exact_lookup` (if it doesn't, something is wrong with the fixture or the
corpus walk).

If `graphify` is in `--baselines`, check `graphify_status` at the top of the
output before trusting that baseline's numbers:

```json
"graphify_status": {
  "available": true,
  "stale": true,
  "built_at_commit": "5aa41bb...",
  "current_commit": "47daca8..."
}
```

`stale: true` means `graphify-out/graph.json` was built before the current
`HEAD` — run `graphify update .` (or the `fleet_graphify.py` wrapper
referenced in `AGENTS.md`) to refresh it, then re-run. `available: false`
means the graphify baseline returned `[]` for every query — not a bug, just
nothing to score.

## 3. Run one baseline and diff over time

```bash
uv run --extra dev python tests/eval_holusight.py \
    --queries tests/fixtures/holusight_eval_taxonomy.json \
    --baselines hybrid \
    --output /tmp/eval-$(date +%Y%m%d).json
```

Keep dated JSON snapshots outside the repo (e.g. `/tmp` or your own notes
directory) and diff `results.hybrid.hit_rate` / `.mrr_at_10` /
`.ndcg_at_10` across runs — a regression here is worth investigating before
merging a retrieval-affecting change.

## 4. Opt-in: try a different embedding model (never automatic)

```bash
uv run --extra dev python tests/eval_variants.py \
    --variant-model sentence-transformers/all-MiniLM-L6-v2 \
    --variant-backend local \
    --queries tests/fixtures/holusight_eval_taxonomy.json \
    --top-k 10 \
    --output /tmp/variant_local_minilm.json
```

- Requires `--variant-model` **and** `--variant-backend` explicitly — there
  is no default variant.
- Builds a disposable local index in a temp directory and deletes it when
  done; the default `~/.codesight/data/` store is never touched.
- `voyage`/`api` backends need the matching API key already set in the
  environment (`VOYAGE_API_KEY` / `OPENAI_API_KEY`) — if it's missing, the
  script fails fast with a clear error rather than silently falling back.
- Check the `guardrail` block in the output — it should always read
  `"variant_changed_process_default": false`.
- Cost is reported as `null` unless you pass `--price-per-1k-input <rate>`
  (a rate you supply, not a hardcoded table — provider prices change).

```bash
# With an explicit price snapshot, to get a cost estimate:
uv run --extra dev python tests/eval_variants.py \
    --variant-model voyage-code-3 --variant-backend voyage \
    --price-per-1k-input 0.00006 \
    --queries tests/fixtures/holusight_eval_taxonomy.json
```

## 5. Add a new query to the taxonomy

Append to `tests/fixtures/holusight_eval_taxonomy.json` following the
existing shape:

```json
{
  "id": "EX-21",
  "query": "literal string that actually exists in the target file",
  "family": "exact_lookup",
  "split": "dev",
  "expected_file": "src/codesight/whatever.py",
  "exact_string": "the literal string above"
}
```

For `exact_lookup`/`config_lookup` entries, verify `exact_string` (or the
query itself) is genuinely present in `expected_file` before committing —
don't hand-guess. For `contradiction_no_answer` entries, set
`"expected_file": "__NO_MATCH__"` (see `tests.eval_harness.NO_MATCH_SENTINEL`)
and add a `notes` field explaining why the capability doesn't exist here.
