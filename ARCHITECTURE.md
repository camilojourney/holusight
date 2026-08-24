# Architecture -- CodeSight

> Guided tour of the codebase. WHY things are built, not just WHAT.
> **Last Updated:** 2026-08-23

---

## System Overview

```
User (non-technical)
      |
      |  Web browser / Slack / CLI
      v
+-----------------------------------------+
|           Interface Layer               |
|  Streamlit Chat UI  |  CLI  |  (Slack)  |
+----------+----------+------+-----------+
           |
           v
+-----------------------------------------+
|        CodeSight Python API             |
|        (src/codesight/api.py)           |
|                                         |
|  index(folder)  search(query)           |
|  ask(question)  status()                |
+----------+------------------------------+
           |
     +-----+--------------------------+
     |                                |
     v                                v
+----------+              +--------------+
| Indexer   |              | Search       |
|           |              |              |
| Walk files|              | BM25 (FTS5)  |
| Parse docs|              | Vector search|
| Chunk     |              | RRF merge    |
| Embed     |              | Reranker     |
| Store     |              |              |
+----------+              +--------------+
           |                       |
     +-----+------+          +----+----+
     v            v           v         v
  LanceDB    SQLite FTS5   LLM Backend (pluggable)
 (vectors)   (keywords)    ├── Claude API
                            ├── Azure OpenAI
                            ├── OpenAI
                            └── Ollama (local)

Storage: ~/.codesight/data/<folder_hash>/
         |- lance/       (vectors)
         |- metadata.db  (SQLite with FTS5)
```

### Data Flow: What's Local vs External

```
100% LOCAL (no internet, no API, no cost):
├── Document parsing (PDF, DOCX, PPTX)
├── Chunking (code AST + document paragraphs)
├── Embedding (sentence-transformers on CPU/GPU)
├── Indexing (LanceDB + SQLite files on disk)
├── Search (BM25 + vector + RRF merge)
└── Results (ranked chunks with file + page)

OPTIONAL API (higher quality, data goes to Voyage AI):
├── voyage-code-3 embeddings for code files (auto-detected via VOYAGE_API_KEY)
└── voyage rerank-2 reranker (auto-detected via VOYAGE_API_KEY)

EXTERNAL (only when ask() is called — client chooses provider):
└── LLM answer synthesis → Claude API / Azure OpenAI / OpenAI / Ollama (local)
```

---

## Source Layout (`src/codesight/`)

| File            | Purpose                                                                  |
| --------------- | ------------------------------------------------------------------------ |
| `api.py`        | Public Python API. `CodeSight` class — single entry point for all UIs.   |
| `indexer.py`    | Orchestrates the index pipeline: walk -> parse -> chunk -> embed -> store.|
| `search.py`     | Hybrid retrieval: BM25 + vector -> RRF merge -> [reranker] -> results.   |
| `chunker.py`    | AST-based code chunking (tree-sitter) + document chunking (paragraphs).  |
| `parsers.py`    | Document text extraction: PDF (pymupdf), DOCX (python-docx), PPTX.      |
| `llm.py`        | Pluggable LLM backend: Claude, Azure OpenAI, OpenAI, Ollama adapters.   |
| `embeddings.py` | Embedding wrapper: local (sentence-transformers) or API (Voyage/OpenAI). |
| `store.py`      | LanceDB + SQLite FTS5 dual-write. Content hash deduplication.            |
| `config.py`     | Pydantic settings from env vars. Auto-detects Voyage API capabilities.   |
| `git_utils.py`  | .gitignore-aware file walking via `pathspec`.                            |
| `holus.py`      | Read-only Holus v1 lineage export adapter: validation + safe provenance. |
| `consistency.py` | Holusight-AXI documentation-code consistency engine (Phase 1) — classification, concept registry, claim/relationship provenance, evidence packets, consistency checks. See spec 013. |
| `consistency_store.py` | SQLite storage for the consistency cache (`.holusight/consistency.db`). |
| `axi_schema.py` | Versioned `holus` command/output schema - single source of truth for the CLI and generated skill. See spec 015. |
| `axi_providers.py` | `holus` evidence providers (exact/structural/consistency/semantic), thin wrappers over `consistency.py`/`search.py`. |
| `cli_axi.py`    | `holus` CLI entry point - job-oriented command surface (`[project.scripts] holus`). See spec 015. |
| `axi_skill_gen.py` | Generates `.claude/skills/holus/SKILL.md` from `axi_schema.py`. |
| `toon.py`       | Compact TOON output encoder (agent-facing projection boundary only; JSON stays canonical). |
| `fleet_scorecard.py` | Bridges `consistency.py`'s `ConsistencyReport` to Fleet `eval-scorecard.v1.2`-shaped documents; `agentic/manifest.yaml`'s `eval_entrypoint` runner. Local, no-spend. See spec 016. |
| `eval_pilot.py` | Safe continuous-evaluation pilot: frozen case corpus, deterministic runner, candidate lineage, status-quo comparison, Fleet aggregate export (additive, not the declared `eval_entrypoint`). Every result binds to an immutable Git commit/tree subject. Local, no-spend, advisory only. See specs 017, 018, and 021. |
| `improvement_control.py` | Deterministic tracked-manifest review, monotonic evidence-stage validation, recomputed Git-subject applicability for pilot results, constrained research signal, and bounded content-minimized derived records for the existing `holus improve-*` commands. See specs 019 and 021. |
| `retrieval_variation.py` | Fixed local evidence-display baseline/candidate evaluator. It content-addresses benchmark and lineage, separates hard constraints from reward, and leaves promotion to independent human review. See spec 020. |
| `control_storage.py` | Shared no-follow, restrictive, atomic durable writer for gitignored control-plane result/history state. It rejects canonical tracked destinations and symlink aliases. |
| `types.py`      | Shared Pydantic models (SearchResult, Answer, IndexStats, RepoStatus).   |
| `__main__.py`   | CLI entry point: `python -m codesight <command>`.                        |

