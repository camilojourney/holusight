# Holusight Product Architecture Research

**Research ID:** `BEGIN_HOLUS_PRODUCT_ARCHITECTURE_RESEARCH_20260821`  
**Decision horizon:** 12–24 months  
**Access date for current web evidence:** August 21, 2026  
**Authorization boundary:** research and specification only; **no code, installs, production indexing, customer communications, or purchases are authorized by this report.**

## Executive decision

### Recommendation

**Holusight should become a narrow, local-first repository evidence layer, not a universal search or company-knowledge platform.**

The customer-visible job should be:

> **Before a person or agent acts on a repository, return the smallest current evidence packet that is sufficient to show what is true at this repository state.**

Under that promise, **routing is an implementation detail**, not the product. The product should decide whether an exact search, semantic retrieval, symbol/graph lookup, repository map, static analyzer, or deterministic contract is the cheapest sufficient source of evidence. Users should normally see the resulting evidence, provenance, freshness, confidence/coverage signals, egress, latency, and cost—not a taxonomy of retrieval algorithms.

I would therefore pursue a **narrowed version of option C, with option G as an optional proof mechanism**:

**C-lite: repository evidence gateway**
→ exact/native tools first  
→ semantic retrieval only when it adds evidence  
→ structural providers delegated to SCIP/LSP/Serena/Graphify-style systems  
→ deterministic repository contracts exposed as a separate `check` job  
→ company memory delegated to a separate GBrain-like provider  
→ GraphRAG kept outside the default code path.

**Confidence: 0.76 / moderate-high in the direction, low-to-moderate in product-market fit.**

The confidence is not higher because Holusight's strongest retrieval evidence is still internal and small. Its architecture document reports a 20-query benchmark on its own 96-file codebase, and a separate 3×3 context experiment in which Fleet Brain averaged 93.0 while Fleet Brain plus CodeSight averaged 93.8; those are useful engineering signals, not evidence of customer value or broad agent improvement. fileciteturn1file0L2-L2 Current public Holusight capability documentation also shows a substantial implemented retrieval base—hybrid retrieval, local embeddings, document/code parsing, API/CLI/web surfaces and provenance—but still lists enterprise ACLs, SSO, M365/SharePoint, multi-tenant SaaS and Graphify integration as planned or unclaimed. fileciteturn0file0L2-L2

The most important external challenge to the existing product thesis comes from March 2026 research showing that off-the-shelf coding agents using filesystem navigation, `grep`/`ripgrep`, scripts and iterative exploration beat fixed RAG baselines on several long-context tasks; adding BM25 or dense retrievers did **not** consistently help and sometimes degraded performance. On the authors' five benchmarks, their no-retriever Codex setup beat their RAG baseline substantially on answer quality, although it was also materially more expensive per query. This is unusually relevant to Holusight because it says the question is no longer “does semantic retrieval work?” but “on which repository tasks does an extra retriever improve the final outcome after a strong agent already has native tools?” citeturn21view0

At the same time, retrieval should not be dismissed wholesale. CodeRAG-Bench found that useful retrieved repository context can improve code generation but that retrieval quality and generator integration are major bottlenecks; broader RAG-versus-long-context work likewise finds no universal winner. citeturn21view1turn21view2 The implication is **routing by task and measured sufficiency**, not semantic retrieval everywhere and not “grep is all you need.”

### What Holusight can plausibly own

The defensible wedge is **not embeddings, BM25, AST chunking, GraphRAG, knowledge graphs, MCP, or code search individually**. Mature or fast-moving products already provide those pieces. Voyage currently offers code-specialized embeddings; Graphify provides a deterministic local code graph; Sourcebot combines self-hosted code search/navigation with cited AI answers; Sourcegraph, Zoekt and SCIP span exact search and precise navigation; Serena exposes symbol-level LSP operations; Aider builds compact repository maps; Augment sells a standalone context engine; and Glean, Microsoft 365 and Onyx already occupy broad enterprise/document knowledge territory. citeturn16search1turn14search3turn14search5turn9view2turn9view3turn11search9turn4search2turn11search0turn10search2turn10search1turn10search3

A more plausible ownership position is the **evidence contract between those systems and a human or agent**:

`question/task → minimal sufficient evidence → repository snapshot → citations/proof → egress/cost/freshness → reproducible provider trace`

That makes provider replacement a feature rather than a migration crisis. It also fits a real external trend: Voyage's own current documentation now recommends `voyage-code-4` for code retrieval, while Holusight's current architecture was built around `voyage-code-3`. Provider quality and names are already changing faster than Holusight's product architecture should. citeturn16search1turn16search5

### The strongest argument not to build Holusight

**The no-build case is strong enough that status quo must remain the control condition for every prototype.**

A capable coding agent already possesses exact search, file traversal, shell programs and increasingly good long-context reasoning. Aider shows that a roughly token-budgeted structural repository map can cheaply expose important symbols; Zoekt provides fast indexed exact/regexp search; SCIP and Serena provide structural relationships; Sourcebot already combines search, navigation and cited answers; Graphify supplies a local structural graph; and Augment already markets context retrieval as a standalone cross-agent service. citeturn4search2turn9view2turn9view3turn11search9turn14search5turn14search3turn11search0

Meanwhile, the strongest recent primary research examined here found that an added retriever could actually reduce coding-agent performance on some long-context tasks. citeturn21view0 Holusight's own tiny context experiment found only a 0.8-point average gain after Fleet Brain was already present. fileciteturn1file0L2-L2

Therefore, **Holusight should not be built merely because routing is architecturally elegant**. It should exist only if it produces a measurable improvement in *correct outcomes per dollar/minute*, including indexing and maintenance—not merely fewer retrieved tokens.

## Users, jobs, and break-even

The following is a **customer-discovery hypothesis**, not a claim that these segments have already validated demand.

| Segment | High-frequency painful job | Existing default | Likely change willingness | Trust requirement | Holusight need |
|---|---|---|---|---|---|
| Solo AI-native developer | “Give my agent enough evidence to understand this unfamiliar part of the repo without wasting context.” | Native agent search, `rg`, repo map, IDE/LSP | Medium if setup is essentially zero | Commit freshness, local operation, no silent egress | **Conditional fit.** Good only when repositories/tasks are hard enough that native tools demonstrably fail |
| Ordinary developer | “Where is this implemented and what depends on it?” | IDE search/navigation, `rg`, Sourcegraph-like search | Low | Results must be obvious and deterministic | **Usually not needed.** Semantic retrieval alone is insufficient reason to change behavior |
| Software team | Onboarding, unfamiliar ownership, PR investigation, cross-service impact | IDE + source hosting search + tribal knowledge | Medium-high when repeated | Shared reproducibility, provenance, repo state | **Good candidate** if evidence questions happen repeatedly |
| AI-heavy company | Keep many coding agents grounded while controlling context, providers and egress | Per-agent context systems, MCP servers, bespoke prompts | High if measurable quality/cost improvement | Reproducibility, egress policy, provider telemetry, rollback | **Strongest target hypothesis** |
| Small nontechnical company | Find policies, contracts, decisions and onboarding information | M365/Google search, Copilot, Glean/Onyx-type tools | Low unless existing search is badly failing | ACL inheritance and connector completeness | **Explicit noncustomer by default** |
| Regulated enterprise | Permission-safe evidence, audit, change impact, policy proof | Sourcegraph/enterprise search/governed platforms | Medium but procurement burden high | SSO, SCIM, ACL correctness, audit, retention, compliance | **Not ready as a broad offering** |
| Consultant with multiple clients | Rapidly understand unfamiliar repositories without cross-client leakage | Native coding agents, local search, ad hoc indexes | High if local and disposable | Physical/logical client isolation and explicit egress | **Strong niche candidate** |

