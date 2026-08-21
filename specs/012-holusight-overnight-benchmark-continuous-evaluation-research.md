# Holusight Overnight Benchmark and Continuous-Evaluation Research

**Research date:** August 21, 2026  
**Intended use:** freeze an evaluation specification for later review and prototyping.  
**Authorization boundary:** this report authorizes **no downloads, API spending, code changes, credential use, private-code transfer, production deployment, or autonomous promotion**.

Evidence notation used below:

- **[C]** canonical repository, dataset card, or official documentation.
- **[P]** primary benchmark/research paper.
- **[I]** independent analysis, audit, or reproduction.
- **[L]** fact supplied and locally verified by the Holusight owner; it was not independently inspected for this report.

Unless otherwise stated, web sources were accessed **2026-08-21**. Confidence refers to the conclusion drawn for Holusight, not merely to whether the cited source exists.

## Executive decision and benchmark architecture

### Recommendation

Choose **C + F, selectively adapting E**:

> **Build a small Fleet-owned layered evaluation specification and adapter harness, with provider-specific task families plus a small end-to-end layer. Reuse public benchmark datasets and an existing general eval runner where convenient, but keep Holusight's task schemas, hidden truth, safety policy, cost ledger, promotion rules, and evaluation ownership independent.**

The best current substrate to *adapt* rather than recreate is **Inspect AI**: it provides composable datasets, agents/tools, scorers, and structured evaluation logs, while leaving the evaluation definition under the user's control. Its official documentation describes the core abstraction as dataset + solver + scorer and provides structured logs and more than 200 pre-built evaluations. citeturn19search2turn19search14turn19search26 Canonical URL: `https://inspect.aisi.org.uk/`.

Inspect should **not** become the source of truth. The source of truth should be Fleet-owned JSONL/manifest schemas and deterministic or hidden graders. That makes replacement of Inspect, Python scripts, or any future runner a reversible engineering choice rather than an eval migration.

The options rank as follows:

| Option | Decision | Why |
|---|---|---|
| **C — layered benchmark** | **Core choice** | The architecture contains specialists that solve genuinely different jobs. Retrieval, graph traversal, memory, compliance and full repair therefore require different gold structures. |
| **F — small Fleet adapter harness** | **Core implementation choice** | Preserves hidden truth, privacy, cost accounting and provider neutrality while reusing public data. |
| **E — adapt existing harnesses** | **Selective use** | Use MTEB/BEIR/CoIR for retrieval imports, Inspect for orchestration/logging, SWE-family executable harnesses for code outcomes, and RAG scoring packages only where useful. MTEB and CoIR already normalize retrieval evaluation schemas. citeturn1search1turn18search3 |
| **B — retrieval-only** | **Necessary but insufficient** | It can identify localization regressions cheaply, but cannot establish whether better retrieval translates into a correct code change, valid synthesis, policy decision or agent outcome. Newer ContextBench and SWE-Explore exist precisely because end-to-end and retrieval/process measurements illuminate different failure modes. citeturn17search6turn17academia36 |
| **A — existing tests only** | **Reject** | Existing product tests can verify software behavior but cannot fairly compare alternative evidence architectures, route regret, citations, memory or interface efficiency. |
| **D — autonomous nightly research platform** | **Reject now** | It introduces far more mutable machinery than the hypothesis requires and creates unnecessary egress, cost, test-integrity and maintenance risks. |

**Confidence: high. Local validation required:** verify that Inspect can represent Holusight's required provider traces without forcing private data into external services; if not, use the same Fleet schema with a tiny native Python runner.

### Why a single leaderboard is the wrong abstraction

The assumption that all systems should be ranked on one universal score should be rejected. **ripgrep/Zoekt, vector search, SCIP, Graphify, GraphRAG, memory, deterministic compliance and a routed composite do not have the same objective function.**

ripgrep is a recursive regex/text search tool, Zoekt is an indexed source-code text-search engine, and SCIP is a protocol for storing code-intelligence facts such as definitions and references. citeturn7search0turn7search1turn7search2 GraphRAG instead constructs entities, relationships, communities and summaries from unstructured documents and exposes local, global and DRIFT query approaches. citeturn19search29turn19search4 These systems should meet on shared tasks **only where their capabilities overlap**.

The benchmark should therefore expose:

**Provider-family scorecards → routed-system scorecard → end-to-end outcome scorecard.**

A routed system is not required to beat the best specialist on every task. Its stronger null hypothesis is:

> **The router should approach the quality of the best sufficient specialist while paying substantially less than exhaustive fan-out and without introducing safety or correctness regressions.**

That changes the central router question from “Did it pick the canonical provider?” to “Did it choose a provider set that was sufficient at near-minimal cost?”

### The central causal model

The evaluation should explicitly separate this chain:

\[
\text{question}
\rightarrow
\text{route}
\rightarrow
\text{retrieval/evidence}
\rightarrow
\text{context}
\rightarrow
\text{reasoning/action}
\rightarrow
\text{outcome}
\]

Every layer needs a metric because otherwise an end-to-end win cannot tell you *why* it occurred, while a retrieval win cannot tell you whether it mattered.

The primary economic metric should be:

\[
\text{resource per correct outcome}
=
\frac{
\text{tokens, \$, wall time, CPU, calls, or human correction time}
}{
\text{correct successful outcomes}
}
\]

not retrieved chunk length. This follows the owner's prior local evaluation principle [L] and is also consistent with the fact that modern code benchmarks separate localization/context behavior from final executable repair. ContextBench supplies human-annotated contexts, while SWE-bench grades issue-resolution patches through repository tests. citeturn17search2turn14search8

A system that retrieves 40% fewer tokens but causes 10% more failed repairs is **not more efficient**.

### The assumptions that should be explicitly falsified

**Books are not general Holusight evidence.** Books can provide long-document themes, cross-chapter relationships, contradiction and citation tasks. They cannot establish repository impact-analysis correctness or company-specific compliance. Project Gutenberg is therefore a *corpus source* for deliberately authored long-document tests, not a benchmark for code retrieval. Its corpus and licensing policy are publicly documented, but territorial/public-domain and Project Gutenberg terms should still be checked work by work. citeturn4search19turn4search3turn4search7

**More data is not automatically better evidence.** A 96-task private suite with hidden executable, qrel and policy truth can be more decision-useful than millions of public retrieval examples if the latter are contaminated or structurally unlike Fleet work. This is especially relevant in 2026 because public SWE-bench results have attracted explicit contamination and benchmark-validity criticism; OpenAI announced in February 2026 that it no longer considered SWE-bench Verified a reliable frontier measure, citing contamination and flawed tasks in its audit. citeturn14search5 Separate academic work has also investigated SWE-bench leakage. citeturn14search1turn14search2

**LLM judges cannot be promotion authorities by themselves.** Research on LLM-as-judge evaluation documents consistency and bias limitations, so fuzzy generation grading should be calibrated against executable or human labels rather than treated as hidden ground truth. citeturn14search4turn14search25turn14search29

**An unattended overnight run must be deliberately bounded.** It should have precommitted request/token/currency/time limits, no silent expansion of retries, and deny-by-default network access. This is a design conclusion rather than a claim that a particular framework already enforces it.

**The “all-components” system should not be expected to dominate specialists everywhere.** Its job is to dominate *aggregate work under a cost/safety constraint*. A grep-style exact lookup may legitimately remain fastest and cheapest with no graph or embedding call.

**AXI's published wins are not evidence that holus-axi will win.** The published AXI GitHub study used 17 tasks, five repeats, one target repository, Claude Sonnet 4.6 as agent and Claude Sonnet 4.6 as judge, yielding 425 runs across five interface conditions. citeturn16search0 The AXI repository separately reports a browser benchmark using 14 tasks, seven conditions and five repeats with the same model family. citeturn16search1turn16search2 Those are meaningful maintainer experiments, but they do not independently establish transfer to repository evidence retrieval, another model family, or Holusight.

## Job taxonomy and public dataset decisions

### Frozen job taxonomy

The first specification should freeze **ten task families**. The output type and truth source differ intentionally.

| Job | Primary question | Required gold | Fair specialists |
|---|---|---|---|
| **Exact lookup** | “Where exactly is string/symbol/config X?” | Exact files/lines/symbols; negative cases | ripgrep, Zoekt, BM25, SCIP/exact, Holusight |
| **Conceptual localization** | “Where is behavior X implemented?” | Relevant file/symbol/line qrels | vector, BM25, hybrid, Graphify, routed system |
| **Symbol/change impact** | “What directly and transitively depends on X?” | Direct + broader dependency/impact set | SCIP/LSP/build graph, Graphify, hybrid graph |
| **Broad document synthesis** | “What are the major themes/trends across this corpus?” | Required points + supporting citations | vector RAG, oversized context, GraphRAG global/DRIFT |
| **Entity/relationship reasoning** | “How are A, B and C related?” | Answer + path/supporting evidence | graph/doc graph, hybrid, vector baseline |
| **Temporal memory** | “What is current after later updates?” | Timestamped facts, supersession chain | GBrain/memory, hybrid, full context |
| **Contradiction / no-answer** | “Sources conflict / evidence is absent.” | Contradiction pair, precedence rule, abstain flag | all retrieval/memory systems |
| **Repository compliance** | “Does change/state violate rule R?” | Deterministic violation oracle | static analyzer/contracts first; routed evidence may explain |
| **ACL / injection safety** | “Can unauthorized or malicious evidence affect output?” | Principal ACL, forbidden records, attack expectation | every candidate; deterministic access control is authoritative |
| **Full code-change outcome** | “Can evidence help complete a real change?” | Hidden tests + optional human review | all end-to-end eligible systems |

This decomposition is central to fairness. GraphRAG should not lose points for not being a regex engine, while ripgrep should not lose points because it cannot synthesize themes from 100 documents.

### Dataset decision table

**All access dates below are 2026-08-21.** “Footprint” deliberately distinguishes benchmark metadata from required repository/container materialization; exact downloaded bytes should be obtained during a **metadata-only dry run before authorization**, because caches, Git history, repository snapshots and Docker layers make advertised dataset sizes poor predictors of local storage.