**Do not add modules at the top level** — new capabilities go inside existing modules or as new submodules.

---

## Public API

```python
from codesight import CodeSight

engine = CodeSight("/path/to/documents")
engine.index()                                    # Index all files
results = engine.search("payment terms")          # Hybrid search (always local)
answer = engine.ask("What are the payment terms?") # Search + LLM answer
status = engine.status()                          # Index freshness check
```

The package root exposes the stable public import surface: `CodeSight`, `ServerConfig`, `Answer`, `IndexStats`, `RepoStatus`, and `SearchResult`. The `CodeSight` class is the single entry point. Streamlit, Slack, CLI, and any future interface all call the same methods.

### The `ask()` Pipeline

```
question -> search(question, top_k=5) -> top chunks    (LOCAL)
         -> format chunks as context
         -> LLM call (pluggable backend)                (EXTERNAL or LOCAL)
         -> Answer(text, sources, model)
```

---

## Document Processing Pipeline

```
File on disk
    |
    |-- Code files (.py, .js, .ts, etc.)
    |   +-- read_text() -> chunk_file() -> chunk_file_ast() [tree-sitter]
    |                                   -> regex fallback   [if no tree-sitter]
    |
    |-- Text files (.md, .txt, .csv)
    |   +-- read_text() -> chunk_file() (sliding windows)
    |
    +-- Documents (.pdf, .docx, .pptx)
        +-- parsers.extract_text() -> chunk_document() (paragraph boundaries)
            |
            |-- PDF: pymupdf -> text per page
            |-- DOCX: python-docx -> text per heading section
            +-- PPTX: python-pptx -> text per slide
```

---

## Retrieval Pipeline (The Core)

```
query string
    |
    +-- [VPRF] embed query → initial vector search → blend top-3 doc vectors
    |         (Vector Pseudo-Relevance Feedback, +1-2% nDCG@10)
    |
    +-----------------------------------------+
    |                                         |
    v                                         v
SQLite FTS5                               LanceDB
BM25 keyword matching                vector similarity
(exact names, dates,                (semantic meaning,
 contract numbers)                   concept proximity)
    |                                         |
    +-----------------+-----------------------+
                      v
             Reciprocal Rank Fusion
             score = sum 1/(k + rank_i)  where k=60
                      |
                      v
             [Metadata Boost]
             filename-matching chunks promoted
             (e.g. query "embeddings" → embeddings.py rises)
                      |
                      v
             [Reranker — optional]
             voyage rerank-2 (if VOYAGE_API_KEY set) → highest MRR lift
             local ms-marco cross-encoder (opt-in, NOT default)
                      |
                      v
               top K chunks
            (with file path + line range)
```

**Why hybrid matters:** Pure vector search misses exact keyword matches (vendor names, contract numbers, dates). Pure BM25 misses semantic synonyms. RRF merges both with zero extra infrastructure. Most cloud competitors use vector-only search — our hybrid approach beats them for scoped document collections.

**Reranker warning:** The local `ms-marco-MiniLM` cross-encoder is trained on MS-MARCO QA pairs and *hurts* code retrieval ranking. Only enable it explicitly. Voyage rerank-2 is code-aware and gives +0.43 MRR lift over voyage-code-3 embeddings alone.