The broad nontechnical-company thesis should be rejected for now. Glean advertises 275+ permission-aware connectors with source ACL inheritance and sync; Microsoft Copilot connectors integrate external enterprise content into Microsoft 365 search while respecting source permissions; Onyx already offers an open-source/self-hosted enterprise RAG platform with dozens of connectors. Holusight's own current capability inventory still calls per-document ACLs, SSO and M365/SharePoint connectors planned. citeturn10search2turn10search1turn10search3 fileciteturn0file0L2-L2

That is not merely a feature-count problem. For company knowledge, **authorization correctness becomes part of retrieval correctness**. Holusight would have to synchronize identity, inherited permissions and source changes, then ensure derivative chunks, caches, evaluation data and generated summaries never broaden access. Microsoft's and Glean's existing products make source-aware permissions central rather than optional. citeturn10search1turn10search2 Consequently, “company search” is a substantially different product from “local repository evidence.”

**Explicitly reject a small nontechnical company when** its corpus already lives primarily in a platform with adequate search/Copilot, it has no repeated high-cost evidence problem, it cannot identify an owner for source authority, or it needs permission-aware multi-user search before Holusight has production ACL support. A tiny uniform-access document folder can remain a consulting use case for current CodeSight, but that is not sufficient justification for turning Holusight into a universal company router. Holusight's current public positioning already describes the offering as a focused consulting product rather than a Glean or Sourcegraph replacement. citeturn7view0

### When routing becomes worth its overhead

There should be **no fixed repository-size claim** such as “RAG starts winning above X lines of code” without a real benchmark. Instead, use this break-even equation for each task class:

\[
\text{Net value} =
Q[
(\Delta P_{correct}\times C_{error})
+(\Delta T\times C_{time})
+\Delta C_{inference}
]
-C_{index}
-C_{maintenance}
-C_{routing}
\]

where `Q` is repeated query/task volume.

This predicts several testable regimes:

| Situation | Expected winner |
|---|---|
| Small/familiar repository + exact identifier question + strong agent | Native exact search / status quo |
| Easy repository orientation | Compact repo map + exact search |
| Ambiguous conceptual question over unfamiliar code/docs | Semantic retrieval may become useful |
| “Who calls/implements/depends on this?” | SCIP/LSP/Serena/Graphify-style structural provider |
| Compiler/build-impact question | Compiler/build graph/static analysis, not semantic RAG |
| Explicit repository policy | Deterministic contract/check |
| Repeated ambiguous questions across several repositories | Router becomes more plausible |
| Low query frequency | Index/maintenance amortization works against Holusight |
| Many repeated agents/questions against same corpus | Shared index and evidence cache become more plausible |
| High-churn repository with weak invalidation | Status quo/native tools can beat stale indexing regardless of recall |

Recent long-context research reinforces this conditional view. LaRA found no universal RAG-versus-long-context winner, while the coding-agent study found different tasks elicited different strategies—native search for retrieval-heavy tasks, scripts for aggregation, and direct reading for other tasks. citeturn21view2turn21view0

Books and large public corpora can therefore test **scale, ingestion, retrieval mechanics and cost curves**, but they should **not** be accepted as evidence that repository routing improves code work. A book benchmark has neither symbol definitions, compiler relationships, branch/commit freshness, PR impact, repository conventions nor realistic agent-editing consequences. This is a methodological conclusion from the mismatch between the desired product job and the benchmark domain, not a claim against using books as stress tests.

## Options, boundaries, and architecture

### Ranked options

I translated the user's ranked criteria into a decision heuristic totaling 100 points: grounded correctness/trust 20; clear job/adoption 16; measured economics 14; usefulness without AI sophistication 11; privacy/egress 10; maintainability/provider replacement 9; freshness/provenance 8; company scalability 5; ecosystem/license/operations 4; speed to build 3. Scores below are judgment calls, not empirical measurements.

| Rank | Option | Score / 100 | Decision |
|---|---|---:|---|
| **First** | **C — narrowed repository evidence router** | **83.8** | **Recommended research/prototype direction** |
| **Second** | **G — repository contracts/compliance, retrieval secondary** | **82.4** | Strong adjacent wedge, but validate buyer/frequency before making it the whole product |
| **Third** | **B — lightweight semantic code/document CLI** | **79.4** | Good fallback if routing does not add enough value |
| **Fourth** | **F — integration/product layer over mature systems** | **73.4** | Likely implementation strategy inside C; weaker standalone customer story |
| **Fifth** | **A — status quo composition** | **67.0** | **Mandatory control; should win if uplift is small** |
| **Fifth** | **D — modular code/docs/company platform** | **67.0** | Architecturally attractive but prematurely broad |
| **Seventh** | **E — universal information router** | **49.2** | Do not pursue |

Importantly, the score does **not** mean C has earned investment. The status quo has a structural advantage not represented by feature scoring: **it requires no new product to maintain**. C should therefore remain an experimental challenger until the proof gates later in this report are passed.

### The component/job boundary

The central architecture decision should be:

> **Code and Markdown share an evidence control plane, not one universal retrieval engine.**

The genuinely reusable primitives are:

| Shared core primitive | Why it transfers |
|---|---|
| Snapshot/source identity | Evidence needs to identify exactly what corpus/revision was queried |
| Provenance envelope | Code and docs both need source location and evidence lineage |
| Provider contract | Exact, semantic, structural and memory systems should be replaceable |
| Routing/sufficiency policy | All domains benefit from asking the least expensive sufficient provider first |
| Egress policy | Local versus external processing must be explicit |
| Cost/latency accounting | Provider economics are cross-domain |
| Freshness/invalidation contract | Every evidence packet needs a staleness definition |
| Evaluation harness | Frozen tasks and outcome comparison are cross-domain |
| Authorization abstraction | Necessary wherever heterogeneous access appears, though the underlying ACL implementation is domain-specific |

What **does not** transfer cleanly is at least as important:

| Domain-specific system | Why it should stay specialized |
|---|---|
| Code parsing/navigation | ASTs, LSP, SCIP, compiler semantics, build systems and generated code have no document analogue |
| Exact code search | Identifier/regexp/symbol semantics are unusually important; Zoekt and OpenGrok already specialize here citeturn9view2turn17search0 |
| Document parsing | Pages, headings, OCR, tables and slides require different parsing/citation logic |
| Enterprise connectors | SharePoint, Drive, Slack, email and SaaS APIs have identity, delta-sync and ACL semantics |
| Institutional memory | Decisions, chronology, people, mutable facts and consent are materially different from repository source truth |
| Narrative graph reasoning | GraphRAG's community summaries and local/global/DRIFT query modes target corpus-level narrative questions, not compiler truth citeturn13search2turn13search3turn13search1 |
| Deterministic contracts | These should execute explicit rules, not inherit probabilistic retrieval semantics |

