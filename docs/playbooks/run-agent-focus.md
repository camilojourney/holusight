# Run Holusight agent-focus (deterministic orientation)

## Why

Holusight is for **agents** that need project context and alignment before they
search, answer, or change the repo. `just agent-focus` is a small harness that:

1. Builds a deterministic **context pack** (what to read, hard rules, P0 gaps).
2. Runs a fixed **council of lenses** (structure, promotion boundary, eval loop,
   CI, docs, security, Fleet entrypoint, rigid tests, …).
3. Emits a single focus verdict: `pass` / `block` / `indeterminate`.

No LLM calls. No spawning chat agents. Promotion stays denied (ADR-0019).

This replaces the idea of “100 copies discussing” with rigid, replayable
viewpoints any agent can trust.

## How to run

```bash
just agent-focus
```

Exit codes: `0` pass, `1` block, `3` indeterminate.

## Where it sits in the improve loop

```text
just agent-focus          # orient / align
# …implement candidate…
just improve-iterate      # measure vs prior receipt
# follow next_action; repeat
```

## Related

- `just proper-eval` — single-shot advisory gate
- `just improve-iterate` — iterative measurement
- `.self-improvement/NEXT.md` — P0 product gaps
