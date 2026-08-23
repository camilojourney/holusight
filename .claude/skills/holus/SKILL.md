---
name: holus
description: >
  Ask this Holusight-tracked repository for evidence before trusting or
  editing a spec, ADR, or the code it governs. Use when a question needs
  repository evidence with provenance/freshness/egress attached, not a
  fluent guess - "where is X enforced", "has this spec drifted from its
  implementation", "is the structural graph stale".
---

# holus - Holusight-AXI repository evidence CLI

Schema version: `0.2.0` (generated from `src/codesight/axi_schema.py` - do not hand-edit the command reference below; run `python -m codesight.axi_skill_gen` after changing the schema).

## When to use this

1. Use native/exact search for exact identifiers and known file questions - `holus` is for uncertain, conceptual, or cross-file/mixed code-and-docs questions.
2. Call `holus evidence "<question>"` when the relevant location is uncertain.
3. Call `holus check [scope]` when the question concerns whether a spec/ADR has drifted from what it governs.
4. Never treat a `stale`, `partial`, or `unavailable` provider state as if it were current, authoritative evidence - surface the state to the user instead of a confident answer.

## Commands

### `holus`

Content-first repository home view: identity, snapshot, provider freshness, egress, contract summary.

Flags:
- `--format` (toon/json/text) [default: toon] - Output encoding.

Examples:
```
holus
python -m codesight.cli_axi
```

### `holus evidence "<question>"`

Return the smallest current evidence packet for a question, routed across the exact, structural, consistency, and (if already indexed) semantic providers.

Flags:
- `--mode` (auto/exact/semantic/structure) [default: auto] - Restrict which providers run.
- `--provider` (exact/structural/consistency/semantic) - Restrict to exactly one named provider.
- `--explain-route` - Include route_reason per provider.
- `--allow-egress` - Permit the semantic provider to query a Voyage-embedded index (external API call). Off by default.
- `--full` - Disable excerpt truncation.
- `--fields` - Comma-separated dotted-path projection (e.g. snapshot,evidence.source).
- `--format` (toon/json/text) [default: toon] - Output encoding.

Examples:
```
holus evidence "where is retry policy enforced?"
python -m codesight.cli_axi evidence "where is retry policy enforced?"
holus evidence "where is retry policy enforced?" --mode exact
python -m codesight.cli_axi evidence "where is retry policy enforced?" --mode exact
holus evidence "<question>" --fields snapshot,evidence.source,evidence.location
python -m codesight.cli_axi evidence "<question>" --fields snapshot,evidence.source,evidence.location
```

### `holus check [scope]`

Post-change consistency check: has the canonical spec/ADR at `scope`, or every concept if `scope` is omitted, drifted from its linked artifacts since the cache was last refreshed?

Flags:
- `--refresh` - Refresh the consistency cache to current disk state before checking (resets the drift baseline).
- `--fields` - Comma-separated dotted-path projection (e.g. snapshot,evidence.source).
- `--format` (toon/json/text) [default: toon] - Output encoding.

Examples:
```
holus check
python -m codesight.cli_axi check
holus check specs/013-holusight-axi-consistency-architecture.md
python -m codesight.cli_axi check specs/013-holusight-axi-consistency-architecture.md
holus check --refresh
python -m codesight.cli_axi check --refresh
```

### `holus status`

Repository snapshot, per-provider freshness/egress, contract (claim) pass/fail counts, and open health-flag counts by severity.

Flags:
- `--fields` - Comma-separated dotted-path projection (e.g. snapshot,evidence.source).
- `--format` (toon/json/text) [default: toon] - Output encoding.

Examples:
```
holus status
python -m codesight.cli_axi status
```

### `holus providers`

List each provider's availability, version/model, freshness, and egress class.

Flags:
- `--format` (toon/json/text) [default: toon] - Output encoding.

Examples:
```
holus providers
python -m codesight.cli_axi providers
```

### `holus improve-status`

Continuous-improvement lifecycle status: frozen-case corpus summary, status-quo coverage, and placement-guard capabilities.

Flags:
- `--cases` - Path to the frozen case corpus JSONL file.
- `--fields` - Comma-separated dotted-path projection (e.g. snapshot,evidence.source).
- `--format` (toon/json/text) [default: toon] - Output encoding.

