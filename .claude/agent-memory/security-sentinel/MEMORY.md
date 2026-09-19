# Security Sentinel Memory - codesight

## Session Notes

- 2026-09-19 audit verdict: FAIL. Full suite passed (726 passed, 1 skipped), targeted security/server tests passed (26), Ruff passed, compileall passed, `uv pip check` passed, and no source/dependency diff was present.
- 2026-09-19 E2E reconfirmation: `walk_repo_files()` indexed a symlinked file whose target was outside the configured root and stored the external file's content. Setting `CODESIGHT_DATA_DIR` below the indexed root created SQLite/LanceDB files inside that root. A `.holusight` symlink redirected consistency-cache writes to an external directory. Public `/api/health` returned the absolute documents path.

## Known Attack Vectors

- **Critical - file symlink escape:** `src/codesight/indexer.py` walks symlinked files and later reads them without a resolved-root containment check immediately before read. Revalidate and use no-follow/open-handle semantics to cover replacement races.
- **High - derived index placement:** `src/codesight/config.py:repo_data_dir()` trusts `CODESIGHT_DATA_DIR`; it can be inside or symlinked through the indexed root and violates the read-only invariant.
- **High - consistency cache symlink:** `src/codesight/consistency_store.py` follows `.holusight` symlinks. Reject symlinked parents before mkdir/connect.
- **Medium - vector filter injection:** `src/codesight/store.py:get_chunk_vectors()` interpolates chunk IDs into a Lance filter without escaping, unlike deletion's allowlist. Quoted filenames can cause VPRF failures or filter manipulation.
- **Medium - auth footgun:** `CODESIGHT_ALLOW_UNAUTHENTICATED=true` bypasses auth even with `CODESIGHT_PRODUCTION=1`, while CLI/Docker defaults bind to `0.0.0.0`.
- **Low - path disclosure:** public health returns the resolved document path; authenticated status also exposes absolute repository paths.
- **Low - DoS:** file-size limit is per file; aggregate file/count/time budgets are absent and API embedding backends do not share the local character bound.

## Cleared Issues

- FTS5 MATCH injection is covered by sanitization and parameterized SQL.
- Protected FastAPI endpoints enforce API-key/Bearer authentication in production-shaped mode unless the explicit unauthenticated escape hatch is enabled.
- Search/provider result excerpts are bounded by default.
- Holus import rejects absolute/traversal references and private/URL-like metadata values.
- No dependency changes were present in the 2026-09-19 cycle; `uv pip check` passed.
