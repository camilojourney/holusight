# ADR-0011: One atomic SQLite database for the consistency cache

**Date:** 2026-08-22
**Status:** Accepted

## Context

Phase 1 of the Holusight-AXI documentation-code consistency system
(`specs/013-holusight-axi-consistency-architecture.md`) needs a local,
gitignored, rebuildable cache under `.holusight/` to store classified
artifacts, the concept registry, edges/claims with provenance, and health
flags. The reference research PDF
(`Documentation Code Consistency Systems.pdf`, page 82) sketches a
multi-file layout:

```
.holusight/
├── artifact-index.sqlite
├── concepts.sqlite
├── relationships.sqlite
├── claims.sqlite
├── embeddings/
├── graph-cache/
└── health/
```

That sketch comes from an unstructured brainstorming transcript, not a
reviewed design, and it was never load-bearing on any actual constraint —
it's simply the shape a first guess takes when naming things by concern.

## Decision

Use **one atomic SQLite database**, `.holusight/consistency.db`, holding six
tables: `repo_state`, `artifacts`, `concepts`, `edges`, `claims`,
`health_flags`. No separate per-concern database files, and no
`embeddings/`, `graph-cache/`, or `health/` directories.

## Consequences

**Easier:**

- `refresh()` writes across all six tables inside one connection; a crash or
  exception mid-refresh leaves the previous consistent snapshot intact
  (SQLite's own transactional guarantees), rather than requiring hand-rolled
  cross-database transaction coordination that the multi-file sketch would
  need to stay consistent (e.g. `concepts.sqlite` updated but
  `edges.sqlite` not, after a partial failure).
- One file to gitignore, one file to delete when a human wants to force a
  full rebuild, one file to inspect with `sqlite3 .holusight/consistency.db`.
- Matches this repository's existing convention: `src/codesight/store.py`'s
  `FTSSidecar` already keeps chunks + FTS5 index + repo metadata in one
  SQLite file (`metadata.db`) per indexed folder, rather than splitting by
  concern.
- No empty placeholder directories are created before there is content to
  put in them (`embeddings/`, `graph-cache/`, `health/` from the PDF sketch
  are all unused in Phase 1 — see below).

**Harder:**

- If a future phase needs to store large binary blobs (e.g. cached
  embedding vectors) at a scale where SQLite's `BLOB` storage becomes a
  bottleneck, that phase will need to introduce a separate store then — not
  before there is a demonstrated need (see spec 013 section 5, "Phase 2
  criteria").
- A single file is a single point of lock contention under concurrent
  writers. Phase 1 has exactly one writer (the `refresh()` CLI command, run
  by a human or one agent at a time); this is not a concern at current
  scale and WAL mode already allows concurrent readers during a write.

## Alternatives Considered

1. **The PDF's multi-file sketch (`artifact-index.sqlite` +
   `concepts.sqlite` + `relationships.sqlite` + `claims.sqlite`).**
   Rejected: no concrete requirement in this repository needs independently
   swappable or independently sized stores per concern, and splitting adds
   cross-database transaction coordination for no benefit at ~127 tracked
   files.
2. **`embeddings/` directory of cached vectors.** Rejected for Phase 1: the
   semantic provider is opt-in and recomputes similarity per invocation
   rather than persisting vectors; there is nothing to cache until the
   semantic provider is used enough (Phase 2 criterion 4 in spec 013) to
   justify persistence.
3. **`graph-cache/` directory mirroring `graphify-out/graph.json`.**
   Rejected: `graphify-out/graph.json` is already tracked in git and read
   directly; copying it into `.holusight/` would create a second, easily
   stale copy of the same data with no benefit.
4. **`health/` directory of health-report files.** Rejected: health flags
   are structured, queryable rows (`flag_type`, `concept_id`, `severity`),
   which a `health_flags` table serves better than a directory of report
   files: it supports "flags for this concept" and "flags of this severity"
   queries directly instead of requiring a second index over the directory.
5. **No persistent cache at all (recompute everything each run).**
   Rejected: this would defeat the "incremental local cache" requirement in
   spec 013 — even Phase 1's partial incrementality (skip re-classifying
   unchanged artifacts by content hash) needs somewhere to remember the
   prior classification.