**Company memory should remain a separate GBrain-like provider**, not be silently merged into the repository index. GBrain's current architecture explicitly treats memory as a versioned brain/source system with graph and hybrid retrieval, and its companion `gbrain-evals` has a useful adapter/evaluation structure; both are MIT-licensed, but their own performance claims remain maintainer evidence and need independent replication. citeturn14search1turn14search0turn14search10

GraphRAG should similarly remain optional. Microsoft's repository now explicitly describes GraphRAG as largely maintenance-mode software focused on maintenance, dependency and security fixes rather than active feature development. Its query documentation distinguishes local search, global community-report map/reduce and DRIFT; global search is explicitly resource-intensive. citeturn13search15turn13search2turn13search3 Microsoft research has shown meaningful cost reductions from dynamically choosing community levels, but that work used AP News questions, making it evidence for graph-query economics rather than repository correctness. citeturn13search7

### Proposed evidence-provider contract

A provider should be replaceable behind a very small conceptual contract:

```text
capabilities()   -> jobs, modalities, egress class, determinism
status(snapshot) -> available, version, freshness, index state
estimate(request)-> expected latency/cost/egress
query(request)   -> evidence envelope
explain(trace_id)-> why provider/routing path was selected
```

The **evidence envelope**, rather than an embedding vector or graph node, should become Holusight's stable internal asset:

```text
query
repository_identity
snapshot:
  commit
  dirty_state
provider:
  kind
  name
  version
route_reason
evidence[]:
  source
  location
  scope
  excerpt
  evidence_kind
  deterministic
  freshness
coverage:
  complete | partial | unknown
egress:
  occurred
  destination
cost:
  provider
  model
  input_tokens
  output_tokens
  dollars
latency_ms
warnings[]
```

This extends a capability Holusight already has rather than inventing an unrelated platform: its current `SearchResult` includes file path, location, scope, snippet, score, chunk identity and source/provenance fields. fileciteturn0file0L2-L2

## Competitive landscape and build/buy decision

The strongest conclusion from the market scan is **adapt providers; do not recreate them**.

| System | Strong job today | Current maintenance / license / deployment evidence | Holusight decision |
|---|---|---|---|
| **Voyage** | Semantic embeddings/reranking, including code | Current docs recommend `voyage-code-4`; embeddings and reranking are usage-priced APIs. Current privacy policy allows an opt-out from model-improvement use and says opted-out customer content is deleted after processing, while separately negotiated business agreements may govern enterprise API data. citeturn16search1turn16search2turn16search4 | **Adapt as optional external provider. Never make it architectural core.** |
| **Graphify** | Local deterministic AST-derived repository graph; graph queries/path/neighbors/impact | Current repository describes local tree-sitter code extraction with no embeddings/vector DB, MCP serving, and explained `EXTRACTED` vs `INFERRED` edges; repo exposes Apache-2.0/MIT-licensed portions. citeturn14search3 | **Adapt for structural questions if it wins evals. Do not duplicate graph extraction.** |
| **Microsoft GraphRAG** | Local/global/DRIFT reasoning over narrative corpora | MIT; repository says largely maintenance mode. Global query uses community reports/map-reduce and is resource intensive. citeturn13search15turn13search3 | **Optional document provider only. Not code truth and not core.** |
| **GBrain / gbrain-evals** | Persistent institutional/agent memory, hybrid graph retrieval, evaluation patterns | MIT; active 2026 project. Companion evals expose adapter-oriented retrieval/ingestion/assistant evaluation with sealed qrels and judge-version pinning. citeturn14search0turn14search1turn14search10 | **Keep as separate memory provider/pattern source. Independently validate all quality claims.** |
| **gstack** | Agent workflows, review roles, durable practices | Maintainer ecosystem uses skills and can integrate GBrain; durable workflow patterns can also work without GBrain. | **Pattern source, not retrieval competitor.** |
| **Sourcegraph** | Large-scale deterministic code search/navigation/oversight | Current product sells enterprise code search; current pricing starts at a substantial enterprise commitment. Self-hosting is supported with privacy assurances. citeturn3search11turn3search3turn3search9 | **Buy/adapt when customers already use it. Do not compete on enterprise-scale indexing.** |
| **Zoekt** | Fast substring/regexp multi-repository search | Apache-2.0, actively maintained Sourcegraph fork; purpose-built indexed search. citeturn9view2 | **Preferred exact-search backend candidate at scale.** |
| **SCIP** | Precise cross-reference/navigation interchange | Apache-2.0 and language-agnostic; supports precise navigation via multiple language indexers. Sourcegraph moved SCIP toward community-driven OSS stewardship in 2026. citeturn9view3turn3search13 | **Use rather than invent compiler-grade cross-reference schema.** |
| **Sourcebot** | Self-hosted multi-repo code search, navigation and cited Ask | Current product provides regex/boolean search, navigation and cited AI answers; releases remained active through July 2026. Core is FSL-1.1-ALv2 with separate enterprise portions. citeturn14search5turn9view1turn14search2 | **One of the most serious adopt-vs-build controls.** |
| **OpenGrok** | Mature source search/cross-reference browser | CDDL; project released 1.14.13 on May 26, 2026; supports source search/cross-reference/history and Docker. citeturn17search0turn17search1 | **Useful mature exact-search control, especially where AI is unnecessary.** |
| **Kythe** | Compiler/build-derived semantic code graph | Apache-2.0; language-agnostic graph model with compiler/build metadata, cross-references and indexers. citeturn17search4turn17search9 | **Use for compiler-grade relationships where supported; don't rebuild the concept.** |
| **Aider repo map** | Small structural orientation packet | Official docs describe graph-ranking important symbols into a token-budgeted repo map. citeturn4search2 | **Mandatory lightweight baseline. A semantic index must beat it, not merely differ from it.** |
| **Serena** | Symbol-level agent navigation/editing using language-server semantics | Current MIT open-source agent toolkit exposes higher-level symbol/reference operations through LSP-oriented abstractions. citeturn11search9 | **Strong structural provider/control.** |
| **Continue** | Source-controlled AI checks in CI | Current project is Apache-2.0 and has shifted heavily toward source-controlled AI checks. citeturn12search6 | **Evidence that CI/checks are an active adjacent category; differentiate deterministic contracts from LLM review.** |
| **OpenHands** | General coding agent/runtime | Current open-source core is MIT, with commercial cloud/enterprise products layered around it. citeturn12search0 | **Integrate with agents; do not become another coding agent.** |
| **Augment Context Engine** | Cross-agent semantic/context retrieval | In February 2026 Augment released its Context Engine through MCP and local/remote modes; published quality gains are vendor benchmarks and need independent replication. citeturn11search0turn11search2 | **Closest commercial “context layer” control. Strong evidence semantic context alone is commoditizing.** |
| **Glean** | Broad enterprise knowledge/search | Current product advertises 275+ permission-aware connectors and inherited source ACLs. citeturn10search2 | **Do not chase broad company search.** |
| **Microsoft 365 Copilot/Search** | Search over Microsoft ecosystem and connectors | External connector content can appear with citations while underlying access controls are respected. citeturn10search1 | **Default incumbent for M365-native small companies.** |
| **Onyx** | Open/self-hosted enterprise RAG/search | Current CE is MIT with a broad connector and agent/search surface. citeturn10search3 | **Strong build-vs-buy control for document/company workloads.** |

