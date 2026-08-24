# Playbook: Run Holusight retrieval quality variation v1

This playbook runs one bounded local improvement loop. It never promotes a
candidate automatically. Every run, including failed and invalid runs, stays in
the evidence report for human review.

## 1. Create a versioned candidate

The immutable registry is `DEFAULT_CANDIDATES` in
`tests/retrieval_variation.py`, with the separate frozen quality benchmark at
`tests/fixtures/holusight_retrieval_quality_variation_benchmark.json`. To propose
one controlled variation:

1. Copy the pinned baseline definition.
2. Give the candidate a unique `candidate_id` and increment its `version` when
   changing an existing candidate.
3. Change exactly one pinned configuration value and document it in
   `controlled_variable`, `controlled_value`, and `description`.
4. Keep `query_enhancement` false. Benchmark queries must never be expanded.
5. Increment `DEFAULT_CANDIDATE_REGISTRY_VERSION` for any registry change.
6. Update the registry tests and obtain normal code review before running it.

The v1 registry contains:

- `baseline-hybrid@v1`
- `cnfb-alpha-0.25@v1`
- `metadata-boost-off@v1`

The runner rejects definitions not exactly present in this registry. The report
records the registry version and `program.candidate_definition_digest`.

## 2. Run the frozen evaluation

The benchmark path and content digest are registered in the runner. Do not edit
the benchmark during a candidate comparison. A changed or alternate benchmark
is rejected rather than silently creating a new decision boundary.

From the repository root, run:

```bash
mkdir -p /tmp/holusight-variation
uv run python -m tests.retrieval_variation \
  --repo . \
  --top-k 10 \
  --output /tmp/holusight-variation/retrieval-variation.json
```

The output path must be outside the indexed repository. The report contains:

- `runs[]` with each versioned candidate, final-record `run_digest`, and lineage
- `comparisons[]` with separate hard constraints and optimization signals
- exact, semantic, hybrid, graph-impact, ambiguity, no-evidence, and adversarial
  benchmark family measurements
- explicit evidence, clarification, and denial-routing outcomes
- `promotions.allowed = false`

A candidate exception is retained as a failed run. It does not abort or erase
other candidate evidence.

## 3. Inspect the comparison

Use this executable summary to inspect the decision fields:

```bash
uv run python - <<'PY'
import json
from pathlib import Path

report = json.loads(Path('/tmp/holusight-variation/retrieval-variation.json').read_text())
print('benchmark:', report['benchmark']['hash'])
print('registry:', report['program']['registry_version'])
for comparison in report['comparisons']:
    print(
        comparison['candidate_id'],
        comparison['status'],
        comparison['decision'],
        comparison['constraints']['violations'],
        comparison['optimization_signal'],
    )
PY
```

Interpret `comparisons[].status` as follows:

- `promotable`: valid evidence passed all hard constraints plus statistical and
  practical optimization gates. Human approval is still required.
- `inconclusive`: valid evidence did not establish a sufficient improvement.
- `reject`: valid evidence violated a protected metric or routing constraint.
- `invalid`: failed, malformed, unregistered, or lineage-mismatched evidence.

Never make a candidate decision from an invalid comparison. Do not delete
failed, invalid, inconclusive, or rejected runs.

## 4. Record human approval, rejection, or retention

Set `DECISION` to `approve`, `reject`, or `retain`, then write an append-only
operator decision next to the report:

```bash
DECISION=retain CANDIDATE=cnfb-alpha-0.25 \
uv run python - <<'PY'
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

report_path = Path('/tmp/holusight-variation/retrieval-variation.json')
report_bytes = report_path.read_bytes()
report = json.loads(report_bytes)
candidate = os.environ['CANDIDATE']
decision = os.environ['DECISION']
if decision not in {'approve', 'reject', 'retain'}:
    raise SystemExit('DECISION must be approve, reject, or retain')
comparison = next(item for item in report['comparisons'] if item['candidate_id'] == candidate)
if decision == 'approve' and comparison['status'] != 'promotable':
    raise SystemExit('only a promotable comparison may be approved')
record = {
    'schema_version': 'holus-retrieval-variation-decision/v1',
    'recorded_utc': datetime.now(timezone.utc).isoformat(),
    'candidate_id': candidate,
    'candidate_run_id': comparison['candidate_run_id'],
    'comparison_status': comparison['status'],
    'decision': decision,
    'report_sha256': hashlib.sha256(report_bytes).hexdigest(),
    'operator': os.environ.get('USER', 'unknown'),
}
out = report_path.with_name(f"decision-{candidate}-{comparison['candidate_run_id']}.json")
out.open('x', encoding='utf-8').write(json.dumps(record, indent=2) + '\n')
print(out)
PY
```

Approval authorizes a separate reviewed rollout change. It does not modify the
registry or production configuration itself. Rejection and retention require no
rollout. Preserve the report and decision record together for future trend
analysis.
