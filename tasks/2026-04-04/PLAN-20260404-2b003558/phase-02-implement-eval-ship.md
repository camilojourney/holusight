# Phase 2: Implement, Eval, and Ship

**Goal:** Implement the top-ranked retrieval technique(s) from Phase 1. Run the eval harness after each implementation. Reach MRR ≥ 0.85. Gate before shipping.

**Done when:** Eval harness reports MRR ≥ 0.85 AND hit_rate = 1.0 AND all tests pass.

**Gate:** hard — present eval results, stop for user approval before committing

---

## FOCUS ANCHOR — Read this before every step

```
You are executing: PLAN-20260404-2b003558 / Phase 2
Read status.json to confirm your current step.

SKILL ENFORCEMENT (mandatory):
  - EVERY spec → use /specs skill
  - EVERY implementation → use /code skill (Codex implements, Gemini reviews)
  - EVERY sync of docs → use /specs --sync
  - NEVER edit .py files directly with Edit/Write tools
  - If you catch yourself about to Edit a source file: STOP → invoke /code instead

After completing each step:
  1. Write output to results/phase-02-step-NN-output.md
  2. Update status.json (mark step COMPLETED, fill skill_cid)
  3. Move to the next step immediately — do NOT stop to ask the user
  
LOOP RULE: Steps 1-4 may repeat up to 3 times total. After each eval (step 3):
  - If MRR ≥ 0.85 → skip to step 5 (sync docs)
  - If MRR < 0.85 → go back to step 1 with the NEXT technique from the consult list
  - Never implement the same technique twice
```

---

## Context from Phase 1

Before starting, read:
- `results/phase-01-step-01-research.md` — technique findings
- `results/phase-01-step-02-consult.md` — ranked list, pick technique #1 first

---

## Steps

### Step 1: Write spec for the highest-priority technique

```
INVOKE: Skill(skill="specs", args="holusight write a spec for [TECHNIQUE NAME from consult output] — a retrieval quality improvement that should push MRR from 0.793 to [expected target]. Include: what it does, where in the pipeline it goes (chunker/embedder/search/store), acceptance criteria (eval harness MRR ≥ 0.85 and all existing tests pass), implementation notes, and what NOT to break.")
```

**What Claude Code does:**
1. Read `results/phase-01-step-02-consult.md` to get the technique name and description
2. Invoke the specs skill above (fill in technique name from consult output)
3. Write output reference to `results/phase-02-step-01-spec.md`
4. Update status.json: mark step 1 COMPLETED, fill `skill_cid`

**Done when:** Spec exists in `specs/NNN-technique.md` with acceptance criteria including MRR ≥ 0.85

---

### Step 2: Implement the technique

**Depends on:** Step 1 (spec)

```
INVOKE: Skill(skill="code", args="holusight implement [TECHNIQUE NAME] as specified in specs/NNN-technique.md. Key constraints: must not break existing 95 tests, must be compatible with LanceDB 1024-dim schema, must work with or without VOYAGE_API_KEY, add tests for new behavior.")
```

**What Claude Code does:**
1. Read the spec from Step 1 to get exact file targets and acceptance criteria
2. Invoke the code skill above (fill in technique name and spec path)
3. Codex implements, Gemini reviews, fixes any CRITICAL/HIGH findings
4. Write summary to `results/phase-02-step-02-impl.md`
5. Update status.json: mark step 2 COMPLETED, fill `skill_cid`

**Done when:** `pytest tests/ -q` passes with zero failures AND the technique is implemented

---

### Step 3: Run eval harness

```bash
# Run the eval harness (from repo root)
uv run python tests/eval_holusight.py \
  --top-k 10 \
  --output tasks/2026-04-04/PLAN-20260404-2b003558/results/phase-02-step-03-eval.json
# or: just eval
```

**What Claude Code does:**
1. Run the bash command above
2. Read the output JSON for `hit_rate` and `mrr_at_10`
3. Write a summary to `results/phase-02-step-03-eval.md` with: technique tested, hit_rate, MRR, delta vs baseline (0.793), pass/fail vs target (0.85)
4. Update status.json: mark step 3 COMPLETED

**Done when:** Eval JSON exists and MRR value is captured

---

### Step 4: Check gate — proceed or loop

**Depends on:** Step 3 (eval results)

Read the eval result from Step 3:

```
IF mrr_at_10 >= 0.85 AND hit_rate >= 1.0:
  → Mark step 4 COMPLETED
  → Proceed to Step 5 (sync docs)
  → Do NOT loop back

ELSE:
  → Log: "MRR = {value}, below 0.85 target. Looping to next technique."
  → Increment loop_iteration counter in status.json
  → IF loop_iteration >= 3: STOP, present results to user, explain what was tried
  → ELSE: Go back to Step 1 with the NEXT technique from the consult list
```

**Done when:** Either MRR ≥ 0.85 (success) OR loop_iteration = 3 (exhausted — escalate to user)

---

### Step 5: Sync docs

**Depends on:** Step 4 (MRR ≥ 0.85 confirmed)

```
INVOKE: Skill(skill="specs", args="holusight --sync update ARCHITECTURE.md, docs/roadmap.md, and CLAUDE.md to reflect the new retrieval technique implemented in Phase 2. Include the new MRR benchmark number in ARCHITECTURE.md performance table and roadmap.")
```

**What Claude Code does:**
1. Invoke the specs --sync skill above
2. Verify ARCHITECTURE.md performance table has updated MRR ≥ 0.85
3. Write summary to `results/phase-02-step-05-sync.md`
4. Update status.json: mark step 5 COMPLETED

**Done when:** ARCHITECTURE.md performance table shows MRR ≥ 0.85 in the new row

---

## GATE (hard) — Present before final commit

After Step 5 completes, STOP and present to user:

```
GATE — Phase 2 Complete

Technique implemented: [name]
Eval results:
  - Hit rate: [X]%
  - MRR@10: [X] (baseline: 0.793, target: 0.85, achieved: YES/NO)
  - Delta: [+X] MRR

Tests: [N] passing
Files changed: [list]

Docs updated: ARCHITECTURE.md (performance table), docs/roadmap.md, CLAUDE.md

Approve to commit and push?
```

**Do NOT commit until user says yes.**

---

## Output

- `results/phase-02-step-01-spec.md` — spec reference
- `results/phase-02-step-02-impl.md` — implementation summary
- `results/phase-02-step-03-eval.json` — eval results
- `results/phase-02-step-03-eval.md` — eval summary with delta
- `results/phase-02-step-05-sync.md` — docs sync summary
- Updated source files in `src/codesight/`
- Updated docs: ARCHITECTURE.md, docs/roadmap.md
