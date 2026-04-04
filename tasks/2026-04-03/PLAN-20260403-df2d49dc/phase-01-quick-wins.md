# Phase 1: Quick Wins — Reranker + Query Expansion

**Goal:** 15-20% lift with zero re-indexing. Swap generic reranker for code-specific voyage rerank-2.5, add LLM query expansion with 3 variants.
**Done when:** eval run shows hit_rate ≥ 65%, token efficiency baseline measured

## FOCUS ANCHOR — Read this before every step

```
You are executing: PLAN-20260403-df2d49dc / Phase 1
Read status.json to confirm your current step.

SKILL ENFORCEMENT (mandatory):
  - EVERY source code change → use /code skill (Codex implements, Gemini reviews)
  - NEVER edit .py files directly with Edit/Write tools
  - If you catch yourself about to Edit a .py file: STOP → invoke /code instead

After completing each step:
  1. Write output to results/phase-01-step-NN-{name}.md
  2. Update status.json (mark step COMPLETED, advance to next)
  3. Move to the next step immediately — do NOT stop to ask the user
```

---

## Step 1: Swap reranker to voyage rerank-2.5

```
INVOKE: Skill(skill="code", args="holusight swap reranker from ms-marco-MiniLM-L-6-v2 to voyage rerank-2.5 API. Changes needed: (1) src/codesight/search.py — add VoyageReranker class that calls voyageai.Client.rerank() with model='rerank-2', input_type='document'. Replace the existing cross-encoder reranker when VOYAGE_API_KEY is set. (2) src/codesight/config.py — add DEFAULT_RERANKER_MODEL logic: if VOYAGE_API_KEY set, use 'rerank-2', else fall back to existing 'cross-encoder/ms-marco-MiniLM-L-6-v2'. (3) Keep the local cross-encoder as fallback for users without VOYAGE_API_KEY. The voyage rerank API signature: client.rerank(query=str, documents=list[str], model='rerank-2', top_k=N). Returns RerankingObject with .results list of {index, relevance_score}.")
```

**What Claude Code does:**
1. Invoke the skill above
2. Verify VOYAGE_API_KEY is detected in config (already set in .env)
3. Write output to results/phase-01-step-01-reranker.md
4. Update status.json: step 1 COMPLETED

**Done when:** `grep -r "rerank-2" holusight/src/` finds the new model reference, tests pass

---

## Step 2: Add LLM query expansion

```
INVOKE: Skill(skill="code", args="holusight add LLM query expansion to search pipeline. In src/codesight/search.py, add a expand_query() function that: (1) takes the original query string, (2) calls the LLM (use existing llm.py backend, claude-haiku for speed) with prompt: 'You are a code search expert. Rewrite this query into 3 diverse variants to maximize code retrieval recall. Return only the 3 variants, one per line, no numbering: {query}', (3) returns list of 3 variant strings. In hybrid_search(), when query expansion is enabled (new ServerConfig flag: query_expansion: bool = False, default False), call expand_query() and search each variant, then merge all result lists via RRF before reranking. Add CODESIGHT_QUERY_EXPANSION=true env var support. Keep expansion off by default to avoid latency regression for users who don't need it.")
```

**What Claude Code does:**
1. Invoke the skill above
2. Write output to results/phase-01-step-02-query-expansion.md
3. Update status.json: step 2 COMPLETED

**Done when:** `CODESIGHT_QUERY_EXPANSION=true` triggers 3-variant search in logs, tests pass

---

## Step 3: Add token efficiency metrics to eval harness

```
INVOKE: Skill(skill="code", args="holusight add token efficiency metrics to the eval harness at ~Projects/system/skills/fleet-brain/scripts/eval_search.py. Add to each result: (1) token_count: estimate token count of all returned chunks (use len(text.split())*1.3 as approximation), (2) tokens_per_hit: token_count if this query was a hit (found relevant result), else None. At end of eval, report: avg_tokens_per_query, avg_tokens_per_hit, token_efficiency_ratio (tokens_per_hit / avg_tokens_per_query). This measures how many tokens the LLM must consume to get a correct answer. Lower = better = cheaper.")
```

**What Claude Code does:**
1. Invoke the skill above
2. Write output to results/phase-01-step-03-token-metrics.md
3. Update status.json: step 3 COMPLETED

**Done when:** `python3 eval_search.py --backend codesight` outputs token efficiency metrics

---

## Step 4: Run eval and record Phase 1 results

```bash
cd /Users/mini/.openclaw/workspace/github/~Projects/system/skills/fleet-brain/scripts
CODESIGHT_RERANKER=true CODESIGHT_RERANKER_MODEL=rerank-2 CODESIGHT_QUERY_EXPANSION=true \
  python3 eval_search.py --backend codesight --output ../data/eval_phase1_results.json
```

Write results to `results/phase-01-eval.json`. Record:
- hit_rate (target ≥ 65%)
- mrr_at_10
- avg_tokens_per_hit
- comparison vs baseline (52.5% / 0.352)

**Done when:** eval completes, numbers recorded in results file

---

## Step 5: Consult checkpoint (conditional)

**Only invoke if hit_rate < 60% after Steps 1-2:**

```
INVOKE: Skill(skill="consult-experiments", args="holusight After implementing voyage rerank-2.5 and LLM query expansion, hit rate is still below 60% (was 52.5% baseline). Diagnose: which technique failed to lift, and what should we prioritize next? Context: eval queries are from fleet-brain/data/eval_queries.json (40 queries), index contains voyage-code-3 vectors + BM25, RRF fusion. Reranker swapped to voyage rerank-2 API. Query expansion adds 3 LLM variants. What's the most likely failure mode and what should Phase 2 prioritize?")
```

**Done when:** decision recorded, Phase 2 priorities updated if needed

---

## Output

- `results/phase-01-step-01-reranker.md` — reranker implementation notes
- `results/phase-01-step-02-query-expansion.md` — query expansion implementation
- `results/phase-01-step-03-token-metrics.md` — token metrics implementation
- `results/phase-01-eval.json` — eval numbers: hit_rate, mrr, token efficiency

## Feeds into Phase 2

Phase 2 needs: confirmed baseline after Phase 1 changes, token efficiency baseline number.
