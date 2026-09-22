# Spec 005: Automatic Re-indexing

**Status:** deprecated
**Phase:** TBD
**Author:** Juan Martinez
**Created:** 2026-02-24
**Updated:** 2026-02-28

## Problem

Originally: users had to manually call `index()` to keep the search index up to date with document changes. The idea was to add `watch`/`unwatch` MCP tools for automatic background indexing.

With the v0.2 pivot away from MCP to a Python API + web chat UI, the original design (MCP watch/unwatch tools) no longer applies. The current approach — auto-refresh on stale index when `search()` is called — is sufficient for consulting deployments.

## Goals (Original — Preserved for Reference)

- Register a folder for automatic refresh when documents change
- Background refresh without user intervention
- Watch list persisted across process restarts

## Why Deprecated

1. **Auto-refresh on search** already handles staleness — when `search()` detects the index is older than `HOLUSIGHT_STALE_MINUTES`, it triggers a re-index automatically
2. **Scheduled re-indexing** via cron covers the gap: `*/60 * * * * python -m holusight index /path/to/docs`
3. **Filesystem watchers** add platform-specific complexity (inotify on Linux, FSEvents on macOS, ReadDirectoryChangesW on Windows) with limited benefit for the consulting use case
4. **Higher priority items**: pluggable LLM (006), reranking (007), Docker deployment (008)

## If Revisited

The implementation would likely be:

```bash
# CLI command that runs a background daemon
python -m holusight watch /path/to/docs --interval 300
```

- Uses `watchdog` library for cross-platform filesystem events
- Debounces changes (wait 5s after last change before re-indexing)
- Alternatively: simple polling loop checking mtimes every N minutes
- Logs re-index events to `~/.holusight/data/<hash>/watch.log`

## Acceptance Criteria (Original — Not Implemented)

- [ ] Register a folder for automatic refresh
- [ ] Background refresh runs when documents change
- [ ] Watch list persisted across process restarts
- [ ] `status()` reports watched folders and their freshness