Examples:
```
holus improve-status
python -m codesight.cli_axi improve-status
holus improve-status --cases tests/fixtures/holusight_eval_pilot_cases.jsonl
python -m codesight.cli_axi improve-status --cases tests/fixtures/holusight_eval_pilot_cases.jsonl
```

### `holus improve-intake "<summary>"`

Produce an explicit, sanitized, content-minimized proposed regression case for human-reviewed admission. No files are written.

Flags:
- `--origin` - Case origin.
- `--kind` (regression/comparative) [default: regression] - Case kind.
- `--diagnosis-ref` - Reference path for reproduced findings.
- `--fix-ref` - Reference to the fix commit/PR for a reproduced gap.
- `--cases` - Path to the frozen case corpus JSONL file.
- `--admitted-by` - Approver name or team in plain text.
- `--admitted-at` - YYYY-MM-DD date for the admission record.
- `--case-id` - Explicit candidate case id to propose.
- `--fields` - Comma-separated dotted-path projection (e.g. snapshot,evidence.source).
- `--format` (toon/json/text) [default: toon] - Output encoding.

Examples:
```
holus improve-intake "holus evidence can starve structural evidence" --origin reproduced_usage_gap --kind comparative --admitted-by team-x
python -m codesight.cli_axi improve-intake "holus evidence can starve structural evidence" --origin reproduced_usage_gap --kind comparative --admitted-by team-x
python -m codesight.cli_axi improve-intake "structural graph stale case" --origin spec_documented_finding --admitted-by team-x
```

### `holus improve-run`

Run the frozen continuous-improvement corpus with explicit lineage and machine-readable lifecycle outcome.

Flags:
- `--cases` - Path to the frozen case corpus JSONL file.
- `--workflow` - Execution workflow label.
- `--tool` - Tool that produced this run.
- `--model` - LLM model name used by the run.
- `--compare-result` - Previous pilot result JSON path to compare against for stagnation/research signals.
- `--candidate-id` - Stable candidate identifier for this run.
- `--output` - Write the full PilotRunResult JSON to this path.
- `--allow-egress` - Allow egress-only pilot operations when a case explicitly requires it.
- `--allow-semantic` - Allow semantic providers while running cases that require them.
- `--scorecard` - Also print the Fleet aggregate scorecard preview.
- `--format` (toon/json/text) [default: toon] - Output encoding.

Examples:
```
holus improve-run
python -m codesight.cli_axi improve-run
holus improve-run --candidate-id run-42 --workflow crewmate --model claude-sonnet-5
python -m codesight.cli_axi improve-run --candidate-id run-42 --workflow crewmate --model claude-sonnet-5
holus improve-run --cases tests/fixtures/holusight_eval_pilot_cases.jsonl --compare-result /tmp/last-run.json
python -m codesight.cli_axi improve-run --cases tests/fixtures/holusight_eval_pilot_cases.jsonl --compare-result /tmp/last-run.json
```

### `holus improve-placement`

Validate a proposed artifact path against structure, canonical locations, and existing duplicates. Never edits files.

Flags:
- `--artifact-type` (case/fixture/test/spec/adr/decision/playbook/source/skill/agent/docs) - Logical placement kind for a proposed artifact.
- `--proposed-path` - Proposed artifact path to validate.
- `--fields` - Comma-separated dotted-path projection (e.g. snapshot,evidence.source).
- `--format` (toon/json/text) [default: toon] - Output encoding.

Examples:
```
holus improve-placement --artifact-type case --proposed-path tests/fixtures/my_case.jsonl
python -m codesight.cli_axi improve-placement --artifact-type case --proposed-path tests/fixtures/my_case.jsonl
holus improve-placement --artifact-type spec --proposed-path specs/018-new-idea.md
python -m codesight.cli_axi improve-placement --artifact-type spec --proposed-path specs/018-new-idea.md
```

## Output formats

`--format toon` (default, compact agent-facing) · `--format json` (lossless canonical interchange) · `--format text` (human-readable). `--fields a,b.c` projects a payload down to just those dotted paths before rendering.

## Getting help

`--help` works on every command, including with no command (`holus --help`) for the full command list. Unknown flags and commands are rejected with exit code 2 and the valid set listed inline - never silently ignored.

## Exit codes

`0` success, including a definitive "no evidence" or "already up to date" answer · `1` runtime error · `2` usage error (unknown command/flag, missing required argument).
