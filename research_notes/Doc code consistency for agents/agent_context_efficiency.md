# Agent Context Efficiency: What Actually Makes Coding Agents Faster and More Accurate at Repository Context

> Research notes for the report writer. Scope: repository-scale context supply to coding agents. Emphasis on measured results with named benchmarks.
>
> **Source-quality caveat applied throughout:** several 2026 arXiv preprints surfaced here (IDs beginning 2601-2609) are recent and in most cases not yet peer-reviewed. Where a number comes from a vendor blog or a practitioner post rather than a paper, it is labeled. Where I could only obtain a number via a search-engine summary of a PDF rather than direct extraction, that is flagged explicitly.
>
> **One extraction failure to note up front:** I attempted direct PDF extraction of arXiv 2606.22417 ("Code Isn't Memory: A Structural Codebase Index Inside a Coding Agent") and got a low-fidelity result that asserted a "~12-15% absolute improvement" I could not corroborate anywhere in the text or in a second source. I am treating that accuracy figure as **unverified and probably an extraction artifact**, and I report only that paper's cost/token/turn figures, which two independent retrievals agreed on. Flagging this rather than passing the number through.

---

## Key Question 1: Retrieval vs. agentic search - what do SWE-bench-era results actually show?

### Takeaway

This is the one place where the evidence is now fairly strong and it runs **against** prebuilt embedding retrieval as the primary context mechanism for single-repo issue-resolution tasks: one-shot lexical and dense retrieval score close to *random* on repository exploration, while agentic grep/read explorers score 4-8x higher on the same metric. Cursor removed semantic indexing from its retrieval path entirely despite measuring a 12.5% accuracy gain from it, which is the single most informative data point in the field because it is a vendor voluntarily giving up a measured win for freshness and simplicity. The important qualifier: agentic search wins on *localization*, and localization is frequently **not** the binding constraint on resolve rate.

### Cited Findings

