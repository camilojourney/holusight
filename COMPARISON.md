# Holusight vs CLAUDE.md: Honest Comparison

> Written 2026-02-28. No sugarcoating.

---

## 1. What Each System Actually Does Well (and Where It Fails)

### System A: CLAUDE.md / AGENTS.md (Static Context)

**What it does well:**
- **Intent and philosophy.** "Why we do things this way" — embeddings can't capture this. A human writing "never modify tool signatures without a spec" carries weight no vector search reproduces.
- **Guardrails and workflow rules.** "Don't push without tests." "Use sequential phases." These are policy, not code.
- **Cheap.** ~2-5K tokens loaded once at session start. Zero retrieval cost.
- **Immediate.** No indexing, no startup, no dependencies.
- **Curated signal.** A human deciding what matters filters noise better than any algorithm.

**Where it fails:**
- **Staleness.** The moment code diverges from docs, CLAUDE.md becomes a liar. And it *always* diverges.
- **Blind spots.** Humans forget to document things. They document what they *think* is important, not what an agent actually needs.
- **Doesn't scale.** Works for 1,500-line repos like Holusight. Falls apart at 50K+ lines.
- **No cross-referencing.** Can't answer "where is this function called?" or "what imports this module?"

### System B: Holusight (Embedding-Based Search)

**What it does well:**
- **Finding things you didn't know to ask about.** "Show me error handling patterns" across a 200-file repo — no human would document all of those.
- **Scales linearly.** 1K files or 100K files, same interface.
- **Freshness.** Re-index and you're current. No human needed.
- **Cross-cutting queries.** "Where do we validate user input?" finds results across files, layers, modules.
- **Token savings.** Returns 5-10 relevant chunks instead of an agent cat-ing 30 files.

**Where it fails — and this is where honesty matters:**
- **Semantic search is fuzzy.** "Find the auth middleware" might return 3 relevant chunks and 2 irrelevant ones. An agent reading CLAUDE.md that says `auth is in src/middleware/auth.py` is faster and more precise.
- **Chunk boundaries are lossy.** Regex chunking (what Holusight uses) breaks at arbitrary points. You lose context. Tree-sitter chunking (spec 004, not yet built) would help but still isn't perfect.
- **Embeddings don't understand code deeply.** `all-MiniLM-L6-v2` was trained on natural language, not code. It knows "authentication" ≈ "login" but doesn't understand that `verify_token()` implements auth. Code-specific models (CodeBERT, StarCoder embeddings) do better but still aren't magic.
- **Small repos don't need it.** For repos under ~5K lines, `grep` + `CLAUDE.md` is genuinely better. Holusight's value inflects around 10-20K lines.
- **Index maintenance is real overhead.** Not huge, but non-zero. Stale indexes are worse than no index.

### Brutally Honest Take on Embeddings

Embeddings for code search are **real but overhyped**. They help most when:
1. The codebase is large (20K+ lines)
2. You don't know what you're looking for (exploratory)
3. The query is conceptual, not exact ("how do we handle rate limiting?" vs "find rate_limit function")

For exact lookups, `grep`/`rg` beats embeddings every time. For small repos with good docs, CLAUDE.md wins. The sweet spot is medium-to-large repos where no single person knows the whole codebase.

---

## 2. Complementary or Redundant?

**Complementary. Not even close to redundant.**

They serve different cognitive functions:

| Need | CLAUDE.md | Holusight |
|------|-----------|-----------|
| "What are the rules?" | ✅ Perfect | ❌ Can't represent rules |
| "Why was this decision made?" | ✅ If documented | ❌ Finds code, not intent |
| "Where is X implemented?" | ⚠️ If mentioned | ✅ Finds it |
| "What calls this function?" | ❌ | ⚠️ Fuzzy but useful |
| "Show me similar patterns" | ❌ | ✅ This is its strength |
| "What's the architecture?" | ✅ Curated overview | ❌ Gives fragments |

**Best setup:** CLAUDE.md for intent/rules/architecture + Holusight for "find me the code that does X." They don't overlap much.

---

## 3. Token Savings — Quantified

