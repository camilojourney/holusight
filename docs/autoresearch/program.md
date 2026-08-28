# Advisory cross-machine experiment program v1

**Status:** setup only — `pending_independent_read_only_review`. This charter is
not authorization to launch a lane or trial. All outputs are advisory only;
promotion, merge, deployment, external action, and network coordination are
out of scope.

## Scope and authority

The global program has exactly 1,000 trial IDs. The laptop owns `0001-0500`;
Mini owns `0501-1000` and must not run any other ID. The assignment is
exclusive even where a global Phase B partition crosses the machine boundary.
The tracked machine-readable contract is
[`../../autoresearch/mini-program-v1.json`](../../autoresearch/mini-program-v1.json).
`mini_runner.py` performs only local pre-launch or proposed-row validation and
cannot start a lane. `--validate-trial` is read-only and checks a proposed row
against an optional local `results.tsv` solely to reject duplicates before it
could count.

No executable AQ-R24 or final G2 evaluator input is visible in this base.
Those are hard pre-launch blockers. This setup does not substitute data, a gold
evaluator, a hidden/shadow packet, or NVIDIA AVO details. A separate reviewed,
tracked change must bind any future required input by immutable hash before an
experiment can be considered launchable.

## Counted-trial contract

A row counts only when it is complete, schema-valid, and has status `recorded`.
Every recorded row must have all of the following, in addition to its unique
assigned trial ID:

- `purpose_id`, `phase`, hypothesis, target failure mode, exactly one
  intervention, expected metric effect, falsifier, control/baseline identity,
  protected gates, and the concrete decision informed;
- immutable subject, evaluator, and manifest hashes; prompt/config identity;
  deterministic seed; and wall time;
- metrics, mutation summary, output identity, status, and a
  `keep`, `discard`, or `crash` outcome.

Malformed, partial, duplicate, out-of-range, purposeless, or gate-violating
rows are non-counting. Do not repair them into counted results. Retain their
idea and rejection reason in the untracked append-only per-lane idea ledger;
never encode rejected ideas as candidate code. A completed ID is never rerun,
including after a crash.

## Frozen phases

**Phase A is exactly 100 metaevaluation trials (`0001-0100`):** 20
parser/normalization, 20 citation-validity adversaries, 20
contradiction-and-`UNKNOWN` calibration, 20 completeness/concision calibration,
and 20 repeatability/negative controls against human-authored gold. Freeze the
evaluator only when deterministic repeatability, FP/FN behavior,
known-good/known-bad sensitivity, and prompt/ordering-artifact checks all pass.
The required human-authored gold is not supplied by this setup.

**Phase B is exactly 900 product trials (`0101-1000`):** four deterministic,
equal partitions of 225: hybrid retrieval/ranking (`0101-0325`),
chunking/context/graph expansion (`0326-0550`), answer/citation/`UNKNOWN`
policy (`0551-0775`), and contradiction/completeness/concision
(`0776-1000`). Mini's subset is `0501-0550`, `0551-0775`, and `0776-1000`.
The Phase A evaluator remains frozen throughout Phase B. Each comparison uses a
matched baseline/control and paired execution with a supported deterministic
seed. Uncertainty is clustered by lineage; any protected failure rejects the
candidate. Top candidates are explicitly reserved for later replay against the
final G2 evaluator; that replay is not authorized here.

## Local execution boundaries

At most four experiment lanes may exist. Their `run.log` files are overwritten
and bounded (maximum 2 MiB); never use `tee`. Their `results.tsv` and idea
ledger are local, untracked, and append-only. Maintain a 2 GiB free-disk floor
before write or execution. No global config, credential, telemetry, private or
hidden input, cross-machine mutable filesystem, service, or network action is
permitted.

Cross-machine supervision is Git-only: checkpoints and references carry
progress. A machine accepts progress only when evaluator, manifest, ledger, and
lineage-parent hashes all match. Checkpoints record purpose coverage, best
lineages, five-trial stagnation, and repeated idea families. They must reject a
completed ID rather than rerun it.

### Laptop checkpoint namespace

A future supervised observer polls the exact ordinary-Git prefix
`refs/remotes/origin/fm/holusight-avo-laptop-` every 15 minutes, using only the
twelve frozen refs in the machine-readable contract: four calibration refs
(`0001-0013`, `0014-0026`, `0027-0038`, `0039-0050`) and eight product refs
(`0051-0107`, `0108-0164`, `0165-0220`, `0221-0276`, `0277-0332`,
`0333-0388`, `0389-0444`, `0445-0500`). This setup does not poll or contact a
remote. Before a first ten-trial checkpoint, a missing ref means
*not yet published*, not zero completed, and grants no duplicate-ID authority.
Reclaim an ID only after a present, hash-verified checkpoint later becomes stale
or explicit laptop-stop evidence arrives. No custom network service or shared
mutable filesystem is permitted.

## Review gate

Before any lane may start, an independent reviewer must perform a read-only
review of this setup, confirm the hard blockers are resolved through visible
tracked material, and approve a new tracked launch checkpoint. This branch does
not perform that review.