| Candidate | Job and gold structure | Size / footprint | License / terms | Decision for Holusight |
|---|---|---|---|---|
| **BEIR** — `https://github.com/beir-cellar/beir` | General retrieval; queries, corpus, qrels; 18 heterogeneous retrieval datasets/tasks in the original benchmark. citeturn1search0turn1search4 | Varies dramatically by constituent dataset; **do not download the full collection**. | Constituent datasets have their own licenses; framework-level licensing is not enough. | **Accept selected small sets only** for retrieval sanity checks. [C/P, high] Not representative of repo impact or end-to-end agent work. |
| **MTEB** — `https://github.com/embeddings-benchmark/mteb` | General embedding/retrieval evaluation framework; current project supports broad text evaluation and provides reusable task schemas. citeturn1search1turn1search21 | Framework is small; selected datasets determine footprint. | Framework is Apache-2.0; dataset licenses are separate. | **Accept as adapter, not truth set.** Excellent way to avoid custom retrieval plumbing. [C/P, high] |
| **CoIR** — `https://github.com/CoIR-team/coir` | Code retrieval; 10 datasets, eight retrieval tasks, seven domains and about two million documents; compatible with MTEB/BEIR-style schemas. citeturn18search3 | Full ~2M-document corpus is larger than an overnight pilot needs. | Project Apache-2.0; underlying source/dataset terms still require dataset-level review. | **Strong accept, stratified subset.** Stronger 2025-era umbrella than using CodeSearchNet alone. [C/P, high] |
| **CodeSearchNet** — `https://github.com/github/CodeSearchNet` | NL-to-code semantic retrieval; roughly six million functions across six languages, with a small expert-judged query set in the original benchmark. citeturn1search2turn1search6 | Multi-million-function corpus; unnecessary for nightly full use. | Source repositories/data provenance require their own review. | **Smoke/regression only.** Historically useful but old and highly exposed to model training; weak evidence for 2026 agent effectiveness. [C/P, high] |
| **RepoBench** — `https://github.com/Leolty/repobench` | Repository-level cross-file retrieval/completion; Python and Java, including explicit cross-file settings. citeturn18search2turn17search4 | Thousands of source repositories in its construction; use released records/subsets rather than materializing everything. | CC-BY-4.0 repository/dataset release. citeturn18search2 | **Accept secondary.** Good cross-file test, but next-line/completion framing is narrower than real impact analysis. [C/P, high] |
| **CrossCodeEval** — `https://github.com/amazon-science/cceval` | Cross-file code completion requiring repository-local APIs; Python, Java, TypeScript and C#. Static analysis is used to identify cross-file dependencies. citeturn17search5turn17search17 | Moderate snippet/repository corpus; exact local footprint should be dry-run measured. | Project Apache-2.0; source repositories were selected for permissive licensing. citeturn17search1turn17search5 | **Accept.** Useful structural/context localization arm; not a substitute for change-impact truth. [C/P, high] |
| **ContextBench** — `https://github.com/EuniAI/ContextBench` | 1,136 issue-resolution tasks from 66 repositories / eight languages with human-annotated gold contexts; 522,115 annotated lines. citeturn17search6turn18search0 | Metadata moderate; repository snapshots dominate materialized disk. A 500-task Lite subset exists. citeturn17search6 | Apache-2.0 project. citeturn18search0 | **Strong 2026 accept.** One of the best public complements to Holusight's own context-localization tests because gold context is human annotated. [C/P, high] |
| **SWE-Explore** — `https://github.com/Qiushao-E/SWE-Explore-Bench` | 848 issues across 203 repositories and ten languages; ranked code regions under a fixed line budget. Ground truth is distilled from successful repair trajectories. citeturn18search1turn17academia36 | Repo snapshots dominate disk; subset rather than full corpus. | Code MIT; maintainers explicitly tell users to check dataset-specific terms. citeturn18search1 | **Accept as secondary process benchmark.** Very relevant, but its trajectory-derived “gold” is not equivalent to independently human-proven minimal context. [C/P, medium-high] |
| **SWE-bench Verified / Mini** — `https://www.swebench.com/verified.html`, `https://hal.cs.princeton.edu/swebench_verified_mini` | Executable issue resolution; Verified has 500 human-filtered tasks; the Mini subset provides 50 tasks. citeturn2search24turn2search16 | Dataset rows small; runtime images/repos can dominate storage and startup cost. | SWE-bench code/data repo states MIT, but each underlying project carries its own licensing obligations. citeturn13search0 | **Use only a small frozen compatibility subset, not as primary 2026 truth.** Public contamination and validity concerns are now material. citeturn14search5turn14search2 |
| **SWE-rebench** — `https://swe-rebench.com/about` | Continuously refreshed real-world software tasks with standardized pipeline and explicit contamination tracking. citeturn15search0turn15search8 | Potentially substantial repo/container materialization; use only selected fresh tasks. | Verify release-specific dataset/repo terms before use. | **Strong rotating canary, not frozen core.** Its freshness is exactly why it should sit outside the immutable historical suite. [C/P, high] |
| **SWE-bench-Live** — `https://github.com/microsoft/swe-bench-live` | Automatically updating, multi-language/multi-OS SWE tasks; by May 2026 its multilingual set reported 743 tasks across six languages and 381 repos. citeturn17search31 | High when environments are materialized. | MIT project; source-project licensing remains relevant. | **Promising rotating canary.** Prefer later when Holusight needs non-Python or OS breadth. [C, high] |
| **SWE-bench Pro** — `https://labs.scale.com/leaderboard/swe_bench_pro_public` | Harder long-horizon issue resolution intended to address limitations of earlier SWE-bench variants. citeturn15search1turn15search29 | Expensive environment-level evaluation; not an overnight starting point. | Review public-dataset and constituent repository terms before copying locally. | **Defer.** Useful pre-promotion challenge set, excessive for smallest reversible nightly loop. [C/P, high] |
| **SWE-PolyBench** — `https://github.com/amazon-science/SWE-PolyBench` | Multi-language executable SWE tasks; 2,110 curated issues with a verified subset reported by maintainers. citeturn2search3turn2search18 | Environment-heavy. | MIT project. citeturn2search18 | **Later.** Add when multi-language generality becomes a decision criterion. [C, high] |
| **LongMemEval** — `https://github.com/xiaowu0162/LongMemEval` | 500 questions testing information extraction, multi-session reasoning, knowledge updates, temporal reasoning and abstention; smaller configuration is around 115k tokens/query context. citeturn5view0turn15search27 | Moderate relative to newer million-token suites; appropriate to subset overnight. | MIT. citeturn5view0 | **Strong accept.** Best first public memory arm because it directly tests supersession and abstention. [C/P, high] |
| **LongMemEval-V2** — `https://github.com/xiaowu0162/LongMemEval-V2` | 451 manually curated questions and 1,870 web/enterprise trajectories; extends memory depth beyond 100M tokens in the full benchmark. citeturn15search15turn15search7 | **Very large full-context footprint.** | Verify dataset-card terms before materialization. | **Strong 2026 benchmark, but later/subset only.** Particularly useful for “experienced agent” memory, too large for first night. [C/P, high] |
| **BEAM** — `https://github.com/mohammadtavakoli78/BEAM` | 100 conversations, 2,000 validated questions, with conversations up to 10M tokens. citeturn15search6turn15search34 | Extremely large at high tiers; use 100k/500k strata before 10M. | License should be verified before download. | **Later stress test.** Strong scale test, but synthetic-generation construction and size make it a poor first nightly core. [C/P, medium-high] |
| **LoCoMo** — `https://github.com/snap-research/locomo` | Long conversations with QA and event summarization; released collection has ten long conversations and evidence-linked questions. citeturn5view1 | Small corpus. | CC BY-NC 4.0. citeturn6view0 | **Hold for legal review in a commercial setting.** Technically useful; noncommercial restriction is the problem. [C, high] |
| **GBrain BrainBench / PrecisionMemBench arm** — `https://github.com/garrytan/gbrain-evals` | Public memory-eval harness; BrainBench includes fictional relational knowledge, and the project also integrates PrecisionMemBench. citeturn19search3turn19search15turn19search19 | Small-to-moderate benchmark artifacts; large stress configurations are separate. | Repository is public/reproducible; pin exact benchmark scorer and commit. | **Accept only as independent reproduction arm.** Maintainer-published GBrain scores remain maintainer evidence, not Holusight ground truth. [C, medium-high] |
| **QASPER** — `https://huggingface.co/datasets/allenai/qasper` | 5,049 questions over 1,585 NLP papers; independent answerers supply supporting evidence. citeturn13search3 | HF converted train parquet shown as 14.4 MB; complete source artifacts remain small relative to repo benchmarks. citeturn13search19 | CC BY 4.0 dataset card. citeturn13search6turn13search19 | **Accept.** Excellent citation/support test, though NLP-paper domain is narrow and likely familiar to frontier models. [C/P, high] |
| **HotpotQA** — `https://hotpotqa.github.io/` | About 113k multi-hop questions with supporting facts. citeturn4search0turn4search12 | Moderate text corpus. | Dataset CC BY-SA 4.0; official code is Apache-2.0. citeturn4search8 | **Accept small subset** for entity/multi-hop support. It should not drive architecture decisions by itself. [C/P, high] |
| **MuSiQue** — `https://github.com/stonybrooknlp/musique` | About 25k compositional 2–4 hop questions; MuSiQue-Full includes contrastive unanswerable questions. citeturn4search1turn4search5 | Moderate. | **License verification required before use.** | **Conditional accept.** Especially attractive for negative/no-answer and multi-hop evaluation, once terms are cleared. [C/P, medium-high] |
| **SummHay / Summary of a Haystack** — `https://github.com/salesforce/summary-of-a-haystack` | Ten released long haystacks in news/conversation domains; evaluates synthesis with Coverage, Citation and Joint metrics. citeturn13search1 | Small number of deliberately long corpora. | Repo was archived June 25, 2026; verify dataset/repo license before redistribution. citeturn13search5 | **Strong accept for global-theme/citation testing.** Better first-purpose fit than arbitrary books. [C/P, high] |
| **Microsoft GraphRAG benchmarking data** — `https://github.com/microsoft/graphrag-benchmarking-datasets` | Includes HotpotQA-derived assets and 125 thematic open-ended questions from Kevin Scott podcast material for multi-document summarization. citeturn19search1 | Small enough for a targeted GraphRAG experiment; indexing cost, not raw corpus storage, is likely the concern. | CDLA-Permissive-2.0, with third-party notices. citeturn19search1turn19search9 | **Accept targeted.** Run only global/local/DRIFT questions for which graph indexing is plausibly load-bearing. [C, high] |
| **WildGraphBench** — `https://github.com/BstWPY/WildGraphBench` | 2026 benchmark spanning factual, multi-fact and section-level summarization questions with cited source material. citeturn10search13turn10search5 | Larger than Microsoft's 125-question set but still subsettable. | Verify repo/data terms at freeze. | **Promising 2026 secondary GraphRAG set.** Use after the small GraphRAG pilot, not before. [P/C, medium-high] |
| **GraphRAG-Bench** — `https://github.com/GraphRAG-Bench/GraphRAG-Benchmark` | Graph-RAG evaluation over diverse corpora/tasks and pipeline stages, including retrieval, reasoning and summarization. citeturn10search2turn19search13 | Multi-corpus and comparatively broad. | Verify dataset components individually. | **Defer to research replication.** Useful for graph-RAG research, less directly representative than Holusight's own documents. [P/C, medium] |
| **NarrativeQA** — `https://github.com/google-deepmind/narrativeqa` | Long-story question answering. citeturn3search7 | Corpus rights/access are more awkward than synthetic/open long-document tests. | Repository Apache-2.0; source narratives have separate copyright considerations. | **Defer.** SummHay/QASPER give cleaner first-night provenance and citation structure. [C/P, high] |
| **Project Gutenberg** — `https://www.gutenberg.org/` | Tens of thousands of ebooks; no native Holusight qrels or repository truth. citeturn4search19 | User-selectable; potentially very large only if one needlessly mirrors it. | Work-level public-domain status and Gutenberg terms must be checked. citeturn4search3turn4search7 | **Reject as a generic benchmark; accept as a source corpus for 2–5 curated global-theme tests.** [C, high] |

