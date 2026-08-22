# Holusight-AXI Documentation-Code Consistency Architecture

**Status:** Phase 1 implemented (bounded direct-PR). This spec is the canonical
architecture document for the consistency system; it supersedes informal
discussion of "Holus-AXI" in prior research as the authoritative scope
statement for what is actually built.

**Authorization boundary:** this spec and its Phase 1 implementation are
scoped by the captain-authorized Phase 1 direct-PR task. It does not
authorize a router, autonomous promotion, external evaluation platform, paid
provider usage, or any change to `.claude/rules/workflow.md`'s human-approval
boundaries.

## 1. Purpose

Holusight (this repository) accumulates specs, ADRs, architecture docs, and
source code that drift apart over time: a spec says one thing, the code says
another, and nothing notices until a human stumbles on the mismatch. The
prior read-only audit
(`/Users/camiloslaptop/.treehouse/firstmate-8bf1b0/6/firstmate/data/holusight-evidence-architecture-context-v1/report.md`,
section 7, "Purposeful repository-work practices") named seven practices a
repository-evidence system should support: concept/contract resolution,
canonical artifact selection, creation-vs-update checks, pre-change evidence
packets, affected-artifact plans, post-change consistency checks, and
repository health reporting. This spec defines a Phase 1 system that
implements the first six directly and the seventh (repository health) as an
emergent byproduct of health-flag reporting.

