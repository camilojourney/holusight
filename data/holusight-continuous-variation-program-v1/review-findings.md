# Review findings

Run: `01M0RM3N2XQZQ97PF8J17R0RCF`

## F001

- severity: error
- file: `tests/retrieval_variation.py`
- line: 84
- action: ask-user
- description: Intent forbids "query expansion of benchmark content", but the default registry enables `query_enhancement` and describes it as query expansion. Remove this candidate or obtain explicit approval to change the requirement.

## F002

- severity: error
- file: `tests/retrieval_variation.py`
- line: 374
- action: ask-user
- description: The requirement says decisions cannot use invalid or malformed evidence, but comparison validates only identifiers and sequence lengths before trusting metrics. A run with altered hashes, lineage, metrics, query order, or digest can still become promotable. Validate the complete canonical run and benchmark identity at the comparison boundary.

## F003

- severity: error
- file: `tests/retrieval_variation.py`
- line: 318
- action: auto-fix
- description: The significance calculation is incorrect and tests hit-rate booleans rather than the primary MRR metric. One discordant win produces p=0.0455 even though the exact two-sided sign-test p-value is 1.0, allowing false promotable verdicts. Use an exact paired test over per-query reciprocal-rank deltas.

## F004

- severity: error
- file: `tests/retrieval_variation.py`
- line: 263
- action: ask-user
- description: The required measurable exact, graph-impact, ambiguity, no-evidence, adversarial, and routing cases are mostly labels rather than measurements: every row uses hybrid retrieval, `exact_string` is ignored, and diagnostic top-result evidence is discarded and excluded from constraints. A candidate can fail every denial case and remain promotable.

## F005

- severity: error
- file: `tests/retrieval_variation.py`
- line: 472
- action: ask-user
- description: The requirement retains failed outcomes, but one candidate exception aborts the list comprehension and produces no report for any candidate. Catch failures per candidate and retain an explicit failed or invalid record with lineage.

## F006

- severity: error
- file: `tests/retrieval_variation.py`
- line: 218
- action: ask-user
- description: The required immutable baseline/candidate registry is not pinned: `ServerConfig(**overrides)` inherits environment-dependent reranker, query-enhancement, CNFB, and embedding defaults that are absent from the candidate digest. The same registry fingerprint can therefore execute different configurations, and a candidate can equal the baseline.

## F007

- severity: error
- file: `tests/retrieval_variation.py`
- line: 465
- action: ask-user
- description: The benchmark is not enforced as frozen or canonical. Any `--benchmark` file, or an edited default fixture, receives a fresh hash and can produce a promotable verdict because no immutable registry checks the canonical path and expected digest.

## F008

- severity: error
- file: `tests/retrieval_variation.py`
- line: 290
- action: ask-user
- description: The required reproducible run fingerprint is not reproducible from the emitted record: `run_digest` is computed before `lineage` is added, so recalculating `_run_record_digest` over the final run yields a different value and lineage changes are undetectable.

## F009

- severity: error
- file: `tests/test_retrieval_variation.py`
- line: 196
- action: ask-user
- description: The required end-to-end tests are absent. The main workflow test replaces both benchmark loading and candidate execution, while the remaining tests call private helpers; none executes the CLI, CodeSight indexing, retrieval variants, output persistence, or denial behavior.

## F010

- severity: error
- file: `tests/retrieval_variation.py`
- line: 603
- action: ask-user
- description: The required no-write-to-indexed-folders invariant is not preserved: `--output` may resolve inside `--repo`, where the command creates directories and writes JSON. Reject output paths within the resolved indexed root.

## F011

- severity: error
- file: `docs/playbooks/run-retrieval-variation-program.md`
- line: 48
- action: ask-user
- description: The required operator workflow is incomplete. The playbook lists existing candidates but does not explain versioned candidate creation, and its approval section provides neither an approval record/rollout procedure nor a rejection-and-retention procedure.