This matrix points to a deliberately thin Holus architecture:

```text
                       HOLUS EVIDENCE CONTRACT
                              |
         +--------------------+---------------------+
         |                    |                     |
       exact              conceptual             structural
   rg / Zoekt /         CodeSight/Voyage      SCIP/LSP/Serena/
    OpenGrok               optional               Graphify
         |                    |                     |
         +--------------------+---------------------+
                              |
                       evidence packet
                              |
               +--------------+--------------+
               |                             |
          person / agent                 holus check
                                        deterministic
```

Narrative GraphRAG and institutional memory plug in **beside** this repository plane, rather than turning the repository plane into a universal knowledge graph.

### Do not build

The next 12–24 months should **not** include a proprietary vector database, proprietary LSP/SCIP replacement, proprietary compiler/build graph, general GraphRAG clone, broad enterprise connector catalog, generic company-chat product, generic coding agent, model-hosting platform, mandatory multi-tenant SaaS control plane, broad IDE suite, or a GBrain clone.

Also do not make “lowest retrieved token count” a product KPI by itself. The coding-agent study gives a useful counterexample: its no-retriever coding agent was much more accurate than the simple RAG baseline on several tasks but also more expensive. citeturn21view0 **Cost per correct outcome** is the relevant metric.

## Product contract and holus-axi

### Narrow product promise and packaging

The recommended promise is:

> **Holus gives a person or agent the smallest current, cited evidence packet needed to establish what is true about a repository before acting.**

Recommended eventual packaging, conditional on proof:

| Package | Job | Default |
|---|---|---|
| **Local `holus` CLI / AXI** | Ask for repository evidence with no server requirement | **Core** |
| **`holus check` CI job** | Prove explicit deterministic repository contracts | Optional pack |
| **Agent-facing `/holus` skill** | Teach Claude/Codex/OpenCode when and how to request evidence | Generated from stable CLI contract |
| **Team evidence gateway** | Shared caching/provider policy and telemetry | Later, only after team proof |
| **Semantic pack** | Local or Voyage/other embeddings and reranking | Optional |
| **Structural pack** | SCIP/LSP/Serena/Graphify adapters | Optional |
| **Document graph pack** | Narrative/cross-document graph provider | Optional, not code default |
| **Institutional-memory connector** | GBrain or equivalent | Separate provider |
| **Hosted service** | Central team deployment | Only after SSO/ACL/security gates |

The current CodeSight engine is already unusually well-positioned to become a provider rather than the whole product. Its current capability inventory shows hybrid BM25/dense retrieval, local embeddings, optional Voyage/reranking, multiple document formats, code chunking, local search and provenance. fileciteturn0file0L2-L2

### `holus-axi`: smallest stable command surface

Do **not** expose every provider as a top-level command. The stable surface should describe jobs:

```text
holus
holus evidence "<question>"
holus check [contract-or-scope]
holus status
holus providers
```

Provider forcing belongs under flags for diagnosis or evaluation:

```text
--mode auto|exact|semantic|structure
--provider NAME
--explain-route
```

**`holus` with no arguments** should be a live, content-first home view rather than help text:

```text
repo        holusight
snapshot    4bf27c1  clean
freshness   exact: live   semantic: current   structure: unavailable
egress      off
contracts   12 pass  0 fail
providers   exact ✓  semantic ✓  structural —
recent      3 evidence packets cached
```

Help then follows, compactly.

### Default evidence output

An agent should not get full chunks unless necessary. Proposed default TOON-like output:

```text
answerable: true
snapshot: 4bf27c1
route: exact+structure
evidence[3]:
  - src/payments/service.py:84-111 | function capture_payment | exact
  - src/payments/routes.py:42-58 | function create_charge | reference
  - docs/payments.md:19-31 | "Retry policy" | text
coverage: sufficient
fresh: true
egress: none
tokens.retrieved: 612
cost.usd: 0
latency_ms: 143
truncated: true
```

`--full` expands excerpts and provider traces. `--fields` performs projection rather than asking an agent to parse unwanted output:

```text
holus evidence "where is retry policy enforced?" \
  --fields snapshot,evidence.source,evidence.location,evidence.excerpt
```

A lossless JSON mode should remain available:

```text
--format toon      # agent default
--format json      # stable machine/API interchange
--format text      # human display
```

This is important because AXI's own benchmark evidence is promising but **not sufficient to declare TOON universally superior**. The AXI maintainers' published GitHub study ran 425 trials using Claude Sonnet 4.6: AXI averaged 100% success, $0.050/task, 15.7 seconds and three turns; raw `gh` CLI averaged 86%, $0.054, 17.4 seconds and three turns; the tested GitHub MCP conditions cost roughly $0.10–$0.15/task and took six to eight turns. citeturn18search0turn18search2

That study is directly relevant but is maintainer-run, uses a single agent model, and its methodology uses the same model family as judge. AXI itself explicitly says results for other models are unpublished and may differ. citeturn18search2 Independent 2026 research on compact agent notations adds a material contradiction: across several agent benchmarks and five open-weight models, TOON reduced tokens by up to 18% but could lose up to roughly nine percentage points of accuracy and exhibited multi-turn parsing failures for some models. citeturn21view3

Therefore: **TOON should be an evaluated agent-facing encoding, not Holusight's canonical storage/API schema. JSON should remain the lossless contract.**

### Errors and empty states

An empty search is an answer, not an invitation to hallucinate:

```text
answerable: false
evidence: []
reason: no_matching_evidence
snapshot: 4bf27c1
fresh: true
providers_checked: [exact, semantic]
```

Structured errors should be similarly small:

```text
error:
  code: PROVIDER_STALE
  message: semantic index is older than repository snapshot
  provider: semantic
  retryable: true
  safe_fallback: exact
  egress: none
```

Crucially, the router should distinguish:

`no evidence found`  
from `provider unavailable`  
from `provider stale`  
from `access denied`  
from `unsupported question`  
from `budget exceeded`.

Those states are much more valuable for agent reliability than a fluent synthesized non-answer.

### Status, freshness, egress and economics

`holus status` should expose provider state separately:

```text
snapshot:
  commit: 4bf27c1
  dirty: false

providers:
  exact:
    version: rg-...
    freshness: live
    egress: none
  semantic:
    version: codesight-...
    model: voyage-code-4
    indexed_commit: 4bf27c1
    freshness: current
    egress: voyage
  structural:
    provider: scip
    indexed_commit: 01ac92e
    freshness: stale
```

Voyage is a useful illustration of why version visibility matters. Its August 2026 docs recommend newer `voyage-code-4`, while `voyage-code-3` remains an older model; current prices for `voyage-code-4` are usage-based at $0.12 per million embedding tokens after the free tier. citeturn16search1turn16search2 A model name should never be buried as an implementation detail when changing it can alter quality, egress and cost.