### What should actually enter the first frozen public pack

The **first public pack should be intentionally small**:

**Code retrieval/localization:** a stratified CoIR sample, a small CrossCodeEval subset, and ContextBench Lite cases. CoIR broadens traditional retrieval coverage, CrossCodeEval supplies explicit cross-file dependence, and ContextBench provides human gold context. citeturn18search3turn17search5turn17search6

**End-to-end code:** 10–20 tasks from SWE-bench Verified Mini purely as executable compatibility cases, plus a fresh SWE-rebench/SWE-bench-Live canary outside the frozen aggregate. The latter matters because continuously refreshed tasks offer a better contamination monitor than continually reusing old public issues. citeturn2search16turn15search8turn17search31

**Documents:** QASPER + SummHay + Microsoft's 125-question GraphRAG set. These separate evidence-backed document QA from broad synthesis. citeturn13search3turn13search1turn19search1

**Memory:** LongMemEval first. LongMemEval-V2 and BEAM are reserved for multi-night stress evaluation because their scale is part of what they test. citeturn15search27turn15search7turn15search34

**Multi-hop/no-answer:** a small HotpotQA sample and, after licensing review, MuSiQue-Full. citeturn4search12turn4search5

Do **not** pre-download full BEIR, full CoIR, full SWE environments, LongMemEval-V2, BEAM, GraphRAG-Bench or large Gutenberg collections merely because they exist.

## Frozen private suite, variants, and schemas

### The private suite should carry the architectural decision

Public benchmarks cannot tell Fleet whether Graphify adds anything beyond Holusight, whether GBrain helps the owner's own workflows, whether private compliance rules are enforced, or whether the router leaks one user's evidence to another. Those are inherently local empirical questions [L].

Freeze a **96-task private core**, plus rotating canaries.

A defensible minimum allocation is:

| Private family | Frozen tasks | Main truth |
|---|---:|---|
| Exact lookup | 10 | file/line/symbol qrels |
| Conceptual localization | 10 | human gold regions |
| Direct + broader impact | 12 | dependency/impact oracle |
| Broad document synthesis | 10 | required claims + citations |
| Entity/relationship | 8 | relation/path qrels |
| Temporal memory/supersession | 10 | dated fact ledger |
| Contradiction/no-answer | 10 | contradiction pair / abstain |
| Repository compliance | 10 | deterministic policy oracle |
| ACL isolation + prompt injection | 8 | forbidden-evidence and attack oracle |
| Full code-change | 8 | hidden tests |
| **Total** | **96** | |

This is small enough to understand manually and large enough to reveal major architecture differences. It is **not** large enough to prove a two-percentage-point generalization advantage; that limitation is handled by multi-night accumulation and confidence intervals.

The suite spans:

**Holusight itself [L].** Use it for exact, conceptual, citation, stale-index and architecture-impact tasks.

**One larger Fleet repository [L].** It should supply realistic cross-module impact, compliance and developer-workflow tasks. The benchmark framework should describe how to create it without asking for the repository or credentials.

**One public reproducibility repository.** The default candidate is `https://github.com/django/django`, which is a mature Python repository under BSD-3-Clause. citeturn20search6turn20search0 This should be replaced *before freezing* if Python is materially unlike Holusight/Fleet's dominant language. Public-code contamination means Django's unmodified historical facts should **not** be considered secret; its main value is reproducible structure and its ability to host private, post-freeze mutations.

A good allocation is roughly 24 tasks per repository plus 24 cross-document/memory/security fixtures. Exact counts may be redistributed **before** freeze; after freeze, changing them creates a new suite version.

### Mutation design

Mutations are critical because they create hidden facts models could not have memorized. Generate them offline from pinned source snapshots and keep the mutation seed/materialized diff hidden.

Mutation families should include:

| Mutation | Tests |
|---|---|
| Rename/move symbol while preserving behavior | exact search, semantic localization, stale indexes |
| Introduce a new call/reference edge | direct impact and graph freshness |
| Delete an expected edge | false-positive impact recall |
| Move implementation behind an adapter | conceptual retrieval vs lexical search |
| Change a configuration default | current-versus-stale evidence |
| Add superseding documentation | temporal precedence |
| Add contradictory obsolete document | contradiction detection |
| Add deterministic policy violation | compliance recall |
| Add near-miss non-violation | compliance precision |
| Insert inaccessible canary fact | ACL leakage |
| Insert prompt-injection-like instruction in comment/doc | evidence/data-vs-instruction separation |
| Introduce small test-covered bug/change request | full code-change outcome |

Prompt-injection test content should be treated as inert benchmark data. AgentDojo and BIPIA provide public patterns for indirect prompt-injection evaluation, but neither substitutes for Holusight's own ACL and read-only evidence invariants. citeturn12search0turn12search1 OWASP's current guidance also treats prompt injection as an active LLM application security problem. citeturn12search2turn12search6 GitHub has documented practical prompt-injection risk in developer tooling, including attacks that can target confidential files/tokens or unintended execution. citeturn12search33

### Split and ownership policy

Do **not** randomly split near-duplicate mutations. Split by **task lineage and mutation family** so the same base task cannot appear in development and held-out forms.

Recommended split of the 96 frozen tasks:

- **32 development-visible tasks**: queries and gold may be exposed to benchmark developers.
- **16 calibration tasks**: queries visible; authoritative labels controlled by evaluation owner.
- **48 held-out tasks**: prompts can be executed by the trusted runner; qrels, tests, mutation seeds and detailed grader logic remain unavailable to the candidate being evaluated.

This gives the candidate enough feedback to debug adapters without letting it optimize directly against most promotion evidence.

The **evaluation owner must be organizationally distinct from the candidate optimizer whenever practical**. The candidate may propose a new retrieval method, prompt or router, but it may never modify its own held-out tasks, graders, thresholds, ACL definitions, secrets policy or promotion gate.

Retired hidden tasks can eventually be disclosed for debugging, but they must then be replaced under a new suite revision.

### Human labeling

For conceptual relevance, broad impact and synthesis claims, establish an annotation manual before scoring.

At minimum:

- Two independent annotators label all ambiguous **impact** and **compliance** cases.
- Two independent annotators label a calibration sample of conceptual and synthesis tasks.
- Disagreements are adjudicated *before candidate identities/results are revealed*.
- Every relevance label records evidence coordinates, not merely `relevant=true`.
- For impact, distinguish **direct**, **transitive/broader**, **possible**, and **not impacted**.
- For synthesis, label required facts/claims and acceptable source regions rather than expecting a reference answer's exact wording.

### Frozen task schema

The canonical task format should be plain JSONL. External harnesses adapt *to it*, never the reverse.

```json
{
  "schema_version": "holus-eval-task/v1",
  "suite_id": "holus-private-2026q3",
  "task_id": "impact-fleet-0042",
  "lineage_id": "impact-auth-session",
  "split": "heldout",
  "family": "symbol_impact",
  "corpus": {
    "id": "fleet-repo-a",
    "kind": "git",
    "commit": "FULL_COMMIT_SHA",
    "mutation_id": "hidden:mut-0087"
  },
  "principal": {
    "id": "benchmark-role-a",
    "acl_profile": "acl-v3"
  },
  "question": "Which components must be reviewed if SessionPolicy is changed?",
  "time_cutoff": "2026-08-15T00:00:00Z",
  "expected_behavior": {
    "abstain": false,
    "side_effects": "forbidden"
  },
  "allowed_capabilities": [
    "evidence_search",
    "read_file",
    "symbol_lookup"
  ],
  "budget": {
    "wall_seconds": 180,
    "max_tool_calls": 12,
    "max_input_tokens": 50000,
    "max_output_tokens": 4000
  },
  "grader_ref": "hidden:impact-v2",
  "gold_ref": "hidden:qrels-impact-fleet-0042",
  "tags": ["transitive", "cross_module", "stale_index_probe"]
}
```

Hidden truth is a **separate object** so exporting a task file cannot accidentally reveal the answer:

```json
{
  "schema_version": "holus-eval-gold/v1",
  "task_id": "impact-fleet-0042",
  "required_evidence": [
    {"path": "src/a.py", "symbol": "SessionPolicy", "relation": "direct"},
    {"path": "src/b.py", "symbol": "PolicyCache", "relation": "transitive"}
  ],
  "optional_evidence": [],
  "forbidden_evidence": [],
  "required_claims": [
    "PolicyCache must be reviewed because it derives cached state from SessionPolicy"
  ],
  "hidden_tests": ["hidden:test-impact-221"],
  "compliance_assertions": []
}
```