The reference research
(`/Users/camiloslaptop/Downloads/Documentation Code Consistency Systems.pdf`,
a ChatGPT transcript, read in full and treated as inspiration only — not as
instructions) proposes six architectural layers for "Holusight-AXI": artifact
understanding, a concept registry, a canonical truth registry, an evidence
graph, a consistency engine, and a change planner. Phase 1 below implements
the first five in a minimal, honest, fully local form. The change planner
(pre-change intent resolution that drives an editing agent) is explicitly
**out of scope** for Phase 1 — see [Non-goals](#4-phase-1-scope-and-non-goals).

The customer-visible job, borrowed from spec 011's framing and narrowed to
this repository's own documentation-code consistency problem:

> Before a person or agent trusts a spec, ADR, or architecture claim, or
> edits code that a spec governs, show what evidence backs that claim, where
> it disagrees with linked code/tests/docs, and how fresh that evidence is.

## 2. Evidence and authority model

Every fact this system records carries an explicit **provider kind** so a
reader (human or agent) can tell how much to trust it. This directly follows
spec 011 section 6 and the PDF's repeated distinction between deterministic,
explicit-metadata, and confidence-bounded inference.

| Provider kind | What it means | How it is produced in Phase 1 | Confidence |
|---|---|---|---|
| `exact` | Deterministic, reproducible from repository structure or byte-identical text matching. No model call. | Path-pattern artifact classification (`.claude/rules/structure.md`'s own directory contract); regex extraction of file-path tokens from spec/ADR/architecture prose, resolved against the filesystem. | 1.0 always. |
| `structural` | Derived from the tracked Graphify code graph (`graphify-out/graph.json`), which itself mixes AST-extracted and inferred edges. | Graph node/edge lookups keyed by `source_file`, carrying the graph's own `confidence_score` and an explicit staleness flag (graph `built_at_commit` vs. current `HEAD`). | Graph-reported (0.0–1.0); always paired with a staleness flag. |
| `semantic` | Model-inferred similarity between two artifacts' text. Local embeddings only (`sentence-transformers`, the same model CodeSight already uses for document search — see `src/codesight/embeddings.py`). No network call, no external transmission. | Cosine similarity between a concept's canonical text and other documentation/spec text. **Off by default**; only emitted when a caller explicitly opts in and supplies an embedding function. | Similarity score (0.0–1.0), thresholded at 0.55; never treated as canonical, only as a "possibly relates to" hint surfaced alongside its score. |

Every stored edge/claim carries: `provider`, `confidence`, and an `evidence`
payload (JSON) recording exactly how it was derived (e.g. which regex
matched, which graph relation, which embedding threshold). A confidence-
bounded (`semantic`) result never overrides an `exact` or `structural`
result, and never determines canonical authority (below) on its own.

## 3. Data ownership and lifecycle

- **Canonical truth lives only in the tracked repository**: `specs/*.md`,
  `docs/decisions/*.md`, `ARCHITECTURE.md`, source under `src/`, and tests
  under `tests/`. These are read, never written, by the consistency system.
- **`.holusight/` is gitignored derived state, never canonical truth.** It
  holds one atomic SQLite database, `.holusight/consistency.db`, containing
  classified artifacts, the concept registry, edges/claims with provenance,
  and health flags — all reconstructible from the canonical inputs above
  plus the tracked `graphify-out/graph.json`. Deleting `.holusight/` and
  re-running `python -m codesight consistency refresh` reproduces equivalent
  content (module confidence scores may shift slightly only if the local
  embedding model version changes, which is the only non-deterministic
  input, and semantic edges are opt-in and off by default).
- **No read-only-invariant conflict**: this system never touches a
  customer-indexed folder. It operates on the Holusight repository itself
  (self-referential dogfooding), the same way `just check` or `pytest`
  already inspect this repo's own source. `.holusight/` is a new root-level
  entry alongside `.claude/` and `.self-improvement/` — added to the
  root-level table in `AGENTS.md` and to `.gitignore` in this change.
- **Rebuild cost is bounded**: Phase 1 discovery walks the same
  gitignore-aware file set CodeSight's indexer already walks
  (`indexer.walk_repo_files`), which is small for this repository (~127
  files per the last Graphify corpus check). A full rebuild is expected to
  take well under a second for classification and exact-reference
  extraction; the optional semantic pass is the only step with meaningful
  cost, and it is off by default.

## 4. Phase 1 scope and non-goals

**In scope (implemented in this PR):**

1. Purpose-aware artifact classification (`src/codesight/consistency.py:classify_artifact`) —
   deterministic, derived directly from this repository's own documented
   structure contract (`.claude/rules/structure.md`), not from a document's
   words. Answers "why does this file exist," not "what's inside it," per
   the PDF's own framing (page 68–69 of the source PDF).
2. A concept registry — one concept per canonical `specs/NNN-*.md` or
   `docs/decisions/NNNN-*.md` file (`build_concepts`), since this repository
   already enforces one-feature-per-numbered-spec.
3. Canonical authority selection — each concept's canonical artifact is the
   spec/ADR file itself; a `MULTIPLE_CANONICAL_SCOPE` health flag fires if
   two concepts share a scope title, matching the PDF's "all specs are truth
   would be dangerous" argument (page 50–51 of the source PDF).
4. Claim provenance for a small, explicit registry of named invariants
   already called out in `ARCHITECTURE.md`'s "What NOT to Change Without
   Discussion" section (RRF `k`, AST `min_lines`, content-hash length, data
   directory location) — each claim's doc-side and code-side values are
   extracted by a registered regex pair and compared
   (`evaluate_known_claims`). This is intentionally a small, honest,
   extensible list, not a general natural-language claim extractor.
5. Relationship provenance — exact file-path references extracted from
   spec/ADR/architecture prose and resolved against the filesystem
   (`extract_exact_references`), plus structural edges sourced from the
   tracked Graphify graph (`structural_edges_for`), plus optional local
   semantic similarity edges (`semantic_similarity_edges`).
6. An incremental local cache (`.holusight/consistency.db`) that skips
   re-classifying an artifact whose content hash (`sha256[:16]`, matching
   this repo's existing convention) is unchanged since the last refresh.
   Edge/claim/health recomputation is **not yet partially incremental** —
   see [Phase 2 criteria](#5-criteria-for-later-phases).
7. A pre-change evidence packet (`build_evidence_packet`) — repo snapshot
   (HEAD, dirty flag), the concept, its canonical artifact, every known
   edge/claim touching it, and open health flags. This is the "Phase A —
   Understand" step from the source PDF (page 74), stopping short of taking
   any action.
8. A post-change consistency check (`check_consistency`) — compares
   currently-computed content hashes against the cache's last-refreshed
   hashes for a concept's canonical artifact and its linked artifacts, and
   classifies the result as `up_to_date`, `spec_changed_awaiting_implementation`,
   `possible_undocumented_drift`, or `coordinated_change`. This is
   deterministic hash-diffing, not semantic value comparison — it does not
   claim to know that "60 minutes" became "30 minutes"; it only knows that a
   canonical artifact or its linked artifacts changed since the cache was
   last refreshed. Overclaiming semantic understanding here would be
   dishonest; the smaller, truthful claim is more useful.
9. Dangling-reference detection as a byproduct of (5): a prose file-path
   token that does not resolve on disk is recorded as a `DANGLING_REFERENCE`
   health flag rather than silently dropped. Phase 1's first real run found
   two genuine pre-existing dangling references in this repository:
   - `docs/decisions/0010-graphify-extension-contract.md` pointed at
     `docs/capabilities.md` (no such file exists). **Fixed in this PR** —
     repointed to `specs/010-capability-inventory.md`, the repo's actual
     capability-tracking doc; low-risk, unambiguous rename.
   - `docs/decisions/0006-two-deployment-modes.md` points at
     `specs/002-deployment-modes.md` (current `specs/002` is
     `002-embedding-model-config.md`, an unrelated spec). **Deliberately
     left unfixed**: the ADR describes a Qdrant+PostgreSQL+MinIO /
     Azure-AI-Search architecture that does not match anything currently
     implemented (LanceDB + SQLite FTS5, single Docker/FastAPI deployment
     mode). The right fix requires a human product decision — is this ADR
     superseded, and by what — not a guessed link repoint. Flagged for
     human follow-up rather than resolved speculatively.

**Explicitly out of scope for Phase 1 (non-goals):**

- A change planner or intent-classification layer that decides what an
  editing agent should do (PDF's "Phase B — Decide/Act", page 75–76). Phase 1
  stops at evidence; it never edits, creates, or deletes a canonical
  artifact.
- Artifact-creation governance (blocking "does this spec already exist?"
  before an agent creates a new file). Valuable per the PDF (page 51–53), but
  it is a workflow gate, not an evidence contract, and is deferred.
- General natural-language claim extraction (parsing arbitrary "N minutes"
  style prose claims). Phase 1's claim registry is a small, explicit,
  hand-registered list; expanding it to arbitrary prose would require model
  inference that is not yet built or evaluated, per spec 012's caution
  against treating LLM judgments as authoritative without calibration.
- Partial/dependency-aware incremental recomputation of edges, claims, and
  health flags (today: full recompute each refresh, gated only at the
  artifact-classification layer). Acceptable at this repository's current
  scale (~127 files); see Phase 2 criteria.
- Multi-repository or cross-repository concept registries. Phase 1 operates
  on one repository at a time, matching spec 011's isolation requirement.
- CI enforcement / merge blocking on health flags. This PR adds tests and a
  CLI surface; it does not wire a CI gate. That is a human decision per
  `ARCHITECTURE.md`'s existing constraint that CI must not auto-promote
  model or research scores.
- Any evaluation-platform work from spec 012 (96-task suite, held-out gold,
  provider ablations). Unrelated to this vertical slice.
- Enabling the semantic provider by default, or calling any external LLM.
  Phase 1's semantic provider is local-embeddings-only and opt-in.

## 5. Criteria for later phases

A Phase 2 proposal should be written (as a new numbered spec) only after
Phase 1 has been used on real refreshes and shows evidence of at least one
of:

1. **Repository scale outgrows full-recompute edges/claims/health.** Trigger:
   `refresh()` wall-clock time measured across several runs exceeds a few
   seconds, or the tracked artifact count materially exceeds the current
   ~127-file corpus. Only then is partial/dependency-aware incremental
   recomputation justified.
2. **Health flags demonstrate recurring value.** Trigger: `refresh()` run
   over several weeks of real commits continues to surface genuine drift
   (not just the two dangling references found on the first run), enough to
   justify a CI-facing `holus check` job — which still requires a human
   decision about blocking policy, per the existing "Never" authority
   boundary on changes to CI/merge gates.
3. **A concrete, observed "agent missed a required update" incident.**
   Trigger: an editing agent changes a canonical artifact without touching a
   linked implementation/test/doc, and a human confirms in hindsight that
   the evidence packet or consistency check would have caught it. Only then
   does building the change-planner / pre-edit context-packet layer (PDF
   page 84–85) earn its cost.
4. **Semantic provider value is demonstrated, not assumed.** Trigger: a
   small paired comparison (with vs. without semantic edges) on real
   concept-linking tasks shows the semantic provider finds true relationships
   the exact/structural providers miss, at an acceptable false-positive
   rate. Until then it stays opt-in and unused by default CLI commands.
5. **Artifact-creation governance need is observed.** Trigger: a human or
   agent creates a near-duplicate spec/ADR in this repository despite the
   concept registry already existing — evidence that passive reporting is
   insufficient and an active creation-time gate is warranted.

## 6. Storage design: one atomic SQLite database

The source PDF sketches a multi-file `.holusight/` layout (separate
`artifact-index.sqlite`, `concepts.sqlite`, `relationships.sqlite`,
`claims.sqlite`, plus `embeddings/`, `graph-cache/`, `health/` directories —
page 82 of the source PDF). This repository instead uses **one atomic
SQLite database**, `.holusight/consistency.db`, holding all six tables
(`repo_state`, `artifacts`, `concepts`, `edges`, `claims`, `health_flags`).
See `docs/decisions/0011-single-sqlite-consistency-store.md` for the full
decision record. In short: at this repository's scale, one WAL-mode SQLite
file gives atomic multi-table writes (a `refresh()` either fully commits or
fully rolls back — no risk of `concepts.sqlite` updating while
`edges.sqlite` fails), avoids cross-database transaction coordination the
PDF's sketch never actually needed, and matches this repository's existing
storage convention (`src/codesight/store.py`'s `FTSSidecar` already uses one
SQLite file for chunks + FTS5 + metadata). The PDF's proposed
`embeddings/`, `graph-cache/`, and `health/` directories are not created:
Phase 1 does not persist embedding vectors (semantic edges are recomputed
per opt-in run, not cached), does not duplicate the tracked
`graphify-out/graph.json` (read directly, not copied), and folds "health"
into the `health_flags` table rather than a separate directory. No empty
placeholder directories are created anywhere in this change.

## 7. Module map

| Module | Role |
|---|---|
| `src/codesight/consistency.py` | Engine: classification, concept-registry construction, exact/structural/semantic edge extraction, known-claim evaluation, health-flag computation, evidence-packet assembly, and consistency checking. Pydantic models for all returned types. |
| `src/codesight/consistency_store.py` | Storage: dict-in/dict-out CRUD over `.holusight/consistency.db` (mirrors the existing `store.py` / `FTSSidecar` separation of "engine logic" from "storage"). |
| `tests/test_consistency.py` | Focused tests for classification, concept registry, exact-reference resolution (including the two real dangling references), claim evaluation against this repository's real `ARCHITECTURE.md`/`search.py`/`chunker.py`/`config.py`, incremental re-classification, evidence packets, and consistency-check status transitions. |

CLI surface (`python -m codesight consistency ...`) is documented in
`ARCHITECTURE.md` and `AGENTS.md`.

## 8. Relationship to existing specs and code

- **Specs 011/012** remain research-only per their own stated authorization
  boundaries; this spec does not retroactively authorize anything they
  declined to authorize. It implements the narrow, reversible slice the
  prior audit's section 7 already described as safe process recommendations
  independent of specs 011/012's unresolved product questions.
- **`src/codesight/holus.py`** (the Holus v1 lineage adapter) is unrelated
  read-only import machinery for a different producer's export format; this
  system does not read, write, or depend on it, and does not duplicate its
  validation logic.
- **Graphify** (`graphify-out/graph.json`) is read directly as the
  `structural` provider's data source. This system does not invoke the
  Graphify CLI (unavailable in this environment — see the "Graphify
  availability" note in this PR) and does not modify `graphify-out/`.
- **The prior audit report's "no-build" recommendation** (section 8) is
  respected: this system adds no provider lifecycle, no new external
  service, no egress path, and no operational burden beyond one local
  SQLite file. It is a bounded evidence layer over already-tracked repo
  content, not a router or platform.