---

## Embedding Layer

```
Dual embedding strategy (code vs documents):

Code files (.py, .js, .ts, .go, etc.):
  IF VOYAGE_API_KEY is set (recommended):
    voyage-code-3 (1024 dims) → sent to Voyage AI API
    Trained on code, 93 dataset benchmark, +13.8% NDCG@10 vs OpenAI v3-large
  ELSE (local, no API key):
    all-MiniLM-L6-v2 (384 dims) via sentence-transformers
    Free, private, runs on CPU — lower recall on code-specific queries

Text/document files (.md, .pdf, .docx, etc.):
  all-MiniLM-L6-v2 (384 dims) — sentence-transformers (always local)

Configurable via CODESIGHT_EMBEDDING_MODEL + CODESIGHT_EMBEDDING_BACKEND
```

---

## Chunking Strategy

### Code Files — AST-Based (tree-sitter)

For Python, JavaScript, and TypeScript, `chunk_file_ast()` uses tree-sitter to parse the file and extract top-level scope nodes (functions, classes, async functions, decorated definitions).

**Algorithm (cAST approach, EMNLP 2025):**
1. Parse with tree-sitter, collect top-level scope nodes
2. **Merge tiny siblings** (< 5 lines) with the next sibling — prevents stub-function fragments
3. **Sub-split oversized nodes** (> max_lines) with sliding windows
4. **Leading/trailing code** (imports, module docstrings, constants) becomes its own chunk

```
def alpha():          → Chunk 1: function alpha (if >= 5 lines)
    ...

def beta():           → Chunk 2: function beta (if >= 5 lines)
    ...

import os             → Leading chunk (imports before first function)
import sys
```

**Why better than fixed windows:** Function boundaries are semantically complete. A fixed 200-line window can split a function in half, making both halves harder to retrieve. AST chunking gave +0.224 MRR@10 in benchmark (0.599 → 0.823).

**Fallback chain:** tree-sitter AST → regex boundary patterns → sliding window

### Documents
Paragraph-aware splitting respecting page boundaries. Each chunk gets metadata:
- `start_line` / `end_line` = page numbers
- `scope` = heading or "page N"
- `language` = "pdf", "docx", "pptx"

### Context Headers
Every chunk gets a context header prepended before embedding:
```
# File: src/codesight/search.py
# Scope: function hybrid_search
# Lines: 189-303
```

This implements Anthropic's contextual retrieval technique — prepending file/scope context reduces retrieval failures by 35–67%.

---

## LLM Backend (Pluggable)

The LLM is only used by `ask()` — search runs without it.

```
CODESIGHT_LLM_BACKEND=claude    → Anthropic API (best quality)
CODESIGHT_LLM_BACKEND=azure     → Azure OpenAI (data in client's tenant)
CODESIGHT_LLM_BACKEND=openai    → OpenAI API
CODESIGHT_LLM_BACKEND=ollama    → Local model, zero network (privacy-first)
```

Client chooses based on their security requirements. We are never in the middle.

---

## Storage Layout

All indexes live in `~/.codesight/data/` (outside the indexed folder — never write inside it).

```
~/.codesight/data/
+-- <sha256(folder_path)[:12]>/
    |-- lance/            <- LanceDB vector tables
    |   +-- chunks.lance  <- chunk_id, embedding vector (all-MiniLM or voyage)
    |   +-- code_chunks.lance  <- chunk_id, code embedding (voyage-code-3, if available)
    +-- metadata.db       <- SQLite with FTS5 virtual table
        |-- chunks         <- chunk_id, content, file_path, lines
        |-- chunks_fts     <- FTS5 index (auto-synced via triggers)
        +-- repo_meta      <- last_indexed_at, last_commit, etc.
```

**Content hashing:** Each chunk is hashed `sha256(content)[:16]`. On re-index, unchanged chunks are skipped entirely — no re-embedding, no write.

---

## Performance Benchmarks

Measured on the holusight codebase (96 files, 20 representative queries):

| Configuration | Hit Rate | MRR@10 | Notes |
|--------------|----------|--------|-------|
| Baseline (fixed windows, no reranker) | 52.5% | 0.352 | v0.2 |
| + VPRF + voyage reranker | 100% | 0.599 | Phase 1 |
| + AST chunking (tree-sitter) | 100% | 0.823 | Phase 2 — largest lever |
| + voyage-code-3 + voyage rerank-2 | 100% | **0.793** | Phase 4 — best overall |