### Manifest and result schemas

The immutable run manifest is the reproducibility root:

```json
{
  "schema_version": "holus-eval-manifest/v1",
  "run_id": "2026-08-21T22-00Z__candidate-x",
  "suite_digest": "sha256:...",
  "config_digest": "sha256:...",
  "seed": 41028491,
  "mode": "dry-run",
  "candidate": {
    "name": "holusight-hybrid",
    "version": "git-sha-or-build-digest"
  },
  "providers": [
    {
      "id": "bm25",
      "version": "pinned-version",
      "index_digest": "sha256:..."
    }
  ],
  "models": [],
  "prompt_digest": "sha256:...",
  "corpus_commits": {
    "holusight": "FULL_SHA",
    "fleet-repo-a": "FULL_SHA",
    "public-repo": "FULL_SHA"
  },
  "environment": {
    "os": "...",
    "cpu": "...",
    "gpu": "...",
    "ram_bytes": 0,
    "container_digest": "..."
  },
  "network_policy": {
    "default": "deny",
    "allowlist": []
  },
  "caps": {
    "paid_usd": 0,
    "requests": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "wall_seconds": 36000,
    "disk_bytes": 0
  },
  "cache_policy": "cold-query",
  "retry_policy_ref": "retry-v1"
}
```

Each task/variant/trial produces one append-only result record:

```json
{
  "schema_version": "holus-eval-result/v1",
  "run_id": "...",
  "task_id": "impact-fleet-0042",
  "variant": "holusight_graphify",
  "trial": 0,
  "attempt": 1,
  "status": "scored",
  "route": ["holusight", "graphify"],
  "retrieved": [
    {
      "source_id": "src/a.py",
      "locator": "L120-L161",
      "source_commit": "FULL_SHA",
      "score": 0.91
    }
  ],
  "answer_ref": "artifact:sha256:...",
  "citations": ["src/a.py:L120-L161"],
  "usage": {
    "tool_calls": 4,
    "schema_tokens": 1200,
    "retrieval_tokens": 6100,
    "model_input_tokens": 15300,
    "model_output_tokens": 760,
    "embedding_tokens": 0,
    "provider_requests": 0
  },
  "cost": {
    "currency": "USD",
    "billed": 0.0,
    "estimated": 0.0,
    "price_snapshot_ref": "prices-v1"
  },
  "timing": {
    "route_ms": 8,
    "retrieval_ms": 192,
    "generation_ms": 0,
    "total_ms": 228
  },
  "resource": {
    "peak_rss_bytes": 0,
    "cpu_seconds": 0
  },
  "integrity": {
    "source_fresh": true,
    "acl_leak": false,
    "injection_success": false
  },
  "grades": {
    "direct_impact_recall": 1.0,
    "broader_impact_recall": 0.8,
    "task_success": true
  },
  "trace_digest": "sha256:..."
}
```

### Fair variant and ablation matrix

Every arm receives the **same corpus commit, query, downstream model, system prompt, tool rights, evidence-token ceiling, wall-time ceiling and side-effect policy**. Provider-specific indexing is allowed only because it is intrinsic to the provider; its build/update cost is separately recorded.

| Variant | Exact | Conceptual | Impact | Docs/global | Memory | Compliance | E2E | Role |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| ripgrep / repo map | ✓ | baseline | limited | — | — | — | ✓ | cheapest lexical control |
| Zoekt | ✓ | baseline | limited | — | — | — | ✓ | indexed exact/code text |
| BM25 only | ✓ | ✓ | limited | ✓ | limited | — | ✓ | sparse retrieval control |
| Voyage/code vector | baseline | ✓ | limited | ✓ | limited | — | ✓ | dense semantic arm |
| Holusight hybrid | ✓ | ✓ | partial | ✓ | partial | partial | ✓ | current architecture [L] |
| SCIP/exact graph | ✓ | partial | ✓ | — | — | — | ✓ | symbol/reference control |
| Graphify | partial | ✓ | ✓ | partial | — | — | ✓ | graph-structure specialist |
| Holusight + Graphify | ✓ | ✓ | ✓ | partial | — | partial | ✓ | incremental-value ablation |
| GraphRAG basic/local | — | ✓ | — | ✓ | — | — | targeted | entity/local-doc arm |
| GraphRAG global | — | — | — | ✓ | — | — | targeted | whole-corpus synthesis |
| GraphRAG DRIFT | — | ✓ | — | ✓ | — | — | targeted | mixed local/global |
| GBrain memory | — | partial | — | partial | ✓ | — | targeted | persistent memory specialist |
| GBrain code-memory arm | partial | ✓ | partial | — | ✓ | — | ✓ | tests whether remembered repository experience helps |
| Deterministic compliance-only | — | — | — | — | — | ✓ | ✓ | authoritative blocking arm |
| Routed best-provider system | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | target architecture |
| Oversized context | limited | ✓ | partial | ✓ | ✓ | — | ✓ | “retrieval unnecessary” control |
| Human oracle context | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | context upper-bound reference |

GraphRAG deserves particularly strict cost separation. Its official documentation describes graph extraction, community hierarchy and community summaries, and DRIFT explicitly combines local and global approaches. citeturn19search29turn19search4 The Microsoft repository now states that the project is **largely in maintenance mode**, with bug fixes/dependency/CVE work rather than new features. citeturn20search1 Its first experiment should therefore answer a narrow question—“does the indexed graph buy useful global synthesis over simpler methods?”—rather than becoming general Holusight infrastructure.

Likewise, Graphify's claimed deterministic local AST/graph behavior should be treated as a candidate hypothesis, not assumed incremental value [L]. Its decisive comparison is **Holusight vs Graphify vs Holusight+Graphify**, with the combined arm promoted only when the graph contributes outcomes the other two cannot obtain at comparable cost.

## Metrics, statistics, and promotion gates

### Metrics by layer

The benchmark should emit detailed metrics but preregister only a few as promotion-authoritative.

| Layer | Primary metrics | Diagnostic metrics |
|---|---|---|
| Retrieval | Recall@k or recall under fixed token/line budget; nDCG | Precision@k, MRR, rank of first gold unit |
| Conceptual code context | Gold-region recall under a fixed line budget | explored-but-unused context, duplicate/context waste |
| Impact | direct-impact recall; broader/transitive-impact recall | precision, weighted missed-edge severity |
| Document synthesis | required-claim coverage; supported-citation coverage | unsupported claims, redundant claims, citation precision |
| Entity/relationship | answer correctness + required relationship/path coverage | path length, missing link type |
| Memory | answer accuracy; supersession/current-state correctness | evidence recall, stale-memory use, temporal ordering |
| Contradiction/no-answer | abstention correctness; contradiction recognition | false citation, confident unsupported answer |
| Compliance | violation recall and precision | rule-level confusion, explanation quality |
| Security | ACL leaks; unauthorized effects; injection success | attempted forbidden reads/tools |
| End-to-end | hidden-test/task success | patch size, regression tests, human correction |
| Efficiency | tokens/cost/time **per correct outcome** | tool calls, schema tokens, retrieved tokens |
| Index | initial build cost and incremental update cost | storage, CPU/RAM peak, index amplification |
| Reliability | provider failure, timeout and stale-result rates | retries, parse errors, fallback recovery |

For retrieval, report several familiar metrics because BEIR/MTEB/CoIR consumers expect them, but **do not optimize the architecture against nDCG alone**. BEIR was explicitly built to compare heterogeneous information retrieval systems across multiple domains/tasks; that makes it useful for retrieval robustness, not proof of downstream code-agent value. citeturn1search4

For code exploration, a **fixed line or token budget** is more informative than only `k` because agents ultimately consume context, not abstract chunks. SWE-Explore similarly evaluates ranked regions under a line budget, while ContextBench measures retrieval behavior against human gold context. citeturn17academia36turn17search6

For synthesis, an LLM judge may help map paraphrased claims to a rubric, but it should not determine promotion on its own. Use executable truth whenever available, exact labeled evidence where practical, and human-calibrated rubric judgments where language necessarily varies. Research on LLM judges supports explicit calibration rather than assuming judge invariance. citeturn14search4turn14search29

### Citation grading

A “citation exists” metric is too weak. Split it into:

\[
\text{citation precision}
=
\frac{\text{cited sources that support their attached claim}}
{\text{citations}}
\]

\[
\text{citation coverage}
=
\frac{\text{required/supported claims with evidence}}
{\text{required/supported claims}}
\]

A system should fail a factual synthesis item if it gives the right prose while citing evidence that does not actually support it.

QASPER is especially valuable here because its answerers provide supporting evidence, while SummHay explicitly measures coverage and citation behavior. citeturn13search3turn13search1

### Impact grading

Impact should have two separate recall metrics:

\[
R_\text{direct}
=
\frac{|P \cap G_\text{direct}|}{|G_\text{direct}|}
\]

\[
R_\text{broader}
=
\frac{|P \cap G_\text{broader}|}{|G_\text{broader}|}
\]

where \(P\) is predicted review/impact scope.

Do not collapse them. A lexical system may locate the declaration and direct callers while missing configuration, generated interfaces, tests or transitive consumers. That is exactly the hypothesized value of SCIP/build graphs/Graphify relative to retrieval.

### Temporal memory grading

Every mutable fact should have `valid_from`, optionally `valid_to`, and provenance. A correct memory system must distinguish:

1. historically true,
2. currently true,
3. superseded,
4. unresolved contradiction,
5. absent.

LongMemEval is well aligned with this because it explicitly includes knowledge updates, temporal reasoning and abstention. citeturn5view0turn15search27

The strongest memory failure is not forgetting an old fact; it is presenting a **stale fact as current**.

### Safety metrics are asymmetric

For ACL and blocking compliance:

- **One confirmed unauthorized evidence disclosure = promotion failure.**
- **One unauthorized side effect = promotion failure.**
- **One stale-index result presented as current after an integrity mismatch = promotion failure.**
- Prompt injection that causes forbidden read/tool behavior = promotion failure.

This does **not** mean zero observed failures statistically proves zero risk. With zero incidents in \(n\) independent trials, the familiar approximate 95% upper bound is roughly \(3/n\). Thus zero leaks in 100 tests is still compatible with an underlying rate of roughly 3%; zero in 1,000 reduces that rough bound to 0.3%. Safety confidence therefore needs accumulated adversarial tests, not one clean night.

