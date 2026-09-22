# Spec 003: Incremental Refresh

**Status:** planned
**Phase:** v0.5
**Author:** Juan Martinez
**Created:** 2026-02-24
**Updated:** 2026-02-28

## Problem

When a client updates a few documents in their folder (e.g., a new version of a contract), re-indexing currently reads every file even though most haven't changed. Content hashing prevents re-embedding unchanged chunks, but the file reading, parsing, and chunking still happens for all files. For a 5,000-document folder, this wastes time on unchanged files.

Clients expect that updating one document and searching again should take seconds, not minutes.

## Goals

- Git repos: use `git diff --name-only` to identify only changed files
- Non-git folders (typical for document collections): use file modification times (mtime)
- Only re-parse, re-chunk, and re-embed changed/new files
- Remove vectors and FTS entries for deleted files
- Re-index of 5K docs where 10 changed should take <10 seconds (vs minutes for full rebuild)

## Non-Goals

- Real-time file watching / filesystem events — too complex, polling is sufficient (see deprecated spec 005)
- Submodule support for git repos
- Tracking files outside the indexed folder

## Solution

```
Re-index flow:
    |
    ├── Git repo detected?
    |   ├── Yes → git diff --name-only <last-indexed-commit> → changed file list
    |   └── No  → compare file mtimes against last_indexed_at → changed file list
    |
    ├── For each changed/new file:
    |   └── Parse → chunk → embed → store (same as full index)
    |
    ├── For each deleted file:
    |   └── Remove chunks from LanceDB + SQLite FTS
    |
    └── Update last_indexed_at / last_commit in repo_meta
```

## Implementation Notes

### Key Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Stale threshold | 60 minutes (default) | Configurable via `HOLUSIGHT_STALE_MINUTES` |
| Large diff threshold | 1000 files | If >1000 files changed, full rebuild is cheaper |
| mtime precision | 1 second | Filesystem-dependent, 1s is safe across platforms |

### Dependencies

- Depends on: Spec 001 (core search engine)
- Depended on by: Spec 008 (Docker deployment — scheduled re-index via cron)

### Implementation Steps

1. Store `last_indexed_at` timestamp and `last_commit` hash in `repo_meta` table
2. On `index()`: check if git repo → use `git diff`, else use mtime comparison
3. Build list of changed/new/deleted files
4. If changes > 1000 files → fall back to full rebuild
5. Process only changed files through parse → chunk → embed → store pipeline
6. Delete vectors + FTS entries for deleted files
7. Update `repo_meta` with new timestamp/commit

## Alternatives Considered

### Alternative A: Filesystem watcher (inotify/FSEvents)

Trade-off: Real-time updates, but platform-specific (Linux vs macOS vs Windows), complex error handling, requires background daemon.
Rejected because: Polling on search (current approach) or cron-based re-index is simpler and sufficient for consulting deployments.

### Alternative B: Hash all files on every check

Trade-off: More accurate than mtime, but requires reading every file to compute hash — defeats the purpose.
Rejected because: mtime is fast and accurate enough. Content hash at chunk level already handles the edge case of mtime changing without content change.

## Edge Cases & Failure Modes

- Non-git folder → fall back to mtime-based change detection automatically
- Merge commits → diff against merge base, not just HEAD~1
- Binary files changed → skip (already filtered by extension check)
- Very large diff (>1000 files) → full rebuild is cheaper, auto-fallback with log message
- File renamed (same content) → mtime detects as new file, content hash prevents re-embedding
- Document replaced with same name but different content → mtime catches it
- Interrupted re-index → partial state is safe (chunks are individually inserted, not transactional)

## Open Questions

- [ ] Should `status()` report which files changed since last index? Useful for debugging but adds overhead. — @juan
- [ ] For non-git folders, should we store per-file mtimes or just a single last_indexed_at? Per-file is more precise but needs a new table. — @juan

## Acceptance Criteria

- [ ] Modify one file in a 500-doc folder, re-index → only that file is processed
- [ ] Delete a file → its vectors and FTS entries are removed
- [ ] `index(force_rebuild=True)` still triggers full rebuild, ignoring incremental logic
- [ ] Git repo: uses `git diff --name-only` to find changed files
- [ ] Non-git folder: uses mtime comparison to find changed files
- [ ] Re-index of 500 docs with 5 changes completes in <5 seconds
- [ ] Large diff (>1000 files) auto-falls back to full rebuild with log message
- [ ] `status()` reports last-indexed commit hash (git) or timestamp (non-git)
