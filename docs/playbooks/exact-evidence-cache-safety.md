# Exact evidence cache safety

`holus evidence` (including default `--mode auto`) and `--mode exact` perform read-only provider work. They do not bootstrap or update `.holusight/consistency.db`, so a fresh consumer repository remains clean and its file manifest is unchanged. In auto mode, the consistency provider reports `unavailable` when no cache exists, while exact, structural, and semantic providers still report their own explicit states.

Other read-only jobs retain the historical one-time consistency bootstrap. This is intentionally not a relocation or migration: an existing repo-local `.holusight/consistency.db` is never deleted, moved, overwritten, or symlinked. The consistency provider reads a warmed legacy cache without modifying it.

To create or refresh the repository-local consistency cache, use the explicit consistency workflow (`holus check --refresh` or the Python `consistency.refresh()` API). To roll back this behavior, revert the evidence bootstrap removal; no data migration is required. Callers using a fresh repository should interpret `unavailable`/`unknown` states rather than inferring consistency freshness.