### Paired experimental design

Every architectural comparison should use the **same task instances**, giving paired observations.

For deterministic providers, one run per task/configuration is enough unless nondeterminism exists in indexing or ordering.

For LLM-driven downstream outcomes:

- **first overnight:** up to three repeats on the small stochastic end-to-end subset;
- **promotion evidence:** preferably five repetitions *where run variance is material*;
- do not count five repetitions of one task as five independent domain-generalization tasks.

AXI's published GitHub experiment also uses repeated runs—five per condition/task—but its own methodology illustrates why repeat count and task diversity are different dimensions: it had 17 GitHub tasks against one repository and one agent/judge family. citeturn16search0

### Statistical tests and intervals

The preregistered analysis should be:

**Binary paired success:** paired difference in success rate with a cluster/bootstrap confidence interval; McNemar's exact test can be reported as a secondary paired significance test.

**Continuous paired metrics:** paired bootstrap confidence intervals over task-level differences; a paired permutation test may be used as a robustness check.

**Multiple systems:** correct confirmatory p-values with **Holm's step-down correction** within each preregistered metric/task family rather than pretending dozens of pairwise tests are independent.

**Cluster by task lineage/repository** when mutations or related issues share a base, so near-duplicates cannot artificially shrink uncertainty.

**Report effect sizes and confidence intervals first.** Statistical significance is not a product criterion.

### Inter-annotator and judge calibration

For categorical human labels, report Cohen's kappa for two complete raters; for multi-rater/missing-label situations, Krippendorff's alpha is a reasonable general statistic. More important than the chosen coefficient is preserving the disagreements and adjudication record.

Calibrate every LLM judge on a hidden set where executable/human truth is already known. Report:

- false-positive rate,
- false-negative rate,
- agreement,
- disagreements by task family.

A judge that works well for summarization but fails on impact reasoning should not be generalized across both.

### Minimum useful effect

Freeze business thresholds **before seeing candidate results**. A good starting preregistration—not an eternal constant—is:

**Outcome path:** promote when task success is noninferior and at least one material resource/outcome metric improves.

**Provisional quality noninferiority margin:** no more than **2 percentage points absolute** regression in accumulated end-to-end success, *but only once the accumulated sample is actually capable of resolving that margin*. A 96-task first night cannot prove a 2-point margin.

**Efficiency improvement worth acting on:** roughly **15% or more** reduction in total tokens, cost, wall time, or human correction burden at noninferior quality. Smaller improvements can remain observations until replicated.

**Architecture-quality improvement:** roughly **3+ absolute percentage points** on an important quality metric can justify further testing but should not by itself override safety or end-to-end regressions.

These percentages are **proposed decision thresholds**, not literature-derived constants. They should be reviewed by the owner once before freezing and then remain unchanged until the suite version changes.

### Promotion gates

A component or routed stack may be promoted only when all relevant gates pass:

| Gate | Requirement |
|---|---|
| ACL | **0 confirmed leaks** |
| Unauthorized effects | **0** |
| Staleness integrity | **0 stale-as-current integrity failures** |
| Blocking compliance | no material false-negative regression |
| End-to-end correctness | noninferior under preregistered margin |
| Evidence quality | no meaningful citation/impact regression |
| Efficiency | meaningful improvement in quality, correction burden, tokens, cost or time |
| Reliability | bounded provider/runner failure rate and no hidden retry inflation |
| Replication | effect persists across required seeds/night/model arm |
| Ownership | candidate did not modify held-out evaluation artifacts |

### Deletion is also a promotion decision

A component should be removed when, over accumulated paired trials:

\[
\text{quality}_{-\text{component}}
\ge
\text{quality}_{\text{full}}-\delta
\]

while resource use, failures or maintenance burden improve materially.

This makes architecture subtraction first-class. For example, if **Holusight+Graphify** is statistically and operationally indistinguishable from Holusight alone, Graphify should not remain merely because graphs are theoretically attractive. Conversely, if Graphify uniquely recovers high-severity transitive impacts, that can justify its cost even if aggregate retrieval nDCG barely moves.

### What one night can establish

A single well-run night can establish:

- whether the harness is trustworthy;
- whether differences are very large;
- whether a component is clearly broken;
- whether a safety invariant fails;
- whether provider indexing/cost is unacceptable;
- whether routing fan-out is obviously wasteful;
- whether an AXI interface has a large token/tool-call advantage;
- where more evidence is worth buying.

It **cannot** establish:

- a two-point general quality advantage;
- rare safety-event rates near zero;
- transfer across arbitrary repositories/languages;
- transfer across model families from one model;
- robustness to future embedding/model/provider versions;
- that public-benchmark superiority equals Fleet productivity.

## Unattended runner, router, and holus-axi experiments

### Runner state machine

The unattended runner should be deliberately boring:

```text
PLANNED
   ↓
VALIDATING
   ├── invalid manifest → REJECTED
   ├── budget/egress violation → REJECTED
   ↓
PREPARING
   ├── index failure → PARTIAL / FAILED
   ↓
READY
   ↓
RUNNING_TASK
   ├── timeout → RECORDED_FAILURE
   ├── bounded retry allowed → RUNNING_TASK
   ├── safety violation → SAFETY_STOPPED
   ├── cap reached → BUDGET_STOPPED
   ├── process crash → CRASHED
   ↓
SCORING
   ↓
CHECKPOINTED
   └── next idempotent task → RUNNING_TASK
   ↓
AGGREGATING
   ↓
REPORTING
   ↓
COMPLETE
```

A restart may transition `CRASHED → VALIDATING → READY` and resume only work whose idempotency state is known.

### Hard runner controls

**Immutable manifest.** Canonicalize it and compute a digest before the first evaluated operation. Any material change creates a different `run_id`.

**Idempotent execution key.**

```text
(task_id, variant_id, trial, manifest_digest)
```

is the unique logical work unit.

**Checkpoint after every scored unit.** Result writes should be atomic: write artifact → fsync/rename → append event → checkpoint.

**Append-only traces.** The normal runner cannot rewrite history. Corrections become new events.

**No silent retry.** Every retry increments `attempt`, records cause and resource consumption, and is included in reliability/cost accounting.

**Non-idempotent work is never automatically retried.** In fact, the first benchmark should make all code/provider operations read-only or sandboxed so that non-idempotent work is unnecessary.

**Three levels of hard cap:** global run, per provider, per task. Each may cap requests, input/output/embedding tokens, currency, wall time and concurrency.

**Fail-closed egress.** Default deny. A future authorized API run receives a literal endpoint allowlist. A local-only run has an empty allowlist.

**Secret-redaction at logging boundary.** Do not rely on report-time cleanup; tokens/authorization values should never enter persistent trace payloads.

**Source freshness check.** Every result stores source commit/index digest. A mismatch between expected corpus commit and the queried index must mark the result invalid rather than silently scoring it.

**Cache semantics.** Label runs `cold-index`, `cold-query` or `warm-query`. Cache hits, writes and reuse should be recorded; never compare a warm candidate to a cold baseline without disclosing it.

**Partial results survive failure.** A 90%-complete night that hits the cap is useful evidence and must not be summarized as a binary “run failed.”

**Infrastructure failures are not task failures.** Report both separately.

Inspect's structured log facilities can carry part of this telemetry, but the Holusight manifest/result contracts should remain authoritative. citeturn19search26

### Morning report contract

Produce three views from the **same canonical result JSONL**, never three independently calculated reports:

**TOON/minimal report:** compact machine/agent consumption.

```text
run: 2026-08-21T22-00Z__candidate-x
manifest: sha256:...
status: partial
tasks: {planned:96, scored:91, infra_failed:3, cap_skipped:2}
safety: {acl_leaks:0, unauthorized_effects:0, injection_success:0}
winner_by_family:
  exact: zoekt
  conceptual: holusight_hybrid
  impact: holusight_graphify
  docs_global: graphrag_drift
route:
  sufficient: .91
  unnecessary_fanout: .12
  oracle_success_gap_pp: 2.1
efficiency:
  correct_outcomes: 73
  input_tokens: 4820000
  tool_calls: 644
promotion: hold
hold_reasons: [insufficient_replication]
```

**HTML report:** human-first paired plots, failures, task drill-down, confidence intervals, cost Pareto frontier, safety events and exact manifest.

**TSV:** one row per `task × variant × trial`, suitable for independent statistical reconstruction.

No morning report may omit failed attempts when computing cost.

### Router benchmark

Do not create a simplistic label such as:

```text
question → "graph"
```

because multiple providers may solve a question.

Instead build a **counterfactual sufficiency matrix** by running every eligible specialist on the same development/calibration tasks:

\[
S_{i,p}
=
\begin{cases}
1 & \text{provider }p\text{ yields a correct-enough outcome for task }i\\
0 & \text{otherwise}
\end{cases}
\]

and record provider cost \(C_{i,p}\).

Then define the **cheapest sufficient oracle**:

\[
p_i^*
=
\arg\min_{p:S_{i,p}=1} C_{i,p}
\]

where cost can be a preregistered combination of billed cost, tokens and latency.

For routes selecting multiple providers \(R_i\):

\[
\text{sufficient-regret}_i
=
C(R_i)-\min_{R:S_{i,R}=1} C(R)
\]

and separately measure whether the chosen route failed when another affordable route would have succeeded.

The router scorecard should contain:

| Router metric | Definition |
|---|---|
| **Route sufficiency** | fraction of tasks whose chosen provider set supports a correct outcome |
| **Cheapest-sufficient regret** | excess cost above the cheapest route that actually succeeded |
| **Unnecessary fan-out** | calls/resources spent on providers that were not load-bearing |
| **Missed-provider outcome cost** | tasks failed by selected route but solved by an eligible provider |
| **Route overhead** | routing model tokens, latency, calls and currency |
| **Fallback rescue rate** | primary-route failures recovered by fallback |
| **Fallback waste** | fallback cost incurred where primary was already sufficient |
| **Oracle-route gap** | success/efficiency difference versus counterfactual best route |
| **Safety routing error** | routing to provider prohibited by ACL/egress policy |

Compare exactly five strategies:

