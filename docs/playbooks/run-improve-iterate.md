# Run Holusight improve-iterate (self-measure loop)

## What this is

`just improve-iterate` is the **advisory self-improvement measurement loop**:

1. Run `proper-eval` (suite bind + fleet-smoke + eval-pilot).
2. Compare to the previous local iteration receipt (if any).
3. Record a new receipt under `.holusight/improvement-runs/proper-eval-iterations/`.
4. Print `progress` + `next_action` for the next human/agent turn.

It does **not** edit source, admit frozen cases, merge PRs, or auto-promote
(ADR-0019). Improvement still happens by implementing a candidate, then
re-running this loop.

## How to run each iteration

```bash
# 1) Implement a candidate change on a branch
# 2) Measure
just improve-iterate
# 3) Follow next_action (fix, admit case via improve-intake, research, or human review)
# 4) Repeat
```

Related commands that feed the wider loop:

- `holus improve-intake "..."` — propose a new regression case (no write)
- `holus improve-run` — pilot corpus with lineage / progress vs prior
- `just proper-eval` — single-shot advisory gate without history

## Progress values

| progress | meaning |
|---|---|
| `baseline` | first recorded iteration |
| `improved` | visible metrics improved or recovered from block |
| `stagnated` | still passing but no metric gain — intake/research |
| `regressed` | visible metrics fell |
| `blocked` | proper-eval blocked |
| `indeterminate` | dirty/unbound subject |

## Deferred

AVO/G2 external acceptance and hidden-holdout scoring remain out of this loop.
