# Phase 1: Research and Decide

**Goal:** Know exactly which 2-3 retrieval techniques are worth implementing for CodeSight. Backed by 2026 literature and 3-specialist deliberation.

**Done when:** Research doc exists with claim-tagged findings on 5+ techniques AND consult output has a ranked list of top 3 techniques with estimated MRR lift, effort, and implementation path.

---

## FOCUS ANCHOR — Read this before every step

```
You are executing: PLAN-20260404-2b003558 / Phase 1
Read status.json to confirm your current step.

SKILL ENFORCEMENT (mandatory):
  - EVERY research question → use /research skill
  - EVERY technical architecture decision → use /consult-engineering skill
  - NEVER edit repo source files directly with Edit/Write tools
  - If you catch yourself about to Edit a .py file: STOP → invoke /code instead

After completing each step:
  1. Write output to results/phase-01-step-NN-output.md
  2. Update status.json (mark step COMPLETED, fill skill_cid)
  3. Move to the next step immediately — do NOT stop to ask the user
```

---

## Steps

### Step 1: Research — latest 2026 retrieval improvement techniques

```
INVOKE: Skill(skill="research", args="holusight two-part research question: (1) What are the best retrieval quality improvement techniques in 2025-2026 for hybrid code+document RAG systems? Cover: HyDE (Hypothetical Document Embeddings), late chunking, contextual compression, multi-vector indexing, RAPTOR, query decomposition, ColBERT/BGE-M3, BGE-reranker-v2, and any others from recent papers. (2) GENERATE NOVEL EXPERIMENT IDEAS not in any paper — think about code-specific retrieval problems: e.g., function-call graph context injection, import-chain aware chunking, scope-aware query routing (function query vs class query vs module query), symbol table augmentation, docstring-vs-body dual embeddings, test-file co-indexing. We have: AST chunking, BM25+vector hybrid with RRF, voyage-code-3 embeddings, voyage rerank-2, metadata filename boost, VPRF. MRR@10=0.793 on 20-query code repo eval (100% hit rate). Target: MRR 0.85+. What would move a result from rank 2 to rank 1?")
```

**What Claude Code does:**
1. Invoke the research skill above using the Skill tool
2. The skill dispatches gatherer agents + adversary analysis + online search
3. Write output to `results/phase-01-step-01-research.md`
4. Update status.json: mark step 1 COMPLETED, fill `skill_cid` with the research CID

**Done when:** Research doc exists at `results/phase-01-step-01-research.md` with:
- At least 5 techniques covered
- Each technique has: what it does, expected MRR lift, implementation complexity, source citations
- [VERIFIED] claims from primary sources (papers, benchmarks)

---

### Step 2: Consult — which techniques to implement for CodeSight

**Depends on:** Step 1 (research doc)

```
INVOKE: Skill(skill="consult-engineering", args="holusight 3 specialists deliberate: given the research findings (known techniques AND novel ideas) in tasks/2026-04-04/PLAN-20260404-2b003558/results/phase-01-step-01-research.md, which 2-3 experiments should CodeSight run to push MRR from 0.793 to 0.85+? Current stack: AST chunking (tree-sitter), BM25+vector RRF, voyage-code-3 embeddings (1024d), voyage rerank-2, metadata filename boost, VPRF. Constraints: must be compatible with LanceDB schema, must not break 95 existing tests, prefer techniques that improve rank ordering (MRR) not just recall (hit rate is already 100%). Novel/unpublished experiments are welcome — we are not restricted to papers. Rank by: expected MRR lift x implementation effort x correctness risk.")
```

**What Claude Code does:**
1. Invoke the consult-engineering skill above using the Skill tool
2. The skill runs 3 specialists (2 Claude + 1 Gemini) with deliberation rounds
3. Write output to `results/phase-01-step-02-consult.md`
4. Update status.json: mark step 2 COMPLETED, fill `skill_cid` with the consult CID

**Done when:** Consult doc exists at `results/phase-01-step-02-consult.md` with:
- Ranked list of top 3 techniques
- For each: expected MRR lift (range), implementation effort (S/M/L), key risks
- Clear recommendation on what to implement first

---

## Output

- `results/phase-01-step-01-research.md` — claim-tagged research findings on 5+ techniques
- `results/phase-01-step-02-consult.md` — ranked implementation list from 3-specialist deliberation

## Feeds into Phase 2

- Technique name and description for spec writing (Phase 2 Step 1)
- Expected MRR lift for gate decision (Phase 2 Step 4)
- Implementation path for `/code` task description (Phase 2 Step 2)