### Session hooks

Hooks for Claude Code, Codex and OpenCode should be **opt-in and ambiently tiny**. They should inject repository identity and status, not retrieved content:

```text
holus: repo=payments commit=4bf27c1
evidence=available exact=live semantic=current structure=stale
egress=off
```

Actual evidence should be fetched only when a task needs it. This avoids paying a context tax on every turn merely because Holusight is installed.

The generated `/holus` skill should teach only four behaviors:

1. Use native/exact evidence for exact identifiers and known file questions.
2. Call `holus evidence` when the relevant location is uncertain, conceptual, cross-file or mixed code/docs.
3. Call `holus check` when the question concerns an explicit repository rule.
4. Never treat a partial or stale packet as authoritative; surface the status.

The installed skill should be generated from the versioned CLI schema so that docs and executable behavior cannot silently diverge.

### CLI/AXI versus MCP versus library API

| Surface | Recommended role | Evidence-based judgment |
|---|---|---|
| **AXI CLI** | Default agent interface | Best current experimental evidence for low schema/context overhead and compact outputs, but AXI evidence is maintainer-run and model-specific. citeturn18search0turn18search2 |
| **Raw human CLI** | Human/debug fallback | Excellent universal availability; AXI's own benchmark shows raw `gh` performed fairly efficiently but had lower task success on its selected tasks. citeturn18search0 |
| **MCP** | Optional interoperability adapter | Strong standard discovery/tooling benefits, but task-level AXI studies found large tool-schema/turn costs in the MCP configurations they tested. Current MCP evolution is also adding deterministic tool ordering/caching-friendly behavior, so today's cost gap should not be assumed permanent. citeturn18search0turn19search1turn19search8 |
| **Direct Python/library API** | Embedded integrations and tests | Likely lowest protocol overhead and strongest type control inside Python, but this research found **no comparable Holus-like task benchmark** against AXI/MCP; benchmark before making economic claims. |

MCP should therefore be **an adapter, not the canonical Holus architecture**. Current MCP draft specification work explicitly encourages deterministic tool ordering for client-side caching and prompt-cache stability, illustrating why protocol economics are changing. citeturn19search1

## Proof plan, roadmap, and stop conditions

### What must be demonstrated before any “faster, cheaper, better” claim

Holusight needs an outcome benchmark, not another retrieval benchmark.

The primary test unit should be a **real completed repository task**, with conditions randomized across:

`native agent tools only`  
`native tools + compact repo map`  
`current Holusight semantic retrieval`  
`best mature external system/provider`  
`proposed routed evidence`

Each condition must record:

| Dimension | Required measurement |
|---|---|
| Correctness | Did the person/agent reach the right answer or code decision? |
| Evidence completeness | Did the packet include every source required for the conclusion? |
| Citation validity | Does each cited location actually support the statement? |
| Freshness | Did any answer rely on content superseded by current repo state? |
| Agent success | Was the final repository task completed correctly, not merely retrieved well? |
| Turns | Total agent/tool interaction turns |
| Tokens | Input, output and cache tokens across the **entire task** |
| Model cost | Actual provider/API dollars |
| Retrieval cost | Embedding/reranking/index amortization |
| Time | Wall-clock and human-active time |
| Egress | Destination and bytes/tokens leaving local environment |
| Operations | Setup, reindex, failure recovery and maintenance time |
| Router value | Which provider produced evidence that another condition lacked? |

**Initial decision gates below are proposed product thresholds, not industry benchmarks.**

The routed product should not advance beyond reversible prototype status unless, on representative real repository tasks, it achieves at least one of these without materially reducing correctness:

- **≥10 percentage-point absolute improvement in completed-task correctness**, or
- **≥25% reduction in total cost per correct task**, or
- **≥25% reduction in human-active/task time**,

while maintaining **≥99% citation-location validity in the evaluation set, zero known stale-evidence acceptance on freshness tests, and zero cross-repository/client leakage**.

Adoption gates should include at least **four of five design partners still voluntarily using the tool after six to eight weeks**, a majority of target users using it weekly without researcher prompting, and repeated usage on the same core evidence jobs rather than novelty exploration. These are deliberately demanding because another repository tool has substantial adoption cost.

The benchmark should include cases where Holusight is expected to lose: exact identifiers, tiny repositories, straightforward edits and strong-agent native-search tasks. Otherwise the router will be trained to win a benchmark designed around itself.

The March 2026 coding-agent study should be replicated on Holusight's target model/agent combinations because it found both a quality advantage for native agent exploration and a significant cost disadvantage relative to simple RAG. citeturn21view0 The correct objective is the Pareto frontier of correctness, time and total cost—not one metric.

### Customer discovery and pilot

Before implementation authorization, customer research should seek **recent incidents, not feature opinions**:

“Show me the last time an agent misunderstood the repository.”  
“Show me the last code question that took more than ten minutes to establish.”  
“What tools did you try?”  
“What evidence would have made the answer trustworthy?”  
“Did the failure come from retrieval, structure, stale information, undocumented intent, or a wrong assumption?”  
“Would exact search or a repo map have been sufficient?”  
“Who bears the cost when the answer is wrong?”

A good discovery sample would intentionally include approximately 20–25 participants across AI-heavy engineering teams, conventional software teams, consultants, solo AI-native developers and a smaller falsification sample of nontechnical businesses/regulatory buyers. This is a proposed research design, not a claim about statistical representativeness.

Any later pilot should use the participants' own retrospective and then authorized live repository tasks. **Books and public corpora should remain secondary stress tests only.**

### Improvement architecture

Provider evolution should be treated as normal:

```text
provider contract
    ↓
version-pinned implementation
    ↓
frozen task corpus + expected evidence
    ↓
candidate provider in shadow
    ↓
paired outcome comparison
    ↓
canary
    ↓
promote or rollback
```

Every evaluation run should pin at minimum:

`repository snapshot`  
`task-set version`  
`provider versions`  
`embedding model/version`  
`reranker model/version`  
`agent/frontier model`  
`prompt/skill version`  
`judge/version`  
`routing policy version`.

This is not academic bookkeeping. Voyage's migration from the `code-3` generation to current `code-4` and GraphRAG's shift into maintenance mode demonstrate that a provider architecture can age independently of Holusight. citeturn16search1turn13search15 GBrain-evals' use of sealed qrels, seeded runs and judge-version pinning is a useful current pattern, though it should be independently assessed rather than imported wholesale. citeturn14search10

Outcome telemetry should be **local by default**, and any aggregate telemetry should be explicitly opt-in. It should prefer event metadata—provider selected, latency, token count, freshness, user accepted/retried—not source code or query content.

A provider should be considered for deletion when, over a sufficiently varied evaluation window, it:

- contributes no unique critical evidence,
- is selected rarely and can be covered by a cheaper provider,
- produces no measurable task-success improvement,
- causes disproportionate stale-index or operations burden,
- or is dominated by a stronger provider on quality, latency, privacy and cost.

### Reversible roadmap

