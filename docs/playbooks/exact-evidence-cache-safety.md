# Exact evidence cache safety

`holus evidence --mode exact` and `holus evidence --provider exact` perform a read-only, gitignore-aware repository walk. They do not bootstrap or update `.holusight/consistency.db`, so a fresh consumer repository remains clean and its file manifest is unchanged.

Other evidence modes retain the historical one-time consistency bootstrap. This is intentionally not a relocation or migration: an existing repo-local `.holusight/consistency.db` is never deleted, moved, overwritten, or symlinked. The consistency provider reports `unavailable` until that cache is explicitly refreshed.

To create or refresh the repository-local consistency cache, use the explicit consistency workflow (`holus check --refresh` or the Python `consistency.refresh()` API). To roll back this behavior, revert the conditional bootstrap change; no data migration is required. Exact mode has no consistency-cache coverage by design, so callers needing that provider should use auto mode or an explicit consistency query and interpret `unavailable`/`unknown` states rather than inferring freshness.