**Key finding:** AST chunking was the single largest lever (+0.224 MRR). The local ms-marco cross-encoder *hurts* code retrieval. voyage rerank-2 adds +0.43 MRR on top of voyage-code-3 embeddings alone.

The 20-query table above is the original harness (`just eval`, still the default). An expanded local eval harness (`just eval-taxonomy`, 85 queries across 7 families) adds exact/BM25-only/Graphify-structural baselines, Recall@K/nDCG/evidence-completeness/latency metrics, and an opt-in embedding-model variant runner — see `specs/014-retrieval-evaluation-harness-expansion.md`. It is a bounded local vertical slice, not a production benchmark; see that spec's Limitations section before citing its numbers.

---

## Deployment Tiers

| Tier | Users | Deployment | Embedding | Reranker |
|------|-------|-----------|-----------|----------|
| Single-team pilot | One team | Docker/VM + FastAPI + shared API key | local default or customer-selected API | optional |
| Future larger deployment | Not claimed | Requires separate design | Depends on deployment | Depends on deployment |
| Air-gapped pilot | One team | On-prem server | local model | off |

---

## Holusight-AXI Consistency Layer (Phase 1, added 2026-08-22)

A separate, self-referential subsystem that keeps this repository's own
specs/ADRs/architecture docs consistent with the code they describe. Full
architecture is `specs/013-holusight-axi-consistency-architecture.md`; the
one-database storage decision is
`docs/decisions/0011-single-sqlite-consistency-store.md`. Summary:

```
python -m codesight consistency refresh .        (rebuild the cache)
python -m codesight consistency evidence <id> .   (pre-change evidence packet)
python -m codesight consistency check <id> .      (post-change consistency check)
python -m codesight consistency status .          (concepts + open health flags)
```

- **Purpose-aware classification**: every tracked file is classified by
  *why it exists* (specification, decision, architecture, implementation,
  test, devlog, report, ...), derived from this repo's own directory
  contract (`.claude/rules/structure.md`), not from its words.
- **Concept registry**: one concept per canonical `specs/NNN-*.md` or
  `docs/decisions/NNNN-*.md` file — this repo already enforces
  one-feature-per-numbered-spec, so the file *is* the concept scope.
- **Three distinguishable evidence providers**, each carrying an explicit
  `confidence` and `evidence` payload: `exact` (deterministic path-token
  extraction from spec/ADR prose, resolved against the filesystem —
  including flagging *dangling* references that don't resolve), `structural`
  (sourced from the tracked `graphify-out/graph.json`, with an explicit
  staleness flag against current `HEAD`), and `semantic` (local
  sentence-transformers similarity, **opt-in only**, never called by
  default, never used to establish canonical authority).
- **Claim registry**: a small, explicit, hand-registered set of named
  invariants already called out in this file's "What NOT to Change Without
  Discussion" section below (RRF `k`, AST `min_lines`, content-hash length,
  data directory location) — each claim's doc-side and code-side values are
  regex-extracted and compared. This is intentionally not a general
  natural-language claim extractor.
- **Incremental cache**: `.holusight/consistency.db`, one atomic SQLite
  file. **`.holusight/` is gitignored derived state, never canonical
  truth** — delete it any time; the next `refresh` rebuilds it. Only
  artifact classification is content-hash-gated today; edge/claim/health
  recomputation is a full pass each refresh (acceptable at this
  repository's ~125-file scale — see spec 013 §5 for the scale-out
  trigger).
- **Evidence packet / consistency check**: `evidence` assembles everything
  known about one concept before a change (repo snapshot, canonical
  artifact, edges/claims, open health flags) without modifying anything.
  `check` compares current on-disk content hashes against the cache's
  last-refreshed hashes and classifies the result (`up_to_date`,
  `spec_changed_awaiting_implementation`, `possible_undocumented_drift`,
  `coordinated_change`) — deterministic hash-diffing, not semantic value
  comparison.
- **Known limitation**: exact-reference extraction cannot distinguish a
  real path reference from a fictional illustrative path inside research
  prose (e.g. specs 011/012 cite invented paths like `src/payments/service.py`
  as worked examples) — both surface as `DANGLING_REFERENCE`. The first real
  run also found two genuine pre-existing dangling references:
  `docs/decisions/0010-graphify-extension-contract.md` pointed at
  `docs/capabilities.md` (fixed in this PR — repointed to the real
  `specs/010-capability-inventory.md`), and
  `docs/decisions/0006-two-deployment-modes.md` points at
  `specs/002-deployment-modes.md` (left unfixed — the ADR describes an
  architecture, Qdrant/PostgreSQL/MinIO/Azure AI Search, that doesn't match
  anything currently implemented; the right fix is a human product
  decision, not a guessed repoint).