| Horizon after authorization | Purpose | What remains reversible | Delete/revisit trigger |
|---|---|---|---|
| **Initial quarter** | Falsify the need. Build/assemble real task corpus; compare native agent, exact search, repo map, current CodeSight, structural tools and mature alternatives | Everything | Stop if native tools/repo maps are essentially tied on final outcomes |
| **Following quarter** | Specify/prototype one evidence envelope and AXI job surface; route only a few task classes | Providers interchangeable | Stop routing if users mostly force one provider |
| **Following half-year** | Small design-partner repository pilots; optional deterministic `check` experiments | Local only; no broad SaaS commitment | Stop if retention/economics gates fail |
| **Second year, early** | Team gateway only if shared usage justifies it; add SCM/CI integrations selectively | Local CLI remains primary fallback | Do not host if SSO/ACL/security cost dominates value |
| **Second year, later** | Consider document graph or memory connectors only where repository customers request them | Separate packs/providers | Delete or spin out if buyer/job differs materially |
| **End of horizon** | Decide whether Holus is a durable evidence layer, a smaller CLI, a contract product, or unnecessary | Keep provider-neutral data/eval artifacts | Reposition aggressively if one component is clearly load-bearing |

### Explicit stop-investment conditions

**Status quo wins** if native agent tools plus exact search/repo maps come within **three percentage points of routed-task correctness** on the target task set and the routed stack does not save at least ~20–25% of time or cost.

**The lighter semantic CLI wins** if semantic retrieval repeatedly adds unique evidence but structural/deterministic routing adds little incremental outcome value.

**The contract product wins** if teams repeatedly pay attention to repository rules/CI proof but rarely ask exploratory evidence questions.

**An existing platform wins** if Sourcebot, Sourcegraph, Augment or another product achieves equivalent task outcomes, privacy and provenance with less than roughly a day of customer setup and acceptable total cost. Sourcebot in particular must be treated as a serious control because its current product already combines self-hosted search, navigation and cited answers. citeturn14search5

**Stop broad company-work investment** if target customers already obtain adequate permission-aware search from Glean/Microsoft/Onyx-class systems, or if ACL/connectors become the majority of engineering effort before differentiated evidence value is proven. citeturn10search2turn10search1turn10search3

**Delete semantic retrieval from the default path** if it appears in fewer than roughly 10% of successful real tasks and produces no unique high-severity wins.

**Stop Holusight as a new product altogether** if, after a representative real-world evaluation, its advantage exists only in retrieval metrics such as MRR/nDCG but disappears at the level of final task correctness, human time and total cost.

## Evidence ledger, claim-source bibliography, and evidence packet

The ledger below gives the requested evidence class, canonical source, date/access date, confidence, contradiction and local-validation requirement for the report's consequential claims.

| ID | Consequential claim | Evidence class | Canonical URL / date | Confidence | Contradiction / limitation | Local validation needed |
|---|---|---|---|---|---|---|
| **E01** | Current Holusight already has enough hybrid retrieval/provenance machinery to be treated as a provider rather than rebuilt from zero | Owner repository, executable capability inventory | `https://github.com/camilojourney/holusight/blob/master/specs/010-capability-inventory.md` — updated 2026-08-13; accessed 2026-08-21. fileciteturn0file0L2-L2 | High for stated implementation | Inventory is self-authored and does not prove customer utility | Re-run shipped capability/test inventory before prototype baseline |
| **E02** | Holusight's current internal retrieval evidence is too small to establish market/product advantage | Owner benchmark documentation | `https://github.com/camilojourney/holusight/blob/master/ARCHITECTURE.md` — last-updated 2026-04-04; accessed 2026-08-21. fileciteturn1file0L2-L2 | High | Benchmarks may be useful for regression even though externally weak | Replicate on external repos and real tasks |
| **E03** | Strong coding agents can sometimes outperform fixed RAG using filesystem/native tools; extra retrieval can hurt | Primary research | `https://arxiv.org/abs/2603.20432` — 2026-03-20; accessed 2026-08-21. citeturn21view0 | Medium-high | Not a dedicated Holus/repository-evidence benchmark; coding agents cost more than simple RAG | Reproduce on target code repos, models and tasks |
| **E04** | Retrieval can still improve code generation when retrieval quality/integration are good | Primary research | `https://arxiv.org/abs/2406.14497` — 2024-06; accessed 2026-08-21. citeturn21view1 | Medium-high | Older models; benchmark tasks may not reflect 2026 agents | Re-run with current models/providers |
| **E05** | There is no universal RAG-vs-long-context winner | Primary research | `https://arxiv.org/abs/2502.09977` — 2025-02-14; accessed 2026-08-21. citeturn21view2 | High directionally | Narrative QA, not repository-specific | Use as routing hypothesis only |
| **E06** | GraphRAG should be optional, especially for narrative global/local/DRIFT questions | Official Microsoft docs/repo | `https://github.com/microsoft/graphrag`; `https://microsoft.github.io/graphrag/query/overview/` — accessed 2026-08-21. citeturn13search15turn13search2 | High for product status/capability | Microsoft research shows valuable results on narrative corpora | Test only if customers have cross-document theme questions |
| **E07** | GraphRAG is currently largely maintenance-mode | Maintainer canonical repository | `https://github.com/microsoft/graphrag` — current README; accessed 2026-08-21. citeturn13search15 | High | Maintenance can still be adequate for stable use | Pin versions if adopted |
| **E08** | Voyage should be a replaceable provider because its model generation is already changing | Official provider docs | `https://docs.voyageai.com/docs/embeddings` — accessed 2026-08-21. citeturn16search1 | High | Vendor quality claims are not independent | Benchmark `code-4` against local/exact baselines |
| **E09** | Graphify is a viable structural provider rather than something Holus must recreate | Maintainer repository | `https://github.com/Graphify-Labs/graphify` — accessed 2026-08-21. citeturn14search3 | Medium-high for capabilities | Performance/adoption claims need independent validation | Run path/reference/impact tasks against SCIP/Serena |
| **E10** | Sourcebot is a strong adopt-vs-build control | Official current repository/releases/license | `https://github.com/sourcebot-dev/sourcebot`; `https://github.com/sourcebot-dev/sourcebot/blob/main/LICENSE.md` — accessed 2026-08-21. citeturn14search5turn9view1turn14search2 | High for feature/license status | Product fit and resource cost not measured here | Side-by-side pilot on same repositories |
| **E11** | Exact search and compiler/symbol navigation are mature separate jobs | Canonical OSS repos/docs | `https://github.com/sourcegraph/zoekt`; `https://github.com/scip-code/scip`; `https://github.com/oracle/opengrok`; `https://kythe.io/docs/kythe-overview.html` — accessed 2026-08-21. citeturn9view2turn9view3turn17search0turn17search4 | High | Coverage varies by language/build system | Determine target-language coverage before adapter choice |
| **E12** | Compact repository maps are a serious low-complexity baseline | Official Aider docs | `https://aider.chat/docs/repomap.html` — accessed 2026-08-21. citeturn4search2 | High for mechanism | Not a full evidence/provenance system | Compare task outcomes and token totals |
| **E13** | Broad company knowledge is highly competitive and permission/connectors are table stakes | Official Glean/Microsoft/Onyx sources | `https://www.glean.com/platform/connectors`; `https://support.microsoft.com/en-us/microsoft-365-copilot/understand-copilot-connectors`; `https://github.com/onyx-dot-app/onyx` — accessed 2026-08-21. citeturn10search2turn10search1turn10search3 | High | Some small local-document niches remain underserved | Interview nontechnical firms only as falsification segment |
| **E14** | Holusight is not presently enterprise-ready for broad permission-aware company search | Owner current capability inventory/public site | `https://github.com/camilojourney/holusight/blob/master/specs/010-capability-inventory.md`; `https://www.holusight.com/` — accessed 2026-08-21. fileciteturn0file0L2-L2 citeturn7view0 | High | Capabilities may change after this date | Reverify before any sales positioning |
| **E15** | GBrain is better treated as a separate memory provider/pattern source | Maintainer code/docs + eval repo | `https://github.com/garrytan/gbrain`; `https://github.com/garrytan/gbrain-evals` — accessed 2026-08-21. citeturn14search1turn14search10 | Medium | Most performance assertions are maintainer claims | Independent pinned comparison required |
| **E16** | AXI has promising task-level cost/turn evidence against tested CLI/MCP configurations | Maintainer reproducible benchmark | `https://github.com/kunchenguid/axi/blob/main/bench-github/published-results/STUDY.md` — published 2026; accessed 2026-08-21. citeturn18search0 | Medium | Single agent model, maintainer-run, task selection/judge effects | Replicate specifically for Holus evidence tasks |
| **E17** | TOON should not be assumed universally accuracy-neutral | Independent primary research | `https://arxiv.org/abs/2605.29676` — 2026-05-28; accessed 2026-08-21. citeturn21view3 | Medium-high | Tested open-weight models/benchmarks, not Holus/frontier-agent exact setup | Benchmark JSON vs TOON on Claude/Codex/OpenCode |
| **E18** | MCP economics are changing; current benchmark overhead is not necessarily permanent | Official MCP specification/changelog | `https://modelcontextprotocol.io/specification/draft/changelog`; `https://modelcontextprotocol.io/specification/draft/server/tools` — accessed 2026-08-21. citeturn19search1turn19search8 | High | Client implementations differ substantially | Measure actual supported clients rather than infer protocol cost |
| **E19** | Augment already competes on standalone cross-agent context retrieval | Official vendor product/blog | `https://www.augmentcode.com/blog/context-engine-mcp-now-live`; `https://www.augmentcode.com/product/context-engine-mcp` — 2026-02 onward; accessed 2026-08-21. citeturn11search0turn11search2 | High for existence/capabilities; low-medium for quality claims | Published performance is vendor-controlled | Include as commercial control where access permits |
| **E20** | Sourcegraph/Zoekt/SCIP make “build a complete code intelligence stack” unattractive | Official product/OSS sources | `https://sourcegraph.com/`; `https://github.com/sourcegraph/zoekt`; `https://github.com/scip-code/scip` — accessed 2026-08-21. citeturn3search11turn9view2turn9view3 | High | Cost/deployment may make smaller local product attractive | Compare customer TCO, not feature count |
| **E21** | Sourcebot's license is not permissive OSS in the same sense as Apache/MIT competitors | Canonical license | `https://github.com/sourcebot-dev/sourcebot/blob/main/LICENSE.md` — accessed 2026-08-21. citeturn14search2 | High | FSL converts under future-license terms; enterprise dirs differ | Legal review before embedding/distribution |
| **E22** | OpenGrok remains maintained enough to be a meaningful non-AI baseline | Official repo/project | `https://github.com/oracle/opengrok`; latest cited release 2026-05-26; accessed 2026-08-21. citeturn17search0 | High | Heavier Java/server operational model than lightweight CLI | Benchmark only for relevant deployment sizes |
| **E23** | Current Holus public positioning is already deliberately narrower than Glean/Sourcegraph | Owner public site | `https://www.holusight.com/` — accessed 2026-08-21. citeturn7view0 | High | Future positioning is precisely what this decision may change | Use as current-state evidence only |
| **E24** | “Cost per correct outcome” is safer than optimizing retrieved tokens | Primary research synthesis | `https://arxiv.org/abs/2603.20432` — 2026-03-20; accessed 2026-08-21. citeturn21view0 | High as decision principle | Error value varies by task | Record actual full-task token/cost/time and task correctness |

