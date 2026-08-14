# Graph Report - 01KZWDFFGEQS7EWF3V8NQZE02M  (2026-08-13)

## Corpus Check
- 124 files · ~80,123 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1701 nodes · 2189 edges · 136 communities (124 shown, 12 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 113 edges (avg confidence: 0.51)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `eb62412b`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- chunk_file_ast
- ndarray
- EvalQuery
- CodeSight
- Market Opportunity — Enterprise Knowledge Appliance
- get_backend
- SearchResult
- Playbook: Client Pitch — Questions, Objections, and Answers
- Research — Enterprise Knowledge Appliance
- CodeSight vs CLAUDE.md: Honest Comparison
- Architecture -- CodeSight
- Spec: Go-To-Market — Where to Sell, Who to Sell To, and How
- TestPathTraversal
- Research: Multi-Model Embedding Architecture for Maximum Retrieval Accuracy
- Workflow: Explore → Plan → Execute → Review
- ChunkStore
- Market — Enterprise Knowledge Appliance
- Spec: Infrastructure & Data Connectors
- ServerConfig
- _cnfb_boost
- chunker.py
- Spec 008: Docker Deployment + FastAPI Production Server
- Spec 004: Tree-sitter Chunking
- Spec 007: Cross-Encoder Reranking
- CodeSight
- Spec 001: Core Search Engine
- Spec: ACL Enforcement — End-to-End Access Control
- Question: Challenge voyage rerank-2.5 and LLM query expansion assumptions for 2026
- indexer.py
- Spec 006: Pluggable LLM Backend
- Implementation Notes
- AI-Powered Document Search for [Company Name]
- Spec: Deployment Modes
- FTSSidecar
- extract_text
- rrf_merge
- test_mcp.py
- _auth_headers
- Presentation Deck — Slide-by-Slide Script
- ADR 0002: Security-Critical Decisions Require Human Escalation
- ADR 0009: Retrieval Experiments — CNFB + Contextual Retrieval
- SPEC-009: CNFB — Query-Aware Multiplicative Filename Boost
- .upsert_chunks
- Roadmap — codesight
- TestFTSQuerySanitization
- Pitch Prep — What to Know Before Every Meeting
- Repository Structure -- codesight
- Pitch Prep — What to Know Before Every Meeting
- Vision — codesight
- Spec 002: Embedding Model Configuration
- Spec 003: Incremental Refresh
- _detect_scope
- chunk_file
- [LOGO] Camilo Martinez — AI Consulting
- Spec: Financial Model — Mode A vs Mode B by Company Size
- Mode A: Local-Only
- Mode A: Local-Only
- Mode A: Local-Only
- Mode A: Local-Only
- Alternatives Considered
- docs/README.md
- Playbook: Development Setup
- __main__.py
- After Contract Signed
- app.py
- ADR 0001: Support Two Deployment Modes from Day One
- After Contract Signed
- Playbook: Ship a Feature
- Self-Improvement Memory — codesight
- Spec Templates
- store.py
- ._delete_vectors_by_ids
- TestMCPSearchTool
- consulting-market-expert Memory -- camilo-martinez-consulting
- static-analysis-expert Memory -- codesight
- Playbook: Investigate a Bug
- NEXT — codesight
- Spec 005: Automatic Re-indexing
- Implementation History
- test_deployment.py
- Sales Process — Lead to Close
- Delivery Planner — Memory
- business-analyst.md
- delivery-planner.md
- model-quality-auditor.md
- prompt-optimizer.md
- proposal-writer.md
- ADR-0000: [Short Decision Title]
- ADR-0001: LanceDB Over ChromaDB for Vector Storage
- ADR-0002: Hybrid BM25 + Vector + RRF Retrieval
- ADR-0003: Strict Read-Only Invariant on Indexed Repositories
- Sales Process — Lead to Close
- Knowledge: Static Analysis Techniques
- .set_meta
- vercel.json
- Business Analyst — Memory
- code-improver Memory — codesight
- judge-agent Memory — codesight
- model-quality-auditor Memory — codesight
- Proposal Writer — Memory
- security-sentinel Memory — codesight
- code-improver.md
- consulting-market-expert.md
- judge-agent.md
- manager.md
- security-sentinel.md
- 0005 — Unified Consulting Repo into CodeSight
- Knowledge Base — codesight
- TestReadOnlyInvariant
- Closed Deals — Won & Lost
- vprf_enhance_query
- .get_chunk_metadata
- Recommended SMB Pilot Offer
- Quick Reference — Cost Drivers
- Knowledge Request Queue
- rules/graphify.md
- workflows/graphify.md
- leads.md
- conventions.md
- research/README.md
- codesight
- server.py
- Docker deployment playbook
- app.js
- .clamp_cnfb_alpha
- CodeSight
- Spec 010: Capability Truth Inventory
- _detect_language
- ADR 0010: Graphify Extension Contract (Not Integrated in v1)
- config.py
- auth_utils.py
- payment-terms.md
- pilot_docs/README.md

## God Nodes (most connected - your core abstractions)
1. `CodeSight` - 49 edges
2. `ChunkStore` - 47 edges
3. `ServerConfig` - 40 edges
4. `SearchResult` - 37 edges
5. `FTSSidecar` - 25 edges
6. `CodeSight` - 23 edges
7. `IndexStats` - 22 edges
8. `chunk_file()` - 21 edges
9. `index_repo()` - 19 edges
10. `RepoStatus` - 19 edges

## Surprising Connections (you probably didn't know these)
- `TestMCPAskExtension` --uses--> `CodeSight`  [INFERRED]
  tests/test_mcp.py → src/codesight/api.py
- `TestMCPIndexTool` --uses--> `CodeSight`  [INFERRED]
  tests/test_mcp.py → src/codesight/api.py
- `TestMCPSearchTool` --uses--> `CodeSight`  [INFERRED]
  tests/test_mcp.py → src/codesight/api.py
- `TestMCPStatusTool` --uses--> `CodeSight`  [INFERRED]
  tests/test_mcp.py → src/codesight/api.py
- `TestChunkIdSanitization` --uses--> `CodeSight`  [INFERRED]
  tests/test_security.py → src/codesight/api.py

## Import Cycles
- None detected.

## Communities (136 total, 12 thin omitted)

### Community 0 - "chunk_file_ast"
Cohesion: 0.16
Nodes (12): pytestmark_ts, chunk_file_ast(), Split a file using tree-sitter AST nodes (cAST approach). Algorithm: 1. Parse…, Tests for chunk_file_ast() — requires tree-sitter to be installed., Two Python functions each >= min_lines → 2 separate chunks., Two consecutive tiny functions (< min_lines=5) should be merged into one chunk., A function exceeding max_lines should be sub-split into multiple chunks., Module-level imports before the first function → own chunk. (+4 more)

### Community 1 - "ndarray"
Cohesion: 0.09
Nodes (16): APIEmbedder, LocalEmbedder, _normalize_rows(), ndarray, OpenAI embedding API backend — best quality, requires API key., Embed texts via OpenAI API in batches of 512., Embed a single query string., Voyage embedding backend for code retrieval. (+8 more)

### Community 2 - "EvalQuery"
Cohesion: 0.10
Nodes (25): _count_tokens(), EvalQuery, EvalResult, Eval harness for CodeSight search quality and token efficiency. Metrics:…, Estimate token count. Uses tiktoken if available, else len//4., A single eval query with its expected answer location., Aggregate metrics from running the eval harness., Run eval harness over a list of queries against an indexed store. Args:… (+17 more)

### Community 3 - "CodeSight"
Cohesion: 0.05
Nodes (39): Agent Authority Matrix, Agent Authority Matrix, AGENTS.md, Ask First — Propose, wait for approval, Ask First — Propose, wait for approval, Autonomous — No confirmation needed, Autonomous — No confirmation needed, `.claude/` -- Claude Code Configuration (+31 more)

### Community 4 - "Market Opportunity — Enterprise Knowledge Appliance"
Cohesion: 0.05
Nodes (37): 1. Microsoft 365 Copilot Is Disappointing Enterprises, 2. Glean Is Enterprise-Only and Expensive, 3. 95% of GenAI Investments See Zero Return, 4. Regulated Industries Have No Good Options, Competitive Landscape, Competitive Pricing Advantage, Deployment Fee Basis ($15K–100K), Deployment Timeline (Per Customer) (+29 more)

### Community 5 - "get_backend"
Cohesion: 0.06
Nodes (19): Lazy-loaded LLM backend. Only initialized when ask() is called., AzureOpenAIBackend, ClaudeBackend, get_backend(), LLMBackend, OllamaBackend, OpenAIBackend, Protocol (+11 more)

### Community 6 - "SearchResult"
Cohesion: 0.14
Nodes (18): Hybrid BM25 + vector search. Auto-indexes if needed., _get_reranker(), _get_voyage_client(), hybrid_search(), Hybrid search: BM25 + vector + RRF + optional cross-encoder reranking.…, Lazy-load the cross-encoder model (cached for process lifetime)., Rerank results using a local cross-encoder model. Scores each (query,…, Route reranking to voyage API or local cross-encoder based on backend. (+10 more)

### Community 7 - "Playbook: Client Pitch — Questions, Objections, and Answers"
Cohesion: 0.06
Nodes (31): "Can't we just use Claude's Projects feature?", "Can we run this completely offline / air-gapped?", Core Questions, Cost Questions, Data Privacy & Security Questions, Demo Script, During the meeting, "How do documents stay updated?" (+23 more)

### Community 8 - "Research — Enterprise Knowledge Appliance"
Cohesion: 0.07
Nodes (29): 10. Updated Competitive Landscape (2026-03), 11. Vector DB Strategy (Updated 2026-03), 1. Core Technical Approach, 2. ACL Enforcement Research, 3. Embedding & Retrieval Research, 4. Local LLM Research (Mode A), 5. Competitive Technical Analysis, 6. Key Technical Risks (+21 more)

### Community 9 - "CodeSight vs CLAUDE.md: Honest Comparison"
Cohesion: 0.07
Nodes (29): 1. What Each System Actually Does Well (and Where It Fails), 2. Complementary or Redundant?, 3. Token Savings — Quantified, 4. How Cursor Actually Works (vs CodeSight), 5. Would CodeSight Help Maintenance Crons?, 6. Consulting Product Angle, 7. Should Juan Build This NOW?, Brutally Honest Take on Embeddings (+21 more)

### Community 10 - "Architecture -- CodeSight"
Cohesion: 0.11
Nodes (19): Architecture -- CodeSight, Chunking Strategy, Code Files — AST-Based (tree-sitter), Context Headers, Context Injection Integration (Added 2026-04-04), Data Flow: What's Local vs External, Deployment Tiers, Document Processing Pipeline (+11 more)

### Community 11 - "Spec: Go-To-Market — Where to Sell, Who to Sell To, and How"
Cohesion: 0.07
Nodes (26): Channel 1 — LinkedIn Outbound (Start Here), Channel 2 — Microsoft Partner Network, Channel 3 — Industry Events & Communities, Channel 4 — Clutch & Toptal (Credibility + Inbound), Channel 5 — Referral Network, Deployment Fees, First 90 Days Action Plan, License Tiers (+18 more)

### Community 12 - "TestPathTraversal"
Cohesion: 0.25
Nodes (5): Security tests for read-only invariant and input sanitization., Verify path traversal attacks are prevented., CodeSight rejects non-directory paths., CodeSight resolves symlinks and validates the real path., TestPathTraversal

### Community 13 - "Research: Multi-Model Embedding Architecture for Maximum Retrieval Accuracy"
Cohesion: 0.08
Nodes (25): Adversary Analysis, Architecture Recommendation: Option B, Code Models, Current State vs. Target, DECISION_POINT: embedding_model_for_code, DECISION_POINT: index_architecture, DECISION_POINT: query_routing_strategy, Discarded Claims (+17 more)

### Community 14 - "Workflow: Explore → Plan → Execute → Review"
Cohesion: 0.08
Nodes (24): Base Command, Behavior Rules for Opus (VS Code), CLI Agent Command Format, Commit Style, Core Principle, Cycle Handoff, Execution Method, Fallback: Copy-Paste Mode (+16 more)

### Community 15 - "ChunkStore"
Cohesion: 0.09
Nodes (13): ChunkStore, Coordinate vector and keyword storage for indexed chunks. `ChunkStore` keeps…, Lazy access to LanceDB table, creating if needed., Lazy access to the code-specific LanceDB table if it exists., BM25 search via FTS sidecar., Update the last_indexed_at timestamp., Chunk IDs with backslashes fail the allowlist., Chunk IDs with semicolons (SQL injection) fail the allowlist. (+5 more)

### Community 16 - "Market — Enterprise Knowledge Appliance"
Cohesion: 0.08
Nodes (23): Business Model, Category, Competitive Landscape, Deal Sizes, Growth Strategy, Kill Criteria, Market — Enterprise Knowledge Appliance, Market Size (+15 more)

### Community 17 - "Spec: Infrastructure & Data Connectors"
Cohesion: 0.09
Nodes (22): 1. Data Sources & Connectors, 2. Ingestion Pipeline, 3. Vector Store Configuration, 4. Metadata Strategy, 5. Hybrid Search Strategy, 6. Background Job Infrastructure, Confluence (Optional Connector), Content Hashing for Skip Logic (+14 more)

### Community 18 - "ServerConfig"
Cohesion: 0.19
Nodes (21): Public Python API for CodeSight. This is the single entry point for Streamlit,…, BaseModel, Runtime configuration., ServerConfig, CodeSight — AI-powered document search engine. Hybrid BM25 + vector retrieval…, Answer, ChunkRecord, IndexStats (+13 more)

### Community 19 - "_cnfb_boost"
Cohesion: 0.06
Nodes (33): _cnfb_boost(), Promote chunks from filename-matching files to the top of the list. DEPRECATED:…, Apply Query-Aware Multiplicative Filename Boost (CNFB, SPEC-009). Precomputes…, _reorder_by_filename_match(), _make_cnfb_result(), _make_result(), Tests for the search module (RRF merging + reranker routing)., _rerank() calls local cross-encoder when backend='local'. (+25 more)

### Community 20 - "chunker.py"
Cohesion: 0.13
Nodes (18): Pattern, _build_chunk_from_lines(), Chunk, _get_ts_parser(), _make_context_header(), Language-aware code chunking + document chunking. Code: tree-sitter AST-based…, Text sent to the embedding model (context header + content)., Unique ID: file + line range + hash. (+10 more)

### Community 21 - "Spec 008: Docker Deployment + FastAPI Production Server"
Cohesion: 0.09
Nodes (22): Acceptance Criteria, Alternative A: Keep Streamlit, add nginx reverse proxy, Alternative B: Flask, Alternative C: Full React frontend, Alternatives Considered, API Contract, Auth Middleware, Dependencies (+14 more)

### Community 22 - "Spec 004: Tree-sitter Chunking"
Cohesion: 0.10
Nodes (20): Acceptance Criteria, Alternative A: Language Server Protocol (LSP), Alternative B: Improved regex patterns, Alternative C: Concrete Syntax Tree (CST) via tree-sitter, Alternatives Considered, AST-Based Chunking Strategy, Code Sketch, Dependencies (+12 more)

### Community 23 - "Spec 007: Cross-Encoder Reranking"
Cohesion: 0.10
Nodes (20): Acceptance Criteria, Alternative A: API-based reranker (Cohere Rerank), Alternative B: Replace RRF with learned fusion, Alternative C: Always-on reranking, Alternatives Considered, Configuration, Dependencies, Edge Cases & Failure Modes (+12 more)

### Community 24 - "CodeSight"
Cohesion: 0.08
Nodes (17): CodeSight, callable, Path, Ask a question — search + LLM answer synthesis. Retrieves the top matching…, Check index status for this folder., Auto-index if not indexed, auto-refresh if stale, rebuild on model mismatch., Check if the configured embedding model differs from the indexed one., Check if the index is older than the staleness threshold. (+9 more)

### Community 25 - "Spec 001: Core Search Engine"
Cohesion: 0.10
Nodes (19): Acceptance Criteria, Alternative A: Vector-only search (no BM25), Alternative B: Cloud-hosted vector DB (Pinecone, Weaviate), Alternative C: LangChain / LlamaIndex framework, Alternatives Considered, API Contract, Dependencies, Document Parsing Pipeline (+11 more)

### Community 26 - "Spec: ACL Enforcement — End-to-End Access Control"
Cohesion: 0.11
Nodes (18): 1. Identity Resolution, 2. Permission Mapping by Source, 3. Query-Time Enforcement, 4. Sensitivity Labels (Optional, Mode B), 5. Audit Trail, 6. Security Threat Model, Authentication Flow, Confluence / Jira (+10 more)

### Community 27 - "Question: Challenge voyage rerank-2.5 and LLM query expansion assumptions for 2026"
Cohesion: 0.11
Nodes (18): Adversary Analysis, Adversary Research Report — Phase 1 Assumption Check, CLAIM 1: "Swap to voyage rerank-2.5", CLAIM 2: "Add LLM query expansion (3 variants via claude-haiku)", Decision Points, Discarded Claims, GO — with one clarification, Impact on Phase 1 Steps (+10 more)

### Community 28 - "indexer.py"
Cohesion: 0.10
Nodes (30): PathSpec, chunk_document(), Split document pages into chunks by paragraph boundaries. Each page's text is…, changed_files(), current_commit(), deleted_files(), is_git_repo(), Path (+22 more)

### Community 29 - "Spec 006: Pluggable LLM Backend"
Cohesion: 0.20
Nodes (10): Acceptance Criteria, API Contract, Backend Adapter, Edge Cases & Failure Modes, Goals, Non-Goals, Open Questions, Problem (+2 more)

### Community 30 - "Implementation Notes"
Cohesion: 0.40
Nodes (5): Dependencies, File Changes, Implementation Notes, Key Parameters, Scaling per Backend

### Community 31 - "AI-Powered Document Search for [Company Name]"
Cohesion: 0.12
Nodes (16): 1. Executive Summary, 2. The Problem, 3. The Solution, 4. Technical Approach, 5. Engagement Phases, 6. Pricing, 7. Why Us, AI-Powered Document Search for [Company Name] (+8 more)

### Community 32 - "Spec: Deployment Modes"
Cohesion: 0.12
Nodes (16): Architecture, Architecture, Azure Cost Estimates, Customer Decision Flow, Decision Matrix, Hardware Requirements, MCP Integration Layer (Both Modes), Mode A — Strict Local-Only (+8 more)

### Community 33 - "FTSSidecar"
Cohesion: 0.11
Nodes (8): FTSSidecar, Path, Delete all chunks belonging to a file. Returns count deleted., Return {chunk_id: content_hash} for all chunks of a file., Sanitize a query for FTS5 MATCH to prevent injection. FTS5 MATCH has its own…, Run BM25 search, returning chunk_ids ranked by relevance., Lightweight SQLite database for BM25 search and repo metadata., Remove all chunks for a file from both stores.

### Community 34 - "extract_text"
Cohesion: 0.24
Nodes (14): DocumentPage, _extract_docx(), _extract_pdf(), _extract_pptx(), extract_text(), is_document(), Path, Document text extraction — PDF, DOCX, PPTX. Converts business documents into… (+6 more)

### Community 35 - "rrf_merge"
Cohesion: 0.18
Nodes (8): Reciprocal Rank Fusion across multiple ranked ID lists. Returns [(chunk_id,…, rrf_merge(), Single ranked list preserves order., Two identical lists: items appear once with doubled scores., Disjoint lists merge all items., Items appearing in both lists get higher scores., Higher k flattens score differences., TestRRFMerge

### Community 36 - "test_mcp.py"
Cohesion: 0.12
Nodes (12): doc_folder(), engine(), isolated_data_dir(), fixture, Tests for the CodeSight API surface that replaces the former MCP tools. The…, CodeSight.status() ↔ former MCP status tool., Minimal document folder with one searchable Python file., Route index storage to a temp dir (config.DATA_DIR is import-time bound). (+4 more)

### Community 37 - "_auth_headers"
Cohesion: 0.10
Nodes (10): Production HTTP server and browser UI for CodeSight deployments., _auth_headers(), client(), fixture, FastAPI server contract tests., Configure isolated server environment., server_env(), TestProductionAuthRequired (+2 more)

### Community 38 - "Presentation Deck — Slide-by-Slide Script"
Cohesion: 0.15
Nodes (12): Objection Prep — Know These Cold, Presentation Deck — Slide-by-Slide Script, Slide 10: Next Step, Slide 1: Title, Slide 2: The Problem, Slide 3: The Solution, Slide 4: How It Works, Slide 5: Data Privacy (+4 more)

### Community 39 - "ADR 0002: Security-Critical Decisions Require Human Escalation"
Cohesion: 0.15
Nodes (12): Access Control, ADR 0002: Security-Critical Decisions Require Human Escalation, Authority Matrix, Consequences, Context, Cross-Tenant Isolation, Data Handling, Decision (+4 more)

### Community 40 - "ADR 0009: Retrieval Experiments — CNFB + Contextual Retrieval"
Cohesion: 0.15
Nodes (12): 3-Specialist Deliberation (2 rounds), ADR 0009: Retrieval Experiments — CNFB + Contextual Retrieval, Consequences, Context, Decision, Negative / Risks, Positive, Rationale (+4 more)

### Community 41 - "SPEC-009: CNFB — Query-Aware Multiplicative Filename Boost"
Cohesion: 0.15
Nodes (13): Acceptance Criteria, Algorithm, Configuration, Decisions, Edge Cases, Files to Change, Input, Out of Scope (+5 more)

### Community 42 - ".upsert_chunks"
Cohesion: 0.18
Nodes (7): ndarray, Return full chunk metadata by ID., Create or append to the LanceDB table., Upsert chunks into both LanceDB and the FTS sidecar., Search LanceDB by vector similarity, returning ranked chunk_ids., Search the code_chunks table by vector similarity, returning ranked chunk_ids., Retrieve embedding vectors from LanceDB for the given chunk IDs. Used by VPRF…

### Community 43 - "Roadmap — codesight"
Cohesion: 0.17
Nodes (12): Retrieval Quality History, Revenue Milestones, Roadmap — codesight, v0.1 — Hybrid Code Search Engine ✅ DONE, v0.2 — Enterprise Document Search ✅ DONE, v0.3 — Pluggable LLM + Better Embeddings ✅ DONE, v0.4 — Retrieval Quality ✅ DONE — 2026-04-04, v0.5 — Single-team Docker + FastAPI pilot ✅ DONE — 2026-08-13 (+4 more)

### Community 44 - "TestFTSQuerySanitization"
Cohesion: 0.17
Nodes (6): Verify that FTS5 MATCH queries are sanitized against injection., Normal search term works., FTS5 operators in query don't cause errors., Empty query returns empty results without error., Whitespace-only query returns empty results., TestFTSQuerySanitization

### Community 45 - "Pitch Prep — What to Know Before Every Meeting"
Cohesion: 0.18
Nodes (10): About cost, About privacy, About scaling, About the product, Before the Meeting Checklist, Closing the Meeting, Key Numbers to Memorize, Pitch Prep — What to Know Before Every Meeting (+2 more)

### Community 46 - "Repository Structure -- codesight"
Cohesion: 0.18
Nodes (10): `.claude/` -- Claude Code Configuration, Demo (`demo/`), Docs (`docs/`), Repository Structure -- codesight, Root Level, `.self-improvement/`, Source Code (`src/codesight/`), Specs (`specs/`) (+2 more)

### Community 47 - "Pitch Prep — What to Know Before Every Meeting"
Cohesion: 0.18
Nodes (10): About cost, About privacy, About scaling, About the product, Before the Meeting Checklist, Closing the Meeting, Key Numbers to Memorize, Pitch Prep — What to Know Before Every Meeting (+2 more)

### Community 48 - "Vision — codesight"
Cohesion: 0.18
Nodes (11): Design Principles, Key Differentiators, Mode A (Local-Only), Mode B (Azure-Native), Target Customer, The Core Business, The Problem, The Solution (+3 more)

### Community 49 - "Spec 002: Embedding Model Configuration"
Cohesion: 0.12
Nodes (16): Acceptance Criteria, Alternative A: Always use API embeddings, Alternative B: Use Ollama for embeddings too, Alternatives Considered, Dependencies, Edge Cases & Failure Modes, Goals, Implementation Notes (+8 more)

### Community 50 - "Spec 003: Incremental Refresh"
Cohesion: 0.13
Nodes (15): Acceptance Criteria, Alternative A: Filesystem watcher (inotify/FSEvents), Alternative B: Hash all files on every check, Alternatives Considered, Dependencies, Edge Cases & Failure Modes, Goals, Implementation Notes (+7 more)

### Community 51 - "_detect_scope"
Cohesion: 0.27
Nodes (5): _detect_scope(), Return a scope label when first_line matches a language-specific pattern., Extract a human-readable scope label from the first line of a chunk., _scope_from_patterns(), TestDetectScope

### Community 52 - "chunk_file"
Cohesion: 0.17
Nodes (6): chunk_file(), Split a file's content into scope-delimited chunks. Strategy: 1. If we have a…, Tests for the chunking pipeline., chunk_file() falls back to regex when tree-sitter raises ImportError., TestChunkFile, TestContentHashDedup

### Community 53 - "[LOGO] Camilo Martinez — AI Consulting"
Cohesion: 0.20
Nodes (9): DATA PRIVACY, HOW IT WORKS, [LOGO] Camilo Martinez — AI Consulting, NEXT STEP, One-Pager Template — Leave-Behind PDF, THE ENGAGEMENT, THE PROBLEM, THE SOLUTION (+1 more)

### Community 54 - "Spec: Financial Model — Mode A vs Mode B by Company Size"
Cohesion: 0.20
Nodes (9): Break-Even Analysis: When Local Becomes Cheaper, Grand Comparison — All Tiers, How to Read This Document, Pricing Recommendations by Tier, Spec: Financial Model — Mode A vs Mode B by Company Size, When Mode A Beats Mode B (Decision Framework), Year 1 Total Cost (Company Pays), Year 2+ Annual Cost (Company Pays) (+1 more)

### Community 55 - "Mode A: Local-Only"
Cohesion: 0.20
Nodes (10): Annual Summary, Annual Summary, Mode A: Local-Only, Mode B: Azure-Native, Monthly Ongoing, Monthly Ongoing, Tier 1 — Small Company (100 employees, ~50K documents), Tier 1 Verdict (+2 more)

### Community 56 - "Mode A: Local-Only"
Cohesion: 0.20
Nodes (10): Annual Summary, Annual Summary, Mode A: Local-Only, Mode B: Azure-Native, Monthly Ongoing, Monthly Ongoing, Tier 2 — Mid-Size Company (500 employees, ~250K documents), Tier 2 Verdict (+2 more)

### Community 57 - "Mode A: Local-Only"
Cohesion: 0.20
Nodes (10): Annual Summary, Annual Summary, Mode A: Local-Only, Mode B: Azure-Native, Monthly Ongoing, Monthly Ongoing, Tier 3 — Large Company (1,000 employees, ~500K documents), Tier 3 Verdict (+2 more)

### Community 58 - "Mode A: Local-Only"
Cohesion: 0.20
Nodes (10): Annual Summary, Annual Summary, Mode A: Local-Only, Mode B: Azure-Native, Monthly Ongoing, Monthly Ongoing, Tier 4 — Enterprise (2,000+ employees, ~1M+ documents), Tier 4 Verdict (+2 more)

### Community 59 - "Alternatives Considered"
Cohesion: 0.50
Nodes (4): Alternative A: LiteLLM wrapper library, Alternative B: LangChain, Alternative C: Only support Claude + Ollama, Alternatives Considered

### Community 60 - "docs/README.md"
Cohesion: 0.18
Nodes (4): Contents, docs - codesight, Playbooks, Rules

### Community 61 - "Playbook: Development Setup"
Cohesion: 0.22
Nodes (9): Directory Layout, Environment Variables, Lint, Playbook: Development Setup, Prerequisites, Python API, Run Locally, Setup (+1 more)

### Community 62 - "__main__.py"
Cohesion: 0.25
Nodes (10): _configure_logging(), _launch_demo(), _launch_serve(), _location_label(), main(), CLI entry point for CodeSight. Usage: python -m codesight index /path/to/docs…, Return 'lines X-Y' for code or 'page X-Y' for documents., Launch the Streamlit demo app. (+2 more)

### Community 63 - "After Contract Signed"
Cohesion: 0.29
Nodes (6): After Contract Signed, Client Onboarding — Delivery Kickoff, Delivery Depends On, Week 0: Setup (1-2 days), Week 1: Discovery + Index, Week 2: Deploy + Train

### Community 64 - "app.py"
Cohesion: 0.25
Nodes (5): cache_resource, _get_engine(), CodeSight -- AI Document Search Chat UI. Run with: streamlit run demo/app.py, Render source citations as expandable cards. Returns serializable data., _render_sources()

### Community 65 - "ADR 0001: Support Two Deployment Modes from Day One"
Cohesion: 0.25
Nodes (7): ADR 0001: Support Two Deployment Modes from Day One, Consequences, Context, Decision, Negative, Neutral, Positive

### Community 66 - "After Contract Signed"
Cohesion: 0.29
Nodes (6): After Contract Signed, Client Onboarding — Delivery Kickoff, Delivery Depends On, Week 0: Setup (1-2 days), Week 1: Discovery + Index, Week 2: Deploy + Train

### Community 67 - "Playbook: Ship a Feature"
Cohesion: 0.25
Nodes (8): 1. Write the Spec, 2. Write Tests First, 3. Implement, 4. Check Security, 5. Run Full Suite, 6. Update Docs, 7. Commit and Push, Playbook: Ship a Feature

### Community 68 - "Self-Improvement Memory — codesight"
Cohesion: 0.25
Nodes (7): Architecture Facts, Implementation History, Key Source Files, Known Issues, Project State, Security Invariants (NEVER violate), Self-Improvement Memory — codesight

### Community 69 - "Spec Templates"
Cohesion: 0.25
Nodes (7): Spec Templates, Template 1: Feature Spec (Full), Template 2: API Spec, Template 3: Schema Spec, Template 4: Integration Spec, Template 5: Bug Fix Spec (Lightweight), Template Selection Guide

### Community 70 - "store.py"
Cohesion: 0.36
Nodes (6): Path, Return the data directory for a given folder, creating parent dirs if needed.…, Return the SQLite FTS5 sidecar DB path for a given folder., repo_data_dir(), repo_fts_db_path(), Storage layer: LanceDB for vectors + SQLite FTS5 sidecar for BM25. This module…

### Community 71 - "._delete_vectors_by_ids"
Cohesion: 0.17
Nodes (6): Open or create the code_chunks LanceDB table with the Voyage vector dimension., Upsert code chunks into the code_chunks vector table and shared metadata store., Upsert shared chunk metadata into the FTS sidecar., Validate a chunk_id against the allowlist regex. Returns the chunk_id if valid,…, Delete vectors from LanceDB using validated chunk IDs. Each chunk_id is…, Insert or replace a chunk in the metadata store.

### Community 72 - "TestMCPSearchTool"
Cohesion: 0.25
Nodes (3): CodeSight.search() ↔ former MCP search tool., MCP search auto-indexed on first call; API must do the same., TestMCPSearchTool

### Community 73 - "consulting-market-expert Memory -- camilo-martinez-consulting"
Cohesion: 0.29
Nodes (6): consulting-market-expert Memory -- camilo-martinez-consulting, Key Insights, Last Updated, Patterns Learned, Research Topics Covered, Sources Database

### Community 74 - "static-analysis-expert Memory -- codesight"
Cohesion: 0.29
Nodes (6): Key Insights, Last Updated, Patterns Learned, Research Topics Covered, Sources Database, static-analysis-expert Memory -- codesight

### Community 75 - "Playbook: Investigate a Bug"
Cohesion: 0.29
Nodes (6): 1. Reproduce, 2. Check Logs, 3. Inspect State, 4. Verify Read-Only Invariant, 5. Write a Regression Test, Playbook: Investigate a Bug

### Community 76 - "NEXT — codesight"
Cohesion: 0.29
Nodes (6): Blocked, NEXT — codesight, P0 — Before v0.4, P1 — Build v0.4 (Spec 008: Docker + FastAPI), P2 — Backlog, Status

### Community 77 - "Spec 005: Automatic Re-indexing"
Cohesion: 0.29
Nodes (6): Acceptance Criteria (Original — Not Implemented), Goals (Original — Preserved for Reference), If Revisited, Problem, Spec 005: Automatic Re-indexing, Why Deprecated

### Community 78 - "Implementation History"
Cohesion: 0.29
Nodes (7): Feature Specs, Implementation History, Specs — codesight, v0.1 — Hybrid Code Search (completed), v0.2 — Enterprise Document Search (completed), v0.3 — Pluggable LLM + Better Embeddings + Reranking (completed), v0.5 — Single-team Docker + FastAPI pilot (implemented)

### Community 79 - "test_deployment.py"
Cohesion: 0.13
Nodes (16): HTMLParser, _fetch_landing_page(), _load_vercel_config(), _PageContract, Deployment regression tests for holusight.com static site., Marketing copy must not claim planned or unverified capabilities., Docker Compose's normalized model must protect the customer boundary., Vercel must serve a static entry point or holusight.com returns 404. (+8 more)

### Community 80 - "Sales Process — Lead to Close"
Cohesion: 0.33
Nodes (5): Discovery Call Script, Pipeline Stages, Pricing Anchors, Proposal Workflow, Sales Process — Lead to Close

### Community 81 - "Delivery Planner — Memory"
Cohesion: 0.33
Nodes (5): CodeSight Current State (v0.2 — Implemented), Delivery Implications, Delivery Patterns, Delivery Planner — Memory, NOT Built Yet

### Community 82 - "business-analyst.md"
Cohesion: 0.33
Nodes (5): Analysis Framework, Rules, What You Monitor, What You Produce, Your Job

### Community 83 - "delivery-planner.md"
Cohesion: 0.33
Nodes (5): Rules, Standard Phases, What You Know About CodeSight, What You Produce, Your Job

### Community 84 - "model-quality-auditor.md"
Cohesion: 0.33
Nodes (5): Audit Protocol, Models to Track, On Startup, Output, Responsibilities

### Community 85 - "prompt-optimizer.md"
Cohesion: 0.33
Nodes (5): Evaluation Loop, Metrics to Report, On Startup, Output, Responsibilities

### Community 86 - "proposal-writer.md"
Cohesion: 0.33
Nodes (5): Inputs You Need, Proposal Structure, Rules, What You Produce, Your Job

### Community 87 - "ADR-0000: [Short Decision Title]"
Cohesion: 0.33
Nodes (5): ADR-0000: [Short Decision Title], Alternatives Considered, Consequences, Context, Decision

### Community 88 - "ADR-0001: LanceDB Over ChromaDB for Vector Storage"
Cohesion: 0.33
Nodes (5): ADR-0001: LanceDB Over ChromaDB for Vector Storage, Alternatives Considered, Consequences, Context, Decision

### Community 89 - "ADR-0002: Hybrid BM25 + Vector + RRF Retrieval"
Cohesion: 0.33
Nodes (5): ADR-0002: Hybrid BM25 + Vector + RRF Retrieval, Alternatives Considered, Consequences, Context, Decision

### Community 90 - "ADR-0003: Strict Read-Only Invariant on Indexed Repositories"
Cohesion: 0.33
Nodes (5): ADR-0003: Strict Read-Only Invariant on Indexed Repositories, Alternatives Considered, Consequences, Context, Decision

### Community 91 - "Sales Process — Lead to Close"
Cohesion: 0.33
Nodes (5): Discovery Call Script, Pipeline Stages, Pricing Anchors, Proposal Workflow, Sales Process — Lead to Close

### Community 92 - "Knowledge: Static Analysis Techniques"
Cohesion: 0.33
Nodes (5): Key Findings, Knowledge: Static Analysis Techniques, Open Research Questions, Pipeline Impact, What Changed vs Last Version

### Community 95 - "vercel.json"
Cohesion: 0.33
Nodes (5): buildCommand, framework, installCommand, outputDirectory, $schema

### Community 96 - "Business Analyst — Memory"
Cohesion: 0.40
Nodes (4): Business Analyst — Memory, Patterns, Pipeline Status, Revenue

### Community 97 - "code-improver Memory — codesight"
Cohesion: 0.40
Nodes (4): code-improver Memory — codesight, Known Issues, Lessons Learned, Session Notes

### Community 98 - "judge-agent Memory — codesight"
Cohesion: 0.40
Nodes (4): Calibration Notes, judge-agent Memory — codesight, Session Notes, Verdict History

### Community 99 - "model-quality-auditor Memory — codesight"
Cohesion: 0.40
Nodes (4): Baseline Metrics, Model Comparison History, model-quality-auditor Memory — codesight, Session Notes

### Community 100 - "Proposal Writer — Memory"
Cohesion: 0.40
Nodes (4): Common Objections, Patterns, Pricing That Worked, Proposal Writer — Memory

### Community 101 - "security-sentinel Memory — codesight"
Cohesion: 0.40
Nodes (4): Cleared Issues, Known Attack Vectors, security-sentinel Memory — codesight, Session Notes

### Community 102 - "code-improver.md"
Cohesion: 0.40
Nodes (4): Grading Rubric, Hard Rules, On Startup, Your Job (Self-Refine Loop)

### Community 103 - "consulting-market-expert.md"
Cohesion: 0.40
Nodes (4): Rules, What You Research, What You Update, Your Job

### Community 104 - "judge-agent.md"
Cohesion: 0.40
Nodes (4): Evaluation Checklist, On Startup, Output, Verdicts

### Community 105 - "manager.md"
Cohesion: 0.40
Nodes (4): NEXT.md Format, On Startup, P0 Triggers (Escalate Immediately), Your Job (OODA Loop)

### Community 106 - "security-sentinel.md"
Cohesion: 0.40
Nodes (4): On Startup, Output, Threat Model (STRIDE for Document Search Engine), What to Check Every Cycle

### Community 107 - "0005 — Unified Consulting Repo into CodeSight"
Cohesion: 0.40
Nodes (4): 0005 — Unified Consulting Repo into CodeSight, Consequences, Context, Decision

### Community 108 - "Knowledge Base — codesight"
Cohesion: 0.40
Nodes (4): Knowledge Base — codesight, Structure, Topic Index, Update Protocol

### Community 109 - "TestReadOnlyInvariant"
Cohesion: 0.50
Nodes (3): Verify the engine never writes to the indexed folder., After indexing, the source folder should have no new files., TestReadOnlyInvariant

### Community 110 - "Closed Deals — Won & Lost"
Cohesion: 0.50
Nodes (3): Closed Deals — Won & Lost, Lost, Won

### Community 111 - "vprf_enhance_query"
Cohesion: 0.17
Nodes (10): ndarray, Vector Pseudo-Relevance Feedback: blend query with top-retrieved document…, vprf_enhance_query(), Tests for Vector Pseudo-Relevance Feedback query enhancement., Returns original query vector when no feedback vectors provided., Enhanced vector must be unit-norm., Enhanced query is a weighted blend of query + feedback, not identical to query., Only top-3 feedback vectors are used even when more are provided. (+2 more)

### Community 113 - "Recommended SMB Pilot Offer"
Cohesion: 0.15
Nodes (11): Acceptance metrics (pilot), Deployment options, Discovery checklist (first call), Exclusions (v1 pilot), Handoff & expansion path, Ideal customer profile, Pricing (recommended starting range), Recommended SMB Pilot Offer (+3 more)

### Community 114 - "Quick Reference — Cost Drivers"
Cohesion: 0.67
Nodes (3): Mode A (Local-Only) Cost Drivers, Mode B (Azure-Native) Cost Drivers, Quick Reference — Cost Drivers

### Community 124 - "server.py"
Cohesion: 0.19
Nodes (20): Exception, FastAPI, Request, api_key(), create_app(), documents_dir(), _env_bool(), _extract_key() (+12 more)

### Community 125 - "Docker deployment playbook"
Cohesion: 0.17
Nodes (12): Backup, Configuration, Docker deployment playbook, Health & operations, Local dev (without Docker), Prerequisites, Quick start (pilot), Remove deployment (+4 more)

### Community 126 - "app.js"
Cohesion: 0.27
Nodes (8): apiFetch(), escapeHtml(), getApiKey(), headers(), loadConfig(), locationLabel(), refreshHealth(), renderSources()

### Community 128 - "CodeSight"
Cohesion: 0.22
Nodes (9): Architecture, CodeSight, Configuration, Deployment (pilot), Performance, Python API, Quick Start, Stack (+1 more)

### Community 129 - "Spec 010: Capability Truth Inventory"
Cohesion: 0.22
Nodes (9): Answer synthesis (`ask`), Authentication & security, Citation contract (API / UI), Core retrieval, Document parsing & chunking, Explicitly planned / not in v1, Interfaces, Legend (+1 more)

### Community 130 - "_detect_language"
Cohesion: 0.36
Nodes (3): _detect_language(), Detect language from file extension., TestDetectLanguage

### Community 131 - "ADR 0010: Graphify Extension Contract (Not Integrated in v1)"
Cohesion: 0.25
Nodes (7): ADR 0010: Graphify Extension Contract (Not Integrated in v1), Context, Decision, Evaluation summary, Extension contract (future experiment), Marketing rule, Roadmap

### Community 132 - "config.py"
Cohesion: 0.13
Nodes (14): Configuration for the CodeSight search engine., Return expected embedding dimension for a model. Falls back to 384., resolve_embedding_dim(), Embedder, get_embedder(), Protocol, Embedding model wrapper — local (sentence-transformers) or API (OpenAI).…, Return a cached Embedder singleton. Args: model_name: Model identifier from the… (+6 more)

### Community 134 - "auth_utils.py"
Cohesion: 0.50
Nodes (3): Security utilities for the pilot deployment. JWT validation middleware lives in…, Validate bearer tokens for internal services., verify_api_token()

## Knowledge Gaps
- **754 isolated node(s):** `codesight`, `$schema`, `framework`, `installCommand`, `buildCommand` (+749 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ChunkStore` connect `ChunkStore` to `FTSSidecar`, `EvalQuery`, `store.py`, `SearchResult`, `._delete_vectors_by_ids`, `.upsert_chunks`, `TestFTSQuerySanitization`, `TestPathTraversal`, `TestReadOnlyInvariant`, `.get_chunk_metadata`, `ServerConfig`, `CodeSight`, `indexer.py`, `.set_meta`?**
  _High betweenness centrality (0.022) - this node is a cross-community bridge._
- **Why does `ServerConfig` connect `ServerConfig` to `EvalQuery`, `config.py`, `test_mcp.py`, `SearchResult`, `TestMCPSearchTool`, `TestFTSQuerySanitization`, `TestPathTraversal`, `TestReadOnlyInvariant`, `ChunkStore`, `server.py`, `CodeSight`, `indexer.py`, `.clamp_cnfb_alpha`?**
  _High betweenness centrality (0.022) - this node is a cross-community bridge._
- **Why does `SearchResult` connect `SearchResult` to `EvalQuery`, `rrf_merge`, `test_mcp.py`, `TestMCPSearchTool`, `vprf_enhance_query`, `ServerConfig`, `_cnfb_boost`, `CodeSight`, `server.py`?**
  _High betweenness centrality (0.020) - this node is a cross-community bridge._
- **Are the 23 inferred relationships involving `CodeSight` (e.g. with `ServerConfig` and `LLMBackend`) actually correct?**
  _`CodeSight` has 23 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `ChunkStore` (e.g. with `CodeSight` and `EvalQuery`) actually correct?**
  _`ChunkStore` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 20 inferred relationships involving `ServerConfig` (e.g. with `CodeSight` and `AskRequest`) actually correct?**
  _`ServerConfig` has 20 INFERRED edges - model-reasoned connections that need verification._
- **Are the 20 inferred relationships involving `SearchResult` (e.g. with `CodeSight` and `AskRequest`) actually correct?**
  _`SearchResult` has 20 INFERRED edges - model-reasoned connections that need verification._