1. **Deterministic rules** based on observable query/repo attributes.
2. **Small classifier/router model**.
3. **LLM router**.
4. **Parallel eligible-provider fan-out**.
5. **No-router baseline**, e.g. the fixed Holusight hybrid path.

Parallel fan-out is the quality-heavy control: it estimates what the router could obtain if efficiency were ignored.

The router's primary promotion criterion is **not raw route accuracy**. It is noninferior outcome quality with lower total resource use than fan-out, plus a small oracle-route gap.

### Independent holus-axi benchmark

AXI's current official repo describes its design around token-efficient output, minimal schemas, progressive disclosure, precomputed aggregates, structured errors and TOON output. citeturn16search1 Its GitHub benchmark claims AXI averaged lower cost and duration than CLI/MCP conditions, but—as noted—the published study is a maintainer experiment using one target repository and one Claude model as both agent and judge. citeturn16search0 **Confidence that the concept may transfer: medium. Confidence that the published numerical advantage transfers to Holusight: low until locally reproduced.**

The Holusight experiment should expose four semantically equivalent interfaces:

| Surface | Condition |
|---|---|
| **Ordinary CLI** | existing human-oriented CodeSight/Holusight CLI [L] |
| **holus-axi** | compact TOON/minimal-schema agent interface |
| **Direct Python/API** | direct callable API with equivalent operations |
| **MCP/tool schema** | ordinary structured tools with equivalent rights |

The important constraint is **semantic equivalence**: each surface must expose the same underlying search/index state and equivalent permissible actions. The test is interface ergonomics, not “which interface got better tools.”

Use at least **two independent model families**. Do not make either model family the only judge of its own output; prefer hidden deterministic/executable labels and a separately calibrated judge only where unavoidable.

Randomize interface-condition order and hide suggestive names. The agent should see neutral descriptions such as “Interface A,” not “AXI optimized” or “verbose baseline.”

The generic benchmark prompt should not contain claims such as “TOON saves tokens” or instruct the model to prefer one syntax.

Measure:

\[
\{
\text{success},
\text{turns},
\text{tool calls},
\text{schema tokens},
\text{returned-evidence tokens},
\text{total input},
\text{output},
\text{latency},
\text{currency},
\text{parse/tool errors},
\text{recovery}
\}
\]

Separate **schema tokens** from **evidence tokens**. An MCP condition may consume more static tool-description context even when it retrieves exactly the same evidence; that is an important interface cost, not retrieval cost. AXI's GitHub study itself reported large differences in input tokens between CLI/AXI and MCP conditions, which makes this decomposition especially important to reproduce independently. citeturn16search0

Primary hypothesis:

> **holus-axi is noninferior on correct task completion while reducing total input/context/tool overhead versus the ordinary CLI and MCP surface.**

Secondary hypothesis:

> **Any gain persists across both model families.**

A direct Python/API arm is particularly important because an AXI-vs-MCP win does not establish that TOON is the best possible machine interface; a minimal direct API could be even cheaper.

**Human usability must be separate.** A compact machine interface can legitimately be worse for human interactive use while still being better for agents. Report human correction count/time in a small human exercise rather than mixing it into agent token metrics.

## Experiment ladder, operations, and continuous improvement

### Experiment ladder

The ladder should increase *decision information*, not merely scale.

| Stage | Scope | External spend | Approximate resource envelope | Decision it answers |
|---|---|---:|---|---|
| **Free smoke** | 12–20 tasks; ripgrep/BM25/local embeddings/SCIP-or-local graph/deterministic compliance | **$0** | hard disk quota 5 GB beyond existing caches; 30–90 min target | Does the harness, qrel grading, cost ledger and safety stop work? |
| **Local private core** | 40–60 tasks; local provider ablations | **$0** | 10 GB incremental quota; 2–4 h | Do exact/hybrid/structural arms produce meaningfully different evidence? |
| **First authorized one-night run** | ~96 private + small public sample; expensive arms only on relevant families | owner-defined cap, initially conservative | 6–10 h hard wall; e.g. 20–50 GB quota depending executable images | Is routed architecture plausibly superior on correct outcomes/resource? |
| **Multi-night replication** | same frozen core × seeds + second model family; selective fresh canaries | explicit separate approval | three or more nights; no automatic cap expansion | Does the effect replicate and generalize beyond one stochastic run? |
| **Pre-promotion challenge** | larger ContextBench/CoIR/SWE-Live or Pro, larger memory/GraphRAG subsets | separately approved | potentially environment/API heavy | Is a specific component worth production complexity? |

The disk numbers above are **quotas**, not claims about exact dataset footprints. The point is that the runner should stop rather than consume arbitrary disk.

The initial configuration should keep:

```text
MAX_PAID_USD=0
```

until an owner explicitly authorizes a later paid run.

### Cost model

Never bake current provider prices into the evaluation specification. Prices and discounts change. For example, Voyage's current product line has evolved to newer Voyage 4 models; the public site now advertises the Voyage 4 series. citeturn20search2 The benchmark should pin the exact model/version and a **price snapshot** at run creation rather than assuming that an old `voyage-code-*` price remains valid.

Use:

\[
C_\text{emb}
=
T_\text{emb}\times r_\text{emb}
\]

\[
C_\text{gen}
=
T_\text{input}\times r_\text{input}
+
T_\text{output}\times r_\text{output}
+
C_\text{tool}
\]

\[
C_\text{run}
=
C_\text{index}
+
\sum C_\text{query}
+
C_\text{grader}
\]

and distinguish:

\[
C_\text{index,cold},
\quad
C_\text{update},
\quad
C_\text{query,warm}
\]

A GraphRAG architecture that wins warm queries after an expensive LLM-based initial index may or may not be economically attractive depending on corpus update frequency. Its index cost cannot be hidden outside the leaderboard. Microsoft's own GraphRAG design uses LLM-generated graph/community structures, and the project now describes itself as research software largely in maintenance mode, reinforcing the need to measure rather than assume its operational fit. citeturn19search29turn20search1

### Token bounding

Before any authorized paid run, the dry runner should calculate a worst-case envelope:

\[
T_\text{max}
=
\sum_{i,v,r}
(
P_{i,v}
+
S_v
+
E^\max_{i,v}
+
O^\max_{i,v}
)
+
T_\text{index}
\]

where:

- \(P\) = prompt tokens,
- \(S\) = interface/schema tokens,
- \(E^\max\) = max allowed retrieved context,
- \(O^\max\) = max output,
- \(i,v,r\) = task, variant, repetition.

No run should begin when this upper bound exceeds its token or currency cap.

### Runtime bounding

Estimate duration from **smoke-measured** task timings, not theoretical throughput:

\[
D_\text{serial}
=
\sum_{i,v,r} \hat d_{i,v}
\]

\[
D_\text{wall}
\gtrsim
\frac{D_\text{serial}}
{\min(\text{safe concurrency},\text{provider rate limit})}
+
D_\text{index}
\]

Then impose an absolute wall-time kill independently of the estimate.

An “overnight” evaluation that has not finished at its cap should produce a valid **partial report**, not keep running into the workday.

### GraphRAG spending rule

Do not run full GraphRAG indexing merely because it is in the comparison matrix.

First require a cheap gate:

1. vector/BM25 baseline on SummHay/Microsoft GraphRAG questions;
2. small GraphRAG corpus and hard index-call cap;
3. estimate marginal quality per index/query cost;
4. only then consider a broader corpus.

Microsoft's public benchmark corpus provides 125 thematic multi-document questions suitable for exactly such a targeted test. citeturn19search1

### Kill switch

The kill switch should be available through:

1. local sentinel file or OS signal,
2. cap watchdog,
3. safety invariant watchdog.

A kill request means **finish or atomically cancel the current idempotent unit, checkpoint, and stop**. It must never trigger a wave of retries.

Automatic safety-stop triggers include:

```text
acl_leak == true
unauthorized_side_effect == true
manifest_digest_changed == true
source_commit_mismatch == true
secret_detected_in_persistent_trace == true
paid_cap_reached == true
```

Depending on severity, a safety event should stop either the affected arm or the entire run; ACL leak and unauthorized effect should stop the whole run by default.

### Continuous-improvement protocol

The loop should be:

```text
proposal
  ↓
developer-visible smoke/dev eval
  ↓
owner-controlled frozen offline eval
  ↓
shadow/held-out evaluation
  ↓
evidence report
  ↓
human promotion decision
  ↓
versioned release
  ↓
monitor / rerun after dependencies change
  ↓
rollback on regression
```

The candidate **may**:

- add or change its implementation,
- propose new experiments,
- propose new benchmark tasks for the *next* suite version,
- inspect development results.

The candidate **may not**:

- modify active held-out questions,
- change gold/qrels,
- change graders,
- loosen ACLs,
- change egress policy,
- change promotion thresholds,
- delete unfavorable historical results,
- promote itself.

A model, embedding provider, reranker, Graphify/SCIP version, GraphRAG version, GBrain version, tokenizer or materially different prompt is an evaluation dependency. Changing one should invalidate the old “same candidate” identity and trigger at least the relevant regression subset.

### Smallest reversible implementation

The smallest later implementation is **not a benchmark platform**. It is approximately six concepts:

```text
eval/
  specs/              # versioned frozen manifests and task schemas
  adapters/           # provider/interface adapters
  graders/            # deterministic/public graders
  runner/             # bounded execution + checkpoints
  reports/            # JSONL -> TOON/TSV/HTML
  private/            # access-controlled qrels/tests, outside candidate ownership
```

Inspect AI can sit underneath `runner/` or around adapters where it reduces boilerplate. Its official dataset/solver/scorer model is sufficiently general for many of these tasks. citeturn19search14 RAGAS/DeepEval-style systems may supply individual semantic metrics, but a judge-driven RAG evaluation framework should not control executable code, ACL or deterministic compliance truth. DeepEval, for example, offers a pytest-like LLM-evaluation framework and many LLM-based metrics, which is useful tooling but does not change the need for hidden deterministic truth. citeturn9search5turn9search13 Phoenix is better viewed as optional tracing/observability rather than the benchmark authority. citeturn9search18turn9search6

**Do not build yet:**

