# Holusight-AXI Command Surface

**Status:** Phase 1 implemented (direct-PR). This spec is the design record
for the `holus` command-line tool; the versioned contract it implements
lives in code as `src/codesight/axi_schema.py`, not in this prose.

**Authorization boundary:** captain-authorized per
`/Users/camiloslaptop/github/firstmate/data/holusight-axi-core-v1/instructions.md`.
Scoped to the smallest stable, job-oriented AXI vertical slice described
there - no hosted gateway, central trace/training store, autonomous
routing/promotion, broad MCP architecture, or production deployment.

## 1. Purpose

`specs/013-holusight-axi-consistency-architecture.md` (Phase 1, PR #16)
built the documentation-code consistency *engine* - the Python functions
and `.holusight/consistency.db` cache. It exposed that engine through the
existing generic `python -m codesight consistency <verb>` subcommand
group. `specs/011-holusight-product-architecture-research.md` (research
only, not implementation authorization) separately proposed a smaller,
job-oriented command surface - `holus`, `holus evidence`, `holus check`,
`holus status`, `holus providers` - described in AXI terms: content-first,
projection-aware, TOON-by-default, structured-error, no-hidden-egress.

This spec is the implementation authorization and design record for that
surface. It does not replace `python -m codesight consistency ...`
(unchanged - still the direct, generic entry point used by tests and by
this repository's own dogfooding), and it does not create a router,
autonomous provider promotion, or a new retrieval mechanism. `holus` is a
thin, job-shaped CLI over already-landed code:

- `src/codesight/consistency.py` (Phase 1 consistency engine, PR #16)
- `src/codesight/search.py` (`hybrid_search`, already-shipped BM25+vector)
- `graphify-out/graph.json` (tracked structural graph, read via the exact
  same `consistency._load_structural_index` /
  `consistency.structural_graph_freshness` functions PR #17's own
  `graphify` eval baseline reuses - see the PR 17 preflight report for the
  non-overlap boundary this spec was built to)

## 2. Command surface

```
holus                        content-first repository home view
holus evidence "<question>"  routed evidence packet
holus check [scope]          post-change consistency check
holus status                 repository/provider status
holus providers              provider availability/freshness/egress
```

Provider selection is a diagnostic flag beneath these jobs, never a
parallel API:

```
--mode auto|exact|semantic|structure
--provider exact|structural|consistency|semantic
--explain-route
```

The full, versioned flag/example set for every command lives in
`src/codesight/axi_schema.py` (`AXI_COMMANDS`). `src/codesight/cli_axi.py`
parses against that schema; `src/codesight/axi_skill_gen.py` generates
`.claude/skills/holus/SKILL.md` from the same schema. `tests/
test_axi_skill_drift.py` fails if the committed skill and the schema ever
disagree - this is the drift check required by acceptance criterion 7 of
the launch instructions. Bump `AXI_SCHEMA_VERSION` (semver, included in
every payload as `schema_version`) on any command/flag/field change.

## 3. Providers

Four provider kinds, implemented in `src/codesight/axi_providers.py`:

| Provider | Source | Egress | Cost |
|---|---|---|---|
| `exact` | Literal/token substring scan over `consistency.discover_artifacts()` (the same gitignore-aware walk the consistency engine uses) | none | bounded scan (400 files / 30 matches) |
| `structural` | Tracked `graphify-out/graph.json`, via `consistency._load_structural_index` / `structural_graph_freshness` - read-only reuse, never modified, matching the PR 17 preflight's non-overlap boundary | none | bounded match count (30) |
| `consistency` | `.holusight/consistency.db` concept/claim/health-flag cache | none | trivial (SQLite lookup) |
| `semantic` | `search.hybrid_search` against an **already-built** local index only | none by default; `external:voyage` only if the index was built with Voyage embeddings **and** `--allow-egress` is passed | one hybrid search call, top 5 |

`--mode auto` (default) runs `exact`, `structural`, and `consistency`
unconditionally (all local, deterministic, sub-second) and `semantic` only
if a local index already exists - `holus evidence` never triggers an
index build or a network call as a side effect of a read-only evidence
job. `--mode exact|semantic|structure` restricts to one provider family;
`--provider NAME` restricts further to exactly one provider and must be
compatible with `--mode` if both are given.

### Egress default

`holus evidence`'s semantic provider inspects the local index's stored
`embedding_model` metadata. If it names a Voyage model, the provider
reports `denied` unless the caller passes `--allow-egress`. Independent of
that check, the CLI also removes `VOYAGE_API_KEY` from its own process
environment for the duration of every provider call unless
`--allow-egress` is set (`axi_providers._no_egress_env`), so an ambient
`VOYAGE_API_KEY` in the shell can never cause a silent external call.

### Explicit provider states

Every provider returns one of: `ok`, `no_evidence`, `unavailable`,
`stale`, `denied`, `unsupported`, `budget_exceeded` - never a fabricated
answer when evidence is absent. `budget_exceeded` is a bounded-work
cutoff (files/matches scanned), not a dollar cost - there is no billing
surface in this local-only CLI.

## 4. Evidence packet shape

```
schema_version, answerable, question, snapshot{commit, dirty},
route[], evidence[]{provider, source, location, excerpt,
  excerpt_truncated, excerpt_total_chars, confidence|score, relation},
evidence_total, coverage(sufficient|partial|none|unknown), reason,
providers_checked[]{provider, state, detail, route_reason?},
egress{occurred, destination}, truncated, latency_ms, warnings[]
```

`coverage` distinguishes "found evidence" (`sufficient`/`partial`) from
"ran fine but found nothing" (`none`, `reason: no_matching_evidence`) from
"couldn't even check" (`unknown`, `reason: no_provider_available`) - the
three states spec 011 asked the router to distinguish, mapped onto this
repository's actual provider set.

## 5. `check` baseline semantics

`consistency.check_consistency` compares *current on-disk content hashes*
against the cache's *last-refreshed* hashes. `holus check` must never
silently call `refresh()` on every invocation - that would erase the very
drift signal `check` exists to surface. So:

- `holus`, `holus status`, `holus providers`, and `holus evidence`'s
  consistency provider all call `_ensure_cache_bootstrapped()`, which
  refreshes **only if `.holusight/consistency.db` has never been built**
  (a one-time, zero-config bootstrap for a fresh checkout).
- `holus check` never auto-refreshes. Pass `--refresh` explicitly to reset
  the baseline to current disk state before checking (useful right after
  a legitimate coordinated spec+code change).

## 6. Output formats

JSON is the lossless canonical contract (`--format json`), matching every
other model in this codebase (`.model_dump()` → `json.dumps`). `--format
toon` (default) is a compact agent-facing projection generated at the
output boundary only (`src/codesight/toon.py`) - nothing in this codebase
parses TOON back into Python. `--format text` is a plain human-readable
rendering. `--fields a,b.c` (dotted-path projection, `src/codesight/
cli_axi.py:project_fields`) works against the same JSON-shaped payload
regardless of the chosen output format.

## 7. AXI compliance notes

- Unknown flags/commands are rejected (exit 2) with the valid set listed
  inline in the error's `help` field - never silently ignored.
- `--help` works on every command, including the bare `holus` home view.
- Structured errors render on stdout in the requested format, never a raw
  Python traceback (`cli_axi.main`'s top-level exception handler).
- Exit codes: `0` success including definitive empty/no-evidence/already-
  up-to-date answers, `1` runtime error, `2` usage error.
- List outputs (evidence items, `check`'s all-concepts view) are capped
  (20 items) with an explicit `truncated` flag, a total count, and a help
  hint naming the escape hatch - never a silent partial list.
- `evidence`'s `--mode auto` display list applies a bounded, deterministic
  **per-provider display quota** (`cli_axi._select_display_items`) when
  merging results into the 20-item cap: providers are visited round-robin
  in the same fixed `exact, structural, consistency, semantic` order every
  round, taking at most one item per provider per round, so that one
  provider's own item count (e.g. `exact`'s scan matches) cannot by itself
  crowd out every other provider's already-successful evidence. This is an
  anti-starvation **display** safeguard, not provider routing or
  promotion - see §8. It does not change which providers run, in what
  order they are attempted, `evidence_total`, or `truncated`; it only
  changes which subset of the already-computed items is shown when the
  merged total exceeds the cap. Items are never sorted, scored, or ranked
  across providers to decide this - see §8.

## 8. Non-goals (unchanged from the launch instructions)

No hosted gateway, no central trace/training store, no autonomous
provider routing/promotion beyond the deterministic `--mode auto` order
above, no broad MCP architecture, no production deployment. `graphify`
CLI invocation is out of scope here exactly as it was for spec 013 - the
structural provider reads the tracked `graphify-out/graph.json` file
directly and never shells out to `graphify`.

**Clarification (anti-starvation display quota is not routing):** the
`--mode auto` order (`exact, structural, consistency, semantic`) governs
which providers run and in what sequence they are attempted - that is
"provider routing" and stays exactly as this spec always described it,
untouched. The per-provider display quota described in §7 operates one
level downstream of that: after every provider in the fixed order has
already run to completion, the quota only bounds how the already-computed
`evidence` items are merged into the capped display list, so that one
provider cannot silently starve another's real, already-successful
results out of what the user sees. It never decides which providers run,
never reorders or skips a provider, and never compares `score`/
`confidence` across providers to pick winners - it is a fixed-order
round-robin over already-run results, not a relevance-based promotion
mechanism. `evidence_total`, `truncated`, and `providers_checked` always
reflect every provider's full, unbounded result regardless of what the
quota chose to display.

## 9. Relationship to PR 17

Per the read-only preflight at
`/Users/camiloslaptop/.treehouse/firstmate-8bf1b0/6/firstmate/data/holusight-axi-pr17-preflight/report.md`:
this spec is independent of, and does not stack on, PR #17 (spec 014,
retrieval-evaluation-harness expansion). It touches no file under
`tests/eval_*.py`, `tests/test_eval_*.py`, or `specs/014-*`, and calls
(never modifies) `consistency._load_structural_index` /
`structural_graph_freshness` - the same two functions PR 17's own
`graphify` eval baseline reuses, so both subsystems agree on what "stale"
means.