### Without Holusight (current agent behavior):
A typical coding agent exploring a 50-file repo:
- Reads directory tree: ~500 tokens
- Reads 8-15 files to find relevant code: ~800-1500 tokens × 12 files = **~12,000 tokens**
- Many reads are wasted (file wasn't relevant)
- Total exploration: **~15,000-20,000 tokens**

### With Holusight:
- `search("JWT validation", top_k=5)`: returns 5 chunks, ~300 tokens each = **~1,500 tokens**
- Agent reads 1-2 full files for context: **~2,000 tokens**
- Total: **~3,500-4,000 tokens**

**Savings: ~75-80% on the exploration phase.** For a multi-step task with 3-4 searches, that's 40-60K tokens saved per session.

### Real-world caveat:
This only matters for large repos. For Holusight's own 1,500-line codebase, an agent reads everything in ~4K tokens. No savings.

### Where it REALLY saves:
Maintenance crons running nightly across multiple repos. If backend-guardian checks 5 repos × 3 searches each = 15 searches. At 15K tokens saved per search vs full-file reading, that's **~225K tokens/night** saved. At ~$0.003/1K tokens (input), that's ~$0.68/night or ~$20/month. Not life-changing, but not nothing.

---

## 4. How Cursor Actually Works (vs Holusight)

### What we know about Cursor:

1. **Codebase indexing**: Cursor uses embeddings (likely OpenAI's `text-embedding-3-small` or similar) to index the entire repo. Similar to Holusight conceptually.

2. **AST awareness**: Cursor parses code with Tree-sitter for structure. It understands function boundaries, class hierarchies, imports. **Holusight does NOT do this yet** (spec 004 is planned but unbuilt).

3. **Cross-file type resolution**: Cursor can follow imports, understand type relationships across files. This is LSP-level intelligence, not just embedding search. Holusight doesn't attempt this.

4. **Retrieval pipeline**: Cursor likely uses a hybrid approach too — keyword + semantic + reranking. Holusight's BM25 + vector + RRF is comparable at the retrieval level.

5. **Context assembly**: Cursor's real magic is **how it assembles context for the LLM** — selecting which code chunks to include, in what order, with what surrounding context. This is prompt engineering at scale, not just search.

### Holusight vs Cursor — Honest Assessment:

| Capability | Cursor | Holusight |
|-----------|--------|-----------|
| Embedding search | ✅ | ✅ |
| BM25/keyword search | ✅ | ✅ |
| Hybrid retrieval | ✅ | ✅ (RRF) |
| Tree-sitter chunking | ✅ | ❌ (planned) |
| Cross-file resolution | ✅ (LSP) | ❌ |
| Type-aware search | ✅ | ❌ |
| Context assembly | ✅ (sophisticated) | ❌ (returns raw chunks) |
| Local/private | ❌ (cloud) | ✅ |
| MCP integration | ❌ | ✅ |

**Bottom line:** Holusight is ~40% of what Cursor does for code understanding. The retrieval layer is comparable. The intelligence layer (AST, types, context assembly) is where Cursor pulls ahead. But Holusight is local, private, and plugs into any MCP-compatible tool — that's a real differentiator.

---

## 5. Would Holusight Help Maintenance Crons?

### Concrete examples:

**backend-guardian** checking for security issues:
- Currently: reads known files, runs linters
- With Holusight: `search("user input without sanitization")` — finds patterns across the entire codebase that static analysis might miss. **Marginal improvement.** Dedicated SAST tools (Semgrep, Bandit) are better for this.

**canvas-guardian** checking UI consistency:
- Currently: checks specific component files
- With Holusight: `search("color hex hardcoded")` or `search("font-size inline style")` — finds style violations scattered across components. **Actually useful** — these are the needles-in-haystacks that guardians miss.

**Dependency drift detection:**
- `search("import deprecated_module")` across all repos — finds usage of deprecated APIs. **Useful but `rg` does this too.**

**Pattern violation detection:**
- `search("direct database query outside repository pattern")` — finds code that bypasses the data layer. **This is where embeddings genuinely help** because the violation isn't a keyword match, it's a semantic pattern.

### Honest verdict:
Holusight would give crons ~20% better coverage on semantic patterns. But 80% of what crons need is still grep/lint/test-based. It's an incremental improvement, not a revolution.

---

## 6. Consulting Product Angle

### The pitch:
"We index your codebase and give your team AI-powered search to understand legacy code, find patterns, and onboard faster."

### Market reality:

**Who competes:**
- **Sourcegraph** (Cody) — mature, well-funded, does exactly this at enterprise scale. $50M+ ARR.
- **GitHub Copilot** — code search is built into the chat now.
- **Cursor** — the darling of developer tools, $100M+ ARR.
- **Greptile** — YC-backed, specifically does codebase indexing as API.
- **Bloop** (now acquired) — was doing semantic code search.
- **Codium/Qodo** — code understanding for testing.

**The uncomfortable truth:** This is a crowded space with well-funded players. Holusight as a standalone product competes with companies that have 50-200 engineers.

**Where it COULD work as consulting:**
- **Legacy codebase audits.** "We'll index your 500K-line Java monolith and give you a report on patterns, anti-patterns, dead code, and architectural issues." This is a *service*, not a product, and services don't need to out-feature Sourcegraph.
- **M&A due diligence.** Companies acquiring tech companies need to understand codebases fast. Holusight + an analyst = faster technical due diligence.
- **Onboarding acceleration.** "New hires ramp up 40% faster with semantic search." Hard to prove but compelling pitch.

**Revenue potential:** $5-15K per engagement for audits. Repeatable but not scalable without turning it into a product.

### Recommendation:
As a consulting *tool* (not product), Holusight is useful. As a standalone SaaS, it's bringing a knife to a gunfight against Sourcegraph and GitHub. **Use it as a differentiator in consulting engagements, not as the product itself.**

---

## 7. Should Juan Build This NOW?

### The priorities (from USER.md):
1. **Job search** — THE bottleneck. Everything else is secondary.
2. **Pilaster.ai** — the flagship product
3. **Holus** — consulting firm

### Holusight's current state:
- ~1,500 lines of Python
- Core search works (BM25 + vector + RRF)
- Missing: Tree-sitter chunking, watch/unwatch, incremental refresh
- Has specs written for next features but unbuilt

### Is it a distraction or force multiplier?

**Right now: distraction.**

Here's why:
1. Juan's own repos are small (1-5K lines each). Holusight doesn't help much at this scale.
2. The job search doesn't benefit from Holusight.
3. Pilaster doesn't need it yet — it needs users, not code search.
4. The consulting firm doesn't have clients yet. Building tools for hypothetical clients is premature optimization.

### When it becomes a force multiplier:
- When Juan has a consulting client with a large codebase to audit
- When Pilaster grows past 20K lines and multiple contributors
- When he's doing technical interviews and can demo it as a portfolio piece

### The portfolio argument:
Holusight IS a good portfolio piece for job interviews. "I built a semantic code search MCP server with hybrid retrieval" is a strong talking point for AI Engineer roles. But the repo already exists and works — polishing it for interviews takes 2-4 hours, not weeks of feature development.

---

## Final Verdict

| Question | Answer |
|----------|--------|
| CLAUDE.md vs Holusight? | **Complementary.** Different jobs. |
| Are embeddings hype? | **Partially.** Real value at scale, overhyped for small repos. |
| Token savings? | **75-80%** on exploration, meaningful for cron workloads. |
| Comparable to Cursor? | **40% of the way.** Retrieval is similar, intelligence layer isn't. |
| Help maintenance crons? | **Incrementally.** ~20% better pattern detection. |
| Consulting product? | **Tool, not product.** Use it to differentiate services. |
| Build now? | **No.** Polish for portfolio (2-4 hrs). Build features when there's a real user. |

### The One-Liner:
Holusight is a solid piece of engineering that doesn't have a customer yet. Ship the job search. When a consulting client shows up with a 200K-line monolith, *then* invest in tree-sitter chunking and cross-file resolution.

---

*This document lives in the Holusight repo for future reference.*