**Claim-source bibliography.** The highest-load-bearing sources are Holusight's current capability/architecture files; the March 2026 coding-agent study; CodeRAG-Bench and LaRA; current Microsoft GraphRAG docs; current Voyage docs; Sourcebot, Zoekt and SCIP repositories; Aider's repo-map documentation; Graphify, GBrain/gbrain-evals and Serena repositories; Glean/Microsoft/Onyx enterprise-search documentation; AXI's published task benchmark; the independent TOON-format study; and the current MCP specification. The canonical URLs and access dates are recorded individually in E01–E24 above.

```yaml
research_packet:
  id: BEGIN_HOLUS_PRODUCT_ARCHITECTURE_RESEARCH_20260821
  date: 2026-08-21
  timezone: America/New_York
  authorization:
    implementation: false
    installs: false
    production_indexing: false
    purchases: false
    external_communications: false

decision:
  recommendation: >
    Pursue, only through reversible validation, a narrow local-first repository
    evidence layer. The customer-visible job is to return the smallest current,
    cited evidence packet sufficient to establish what is true about a repository
    before a human or agent acts.
  option: C-lite
  adjacent_option: G
  confidence: 0.76
  routing_is:
    customer_product: false
    implementation_mechanism: true
  customer_visible_outcome:
    - minimal_sufficient_evidence
    - repository_snapshot
    - citations_and_provenance
    - freshness
    - egress
    - task_level_cost
  default_control: status_quo_composition

target_segments:
  strongest:
    - ai_heavy_software_teams
    - software_teams_with_repeated_unfamiliar_repo_questions
    - multi_client_consultants_requiring_local_isolation
  conditional:
    - solo_ai_native_developers
    - ordinary_developers
  reject_by_default:
    - small_nontechnical_companies_with_adequate_existing_suite_search
    - regulated_enterprises_requiring_enterprise_acl_sso_compliance_today

product_boundary:
  shared_core:
    - source_and_snapshot_identity
    - provenance
    - evidence_envelope
    - provider_contract
    - routing_and_sufficiency
    - freshness_contract
    - egress_policy
    - cost_latency_telemetry
    - evaluation_hooks
  code_specific:
    - exact_search
    - ast
    - lsp
    - scip
    - compiler_build_graphs
    - static_analysis
  document_specific:
    - page_heading_layout_parsing
    - ocr
    - enterprise_connectors
    - document_acl_sync
  separate_providers:
    company_memory: gbrain_like
    narrative_graph: microsoft_graphrag_like
  deterministic_contracts:
    packaging: optional_check_job
    retrieval_dependency: false

provider_strategy:
  exact:
    build: false
    candidates:
      - ripgrep
      - zoekt
      - opengrok
  semantic:
    current_holusight: true
    optional_external_candidates:
      - voyage
    mandatory: false
  structural:
    build_compiler_graph: false
    candidates:
      - scip
      - lsp_serena
      - graphify
      - kythe
  repo_map:
    baseline:
      - aider_style_map
  memory:
    build_clone: false
    candidate_pattern:
      - gbrain
  enterprise_search:
    build_broad_platform: false
    controls:
      - glean
      - microsoft_365
      - onyx

holus_axi:
  stable_jobs:
    - "holus"
    - "holus evidence <question>"
    - "holus check [scope]"
    - "holus status"
    - "holus providers"
  provider_override:
    flag: "--mode auto|exact|semantic|structure"
  diagnostics:
    - "--provider"
    - "--explain-route"
  formats:
    default_agent: toon
    canonical_machine: json
    human: text
  expansion:
    - "--full"
    - "--fields"
  no_args_view:
    - repository
    - snapshot
    - dirty_state
    - provider_freshness
    - egress_mode
    - contract_summary
    - recent_cache_summary
  empty_state:
    definitive: true
  errors:
    structured: true
    distinguish:
      - no_evidence
      - provider_unavailable
      - provider_stale
      - access_denied
      - unsupported_question
      - budget_exceeded
  ambient_hooks:
    opt_in: true
    content_injection_default: false
    clients:
      - Claude
      - Codex
      - OpenCode
  skill:
    name: /holus
    generated_from_versioned_contract: true

interface_decision:
  axi_cli:
    role: default_agent_surface
    evidence: promising_but_maintainer_run
  mcp:
    role: optional_adapter
    canonical_architecture: false
  direct_library_api:
    role:
      - embedded_integrations
      - tests
    comparative_task_evidence: missing

proof_gates:
  advancement_requires_one_of:
    task_correctness_absolute_gain: ">=10 percentage points"
    total_cost_per_correct_task_reduction: ">=25%"
    human_active_time_reduction: ">=25%"
  non_regression:
    citation_location_validity: ">=99% on evaluation set"
    stale_evidence_acceptance: 0
    cross_repository_or_client_leakage: 0
  retention:
    design_partners_remaining_after_6_to_8_weeks: ">=4 of 5"
  measurements:
    - completed_task_correctness
    - evidence_completeness
    - citation_validity
    - freshness
    - turns
    - total_input_output_cache_tokens
    - model_cost
    - indexing_amortization
    - wall_clock_time
    - human_active_time
    - egress
    - maintenance_time

benchmark_conditions:
  - native_agent_tools
  - native_tools_plus_compact_repo_map
  - current_holusight_semantic
  - mature_external_platform
  - routed_holus_evidence
  rule: >
    Include tasks deliberately expected to favor the baseline; do not benchmark
    only semantic or ambiguous questions.
  books_and_public_corpora:
    allowed_for:
      - scale
      - ingestion
      - retrieval_mechanics
      - cost_stress
    accepted_as_product_proof: false

evolution:
  pin:
    - repository_snapshot
    - task_set_version
    - provider_version
    - embedding_model
    - reranker_model
    - frontier_agent_model
    - prompt_skill_version
    - judge_version
    - routing_policy
  deployment:
    - frozen_eval
    - shadow
    - paired_comparison
    - canary
    - promote_or_rollback
  telemetry:
    default: local
    aggregate: opt_in
    source_content_collection_default: false
  delete_provider_when:
    - no_unique_critical_evidence
    - dominated_on_quality_cost_privacy_latency
    - no_task_success_contribution
    - excessive_staleness_or_operations
    - negligible_real_usage

roadmap:
  initial_quarter:
    goal: falsify_need_with_real_repository_tasks
    broad_platform_work: false
  following_quarter:
    goal: evidence_envelope_and_axi_contract_prototype_if_authorized
  following_half_year:
    goal: small_design_partner_repository_pilots_if_gates_allow
  second_year_early:
    goal: team_gateway_only_if_shared_usage_and_security_gates_pass
  second_year_late:
    goal: optional_document_or_memory_connectors_only_on_proven_demand
  end_state_options:
    - repository_evidence_layer
    - lighter_semantic_cli
    - repository_contract_product
    - status_quo_composition
    - stop_product

stop_conditions:
  status_quo_wins_if:
    - native_plus_repo_map_within_3pp_correctness_and_router_has_no_material_economic_gain
    - router_saves_less_than_roughly_20_to_25_percent_time_or_cost
  semantic_cli_wins_if:
    - semantic_has_unique_repeated_value_but_multi_provider_routing_does_not
  contracts_win_if:
    - deterministic_checks_have_repeat_usage_and_buyer_but_exploratory_evidence_does_not
  existing_platform_wins_if:
    - equivalent_outcomes_privacy_provenance_with_materially_lower_adoption_and_operations_cost
  remove_semantic_default_if:
    - used_in_less_than_roughly_10_percent_of_successful_tasks_without_unique_critical_wins
  stop_holusight_if:
    - gains_exist_only_in_retrieval_metrics_not_final_task_outcomes

do_not_build:
  - proprietary_vector_database
  - proprietary_lsp_or_scip_replacement
  - proprietary_compiler_build_graph
  - graphrag_clone
  - universal_company_information_router
  - broad_enterprise_connector_catalog
  - generic_coding_agent
  - gbrain_clone
  - mandatory_multitenant_saas_control_plane
  - model_hosting_platform
  - retrieval_token_reduction_as_standalone_success_metric

key_sources:
  holus_capability_inventory:
    url: https://github.com/camilojourney/holusight/blob/master/specs/010-capability-inventory.md
  holus_architecture:
    url: https://github.com/camilojourney/holusight/blob/master/ARCHITECTURE.md
  coding_agents_long_context:
    url: https://arxiv.org/abs/2603.20432
  coderag_bench:
    url: https://arxiv.org/abs/2406.14497
  lara:
    url: https://arxiv.org/abs/2502.09977
  graphrag:
    url: https://github.com/microsoft/graphrag
  voyage:
    url: https://docs.voyageai.com/docs/embeddings
  graphify:
    url: https://github.com/Graphify-Labs/graphify
  gbrain:
    url: https://github.com/garrytan/gbrain
  gbrain_evals:
    url: https://github.com/garrytan/gbrain-evals
  sourcebot:
    url: https://github.com/sourcebot-dev/sourcebot
  zoekt:
    url: https://github.com/sourcegraph/zoekt
  scip:
    url: https://github.com/scip-code/scip
  opengrok:
    url: https://github.com/oracle/opengrok
  kythe:
    url: https://kythe.io/docs/kythe-overview.html
  aider_repomap:
    url: https://aider.chat/docs/repomap.html
  serena:
    url: https://github.com/oraios/serena
  axi_study:
    url: https://github.com/kunchenguid/axi/blob/main/bench-github/published-results/STUDY.md
  notation_matters:
    url: https://arxiv.org/abs/2605.29676
  mcp:
    url: https://modelcontextprotocol.io/specification/draft/server/tools

final_decision_rule: >
  Do not ask whether Holusight can build a more complete retrieval stack.
  Ask whether a small evidence layer measurably improves correct repository
  outcomes after strong agents, exact search, repository maps, structural
  tools, and mature products have already been given a fair chance to win.
```