- **SWE-Explore** (848 instances, 10 languages, 203 repositories, ground truth from successful agent trajectories, K=5 returned regions, line-level core context averaging 1,578 visible lines per instance) measured classical retrievers clustering near random and agentic explorers far above them: BM25 HitFile 0.079 / nDCG@500 0.132; TF-IDF 0.140 / 0.223; RAG (Potion embeddings) 0.088 / 0.136; Mini-SWE-Agent 0.640 / 0.885; Claude Code 0.667 / 0.938. Context efficiency: BM25 0.087, RAG 0.100, Mini-SWE-Agent 0.754, Claude Code 0.829 — [SWE-Explore, arXiv 2606.07297](https://arxiv.org/html/2606.07297v1)
- The same paper's stated conclusion: "repository exploration is not well captured by one-shot lexical or embedding retrieval alone" — [SWE-Explore](https://arxiv.org/html/2606.07297v1)
- **Asymmetry finding, directly relevant to top-k choice:** SWE-Explore's controlled degradation experiments found that removing 50% of core regions sharply reduces resolve rate, while padding with irrelevant non-core code has minimal impact once essential evidence is present. On easier subsets "the redundant-context curve closely tracks the missing-context curve," and the authors conclude "missing core evidence matters more than moderate precision loss," recommending explorers prioritize recall over filtering — [SWE-Explore](https://arxiv.org/html/2606.07297v1)
- **CORE-Bench** (built partly from SWE-bench-series instances, three levels: code understanding, issue-to-edit localization, broader context retrieval) measured a sharp drop from traditional code search to agentic-coding code retrieval for embedding models. Qwen3-Embedding-8B: 71.7/96.9 on LEVEL-1, dropping to 20.3/48.0 on LEVEL-2 and 34.4/41.5 on LEVEL-3. The paper also found simple supervised fine-tuning of existing embedding models significantly improves the agentic setting — [CORE-Bench, arXiv 2606.11864](https://arxiv.org/html/2606.11864)
- **Cursor removed semantic indexing.** Cursor's current docs describe the retrieval path as local and grep-based ("Instant Grep"), stating Cursor does not upload file paths or code to build a search index and does not store embeddings of your codebase for search — [Cursor docs, codebase indexing](https://cursor.com/docs/context/codebase-indexing) (**vendor doc**)
- Cursor's stated reasoning as discussed publicly: newer coding agents are good enough at searching repos directly, greping in parallel, inspecting directories, reading likely files and refining the search themselves, which Cursor says now works as well or better in most cases — [HN discussion of Cursor dropping indexing](https://news.ycombinator.com/item?id=49487825) (**secondary/forum**)
- **The number Cursor gave up:** Cursor was reporting a ~12.5% average agent-accuracy gain from semantic search on top of grep as of January 2026, ranging 6.5%-23.5% by model, plus +2.6% code retention on large codebases and -2.2% dissatisfied follow-up requests — [How Cursor Actually Indexes Your Codebase, Towards Data Science](https://towardsdatascience.com/how-cursor-actually-indexes-your-codebase/) (**secondary write-up of vendor research; I did not locate Cursor's own primary post for the 12.5% figure — treat as vendor-originated**)
- Cursor's pre-shift pipeline, for contrast: file change triggers syntactic chunking, asynchronous background embedding, embeddings cached by chunk content so unchanged chunks hit cache, embeddings plus line numbers and obfuscated file paths in a remote vector DB (Turbopuffer), running over 1 trillion vectors across 80 million namespaces — [Cursor, Securely indexing large codebases](https://cursor.com/blog/secure-codebase-indexing) (**vendor blog**)
- **Augment's SWE-bench Verified experience (practitioner report):** Augment reached the top of the SWE-bench Verified leaderboard and reported exploring embedding-based retrieval tools but finding that "for SWE-bench tasks this was not the bottleneck - grep and find were sufficient," with agent *persistence* compensating for less sophisticated tools — [Why Grep Beat Embeddings in Our SWE-Bench Agent (Augment lessons)](https://jxnl.co/writing/2025/09/11/why-grep-beat-embeddings-in-our-swe-bench-agent-lessons-from-augment/) (**practitioner blog summarizing a talk, not a controlled ablation**)
- **Counter-evidence that embeddings can win:** one research-agent benchmark found embedding-based retrieval significantly outperformed agent-led in-context retrieval (41.7% pass rate vs. 36.1%) and AST-based retrieval (33.3%), and that placing all relevant code into the context window degraded performance — [surfaced via search of arXiv 2506.19724, "From Reproduction to Replication"](https://arxiv.org/pdf/2506.19724) (**note: this is a research-reproduction agent benchmark, not SWE-bench-style bug fixing; domain differs**)
- **Agentic search is 2-8 seconds per query vs. sub-100ms for an index.** Reported typical latencies: semantic search under 100ms (requires index), lexical grep/ripgrep under 50ms (no index), agentic multi-turn search 2-8 seconds — [Morph, Agentic Search](https://www.morphllm.com/agentic-search) (**vendor blog**)
- **The critical mechanism finding, from CodeGrep:** retrieval quality does not translate linearly into downstream utility. Below a precision threshold retrieval actively *hurts*: BM25 at file-precision 0.375 lowered resolve rate by 0.6pp and inflated resolved tokens by 21% relative to baseline on SWE-bench Verified. CodeGrep's stated mechanism is that "file localization is often not the binding bottleneck on resolve rate, since the downstream agent recovers much task-relevant context through its own grep/view tools," and that on failures the failure is typically in *patch synthesis*, not file location, so sharper retrieval compresses rollouts rather than enlarging the resolvable set. It also notes the marginal harm of a false positive is comparable to the marginal benefit of a true positive — [CodeGrep, arXiv 2608.05886](https://arxiv.org/pdf/2608.05886)
- **Logged agent trajectories show real recovery but also real misses:** Agent Retrieval Bench found 27-35% of samples never touched gold files despite interactive exploration. OpenAI agents averaged 3.2 file reads; Codex averaged 6.2-6.5 — [Agent Retrieval Bench, arXiv 2607.24882](https://arxiv.org/html/2607.24882v1)
- **A trained search subagent is a third architecture:** Morph's WarpGrep is an RL-trained search subagent reported at ~2,500 tok/s, sub-4-second searches, claimed #1 on SWE-Bench Pro paired with frontier models, and 15.6% cheaper / 28% faster per task for v2 — [Morph, Agentic Search](https://www.morphllm.com/agentic-search) (**vendor marketing claims; no independent replication found**)
- **GrepSeek** (RL-trained corpus-interaction search) reports higher end-to-end latency than dense baselines (8.67s vs. E5 4.77s, Qwen3-4B 6.07s) but with retrieval execution costing only 0.81s of that, the rest being LLM decoding (7.86s). Its resource story is the interesting part: 14 GB host memory (raw corpus size) vs. 70 GB for E5 and 221 GB for Qwen3-4B, with setup of ~1 minute vs. 3.2 and 62.4 A100-hours — [GrepSeek, arXiv 2605.29307](https://arxiv.org/pdf/2605.29307)

### Inferences

- The apparent contradiction between "agentic search beats RAG" and "Cursor measured +12.5% from semantic search" resolves cleanly: semantic retrieval **adds** accuracy as a *seed* on top of agentic search, and the gain is real but small enough that index-freshness and operational-simplicity costs can dominate it for a product. Cursor's decision is a cost/complexity verdict, not an accuracy verdict.
- The client's engine sits on the losing side of one framing and the winning side of another. As a **replacement** for agent tool use it is weakly supported. As a **first-turn seed** that shortens the agent's search, the evidence is favorable (see Q7's seed-intervention numbers). The client's 93.0 -> 93.8 measurement is entirely consistent with the field: this is exactly the size of effect the literature reports for seeding a capable agent that can already recover context itself.
- CodeGrep's "patch synthesis, not localization, is the failure mode" claim is the single most important reframing for the client. If true for his workload, further retrieval-quality investment has a low ceiling regardless of technique.

### Gaps

- I found no controlled head-to-head of "hybrid BM25+vector+RRF injection" vs. "pure agentic search" vs. "both" on SWE-bench Verified with the same model and scaffold. SWE-Explore and Agent Retrieval Bench each get close but measure retrieval quality, not resolve rate, for the hybrid arm.
- I could not locate Cursor's own primary engineering post containing the 12.5% figure; only secondary write-ups. The figure should be attributed cautiously.
- No public data on where the crossover point sits by repository size (SWE-bench repos are moderate; large monorepos are repeatedly asserted to favor indexes, with no measurement found).

---

## Key Question 2: Graph and structural context - measured benefit

### Takeaway

Graph/structural context is the best-evidenced *complement* to flat retrieval in these notes, and Aider's repo-map design specifically is now independently validated as a strong retrieval signal: it beat every dense embedding model on structural "trace to root cause" retrieval and produced the single best budgeted-context-yield score in Agent Retrieval Bench. But absolute gains from bolting a graph onto an agent framework are small in absolute terms (+2.0 to +2.7 percentage points resolve rate in RepoGraph's ablations), and the strongest graph results are in *localization*, which Q1 suggests is often not the bottleneck.

### Cited Findings

**Aider's repo-map (the directly comparable design)**

- Aider builds the map with tree-sitter symbol extraction, forms a file-level dependency graph, and applies **personalized** PageRank seeded from chat files and mentioned identifiers, rendering top-ranked definitions as scope-aware elided code within a token budget defaulting to 1,024 tokens. It is fully deterministic, makes zero LLM calls, and caches tags by mtime — [Aider, Building a better repository map with tree sitter](https://aider.chat/2023/10/22/repomap.html) (**vendor/tool docs, but unusually transparent about mechanism**)
- Implementation details: falls back to Pygments lexer `Token.Name` extraction when tree-sitter queries yield definitions but no references (e.g. C++); uses grep_ast `TreeContext` for elision; 26+ languages via per-language `.scm` tag queries — [Aider repomap analysis, surfaced via search](https://aider.chat/2023/10/22/repomap.html)
- Aider's release history ties repo-map to `--map-tokens` budgeting (v0.5.0) and benchmarks the tree-sitter repo map alongside search/replace blocks at 66.2% with no regression (v0.16.0) — [Aider release history](https://aider.chat/HISTORY.html)
- **Important negative:** a claim circulating that "Aider's benchmarks show PageRank-scored context achieves significantly higher edit accuracy than naive file inclusion" is a secondary paraphrase, **not** a published head-to-head ablation from the Aider team. I found no isolated repo-map on/off ablation from Aider — [noted during search; no primary source exists](https://aider.chat/HISTORY.html)
- **Independent validation of the repo-map design:** in Agent Retrieval Bench, "RepoMap" produced the best BCY@8k (Budgeted Context Yield at 8k tokens) of all methods at **0.3788**, beating Qwen3-8B (0.3732), Qwen3-4B (0.3409), pplx-4B (0.3549), Lexical (0.2650) and BM25 (0.2051). RepoMap dominated the trace2code (causal-indirect / root-cause) task at MRR 0.2742 — [Agent Retrieval Bench, arXiv 2607.24882](https://arxiv.org/html/2607.24882v1)

**Complementarity, measured**

- Agent Retrieval Bench setup: 427 samples across 25 repositories (345 positive: code2test 106, comment2context 80, trace2code 101, edit2ripple 58; plus 82 no-gold samples), corpus of 308 base-commit snapshots, 391,932 files, 7.9M chunks — [Agent Retrieval Bench](https://arxiv.org/html/2607.24882v1)
- **RRF hybrid of embedding + repo-map beat either alone:** Qwen3-8B + RepoMap fused with Reciprocal Rank Fusion improved MRR from 0.2336 to **0.2713** and Recall@20 from 0.7070 to **0.7331** on the 287-sample core — [Agent Retrieval Bench](https://arxiv.org/html/2607.24882v1)
- Different tasks have different winners: Qwen3-4B leads code2test (MRR 0.3225), Jina-0.5B leads comment2context (0.3043), RepoMap leads trace2code (0.2742), pplx-4B leads edit2ripple (0.2877). The paper's conclusion: "different agentic retrieval signals require different inductive biases" and "semantic and structural methods are complementary." Embeddings dominate semantic-direct cases (MRR 0.3939 with RRF-3) while RepoMap dominates causal-indirect — [Agent Retrieval Bench](https://arxiv.org/html/2607.24882v1)

**RepoGraph (ICLR 2025) - the cleanest graph ablation**

- RepoGraph is a plug-in repository-level code graph tested against four frameworks on SWE-bench-Lite, with an average **relative** improvement of 32.8% — a number that is misleading in isolation because the absolute deltas are small — [RepoGraph, arXiv 2410.14684](https://arxiv.org/html/2410.14684v1) / [ICLR 2025 proceedings](https://proceedings.iclr.cc/paper_files/paper/2025/file/4a4a3c197deac042461c677219efd36c-Paper-Conference.pdf)
- Absolute resolve-rate deltas on SWE-bench-Lite: RAG 2.67% -> 5.33% (+2.66pp, +99.63% relative; patch application 29.33% -> 47.67%); Agentless 27.33% -> 29.67% (+2.34pp, +8.56% relative); AutoCodeRover 19.00% -> 21.33% (+2.33pp); SWE-agent 18.33% -> 20.33% (+2.00pp). Best config (Agentless + RepoGraph, 29.67) was open-source SOTA at publication — [RepoGraph](https://arxiv.org/html/2410.14684v1)
- Gains were *larger on procedural frameworks than agent ones*; the authors attribute this to procedural frameworks' well-defined execution flow letting them leverage plug-ins more effectively, and to reduced complexity from dynamic decision-making — [RepoGraph](https://arxiv.org/html/2410.14684v1)
- Efficiency: SWE-agent's average turns fell 21.47 -> 19.12, though graph calls increased prompt cost. Authors argue the gains are not mainly due to increased token usage — [RepoGraph](https://arxiv.org/html/2410.14684v1)

**LocAgent - graph traversal for localization**

- LocAgent parses codebases into directed heterogeneous graphs and exposes TraverseGraph / RetrieveEntity / SearchEntity tools. On SWE-bench-Lite it reports up to **94.16% file-level Acc@5** and **77.37% function-level Acc@10** — [LocAgent, ACL 2025](https://aclanthology.org/2025.acl-long.426.pdf) / [arXiv 2503.09089](https://arxiv.org/html/2503.09089v1)
- Graph traversal specifically is worth a few points: ablation shows full system 88.32 / 82.85 / 71.53 vs. 86.13 / 78.47 / 66.06 without TraverseGraph, and 86.50 / 79.56 / 66.42 using only "contain" relations (metrics: file Acc@5, module Acc@10, function Acc@10). So the *relational* edges beyond containment are worth ~5pp at function level — [LocAgent](https://arxiv.org/html/2503.09089v1)
- Cost: a fine-tuned Qwen-2.5-Coder-Instruct reached comparable results to SOTA proprietary models at ~86% reduced cost, ~$0.09/example, up to 92.7% file-level accuracy, and improved downstream issue-resolution success by **12% for multiple attempts**. Baselines: SWE-agent+GPT-4o 8 rounds at $0.56; SWE-agent+Claude-3.5 9 rounds at $0.67 — [LocAgent](https://arxiv.org/html/2503.09089v1)
- Evaluation caveat: instances where no existing functions were modified were excluded (274 of 300 retained), and instances touching >5 Python files or >10 functions were excluded — so the headline accuracy is on a filtered, easier subset — [LocAgent](https://arxiv.org/html/2503.09089v1)
- Later work reports competing/higher numbers: SWE-Debate claims 81.67% file-level localization vs. LocAgent's 77.74% — [SWE-Debate, arXiv 2507.23348](https://arxiv.org/pdf/2507.23348). One independent evaluation noted LocAgent with Claude-4.6-Sonnet exhausted a fixed $300 budget after only 182 of 300 SWE-bench-Lite instances (valid results for 158), i.e. graph-traversal agents can be expensive in practice.

**CodexGraph and other graph designs**

- CodexGraph (NAACL 2025) exposes code graphs to LLM agents through a Neo4j graph database queried with agent-issued Cypher, operating at file- and repo-level granularity, in contrast to RepoGraph's line-level reference graph — [comparison surfaced in ARISE, arXiv 2605.03117](https://arxiv.org/html/2605.03117)
- ARISE reports ARISE-Full outperforming SWE-agent+RepoGraph (19.3%), Agentless (13.3%) and KGCompass (15.3%) on the same Qwen2.5-Coder-32B-Instruct backbone, and surpassing the published GPT-4o-based SWE-agent+RepoGraph result (20.3%) — [ARISE, arXiv 2605.03117](https://arxiv.org/html/2605.03117)
- **A structural index inside an agent, measured on cost:** "Code Isn't Memory: A Structural Codebase Index Inside a Coding Agent" reports $/solved of **$2.30 with the index on vs. $2.92** for the OpenCode baseline (~21% lower), mean tokens **10.1k vs. 14.0k**, mean turns **28.3 vs. 36.0** (both p < 0.0001), wall-clock **4.5 vs. 5.4 minutes**, and — importantly — per-cell mean cost statistically null (paired Wilcoxon p = 0.35), with the authors' substantive claim being that the index is *not more expensive to run* than agentic grep — [figures surfaced via search of arXiv 2606.22417](https://arxiv.org/pdf/2606.22417) (**see the extraction caveat at the top of this document: I could not directly verify an accuracy/resolve delta for this paper and am deliberately not reporting one**)
- Other graph designs found but not independently measured against flat retrieval in my sources: KGCompass (issue-to-PR entity linking for path-guided retrieval; reported at 58.3% on SWE-bench Lite in one later citation), Codebase-Memory (tree-sitter knowledge graphs, [arXiv 2603.27277](https://arxiv.org/html/2603.27277v1)), RepoAtlas (evolving multimodal repository views, [arXiv 2609.16936](https://arxiv.org/pdf/2609.16936)) — cited for the report writer's awareness, not as measured evidence.

### Inferences

- The client already has both arms of the one combination the literature measures as best: a dense/hybrid retriever and an AST-derived graph. **Fusing them with RRF is the highest-confidence improvement available to him**, and he already owns an RRF implementation. Agent Retrieval Bench's +0.038 MRR / +0.026 Recall@20 from exactly this fusion is the closest thing to a direct prescription in these notes.
- The task-decomposition finding matters more than the aggregate: graph signal wins on *causal-indirect / trace-to-root-cause* queries; embeddings win on *semantic-direct* queries. A router that picks by query type is better supported by evidence than a single blended ranker.
- "Relative improvement" framing in graph papers is systematically flattering (RepoGraph's 32.8% average relative = +2.0 to +2.7pp absolute). The report should quote absolutes.
- Graph benefit appears to concentrate where the agent's own grep is weakest: multi-hop reference chains and ripple effects. That is a narrow but genuine niche, not a general context upgrade.

### Gaps

- No paper I found isolates "graph added tokens without gain" as a measured negative result. RepoGraph notes graph calls increase prompt cost but argues gains are not token-driven; the failure case is asserted by practitioners (graph output is verbose) rather than measured.
- No ablation of Aider's repo-map alone, by Aider, on Aider's own benchmark. This is a real hole given how widely the design is copied.
- I did not find GraphRAG-specific code-domain numbers. GraphRAG appeared in searches only as a category label; the code-domain graph work that is actually measured is RepoGraph / LocAgent / CodexGraph / ARISE. **Report writer should not attribute code-retrieval numbers to Microsoft GraphRAG - I found none.**

---

## Key Question 3: Chunking - AST vs. fixed windows, and contextual retrieval

### Takeaway

This is where the evidence most directly contradicts the client's design. cAST's own paper reports modest gains, and a much larger independent controlled study (864 settings) found **sliding-window chunking slightly beat cAST on both RepoEval and CrossCodeEval** and concluded structure-aware chunking does not outperform sliding window on quality or cost. Anthropic's contextual-retrieval numbers, by contrast, are solid, large, and consistent across every embedding/source combination tested — and the client already implements that technique.

### Cited Findings

**cAST (the pro-AST evidence)**

- cAST (Zhang, Zhao, Wang, Yang, Wei, Wu; CMU; EMNLP) uses tree-sitter parsing with a recursive split-then-merge algorithm, greedily merging AST nodes into chunks and recursively splitting nodes that overflow, and measures chunk size in **non-whitespace characters** rather than lines — [cAST, arXiv 2506.15655](https://arxiv.org/abs/2506.15655) / [HTML](https://arxiv.org/html/2506.15655v1)
- Reported gains: RepoEval average **Recall@5 +4.3 points**; CrossCodeEval **up to +4.3 points**; SWE-bench Precision **+0.5 to +1.4**, Recall **+0.7 to +1.1**, and **~+2.67 points Pass@1**; up to +2.7 points on hybrid code+NL tasks — [cAST](https://arxiv.org/html/2506.15655v1)
- The authors' own forward-looking suggestion is to add higher-level AST-parent and file-level context in a multi-level approach, i.e. they view plain AST chunking as incomplete — [cAST](https://arxiv.org/html/2506.15655v1)

**The contradicting study (larger, more controlled)**

- "How Does Chunking Affect Retrieval-Augmented Code Completion?" crossed **4 chunking strategies x 4 retrievers x 5 generators x 9 parameter configurations x 2 benchmarks = 864 experimental settings** — [arXiv 2605.04763](https://arxiv.org/html/2605.04763)
- RepoEval, API-level EM / line-level EM: **Sliding Window 46.23% / 56.91%**; cAST 45.93% / 56.54%; Declaration 45.85% / 54.84%; Function 42.27% / 51.27% — [arXiv 2605.04763](https://arxiv.org/html/2605.04763)
- CrossCodeEval EM: **Sliding Window 28.40%**; cAST 28.19%; Declaration 27.71%; Function 24.21% — [arXiv 2605.04763](https://arxiv.org/html/2605.04763)
- Stated conclusion: "structure-aware methods do not outperform Sliding Window on quality or cost efficiency," with cAST and Sliding Window differing by only 0.38pp (API-level) and 2.07pp (line-level), and the apparently significant 3.43-6.51pp strategy gap being driven almost entirely by **Function**-granularity chunking's weakness rather than by structure-awareness helping — [arXiv 2605.04763](https://arxiv.org/html/2605.04763)
- Retriever choice accounted for <=1.11pp EM variation on RepoEval, far less than the chunking-strategy spread — i.e. in that study *neither* chunking nor retriever choice was a large lever — [arXiv 2605.04763](https://arxiv.org/html/2605.04763)
- Chunk *size* is non-monotonic: EM peaks at chunk size 2,000 and declines at 3,000; at chunk size 1,000, 5-15 line overlap gives up to +0.5pp at API level but 25-line overlap degrades EM by 1.2pp. Caveat: that study fixed top-k at 10 following RepoCoder and did not ablate it, so chunk-size findings may be entangled with the fixed budget — [arXiv 2605.04763](https://arxiv.org/html/2605.04763)

**Contextual retrieval (the well-supported technique)**

- Anthropic's Contextual Retrieval combines Contextual Embeddings and Contextual BM25. Metric is 1 - recall@20 (percentage of relevant documents failing to appear in top-20 chunks). Baseline failure 5.7% -> Contextual Embeddings 3.7% (**-35%**) -> + Contextual BM25 2.9% (**-49%**) -> + reranking 1.9% (**-67%**) — [Anthropic, Contextual Retrieval in AI Systems](https://www.anthropic.com/engineering/contextual-retrieval) (**vendor engineering blog with a results appendix; not peer-reviewed, but methodology is disclosed**)
- Domains covered included codebases, fiction, ArXiv papers and science papers, across multiple embedding models and retrieval strategies; headline figures use Gemini Text 004 as the top-performing embedding configuration at top-20 retrieval. **Contextualizing improved performance in every embedding-source combination evaluated** — [Anthropic](https://www.anthropic.com/engineering/contextual-retrieval)
- Cost of contextualization: one-time preprocessing, estimated at **$1.02 per million document tokens** with prompt caching — [Anthropic](https://www.anthropic.com/engineering/contextual-retrieval)
- **Correction to circulating numbers:** Precision@20 figures of 0.65 -> 0.89 attributed to Anthropic in third-party write-ups do **not** appear in Anthropic's own post and should be treated as blog-author estimates — [noted in search of third-party write-ups against the primary post](https://www.anthropic.com/engineering/contextual-retrieval)

### Inferences

- The client's reported +0.224 MRR from AST chunking (0.599 -> 0.823 in his own ARCHITECTURE.md benchmark) is far larger than anything in the literature - cAST's own paper claims +4.3 Recall@5 points, and the larger independent study found essentially zero. A gain that much bigger than published results on a 96-file / 20-query harness is most plausibly explained by small-sample variance or by the AST change being confounded with something else in that comparison, not by AST chunking being unusually good on his repo. **This is worth saying plainly to the client.**
- The two chunking studies are not irreconcilable: cAST's gains are largest on *retrieval* metrics and on cross-language generalization; 2605.04763 measures *completion EM*. Downstream EM being insensitive to chunking while retrieval metrics move is itself the recurring theme of these notes (see Q7).
- Contextual retrieval (which the client already does via context headers) is the best-supported chunking-adjacent technique in the field and is where AST information pays off indirectly - the AST is what lets you name the scope in the header.

### Gaps

- No study I found isolates *context headers alone* on code retrieval with resolve-rate as the endpoint. Anthropic's numbers are recall-based and span mixed domains.
- Anthropic's post does not break out the code-only subset, so the 35%/49%/67% figures cannot be claimed as code-specific.

---

## Key Question 4: Context window economics - is top-5 defensible?

### Takeaway

Top-5 is well supported and arguably the single best-justified choice in the client's design. Multiple independent lines of evidence put saturation at k=3-5 with nothing gained by k=10, precision falling sharply as k grows, and hard distractors doing nonlinear damage. The one important counter-pressure is SWE-Explore's finding that *missing* core evidence hurts far more than redundancy, and The Recall Trap's finding that trading breadth for depth within files beat higher recall.

### Cited Findings

**Saturation at k=3-5**

- Experiments with codegen25-7b and GraphCoder showed significant performance saturation for both retrieval methods at top_k 3-4, with no observable fluctuation up to top_k=10 — [surfaced via search; Hierarchical Context Pruning line of work, arXiv 2406.18294](https://arxiv.org/pdf/2406.18294)
- A hierarchical context pruning study testing top-k at fixed top-p=1.0 observed no significant accuracy improvement beyond k=5 and concluded **top-k=5 is sufficient** — [arXiv 2406.18294](https://arxiv.org/pdf/2406.18294)
- Measured precision/recall crossover: Precision@k declines 0.23 (k=3) -> 0.10 (k=10) while Recall@k rises 0.33 -> 0.45; highest F1@k is 0.26 at **k=3** — [surfaced via search, "Beyond More Context: How Granularity and Order Drive Code Completion Quality", arXiv 2510.06606](https://arxiv.org/pdf/2510.06606)
- The same line of work reports higher *precision* converts into better generation while recall-oriented metrics and nDCG correlate only weakly with downstream quality — once necessary evidence is in the set, adding lower-ranked chunks gives diminishing or negative returns — [arXiv 2510.06606](https://arxiv.org/pdf/2510.06606)
- Shapley-based context filtering found K=7 too small (52.16% EM), diminishing returns past K=10, and K=13 improving ES by only 0.51% while pushing latency past 3.5 seconds; K=10 adopted as the balance — [RepoShapley, arXiv 2601.03378](https://arxiv.org/pdf/2601.03378)
- A code-completion contest entry used top-5 BM25 chunks with local-scope trimming for 0.64 average chrF and third place — [surfaced via search, arXiv 2605.04763 context](https://arxiv.org/html/2605.04763)

**The Recall Trap - the sharpest result against recall-maximization**

- "The Recall Trap: A Recall-Maximizing Retriever Configuration Reduces Issue Resolution in Fixed-Budget Code Context" (August 2026). Setup: **fixed 12-slot context pack with no search tools**, primary benchmark SWE-bench Verified, secondary SWE-PolyBench (4 languages, N=617) — [arXiv 2608.14838](https://arxiv.org/abs/2608.14838)
- Results: disabling hard file-level deduplication (trading breadth for depth within files) gave **gpt-5.6-sol +7.6pp resolve rate (39.2% -> 46.8%, n=500, McNemar exact p=0.0003)**, open-weights replication **+3.6pp (n=499, p=0.0133)**, SWE-PolyBench **+2.6pp (p=0.056)** — while gold-file-presence recall *fell* from 0.878 to 0.806 — [arXiv 2608.14838](https://arxiv.org/abs/2608.14838)
- The authors' recommendation: tune retrieval packing strategies against **actual task performance**, not retrieval metrics — [arXiv 2608.14838](https://arxiv.org/abs/2608.14838)

**Long-context degradation**

- Original lost-in-the-middle: accuracy is poorest when critical information is mid-context and improves near beginning or end. Crucially, swapping retrieved hard-negative distractors for random Wikipedia documents raised absolute scores but models still struggled to reason over the full input, so degradation is *not solely* a relevance-identification failure. The U-shape persisted even with randomized distractor order and a prompt disclosing the randomization — [Liu et al., Lost in the Middle, arXiv 2307.03172](https://arxiv.org/pdf/2307.03172)
- **Length alone hurts:** across 5 open and closed LLMs on math, QA and coding, performance degraded **13.9%-85%** as input length increased *even when models could perfectly retrieve all relevant information* and stayed well within claimed context limits — [Context Length Alone Hurts LLM Performance, Findings of EMNLP 2025](https://aclanthology.org/2025.findings-emnlp.1264.pdf)
- **Distractor damage is nonlinear:** with 100 distractor documents, attention on the gold document drops **76% after adding only 10% hard distractors**; hard distractors receive attention logits similar to gold documents and dominate the softmax even at low proportions. Because collapse persists while any small fraction of hard distractors remains, post-hoc filtering recovers only marginally, so **prevention beats filtering** — [The First Drop of Ink, arXiv 2605.10828](https://arxiv.org/pdf/2605.10828)
- **Code-specific, and the most important long-context finding for this client:** "Sense and Sensitivity" found lexical recall is position-independent (frontier models >95% accuracy on function retrieval regardless of position) but **semantic** recall degrades with position, relative accuracy dropping 16.25%-84.29%, worst at the 60-80% position, appearing with as few as **20 distractor contexts (~4k tokens)** and worsening with scale. On their harder SemTrace benchmark, Qwen 2.5 Coder 32B went from 23.31% relative degradation (CRUXEval-0, 80 distractors / ~16k tokens) to **91.38% relative accuracy loss**; Codestral 22B and Gemma 3 27B reached zero accuracy — [Sense and Sensitivity, arXiv 2505.13353](https://arxiv.org/pdf/2505.13353)
- LongCodeBench reported degradation from **29% to 3% for Claude 3.5 Sonnet** as context scales toward million-token level — [surfaced via search; see LoCoBench comparison, arXiv 2509.09614](https://arxiv.org/pdf/2509.09614)
- **Caveat against naive truncation:** one paper argues the inference "truncate the middle" is a non-sequitur - the middle being hard to use does not mean it is unused, and in benchmarks where the answer-bearing fact sits mid-context, removal destroys it. The defensible mitigation is transforming a long-context task into a short-context one — [Distractor-Aware Truncation, arXiv 2608.03297](https://arxiv.org/pdf/2608.03297)
- Why coding agents are the worst case for this: accumulative context (every file read, grep result and tool output persists), high distractor density (code search returns many semantically similar results: test fixtures, deprecated implementations, mocks, similarly-named functions), and long task horizons of 15-60 minutes. Counterintuitively, **good naming conventions and consistent architecture increase distractor density** — [Morph, Context Rot](https://www.morphllm.com/context-rot) (**vendor blog synthesizing the papers above; the compounding argument is theirs, not measured**)

### Inferences

- Top-5 is defensible on the evidence and should not be increased. If the client changes anything about k, the better-supported direction is **fewer, larger, in-file-contiguous chunks** (The Recall Trap) rather than more chunks.
- There is a genuine tension the report should surface rather than paper over: SWE-Explore says redundancy is cheap and missing evidence is expensive (favoring higher k); the distractor and Recall Trap literature says extra chunks are expensive (favoring lower k). The reconciliation is probably that **redundancy is cheap when the agent can still explore, and expensive when the context pack is all the agent gets** - note that The Recall Trap ran with *no search tools*. The client injects into an agent that *does* have tools, which puts him closer to the SWE-Explore regime.
- "Sense and Sensitivity" is the strongest argument for the client's whole approach: models can *find* buried code but lose the ability to *reason about* it. Front-loading a small, high-precision pack is exactly the intervention that addresses this.

### Gaps

- I found no study measuring optimal k for *injected seed context to a tool-using agent* specifically. All the k=3-5 evidence is from retrieval-augmented *completion*, a different regime.
- No measurement of where in the prompt injected chunks should sit for a coding agent (beginning vs. immediately-before-query), only general positioning advice from a non-primary source.

---

## Key Question 5: Documentation's actual value to agents

### Takeaway

The evidence here is genuinely conflicting and the client should hear that plainly, but the conflict resolves around one variable: **documentation helps as a substitute for code the agent cannot see, and does not help as a supplement to code the agent can see.** The largest study found context files do not generally improve task success while adding 20%+ inference cost, with LLM-generated files *net negative* and human-written ones worth only ~+2.4% (p=0.21). Separately, the evidence that *wrong* documentation actively harms agents is strong and asymmetric: incorrect comments substantially degrade performance while missing comments barely matter.

### Cited Findings

**The negative results**

- "Evaluating AGENTS.md: Are Repository-Level Context Files Helpful for Coding Agents?" evaluated SWE-bench tasks with LLM-generated context files plus a new collection of issues from repositories with developer-committed context files. Finding: context files **do not generally improve task success rates while increasing inference cost by over 20% on average**, holding across LLMs, agents, and both file types. Instructions were well followed; **repository overviews - popular and recommended by model providers - were not helpful** — [arXiv 2602.11988](https://arxiv.org/html/2602.11988v2) / [alphaXiv](https://www.alphaxiv.org/abs/2602.11988)
- Breakdown: LLM-generated files caused drops in **5 of 8 settings**, reducing average resolution rate by **0.5% on SWE-bench and 2% on CTXbench**; developer-provided files improved performance by **+2.4% on average (p=0.21)**, significantly better than LLM-generated (p=0.038), and helped all agents **except Claude Code** — [arXiv 2602.11988](https://arxiv.org/html/2602.11988v2)
- **The "exploration paradox":** agents *do* follow context-file instructions faithfully - when a file names `uv` as package manager, uv usage jumps to ~1.6 times per instance vs. <0.01 without; when it specifies a test framework, agents switch. But agents with context files run more tests, search more files, traverse more of the repo and generate more reasoning output. Thorough exploration is not correct exploration — [summarized at DAIR.AI Academy](https://academy.dair.ai/blog/agents-md-evaluation), primary [arXiv 2602.11988](https://arxiv.org/html/2602.11988v2)
- **The decisive ablation:** when researchers removed all documentation from repositories (.md files, docs/ folder, example code), LLM-generated context files **became helpful, improving performance by 2.7% on average** - suggesting `/init`-style files mostly pre-cache information the agent would have discovered itself — [DAIR.AI summary](https://academy.dair.ai/blog/agents-md-evaluation) of [arXiv 2602.11988](https://arxiv.org/html/2602.11988v2)
- "Compact Documentation for Coding Agents" independently replicates the null across two model families and ten repositories, against a positive control confirming its harness could detect genuine improvement: **when the source is present, neither static compact documentation nor retrieved context beats the issue alone.** When the source file is *withheld*, an optimized description lifts mean test-pass fraction from **0.08 to 0.71** — documentation acts as a code substitute, not a supplement — [arXiv 2609.31587](https://arxiv.org/html/2609.31587v1)

**The positive results**

- A repository-documentation evaluation using 57 SWE-bench Verified instances with SWE-Agent and retrieved documentation (top 4096 tokens, selected by issue description) reports baseline **43.86%** with **relative improvements of 8-20%** when documentation was provided, and issue-file-location rates improving 6.01-11.19%. Documentation *quality* mattered: RepoAgent-generated docs highest at **52.63%**, DocAgent and AutoDoc **49.12%**, DeepWiki **47.37%** — [arXiv 2604.06793](https://arxiv.org/pdf/2604.06793) (**n=57 is small; treat the spread cautiously**)
- "Probe-and-Refine Tuning of Repository Guidance" argues the *production method* is what matters: synthetic bug-fix probes iteratively diagnose and patch a repository's guidance file via single-shot LLM calls, achieving **33.0% mean resolve rate on SWE-bench Verified across four trials vs. 25.5% no_context and 28.3% static knowledge base at 200 steps**. Mechanism is localization, not correctness: refined guidance produced evaluable patches for **+14.5pp more instances** while per-patch precision stayed statistically constant (~59%, p=0.119). **Budget dependence is the key caveat: at 25 steps all conditions are equivalent; effects only separate as budget grows, with the unguided baseline flat at ~25% and probe-and-refine the only condition still improving past 100 steps** — [arXiv 2606.20512](https://arxiv.org/html/2606.20512v1)
- A contrasting *efficiency* result: "On the Impact of AGENTS.md Files on the Efficiency of AI Coding Agents" studied 10 repositories and 124 pull requests with and without AGENTS.md, finding **lower median runtime (-28.64%)** and **reduced output token consumption (-16.58%)** with comparable task completion behavior — the direct opposite of the ETH study's +20% cost — [arXiv 2601.20404](https://arxiv.org/abs/2601.20404). The tension likely reflects PR-based real repos vs. benchmark suites, and real developer-written vs. LLM-generated files.

**Harm from wrong documentation and comments**

- **CodeCrash** injects misleading natural language into code and finds LLMs treat comments as authoritative even when they conflict with code logic. In one case study GPT-4o correctly traced execution to the right output, then adopted the false comment and believed the update operation had no effect, **contradicting its own reasoning** - and never mentioned the comments in its reasoning trace, so the influence is implicit. The authors conclude LLMs do not separate comments from executable logic but treat them as part of ground truth — [CodeCrash, arXiv 2504.14119](https://arxiv.org/pdf/2504.14119)
- **The asymmetry that matters most for stale docs:** "Inside Out: Uncovering How Comment Internalization Steers LLMs for Better or Worse" (ICSE) summarizes Macke and Doyle (2024), who used unit-test generation to probe code understanding and found **incorrect comments can substantially degrade model performance while missing or incomplete comments had relatively minor impact** — [arXiv 2512.16790](https://arxiv.org/html/2512.16790v1)
- The weakness has been weaponized: "Code Poisoning Through Misleading Comments: Jailbreaking Large Language Models via Contextual Deception" (ICCIT 2025) — [cited in CodeCrash follow-up work](https://arxiv.org/pdf/2504.14119)
- Related: a taxonomy of inaccuracy patterns in LLM-generated comments including intent-misdescription, "Hallucinating Reference" and "Lacking Code Context" — [arXiv 2406.14836](https://arxiv.org/pdf/2406.14836)

**Instruction-file bloat**

- A grey-literature review of 14 articles catalogued six "configuration smells," with **context bloat the most frequently cited (10 of 14)**: files become excessively large and overloaded with rules, examples or low-priority details, increasing token consumption, raising costs and reducing visibility of important instructions. Also named: **skill leakage** (rarely used instructions living in AGENTS.md rather than on-demand skill files, so specialized knowledge leaks into every session) and **init fossilization** (a `/init`-generated file never reviewed, becoming permanent configuration carrying irrelevant instructions) — [Configuration Smells in AGENTS.md Files, arXiv 2606.15828](https://arxiv.org/html/2606.15828v2)
- Instruction-count limits: frontier thinking LLMs follow roughly **150-200 instructions** with reasonable consistency; smaller models attend to fewer, non-thinking fewer than thinking, and smaller models show *exponential* decay in instruction-following as instruction count rises while larger frontier thinking models decay linearly. Derived practical guidance: keep files under ~200 lines — [Upsun, the research is in: your AGENTS.md is probably too long](https://developer.upsun.com/posts/ai/agents-md-less-is-more) (**practitioner synthesis of research; the 150-200 figure is from the instruction-following literature it cites, not measured by Upsun**)
- An empirical study of Claude Code manifests explicitly names directly assessing CLAUDE.md impact on agent performance as a **critical open future direction**, recommending controlled experiments with identical coding challenges and varying manifest quality — i.e. the field considers this under-measured — [On the Use of Agentic Coding Manifests, arXiv 2509.14744](https://arxiv.org/pdf/2509.14744)

### Inferences

- **This is the finding most relevant to a "doc-code consistency" product, and it cuts both ways.** The substitute-not-supplement result plus the removed-documentation ablation means documentation's marginal value to an agent is highest exactly where code is hard to read or unavailable, and near zero where the agent can just read the code. That is a narrower value proposition than "honest documentation makes agents efficient."
- But the *consistency* half of the client's thesis is where the strongest support lies. Incorrect comments substantially degrade performance while missing ones barely matter, and models adopt false comments over their own correct reasoning without even citing them. That is a direct, measured argument for detecting doc-code drift: **the asymmetry means the expected value of removing a wrong doc exceeds the expected value of adding a right one.**
- Probe-and-refine's budget dependence explains much of the conflict: documentation effects appear only at high step budgets. Short-budget benchmarks will systematically report nulls.
- The client's own AGENTS.md/CLAUDE.md files (which are very long, heavily duplicated, and include content repeated three or four times in the same load) are a textbook instance of the context-bloat smell. Worth saying.

### Gaps

- No study measured whether *automated doc-code consistency checking* improves agent outcomes. The harm of stale docs is measured; the benefit of fixing them via tooling is not. This is an open, publishable question and also a risk to the client's thesis.
- The AGENTS.md efficiency study (-28.6% runtime) and the ETH cost study (+20% cost) are in direct conflict and I found no work reconciling them.
- No measurement of ARCHITECTURE.md-style human-written architecture documents specifically, as distinct from AGENTS.md instruction files or auto-generated API docs.

---

## Key Question 6: Latency and cost of context assembly

### Takeaway

Per-query retrieval latency favors indexes by two to three orders of magnitude, but retrieval latency is a rounding error in agent wall-clock, so the break-even must be computed in **$/solved and tokens/solve**, not milliseconds. The one controlled comparison found a structural index roughly 21% cheaper per solve than agentic grep with statistically null per-call cost. Index-construction cost is the term most often omitted and can be enormous for embedding pipelines.

### Cited Findings

- Per-query latency: lexical grep/ripgrep <50ms, no index; semantic search <100ms, requires index; agentic multi-turn search 2-8 seconds — [Morph, Agentic Search](https://www.morphllm.com/agentic-search) (**vendor**)
- Finer practitioner breakdown: ripgrep 1-5ms / very low tokens per result; ast-grep 10-50ms; repo-map 50-200ms / medium tokens per result; embeddings 100ms-1s / high tokens per result / low precision — [Code Search for AI Agents: ripgrep, ast-grep, or Semantic?](https://ceaksan.com/en/code-search-for-ai-agents-which-tool-when) (**practitioner blog**)
- Code-embedding index retrieval on a 156k-document corpus: ~38µs (768-dim) to 115.5µs (E5-Mistral) GPU retrieval, index sizes 0.3G-2.3G, but **E5-Mistral averages 1840ms per sample to embed** — the embedding step, not the search, is the cost — [CoIR, arXiv 2407.02883](https://arxiv.org/pdf/2407.02883)
- **The controlled end-to-end comparison:** structural index on vs. OpenCode agentic-grep baseline — **$2.30 vs. $2.92 $/solved (~21% lower)**, mean tokens **10.1k vs. 14.0k**, mean turns **28.3 vs. 36.0** (both p<0.0001), wall-clock **4.5 vs. 5.4 min**, per-cell mean cost statistically null (paired Wilcoxon p=0.35). Authors' framing: the index is *not more expensive to run* than agentic grep — [arXiv 2606.22417](https://arxiv.org/pdf/2606.22417) (**figures via search summary; direct PDF extraction was unreliable, see caveat at top**)
- **Index-construction cost, the omitted term:** GrepSeek needs 14 GB host memory (raw corpus size) vs. 70 GB (E5) and 221 GB (Qwen3-4B), with **~1 minute setup vs. 3.2 and 62.4 A100-hours** — [GrepSeek, arXiv 2605.29307](https://arxiv.org/pdf/2605.29307)
- An inverted-index-only backend avoided corpus-wide embedding plus FAISS indexing that incurred **~41x higher offline construction time: 1.27h vs. 52.02h** on a KILT-scale corpus; graph-based retrieval in the same comparison required roughly **37B input and 18B output tokens of LLM preprocessing** — [Semi-Parametric Retrieval via Binary Bag-of-Tokens Index, arXiv 2405.01924](https://arxiv.org/pdf/2405.01924)
- Tokenization-based indexes complete in under 1 hour on CPU vs. over 20 GPU-hours for embedding-based indexes, with indexing often a large share of total pipeline time and cost — [arXiv 2405.01924](https://arxiv.org/pdf/2405.01924)
- Agentic-loop token overhead where measured against single-shot: AgenticRAG averages **52.3K tokens/query on BRIGHT vs. 20.4K single-shot (2.6x)** but reaches **49.6% recall@1 vs. 8.41%**; on FinanceBench **114.8K tokens/query, a 7.8x ratio** — [AgenticRAG, arXiv 2605.05538](https://arxiv.org/pdf/2605.05538)
- A text-to-JQL study measured agentic latency rising **4.8s -> 32.4s** and tokens **1.8K -> 27.2K (~15x)**, overhead dominated by LLM inference across iterations rather than API round-trips — [Agentic Jackal, arXiv 2604.09470](https://arxiv.org/pdf/2604.09470)
- Input tokens dominate agentic coding cost: one token-economics analysis reports agentic coding consuming over **1,000x more tokens than single-turn reasoning at an input ratio exceeding 150:1** — [Augment, AI Coding Cost Analysis](https://www.augmentcode.com/guides/ai-coding-cost-analysis-agent-token-spend) (**vendor**)
- Parallelism hides agentic latency: eight parallel greps in one turn cost roughly the same latency as one while exploring 8x more of the codebase — [Morph, Agentic Search](https://www.morphllm.com/agentic-search) (**vendor; mechanism is plainly correct, magnitude is theirs**)
- Index staleness is claimed to cause up to 20% performance declines downstream, cited as a reason Claude Code uses grep rather than vector search — [Why Cursor, Claude Code, and Devin Use grep, Not Vectors](https://www.mindstudio.ai/blog/is-rag-dead-what-ai-agents-use-instead) (**secondary blog; I could not trace the 20% figure to a primary source and it should be treated as unsupported**)
- Claude Code's own architecture is described as not indexing the codebase, using tool-based exploration instead — [Claude Code Doesn't Index Your Codebase](https://vadim.blog/claude-code-no-indexing/) (**practitioner analysis, not an Anthropic statement**)

### Inferences

- The break-even for maintaining an index at all is best framed as: does the index reduce *agent turns* enough to pay for its own maintenance? The only controlled data point says yes (-21% $/solved, -7.7 turns), and turn reduction is also what RepoGraph measured (21.47 -> 19.12). Turn count, not ranking quality, is the metric with a credible economic story.
- The client's specific cost profile is unusual and worth flagging: his default local embedder is Qwen3-Embedding-8B at 4096 dims, which per the CoIR-style numbers above puts him in the expensive-to-embed regime (E5-Mistral-class, ~1.8s/sample), mitigated by his persistent embedding daemon and content-hash dedup. His own recorded index times (holusight 230 chunks / 28s; pythia 875 chunks / 346s) imply roughly 0.4s/chunk, consistent with a large local model. At that rate a 50k-chunk repository is ~5.5 hours of first index.
- His 5-minute staleness threshold with incremental content-hash-gated re-embedding is the correct architectural answer to the freshness objection that drove Cursor's decision, and is a genuine point in his design's favor that the vendor discourse does not credit.

### Gaps

- No published break-even analysis by repository size. The claim that large monorepos favor indexes is universally asserted and, as far as I can find, never measured.
- No numbers on index *refresh* cost in production agent workflows (as opposed to first build).

---

## Key Question 7: Measurement - what counts as a credible eval, and the client's MRR gap

### Takeaway

The literature is unusually clear here and it directly indicts the client's current eval: **retrieval ranking metrics correlate weakly with downstream agent success**, with measured Spearman ρ between initial-context quality and agent outcomes of only 0.129-0.237. Multiple papers independently recommend tuning against task performance rather than retrieval metrics. The good news is that a credible cheap downstream eval exists and the field has a published design for it: a paired, seeded-vs-unseeded A/B on a few dozen real issues with test-based pass/fail, a positive control, and a fixed step budget.

### Cited Findings

**The correlation evidence**

- Agent Retrieval Bench reports Spearman correlations between initial-context quality and agent outcomes of **ρ = 0.129 to 0.237** (BCY@8k vs. "any-gold touched" and vs. final File F1, across scaffolds, n=287). The authors attribute the weakness to BCY measuring *initial* ranked-context quality while logged agents can still explore, miss or recover files interactively, and conclude context-acquisition metrics "should be used as a **diagnostic proxy, not a scalar causal estimate** of downstream success" — [Agent Retrieval Bench, arXiv 2607.24882](https://arxiv.org/html/2607.24882v1)
- The Recall Trap's own result is the cleanest demonstration: recall **fell** (0.878 -> 0.806) while resolve rate **rose 7.6pp** (39.2% -> 46.8%, McNemar p=0.0003). Its recommendation is to tune packing against actual task performance rather than retrieval metrics alone — [arXiv 2608.14838](https://arxiv.org/abs/2608.14838)
- CodeGrep's three-regime finding: below a precision threshold retrieval actively hurts (BM25 at file-precision 0.375 cost 0.6pp resolve rate and +21% resolved tokens on SWE-bench Verified); marginal harm of a false positive ≈ marginal benefit of a true positive — [arXiv 2608.05886](https://arxiv.org/pdf/2608.05886)
- A skills-retrieval study found downstream success changed only from **36.4% to 39.3% while actual-use precision fell from 29.6% to 3.3%**, concluding exact ground-truth invocation is "neither sufficient nor strictly necessary" for success — [Demystifying Agent Skills, arXiv 2608.14036](https://arxiv.org/pdf/2608.14036)
- Precision, specifically, is the retrieval metric that does convert: higher precision converts into better generation while recall-oriented metrics and nDCG correlate only weakly — [arXiv 2510.06606](https://arxiv.org/pdf/2510.06606)
- A practitioner report with the exact failure mode the client should fear: **Recall@1 rose 13% -> 50% and Recall@5 13% -> 80%, while end-to-end answered questions fell from 2-in-10 to 0-in-10** — [I made retrieval 4x better and my agent got worse](https://dev.to/etkaozer/i-made-retrieval-4x-better-and-my-agent-got-worse-3kpk) (**practitioner blog, single anecdote, but a well-described one**)
- Methodological note from the policy-retrieval literature: the authors explicitly **avoided** an observational "does retrieval success predict accuracy" correlation design, using a controlled gold-injection sweep instead, because the correlation is tiny and confounded with per-example difficulty — [When Retrieval Metrics Mislead, arXiv 2606.23937](https://arxiv.org/html/2606.23937v1)

**A ready-made cheap downstream eval design**

- Agent Retrieval Bench's **Seed Intervention Pilot (45 samples, single-run)** is essentially the minimum credible eval for "did this context change help my agent": No seed File F1 **0.3222**; retrieval-derived seed **0.3967-0.3981**; oracle gold **0.6337**. Retrieval-derived seeds reduced post-seed tokens from 2,137 to 1,856-2,243, reached gold faster (**first hit at step 1 vs. step 3**) and needed fewer tool calls (**3.7 vs. 5.4**) — [Agent Retrieval Bench, arXiv 2607.24882](https://arxiv.org/html/2607.24882v1). Note this is exactly the client's use case (inject top-k as a seed into a tool-using agent) and it is a *positive* result with an oracle ceiling included.
- The documentation-evaluation literature contributes the methodological checklist: control for source availability (the biggest confound), distinguish instructions from overviews, measure cost not just resolve rate, use adequate step budgets (effects vanish at 25 steps and separate by 200), prevent fix leakage by generating all descriptions from the pre-fix file, and **include a positive control to confirm your harness can detect real improvement** — synthesized from [arXiv 2609.31587](https://arxiv.org/html/2609.31587v1), [arXiv 2606.20512](https://arxiv.org/html/2606.20512v1), [arXiv 2602.11988](https://arxiv.org/html/2602.11988v2)
- Statistical practice in the best of these papers: paired designs with **McNemar exact test** for paired binary resolve outcomes (Recall Trap, n=500, p=0.0003) and **paired Wilcoxon** for per-instance cost (structural index, p=0.35) — [arXiv 2608.14838](https://arxiv.org/abs/2608.14838), [arXiv 2606.22417](https://arxiv.org/pdf/2606.22417)

**Named benchmarks, what each measures**

- **SWE-bench Verified** - human-validated subset, test-based resolve rate on real GitHub issues; the de facto endpoint metric. SWE-bench Lite is the cheaper 300-instance variant used by most graph papers above.
- **SWE-PolyBench** - multi-language SWE-bench analogue, N=617 across four languages — [used in Recall Trap, arXiv 2608.14838](https://arxiv.org/abs/2608.14838)
- **RepoBench** (Liu et al. 2023) - three interlinked tasks: RepoBench-R (retrieval), RepoBench-C (completion), RepoBench-P (pipeline), Python and Java. **Limitation: no unit tests, so pass@k cannot be computed** — [surfaced in YABLoCo comparison, arXiv 2505.04406](https://arxiv.org/pdf/2505.04406)
- **CrossCodeEval** (Ding et al. 2023) - 10K examples in Python, Java, TypeScript, C#; static analysis used to select completions that *require* cross-file context; metrics Exact Match and Edit Similarity — [arXiv 2505.04406 comparison](https://arxiv.org/pdf/2505.04406)
- **Long Code Arena** (Bogomolov et al. 2024, arXiv 2406.11612) - 1,500+ instances, multiple languages, context up to 2M tokens, multi-file, but concentrated on repository-level *completion* rather than full development scenarios — [LoCoBench comparison, arXiv 2509.09614](https://arxiv.org/pdf/2509.09614)
- **RepoCod** - 980 whole-function generation tasks from 11 projects, 50.8% requiring repository-level context, with 314 developer-written test cases per instance; addresses RepoBench's pass@k gap — [arXiv 2410.21647](https://arxiv.org/html/2410.21647v4)
- **Loc-Bench** - purpose-built for code localization, motivated by SWE-bench contamination risk from training-data overlap and its bug-fix focus — [LocAgent, arXiv 2503.09089](https://arxiv.org/html/2503.09089v1)
- **SWE-Explore** - 848 instances, 10 languages, 203 repositories; measures *exploration* under a fixed line budget with HitFile / nDCG@500 / line recall / context efficiency — [arXiv 2606.07297](https://arxiv.org/html/2606.07297v1)
- **CORE-Bench** - three-level code retrieval in the agentic era, built partly from SWE-bench-series instances — [arXiv 2606.11864](https://arxiv.org/html/2606.11864)
- **Agent Retrieval Bench** - 427 samples / 25 repos, four agent-shaped retrieval tasks (code2test, comment2context, trace2code, edit2ripple) plus 82 no-gold negatives, with BCY (Budgeted Context Yield at 4k/8k/16k/32k) as its headline metric — [arXiv 2607.24882](https://arxiv.org/html/2607.24882v1)
- **SWE-Lancer** - the client's brief names this one. I did not search it specifically and have no numbers for it in these notes; flagging as unresearched rather than guessing.

### Inferences

- The client's MRR/hit-rate harness (20 queries, 96 files, later 85 queries) is measuring the metric the literature says correlates at ρ≈0.13-0.24 with what he cares about. His 0.599 -> 0.823 MRR jump from AST chunking is, on this evidence, **not predictive** of an agent-task improvement of any particular size — and his own downstream number (93.0 -> 93.8, n=9) is consistent with near-zero.
- **The cheapest credible upgrade to his measurement, concretely:** 30-50 real issues from his own repos with executable tests; paired runs of the same agent and model with the context pack on vs. off; primary endpoint test-pass; secondary endpoints tool calls to first gold-file touch, total input tokens, and wall-clock; McNemar exact test on the paired binary outcome; a positive control (inject the oracle gold files) to prove the harness can detect an effect; and a fixed, generous step budget. Agent Retrieval Bench's 45-sample seed pilot shows this is detectable at n≈45 on the *process* metrics (steps-to-gold, tool calls) even when the outcome metric is noisy — which is the practical trick: **process metrics are far cheaper to move detectably than resolve rate.**
- His existing 3x3 experiment (no context / Fleet Brain only / Fleet + Holusight, n=9) is the right shape but roughly an order of magnitude too small, has no positive control, and uses an LLM-graded 0-100 score rather than a test-based binary, which makes McNemar-style paired inference unavailable.

### Gaps

- I found no published *minimum detectable effect* analysis for SWE-bench-style paired evals, so I cannot give the client a defensible n for a given effect size. The empirical hint is that papers use n=274-500 for resolve-rate effects of 2-8pp, and n=45 for process-metric effects.
- SWE-Lancer: not researched. No numbers.

---

## Synthesis: where the leverage is, and what is likely a dead end

### Takeaway

Given hybrid retrieval that already works and an available AST graph, the highest-leverage moves are (1) RRF-fusing the graph into the existing ranker, which is the one combination independently measured as better than either arm, (2) routing by query type rather than blending, and (3) replacing the MRR harness with a paired downstream eval measuring turns-to-gold. The likely dead ends are further chunking work, increasing top-k, and betting the thesis on documentation *addition*. The strongest version of the client's thesis is not "retrieval + structure + docs makes agents efficient" but the narrower, better-evidenced "a small high-precision structural seed cuts agent turns, and wrong docs actively poison agents."

### Cited Findings

Highest-leverage, in descending order of evidential support:

1. **Fuse graph + embedding with RRF.** Measured: MRR 0.2336 -> 0.2713, Recall@20 0.7070 -> 0.7331, and the repo-map arm alone already produced the best BCY@8k (0.3788) of any method tested — [Agent Retrieval Bench, arXiv 2607.24882](https://arxiv.org/html/2607.24882v1). The client already has RRF, tree-sitter, and a graph.
2. **Optimize for turns-to-gold and $/solved, not ranking.** Measured precedents: structural index -21% $/solved, -7.7 turns, -3.9k tokens — [arXiv 2606.22417](https://arxiv.org/pdf/2606.22417); RepoGraph 21.47 -> 19.12 turns — [arXiv 2410.14684](https://arxiv.org/html/2410.14684v1); seed intervention first-gold-hit step 3 -> 1, tool calls 5.4 -> 3.7 — [arXiv 2607.24882](https://arxiv.org/html/2607.24882v1).
3. **Route by query type.** Measured: structural wins causal-indirect (RepoMap MRR 0.2742 on trace2code), embeddings win semantic-direct (0.3939 with RRF-3), and per-task winners differ across all four task types — [arXiv 2607.24882](https://arxiv.org/html/2607.24882v1).
4. **Detect and remove wrong docs rather than add right ones.** Measured asymmetry: incorrect comments substantially degrade performance, missing ones have relatively minor impact — [arXiv 2512.16790](https://arxiv.org/html/2512.16790v1); models adopt false comments over their own correct reasoning, implicitly — [CodeCrash, arXiv 2504.14119](https://arxiv.org/pdf/2504.14119).
5. **Trade breadth for depth within files at fixed budget.** Measured: +7.6pp resolve rate (p=0.0003) from *reducing* file-level deduplication despite lower recall — [arXiv 2608.14838](https://arxiv.org/abs/2608.14838).

Likely dead ends, with the evidence against each:

- **More chunking work.** Sliding window beat cAST on both RepoEval (46.23% vs. 45.93% API-level) and CrossCodeEval (28.40% vs. 28.19%) across 864 settings, and the paper concludes structure-aware chunking does not outperform on quality or cost — [arXiv 2605.04763](https://arxiv.org/html/2605.04763). cAST's own claimed gains are +4.3 Recall@5 and ~+2.67 Pass@1 — [arXiv 2506.15655](https://arxiv.org/html/2506.15655v1). Either way the ceiling is low.
- **Raising top-k.** Saturation at k=3-4 with no fluctuation to k=10 — [arXiv 2406.18294](https://arxiv.org/pdf/2406.18294); F1@k peaks at k=3 — [arXiv 2510.06606](https://arxiv.org/pdf/2510.06606); 10% hard distractors drop gold-document attention 76% and post-hoc filtering recovers only marginally — [arXiv 2605.10828](https://arxiv.org/pdf/2605.10828).
- **Documentation *addition* as the value proposition.** When source is present, neither compact documentation nor retrieved context beats the issue alone; the effect appears only when source is withheld (0.08 -> 0.71 test-pass) — [arXiv 2609.31587](https://arxiv.org/html/2609.31587v1). Context files do not generally improve success while adding 20%+ cost; repository overviews specifically were not helpful — [arXiv 2602.11988](https://arxiv.org/html/2602.11988v2).
- **Positioning the engine as a replacement for agent tool use.** Agentic explorers score 0.64-0.67 HitFile vs. 0.079-0.140 for BM25/TF-IDF/dense — [arXiv 2606.07297](https://arxiv.org/html/2606.07297v1); Cursor removed semantic indexing from its retrieval path — [Cursor docs](https://cursor.com/docs/context/codebase-indexing).
- **Further reranker investment specifically.** Anthropic's reranking step moved failure rate 2.9% -> 1.9% on top of contextual embeddings + contextual BM25 — real, but a small slice of a pipeline the client already runs — [Anthropic](https://www.anthropic.com/engineering/contextual-retrieval).

### Inferences

- The client's 93.0 -> 93.8 result is **not** evidence that his machinery fails to pay off. It is the effect size the literature predicts for seeding a capable tool-using agent (Cursor's own measured +12.5% accuracy from semantic-on-grep is the optimistic end; the seed-intervention File F1 0.3222 -> 0.3967 is the same shape). His +25 points on one architecturally complex task is also the pattern the literature reports: gains concentrate on multi-hop / cross-file / root-cause tasks, which is precisely where RepoMap and graph traversal win and where embeddings alone do not.
- The one thing his measurement genuinely cannot support is *which* component earned the 0.8 points. With n=9 and no ablation, the AST chunking, the context headers, the hybrid fusion, and the reranker are all confounded.
- The strongest strategic reframe available to him: his differentiator is not retrieval quality, it is that he has **both** a semantic index and a structural graph over the same tracked corpus, plus a consistency engine that knows when docs and code disagree. The literature says graph+semantic fusion is the best measured combination, and that wrong docs are measurably harmful while missing docs are not. Those two facts together describe a product; "better retrieval" does not.
- A caution worth stating: the per-repo index economics of a 4096-dim 8B local embedder are materially worse than the small-model economics most of this literature assumes, and index freshness was the decisive factor in Cursor's retreat from embeddings. His content-hash-gated incremental re-embedding and 5-minute staleness threshold are the right answer, and should be treated as load-bearing rather than incidental.

### Gaps

- **The central unmeasured question for his product:** does automated doc-code consistency checking improve agent outcomes? Nobody has measured it. The harm of stale docs is established; the benefit of a tool that finds them is not.
- No evidence either way on whether a *consistency signal* (this doc is stale, distrust it) supplied to an agent changes behavior. Given CodeCrash's finding that models adopt comments implicitly without citing them, it is not obvious a warning would even be heeded.
- No measured guidance on how to present graph context to an agent without token bloat. Aider's 1,024-token budget is a design choice, not a measured optimum, and I found no ablation of repo-map budget against outcomes.
