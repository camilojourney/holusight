# Playbook: Run Holusight retrieval quality variation v1

This playbook is for a single, bounded local loop. The loop has **no automatic
promotion**. Humans review every candidate and must manually approve any rollout.

## 1. Candidate definition and version anchor

Use the baseline plus explicit candidate registry in
`tests/retrieval_variation.py` with the separate quality benchmark at
`tests/fixtures/holusight_retrieval_quality_variation_benchmark.json`:

- baseline: `baseline-hybrid`
- candidate: `cnfb-alpha-0.25`
- candidate: `query-enhancement-on`

The candidate definition digest is emitted in each run as
`program.candidate_definition_digest` and `benchmark.hash` is emitted as
`benchmark.hash`.

## 2. Freeze benchmark and run the loop

```bash
python -m tests.retrieval_variation \
  --repo . \
  --top-k 10 \
  --output /tmp/retrieval-variation.json
```

The output includes:
- `runs`: one entry per candidate with `run_id`, `run_digest`, and full lineage.
- `comparisons`: baseline-vs-candidate outcome records.
- `promotions.allowed = false` and a required human review marker.

## 3. Compare outcomes and retain lineage

Open `/tmp/retrieval-variation.json` and check:

- `comparisons[].status`
  - `promotable` means statistically significant and practical gate passed.
  - `inconclusive` means no practical improvement.
  - `reject` means protected metric regression.
  - `invalid` means evidence mismatch (query-set drift or bad run integrity).
- `comparisons[].constraints.violations` for hard-stop rules.
- `comparisons[].optimization_signal` for primary improvement signal.

Do not delete non-promotable candidate runs. They are required for failed-case
retention and future trend analysis.

## 4. Human approval workflow

Before approval:

- Candidate must keep all hard constraints non-regressing:
  - `hit_rate`, `recall_at_10`, `evidence_completeness`, `ndcg_at_10`
- Primary improvement must pass both gates:
  - significance p < 0.05
  - `mrr_at_10` delta >= 0.02

After approval:

- Add follow-up action as a future gap row in
  `tests/fixtures/holusight_retrieval_quality_variation_benchmark.json` if real-user
  failures appear.
- Re-run the loop after the code or dataset change.

## 5. Add a new real-use gap test for future rounds

Append a new frozen row with:

- unique `id`
- `query`
- `family` (for trend visibility)
- `expected_file` (or `__NO_MATCH__` for diagnostic/no-answer)
- any `notes` needed for review

Keep raw file paths and prompt-like text out of candidate metadata. Evidence is kept
in-repo with repository-relative references only.