- **Out of scope for Phase 1**: no change planner, no artifact-creation
  governance, no CI enforcement/merge blocking. See spec 013 §4 for the
  full non-goals list.

---

## `holus` - Holusight-AXI Command Surface (Phase 1, added 2026-08-23)

A job-oriented CLI (`[project.scripts] holus`, see spec 015) over the
already-landed consistency engine above and the already-shipped
`search.hybrid_search`. Not a new retrieval mechanism - a thin,
AXI-compliant command surface:

```
holus                        content-first repository home view
holus evidence "<question>"  routed evidence packet
holus check [scope]          post-change consistency check
holus status                 repository/provider status
holus providers              provider availability/freshness/egress

--mode auto|exact|semantic|structure   (diagnostic, beneath the jobs above)
--provider exact|structural|consistency|semantic
--explain-route
```

- **Providers** (`src/codesight/axi_providers.py`): `exact` (literal/token
  scan), `structural` (reads `graphify-out/graph.json` via the same
  `consistency._load_structural_index`/`structural_graph_freshness` PR
  #17's `graphify` eval baseline reuses), `consistency` (the cache above),
  `semantic` (`hybrid_search` against an **already-built** local index
  only - never auto-indexes, never a side effect of a read-only job).
  Every provider reports one of `ok`/`no_evidence`/`unavailable`/`stale`/
  `denied`/`unsupported`/`budget_exceeded` - never a fabricated answer.
- **Egress**: off by default. The CLI strips `VOYAGE_API_KEY` from its own
  process environment for every provider call unless `--allow-egress` is
  passed; the semantic provider additionally reports `denied` if the
  local index's stored embedding model is Voyage and `--allow-egress`
  wasn't given.
- **Output**: JSON is the lossless canonical contract; `--format toon`
  (default) is a compact agent-facing projection (`src/codesight/
  toon.py`) generated only at the output boundary; `--format text` is
  human-readable. `--fields a,b.c` projects any payload to dotted paths.
- **Schema/skill drift**: `src/codesight/axi_schema.py` is the single
  source of truth for commands/flags; `axi_skill_gen.py` generates
  `.claude/skills/holus/SKILL.md` from it; `tests/test_axi_skill_drift.py`
  fails the normal `pytest` run if the two diverge.
- **`check` baseline**: never auto-refreshes (that would erase the drift
  signal it exists to detect); `holus`/`status`/`providers`/`evidence`
  bootstrap the cache once if it has never been built. Pass `holus check
  --refresh` to explicitly reset the baseline.

---

## Fleet v1.2 Protocol Pilot (Added 2026-08-23)

Wires the consistency evaluator above and this repo's manifest to Fleet's
canonical, now-landed `v1.2` agentic contracts (`github.com/camilojourney/
fleet-system` @ `7d396b3`, [PR #58](https://github.com/camilojourney/fleet-system/pull/58))
without vendoring those contracts into this repository. Full design
record: `specs/016-fleet-v1.2-protocol-pilot.md`; decision record:
`docs/decisions/0012-fleet-v1.2-protocol-wiring.md`.

```
agentic/manifest.yaml   fleet.repo_agent_manifest.v1.2 -- eval_entrypoint,
                        privacy boundary, provenance_policy
agentic/memory.yaml     fleet.memory_policy.v1.1 -- fleet_visibility,
                        byte-identical to manifest.yaml's privacy boundary
src/codesight/fleet_scorecard.py
  build_eval_scorecard()      ConsistencyReport -> fleet.eval_scorecard.v1.2
                               (Holusight's own honest local preview -- see
                               spec 016 §6 for why this is not yet what
                               Fleet's own runner emits)
  domain_result_summary()     the minimal JSON object `run_repo_eval.py`'s
                               parse_domain_result() actually reads from the
                               entrypoint's last stdout line
  main() / `just fleet-smoke` runs tests/test_fleet_smoke.py, then prints
                               domain_result_summary() as the last line
```

- **Honest outcome mapping**: `consistency.py`'s four outcomes map to
  `gate_decision`/`hidden_correctness` conservatively — only `up_to_date`
  is `pass` (the one claim deterministic hash-diffing can stand behind);
  `possible_undocumented_drift` is `fail`; the other two changed-but-
  unconfirmed outcomes are `hold`, never `pass`. See spec 016 §5.
- **No spend, no telemetry, no promotion**: only the `exact`/`structural`
  providers run (`run_semantic` stays `False` everywhere in this pilot);
  nothing here makes a network call; `gate_decision` is informational
  output only — nothing in this repository acts on it automatically. See
  spec 016 §7.
- **Smoke suite**: `tests/test_fleet_smoke.py`, 20 local tasks, proves
  partial-result survival (missing/corrupt `graphify-out/graph.json`
  degrades the structural provider without raising) and that deleting
  `.holusight/` and rebuilding reproduces an equivalent Fleet-shaped
  scorecard, not just equivalent artifact counts.
- **Does not duplicate `holus`**: calls `consistency.check_consistency()`
  directly — the same function `holus check` calls — rather than adding a
  second CLI surface.

---

## Safe Continuous-Evaluation Pilot (Added 2026-08-23)

The smallest useful local, no-spend continuous-evaluation loop over
already-shipped `holus`/consistency-engine behavior. Full design record:
`specs/017-holusight-safe-continuous-evaluation-pilot.md`; decision
record: `docs/decisions/0013-eval-pilot-scope-boundaries.md`; case
admission: `docs/playbooks/eval-pilot-case-admission.md`.

```
tests/fixtures/holusight_eval_pilot_cases.jsonl   frozen, human-admitted
                                                   case corpus (4 seed
                                                   cases)
src/codesight/eval_pilot.py
  run_pilot()                       runs every frozen case, records
                                     CandidateLineage, catches grader
                                     errors as retained verdict="error"
  build_pilot_aggregate_scorecard() content-free fleet.eval_scorecard.v1.2
                                     preview (counts/rates/hashes only)
  pilot_domain_result_summary()     minimal parse_domain_result()-shaped
                                     dict, mirroring fleet_scorecard.py's
                                     precedent
just eval-pilot                     runs it locally; NOT
                                     agentic/manifest.yaml's declared
                                     eval_entrypoint (still `just
                                     fleet-smoke`, unchanged)
```

- **One genuine candidate-vs-status-quo comparison**: the
  `cli-axi-provider-starvation-display-quota` case runs the shipped PR #20
  fix (`cli_axi._select_display_items`) against a frozen, pilot-only
  pre-fix comparator (`eval_pilot._naive_concatenate_then_slice`, never
  imported by production code) on a synthetic fixture reproducing the
  historical starvation shape.
- **Three deterministic regression cases** anchored to already-documented
  spec 013/015 contracts (dangling-reference detection, hash-diffing
  up-to-date check, egress-off-by-default) — all local, no embeddings, no
  network.
- **Advisory only**: nothing in this repository reads a verdict from this
  module and takes an automatic action. `provenance_policy.
  default_training_eligibility` in `agentic/manifest.yaml` stays `false`,
  untouched.
- **Not the 96-task suite** specs 011/012 describe — deliberately narrower
  than even spec 012's own "Free smoke" experiment-ladder stage. See spec
  017 §9 for the explicit boundary.
- **Documents, does not fix**, the spec 002 default-drift finding (spec
  002's "Status Note", 2026-08-23): the shipped embedding default is
  `all-MiniLM-L6-v2`/`voyage-code-3`, never the `nomic-embed-text-v1.5`
  spec 002's table states.

---

## Continuous-Improvement Loop v1 (Added 2026-08-23)

Four new `holus` commands (`AXI_SCHEMA_VERSION` `0.1.0` -> `0.2.0`) that
turn the eval pilot above into a discoverable, machine-readable lifecycle,
plus a standalone repository-placement guard. Full design record:
`specs/018-holusight-continuous-improvement-loop.md`; decision record:
`docs/decisions/0014-continuous-improvement-loop-placement-guard.md`.
Adds no new provider, retrieval mechanism, or Fleet contract — a thin
lifecycle wrapper over `eval_pilot.py` (spec 017) and the same
`.claude/rules/structure.md` contract `consistency.py`'s classifier
already depends on (spec 013).

```
holus improve-status       frozen-case corpus + status-quo coverage + placement capability
holus improve-intake "<gap>"   opt-in, content-minimized proposed regression case (no write)
holus improve-run          runs the frozen corpus; lineage; research_needed/stagnated/improved
holus improve-placement    validates a proposed artifact path; never edits files
```

- **Intake is opt-in and content-minimized, never a silent capture.**
  `eval_pilot.build_intake_proposal` truncates the caller-supplied summary
  to 240 characters and never opens the frozen case file for writing.
  Turning a proposal into a real case is still the unchanged, ordinary
  human-reviewed PR process `docs/playbooks/eval-pilot-case-admission.md`
  already documents — `improve-intake` only generates the paste-ready
  skeleton.
- **`improve-run` adds structured stagnation/research-needed detection**
  (`eval_pilot.evaluate_progress`) on top of the unchanged `run_pilot`:
  comparing two runs' `counts` only (no case content) yields one of
  `improved` / `research_needed` / `stagnated`, each carrying a
  `recommended_research` label (`normal_review` or `gpt_deep_research`) —
  a string only; nothing here launches research automatically. Every
  response also carries `lifecycle.promotion = {"allowed": false, ...}`
  unconditionally — promotion and rollback stay human-controlled.
- **Placement compliance is evidence-only.** `improve-placement`
  (`cli_axi._placement_recommendation`) checks canonical-location
  membership, per-type structural rules (`specs/` flat; `docs/` limited
  to its three fixed root files, not the ad-hoc `docs/RESEARCH.md`-shaped
  legacy violation pattern `AGENTS.md` already names; `test` files must be
  `test_*.py` directly under `tests/`), and duplicate-artifact-name
  detection — then returns a recommended existing-or-new path. It never
  creates a directory or file, and an absolute or repo-escaping
  `--proposed-path` never reaches a filesystem check against anything
  outside this repository (`cli_axi._safe_repo_relative_path`).
- **Proven end to end**: `improve-run` reproduces the real, already-fixed
  `cli-axi-provider-starvation-display-quota` regression (PR #20) through
  the new CLI surface; `improve-placement` blocks a real duplicate-
  artifact case (`tests/test_eval_pilot.py`, already exists). See spec 018
  §4.1/§6.1 and `tests/test_improve_loop.py` (29 tests, including explicit
  refusals of evaluator mutation, private/raw-content export, automatic
  promotion, external egress, and unsupported placement).

---

## Research-to-Improvement Control Plane v1 (Added 2026-08-23)

A deterministic review layer over the existing continuous-improvement loop,
not a new workflow engine or Fleet contract. Full design record:
`specs/019-research-to-improvement-control-plane.md`; decision record:
`docs/decisions/0015-deterministic-improvement-review-records.md`; operating
guide: `docs/playbooks/improvement-control-review.md`.

```
tracked *.change.json manifest
  -> holus improve-review <manifest> --phase <step>
  -> classification + stage + missing evidence + blockers + next action
  -> optional .holusight/improvement-runs/<change-id>/ record
  -> holus improve-history <change-id>
  -> holus improve-integration <manifest> (future local consumer contract)
```

- **Authority is exact and repository-local.** The manifest classification,
  required structured sections, canonical role paths, SHA-256 link hashes, and
  structured Markdown status markers determine the result. No model infers
  authority from prose. Accepted/implemented/evaluated conclusions require
  governing, implementation, test, documentation, evaluation-case, and
  evaluation-result links. Research-only, rejected, and superseded material
  never falsely requires code.
- **Stepwise and advisory only.** The four phases are `before_change`,
  `after_implementation`, `after_test`, and `pre_promotion`. Every result has
  `promotion.allowed: false`; a complete pre-promotion review permits only
  human promotion review. Placement, evaluator mutation, dangling, stale,
  duplicate, wrong-role, and contradictory evidence block progression.
- **Derived state is minimized and rebuildable.** `--record` is opt-in and
  stores only stage/outcome, hashes, lineage, references, and blocker codes in
  gitignored `.holusight/`. It stores no source/prompt content, private data,
  credentials, or production telemetry. Delete it and rerun the review to
  rebuild without changing canonical truth.
- **Research does not run itself.** A `research_needed` packet is emitted only
  for contradictions, material incompleteness/unfamiliarity, or repeated
  blocked history. It may name normal review or a precise GPT Deep Research
  question, always with `external_action: "not_launched"`.

---

## Controlled Retrieval Variation Program v1 (Added 2026-08-24)

A small local experiment inside the existing `holus improve-*` control plane,
not a candidate-generation framework. Full design record:
`specs/020-controlled-retrieval-variation-program.md`; decision record:
`docs/decisions/0016-controlled-retrieval-variation-boundary.md`; operator
workflow: `docs/playbooks/run-retrieval-variation-program.md`.

```
clean tracked benchmark + frozen legacy baseline
  -> production display selector + one fixed alternate, with executable hashes
  -> deterministic baseline/candidate evaluation + identical typed replay
  -> hard constraints kept separate from provider-coverage reward
  -> failed/inconclusive outcomes retained in no-follow typed derived state
  -> recomputation + clean tracked manifest anchor at holus improve-review
  -> independent human decision (never automatic promotion)
```

The benchmark covers exact, hybrid, graph/impact, ambiguity, no-evidence, and
adversarial provider-flood cases. A synthetic semantic-provider case tests
routing without invoking a model or egress. Every run pins the benchmark,
supporting fixture, evaluator, executable baseline/candidate definitions, and
result identities. Malformed, partial, tampered, unanchored, or independently
unrecomputable results fail closed. Aggregate-only feedback
can propose a future ordinary fixture-review PR, but cannot change a label,
threshold, evaluator, authority, or canonical truth.

---

## Evidence Subject Binding v1 (Added 2026-08-24)

Closes gap G1 from a captain-authorized completeness review of specs
017-020: a manifest link path was a locator, but review never proved the
linked implementation/tests/documentation/evaluation-case were the exact
bytes a linked eval-pilot result was evaluated against. Full design record:
`specs/021-holusight-evidence-subject-binding.md`; decision record:
`docs/decisions/0017-immutable-evaluation-subject-binding.md`.

```
run_pilot() -> PilotRunResult.subject = {repository_id, commit, tree,
                                          clean, branch (annotation only)}
                                          computed from real Git state, not
                                          caller input
holus improve-review --phase pre_promotion
  -> _subject_applicability_blockers() recomputes, for implementation/
     tests/documentation/evaluation_case links only:
       subject clean+resolvable, repository identity, commit still exists,
       tree matches, every linked path resolves to the same Git blob at the
       evaluated commit as it has on disk right now
  -> any mismatch (dangling/stale/wrong_tree/changed) demotes stage away
     from "evaluated" via the existing _stage() blocker-prefix mechanism,
     so it can never reach pre_promotion's human_promotion_review
```

`EvaluationSubject.clean` also closes a real pre-existing loophole: a
non-Git directory previously read as "not dirty" (`git status` simply fails
there), letting an eval-pilot result produced outside a real repository
still become promotion-relevant evidence. It is now `dangling_evaluation_subject`.
A manifest-only descendant commit that touches nothing consequential stays
applicable — the check compares blobs and tree/commit identity, never
commit recency or the manifest's own branch name (an inert annotation
only). `retrieval_variation.py`'s own applicability check (full
re-execution and byte-comparison against current tracked `HEAD` on every
load) is untouched — a different, already-adequate mechanism for that
subsystem. No new manifest field, link role, or promotion mechanism was
added; the six existing link roles and the `promotion.allowed: false`
boundary are unchanged. `AXI_SCHEMA_VERSION` moved `0.5.0` -> `0.6.0`
(one new required result field).

---

## Context Injection Integration (Added 2026-04-04)

CodeSight is used as a runtime context provider inside the OpenClaw skill pipeline. When a developer runs `/code` on any repo, `codesight_context.py` searches that repo's index and injects the top-5 relevant chunks into the Codex prompt.

```
/code skill invoked
  → fleet_brain_hook.py "$REPO" "code"     (~150 tokens, project state)
  → codesight_context.py "$REPO_PATH" "$TASK"  (~1000-2000 tokens, code context)
  → both injected into RICH_TASK for Codex
```

**Key design decisions:**
- Engine lives in `holusight/src/codesight/` — shared across all repos
- Index is per-repo at `~/.codesight/data/<sha256(repo_path)[:12]>/` — isolated, no cross-repo bleed
- VOYAGE_API_KEY loaded from `holusight/.env` explicitly in `codesight_context.py` (not from CWD)
- Batch size capped at 8 chunks/request to stay under Voyage's 120K token/batch limit
- Stale threshold: 5 min — auto-reindexes changed files on next `/code` invocation

**Experiment results (3×3 eval, 2026-04-04):**
- No context: avg 76.3 | Fleet Brain only: avg 93.0 | Fleet + CodeSight: avg 93.8
- Context helps most on architecturally complex tasks (+25 pts on task requiring dual-store knowledge)
- Easy tasks already near-ceiling without context (99/99/99)

**Repos indexed:** holusight (230 chunks, 28s), pythia (875 chunks, 346s)

---

## What NOT to Change Without Discussion

1. **RRF k=60 constant** — changing this shifts recall/precision tradeoff. Benchmark before changing.
2. **Data directory location** (`~/.codesight/data/`) — changing this invalidates all existing indexes.
3. **Content hash algorithm** — changing from `sha256[:16]` invalidates all deduplication state.
4. **FTS5 trigger schema** — the SQLite triggers that sync FTS5 from the chunks table. Incorrect triggers cause silent search failures.
5. **LLM system prompt** — the `SYSTEM_PROMPT` in `llm.py` controls answer quality across all backends. Test changes with real documents.
6. **AST min_lines=5 threshold** — the merge-small threshold. Lowering it creates fragment chunks; raising it merges logically separate functions. Benchmark before changing.