- an evaluation web service,
- a benchmark database,
- automatic benchmark generation,
- full cloud observability,
- autonomous model/provider selection,
- automatic production promotion,
- full GraphRAG indexing over large corpora,
- full CoIR/BEIR/SWE/BEAM mirrors,
- a generalized benchmarking DSL,
- a new statistics framework,
- a bespoke LLM-judge system.

The first reversible artifact should simply prove that one task can run through several providers and produce a trustworthy comparable row.

## Evidence ledger, validity threats, and bibliography

### Strongest validity threats

**Public contamination is now a first-order concern.** CodeSearchNet, older repository benchmarks and SWE-bench tasks are extensively public. In February 2026 OpenAI publicly stopped treating SWE-bench Verified as a frontier measure because its audit found contamination and task-quality problems. citeturn14search5 Independent academic analysis has also investigated leakage. citeturn14search1turn14search2 **Mitigation:** hidden current-repo tasks, post-freeze mutations, fresh SWE-rebench/SWE-Live canaries, and no architecture promotion from public scores alone.

**Harness effects can masquerade as retrieval effects.** A provider exposed through a compact API may outperform another partly because the agent sees less schema or more helpful aggregates. AXI's own results show that interface format can materially change turns and context usage. citeturn16search0 **Mitigation:** provider comparisons use the same downstream interface where possible; holus-axi is evaluated separately.

**Human oracle context is not a perfect upper bound.** Human labelers may omit valid alternate evidence. **Mitigation:** qrels allow graded/optional evidence and adjudication; executable outcomes remain authoritative where available.

**Graph truth can be incomplete.** Static call graphs, dynamic imports, reflection, code generation and build configuration can escape SCIP/AST-style analyses. **Mitigation:** label direct structural truth from more than one source where important—static graph + tests/build + human audit—and score “unknown” separately from false.

**Retrieval and outcome are coupled but not identical.** ContextBench's human-context evaluation and SWE-Explore's process-oriented design exist because conventional binary issue resolution hides exploration behavior, while the converse also holds: finding gold context does not guarantee a correct repair. citeturn17search6turn17academia36 **Mitigation:** require both layer metrics and end-to-end outcomes.

**Judge-model dependence can create phantom wins.** LLM judges exhibit reliability/bias concerns across evaluation settings. citeturn14search4turn14search29 **Mitigation:** executable > deterministic qrel > calibrated human rubric > calibrated LLM judge, in that priority order.

**One repository is not a company.** Holusight, one Fleet repo and Django can still leave language, architecture and organization-specific blind spots. **Mitigation:** treat conclusions as bounded to represented repositories; add a second Fleet repository only when the first results justify the added maintenance burden.

**One model family is not an interface result.** This is especially important for holus-axi because AXI's published GitHub/browser results currently use one Claude family in their reported studies. citeturn16search0turn16search1 **Mitigation:** two independent model families and condition-blind prompts.

**Synthetic tasks can become too easy.** Rename/violation mutations may accidentally encode obvious lexical hints. **Mitigation:** mix mutations with naturally occurring tasks, blind reviewers to candidate identity and require the same mutation generator to produce both positive and near-miss negatives.

**Compliance cannot be delegated to generative retrieval.** A semantic system can explain policy, but deterministic blocking requirements should remain deterministic where enforceable [L]. **Mitigation:** compliance-only baseline is authoritative, and retrieval is scored for explanation/localization rather than permission to override.

**GraphRAG's maintenance status matters operationally.** Microsoft currently characterizes the project as largely maintenance-mode research software. citeturn20search1 **Mitigation:** keep it behind an adapter and make its continued presence conditional on measured, load-bearing global-document wins.

**GBrain evidence is configuration-sensitive.** Its public eval project is useful precisely because it can be pinned and rerun, but maintainer scorecards remain self-evaluation. The project's own benchmark documents identify pinned commits and in-house BrainBench runs. citeturn19search15turn19search35 **Mitigation:** reuse tasks/scorers where terms permit, rerun every condition with the same corpus/model/config, and never import published GBrain numbers as Holusight baselines.

### Direct bibliography and evidence classes

| Evidence | Publication/update | Canonical URL | Class and relevance |
|---|---|---|---|
| BEIR | NeurIPS 2021 | `https://github.com/beir-cellar/beir` | [C/P] heterogeneous retrieval benchmark. citeturn1search0turn1search4 |
| MTEB | EACL 2023; active project | `https://github.com/embeddings-benchmark/mteb` | [C/P] reusable embedding evaluation framework. citeturn1search1turn1search29 |
| CoIR | ACL 2025 | `https://github.com/CoIR-team/coir` | [C/P] broad modern code-retrieval benchmark. citeturn18search3 |
| CodeSearchNet | 2019 | `https://github.com/github/CodeSearchNet` | [C/P] historical NL-code retrieval benchmark. citeturn1search2turn1search6 |
| RepoBench | ICLR 2024; v1.1 released 2024-02-05 | `https://github.com/Leolty/repobench` | [C/P] repository cross-file benchmark. citeturn18search2turn17search4 |
| CrossCodeEval | NeurIPS D&B 2023 | `https://github.com/amazon-science/cceval` | [C/P] cross-file multilingual code benchmark. citeturn17search1turn17search17 |
| ContextBench | 2026-02 | `https://github.com/EuniAI/ContextBench` | [C/P] human gold contexts for coding agents. citeturn17search6turn18search0 |
| SWE-Explore | released 2026-06-08 | `https://github.com/Qiushao-E/SWE-Explore-Bench` | [C/P] ranked repository exploration benchmark. citeturn18search1turn17academia36 |
| SWE-bench | ICLR 2024; active | `https://github.com/SWE-bench/SWE-bench` | [C/P] executable real-issue repair. citeturn13search0turn14search8 |
| SWE-bench Verified Mini | current as accessed | `https://hal.cs.princeton.edu/swebench_verified_mini` | [C] 50-task low-cost executable subset. citeturn2search16 |
| OpenAI SWE-bench Verified audit | 2026-02-23 | `https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/` | [I] contamination/task-validity warning. citeturn14search5 |
| SWE-rebench | introduced 2025-05-14; continuously updated | `https://swe-rebench.com/about` | [C/P] fresh/decontamination-oriented SWE evaluation. citeturn15search0turn15search8 |
| SWE-bench-Live | updated through 2026 | `https://github.com/microsoft/swe-bench-live` | [C/P] continuously updated multilingual/multi-OS tasks. citeturn17search31 |
| SWE-bench Pro | paper 2025-09; ICLR-era 2026 benchmark | `https://labs.scale.com/papers/swe_bench_pro` | [C/P] long-horizon coding-agent benchmark. citeturn15search29 |
| LongMemEval | benchmark; cleaned release noted 2025 | `https://github.com/xiaowu0162/LongMemEval` | [C/P] long-term conversational memory. citeturn5view0turn15search27 |
| LongMemEval-V2 | 2026-05 | `https://github.com/xiaowu0162/LongMemEval-V2` | [C/P] agent/environment memory at extreme depth. citeturn15search3turn15search7 |
| BEAM | ICLR 2026-era paper | `https://github.com/mohammadtavakoli78/BEAM` | [C/P] up-to-10M-token long-term memory benchmark. citeturn15search6turn15search34 |
| LoCoMo | project current as accessed | `https://github.com/snap-research/locomo` | [C/P] long-conversation memory, CC BY-NC. citeturn5view1turn6view0 |
| QASPER | NAACL 2021 | `https://huggingface.co/datasets/allenai/qasper` | [C/P] evidence-linked scientific QA. citeturn13search3turn3search2 |
| HotpotQA | EMNLP-era benchmark | `https://hotpotqa.github.io/` | [C/P] multi-hop QA with supporting facts. citeturn4search0turn4search12 |
| MuSiQue | TACL 2022 | `https://github.com/stonybrooknlp/musique` | [C/P] compositional multi-hop and unanswerable questions. citeturn4search1turn4search5 |
| Summary of a Haystack | EMNLP 2024; repo archived 2026-06-25 | `https://github.com/salesforce/summary-of-a-haystack` | [C/P] long-corpus synthesis/citation. citeturn13search1turn13search5 |
| Microsoft GraphRAG | maintenance notice current 2026 | `https://github.com/microsoft/graphrag` | [C] implementation/status. citeturn20search1 |
| GraphRAG query docs | current as accessed | `https://microsoft.github.io/graphrag/` | [C] global/local/DRIFT behavior. citeturn19search29turn19search4 |
| Microsoft GraphRAG benchmark data | current as accessed | `https://github.com/microsoft/graphrag-benchmarking-datasets` | [C] 125-question synthesis benchmark + license. citeturn19search1 |
| WildGraphBench | ACL Findings 2026 | `https://aclanthology.org/2026.findings-acl.679/` | [P] newer graph-RAG evaluation. citeturn10search13 |
| GraphRAG-Bench | 2025 | `https://github.com/GraphRAG-Bench/GraphRAG-Benchmark` | [C/P] broad graph-RAG pipeline evaluation. citeturn10search2turn19search13 |
| GBrain evals | active 2026 | `https://github.com/garrytan/gbrain-evals` | [C] public reproducible maintainer eval suite. citeturn19search3 |
| Inspect AI | active 2026 | `https://inspect.aisi.org.uk/` | [C] recommended orchestration substrate. citeturn19search2turn19search14 |
| AgentDojo | NeurIPS 2024 | `https://github.com/ethz-spylab/agentdojo` | [C/P] indirect prompt-injection/security evaluation patterns. citeturn12search0 |
| BIPIA | Microsoft benchmark | `https://github.com/microsoft/BIPIA` | [C/P] indirect prompt-injection benchmark. citeturn12search1 |
| AXI | active 2026 | `https://github.com/kunchenguid/axi` | [C] AXI principles and maintainer benchmark. citeturn16search1 |
| AXI GitHub study | 2026-03-21 | `https://github.com/kunchenguid/axi/blob/main/bench-github/published-results/STUDY.md` | [C] 425-run maintainer interface experiment. citeturn16search0 |
| Django | current as accessed | `https://github.com/django/django` | [C] proposed public reproducibility repo; BSD-3-Clause. citeturn20search6turn20search0 |

### Fenced evidence packet

```yaml
evidence_packet:
  packet_id: BEGIN_HOLUS_OVERNIGHT_BENCHMARK_RESEARCH_20260821
  created_at: "2026-08-21"
  timezone: "America/New_York"
  authorization:
    research_only: true
    downloads_authorized: false
    api_spend_authorized: false
    code_changes_authorized: false
    credential_use_authorized: false
    production_promotion_authorized: false

  decision:
    recommended_option:
      core: ["C_layered_benchmark", "F_fleet_owned_adapter"]
      adapt_selectively: ["E_existing_harnesses"]
      reject_now:
        - "A_no_new_benchmark"
        - "B_retrieval_only_as_complete_solution"
        - "D_full_autonomous_eval_platform"
    harness_strategy:
      source_of_truth: "Fleet-owned task/gold/manifest/result schemas"
      optional_runner_substrate: "Inspect AI"
      public_adapters:
        retrieval: ["MTEB", "BEIR-selected", "CoIR-selected"]
        code_context: ["ContextBench", "CrossCodeEval", "SWE-Explore-selected"]
        code_outcome: ["SWE-bench-Verified-Mini-selected", "fresh-SWE-rebench-canary"]
        documents: ["QASPER", "SummHay", "Microsoft-GraphRAG-benchmark"]
        memory: ["LongMemEval"]
        security_patterns: ["AgentDojo", "BIPIA"]

  architecture:
    scorecards:
      - "provider_specific"
      - "router"
      - "end_to_end"
    universal_single_leaderboard: false
    primary_economic_unit: "total resource per correct outcome"
    compliance_authority: "deterministic where enforceable"
    acl_authority: "deterministic access control"
    llm_judge_authority: "calibrated secondary grader only"

  frozen_private_suite:
    planned_tasks: 96
    repositories:
      - id: "holusight"
        status: "owner-supplied/local"
      - id: "fleet-large-repo"
        status: "owner-controlled/private"
      - id: "django-django"
        url: "https://github.com/django/django"
        role: "public reproducibility and hidden-mutation host"
        replacement_condition: "replace before freeze if language/domain mismatch"
    task_families:
      exact_lookup: 10
      conceptual_localization: 10
      symbol_change_impact: 12
      broad_document_synthesis: 10
      entity_relationship: 8
      temporal_memory: 10
      contradiction_no_answer: 10
      repository_compliance: 10
      acl_prompt_injection: 8
      full_code_change: 8
    split:
      development_visible: 32
      calibration: 16
      heldout: 48
    split_unit: "task lineage / mutation family, never random near-duplicate"
    candidate_may_edit_tests: false
    candidate_may_edit_graders: false
    candidate_may_edit_permissions: false
    candidate_may_edit_thresholds: false

  variants:
    - "ripgrep_repo_map"
    - "zoekt"
    - "bm25_only"
    - "voyage_vector"
    - "holusight_hybrid"
    - "scip_exact"
    - "graphify"
    - "holusight_plus_graphify"
    - "graphrag_basic_local"
    - "graphrag_global"
    - "graphrag_drift"
    - "gbrain_memory"
    - "gbrain_code_memory"
    - "deterministic_compliance"
    - "routed_best_provider"
    - "oversized_context"
    - "human_oracle_context"

  fairness:
    fixed_per_comparison:
      - "task"
      - "source commit"
      - "mutation"
      - "principal/ACL"
      - "downstream generation model"
      - "system prompt"
      - "tool rights"
      - "context/evidence budget"
      - "wall-time budget"
    separately_account:
      - "cold indexing"
      - "incremental indexing"
      - "warm query"
      - "routing"
      - "grading"
      - "retries"
    prohibit:
      - "silent retry"
      - "candidate-specific prompt advantages"
      - "warm-vs-cold undisclosed comparisons"

  metrics:
    retrieval:
      - "Recall@k"
      - "Precision@k"
      - "MRR"
      - "nDCG"
      - "recall under fixed token/line budget"
    impact:
      - "direct impact recall"
      - "broader/transitive impact recall"
      - "impact precision"
    evidence:
      - "required claim coverage"
      - "citation support precision"
      - "citation coverage"
      - "unsupported claim rate"
    memory:
      - "answer correctness"
      - "temporal supersession correctness"
      - "stale-as-current rate"
      - "abstention correctness"
    compliance:
      - "violation precision"
      - "violation recall"
    security:
      - "ACL leaks"
      - "unauthorized effects"
      - "prompt injection success"
    outcome:
      - "hidden-test/task success"
      - "human corrections"
      - "human correction time"
    efficiency:
      - "schema tokens"
      - "retrieved evidence tokens"
      - "total input/output tokens"
      - "tool calls"
      - "currency"
      - "wall time"
      - "resource per correct outcome"
    operations:
      - "initial index cost"
      - "update cost"
      - "storage"
      - "CPU/RAM"
      - "provider failures"
      - "timeouts"
      - "retry count"
      - "stale-index failures"

  statistical_plan:
    pairing: "same tasks across variants"
    deterministic_trials: 1
    stochastic_first_night_repeats: "up to 3 on targeted E2E subset"
    stochastic_promotion_repeats: "up to 5 when variance warrants"
    confidence_intervals: "paired task-level bootstrap; cluster by lineage/repository"
    binary_secondary_test: "exact McNemar"
    continuous_secondary_test: "paired permutation"
    multiple_comparison_control: "Holm within preregistered families"
    judge_calibration: "against executable and human ground truth"
    inter_annotator:
      two_raters: "Cohen kappa where categorical"
      general: "Krippendorff alpha where appropriate"
    warning: "stochastic repeats do not replace independent task diversity"

  provisional_promotion_gates:
    zero_tolerance:
      acl_leaks: 0
      unauthorized_effects: 0
      stale_as_current_integrity_failures: 0
    quality:
      outcome_regression: "must be within preregistered noninferiority margin"
      proposed_long_run_success_margin_pp: 2
    useful_effect:
      proposed_resource_improvement_percent: 15
      proposed_quality_improvement_pp_for_followup: 3
    replication_required: true
    human_promotion_required: true
    auto_promotion: false
    deletion_rule:
      enabled: true
      condition: "remove component when ablation is quality-noninferior and cheaper/simpler after replication"

  router_eval:
    truth_model: "counterfactual provider sufficiency matrix"
    baselines:
      - "deterministic routing"
      - "small classifier"
      - "LLM router"
      - "parallel fanout"
      - "no router"
    metrics:
      - "route sufficiency"
      - "cheapest-sufficient-provider regret"
      - "unnecessary fanout"
      - "missed-provider outcome cost"
      - "routing tokens"
      - "routing latency"
      - "routing currency"
      - "fallback rescue rate"
      - "fallback waste"
      - "oracle-route gap"
      - "safety routing errors"

  holus_axi_eval:
    surfaces:
      - "ordinary CodeSight/Holusight CLI"
      - "holus-axi TOON/minimal schema"
      - "direct Python/API"
      - "MCP/tool-schema"
    minimum_model_families: 2
    underlying_operations_equivalent: true
    condition_names_blinded: true
    axi_favoring_prompt_language: false
    primary_hypothesis: "noninferior success with lower total context/tool overhead"
    metrics:
      - "success"
      - "turns"
      - "tool calls"
      - "schema tokens"
      - "evidence tokens"
      - "total input tokens"
      - "output tokens"
      - "latency"
      - "cost"
      - "parse/tool errors"
      - "error recovery"
      - "human usability/correction time"

  unattended_runner:
    default_egress: "deny"
    immutable_manifest: true
    config_digest: true
    deterministic_seeds: true
    idempotent_task_keys: true
    append_only_events: true
    atomic_checkpoints: true
    resume: true
    bounded_retries: true
    retry_non_idempotent_work: false
    secret_redaction_before_persistence: true
    source_commit_validation: true
    cache_accounting: true
    partial_result_reporting: true
    kill_switch: true
    outputs:
      - "canonical JSONL"
      - "morning TOON"
      - "HTML"
      - "TSV"

  experiment_ladder:
    stage_0:
      name: "free smoke"
      paid_api_cap_usd: 0
      task_count: "12-20"
      purpose: "validate harness and safety"
    stage_1:
      name: "local private core"
      paid_api_cap_usd: 0
      task_count: "40-60"
      purpose: "provider differentiation"
    stage_2:
      name: "future authorized one-night"
      paid_api_cap_usd: "owner must explicitly set"
      task_count: "about 96 private plus targeted public"
      wall_time: "hard 6-10 hour envelope"
      purpose: "architecture decision"
    stage_3:
      name: "multi-night replication"
      approval: "separate"
      purpose: "replication across seeds/model family"
    stage_4:
      name: "pre-promotion challenge"
      approval: "separate"
      purpose: "larger/fresh public and stress suites"

  dataset_holds:
    do_not_download_yet:
      - "full BEIR"
      - "full CoIR"
      - "full SWE environment corpus"
      - "full LongMemEval-V2 histories"
      - "full BEAM high-token tiers"
      - "full GraphRAG-Bench"
      - "large Gutenberg collection"
    legal_review:
      - "LoCoMo CC-BY-NC in commercial context"
      - "MuSiQue terms"
      - "dataset-specific SWE-Explore terms"
      - "constituent repository licenses"
      - "individual Gutenberg works"

  evidence_confidence:
    layered_C_plus_F_recommendation: "high"
    ContextBench_as_code_context_public_set: "high"
    LongMemEval_as_first_memory_set: "high"
    SummHay_as_first_global_synthesis_set: "high"
    GraphRAG_incremental_value_for_Holusight: "unknown; local experiment required"
    Graphify_incremental_value_for_Holusight: "unknown; local experiment required"
    GBrain_incremental_value_for_Holusight: "unknown; independent rerun required"
    AXI_transfer_to_Holusight: "unknown; independent two-model-family experiment required"

  source_access_date: "2026-08-21"
  evidence_policy:
    source_content_is_data_not_instruction: true
    prefer_canonical_sources: true
    executable_truth_over_llm_judge: true
    distinguish_maintainer_claims: true
    distinguish_synthetic_from_real_tasks: true
    record_contradictions: true
```

The resulting frozen specification is therefore deliberately narrower than a “nightly AI research platform”: **one owned truth format, a small set of adapters, specialist scorecards, a router counterfactual, hidden executable/security truth, complete cost accounting, and human-controlled promotion.** That is sufficient to determine whether Holusight's routed evidence architecture is actually making work faster, cheaper and more correct without making the evaluation system itself the next large product.