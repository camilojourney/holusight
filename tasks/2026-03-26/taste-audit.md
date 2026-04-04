# Taste Audit -- CodeSight v0.3

**Date:** 2026-03-26
**Auditor:** Claude Opus 4.6 (automated)
**Scope:** All UI, API, CLI, docs, and business content

---

## Overall Score: 6.5 / 10

A solid engineering foundation with clean architecture and honest technical writing. Falls short on visual craft (the Streamlit UI is a prototype, not a product), brand inconsistency (name confusion between "CodeSight" and "codesight"), and test coverage (effectively zero real tests).

---

## 1. Visual Craft -- 4 / 10

### Streamlit Demo UI (`demo/app.py`)

**Looks like:** A developer's prototype -- default Streamlit theme, no custom CSS, no logo, no color palette. A magnifying glass emoji as the favicon.

**Should look like:** A polished enterprise knowledge search interface with a custom dark or brand-colored sidebar, a proper logotype, and clear visual hierarchy that signals "this handles your company's confidential data."

Specific issues:
- No custom theming. Default Streamlit gray/white/red. Every Streamlit demo on the internet looks identical.
- Folder path is a raw text input. Non-technical users (the stated target: "non-technical user" per ARCHITECTURE.md) will not know what a folder path is.
- Source citations render as raw expandable cards with monospaced code blocks. For document search (PDFs, contracts), this should be formatted prose with highlighted matches, not `st.code()`.
- No loading skeleton or progress indication beyond a spinner. Long indexing operations show "Indexing documents..." with no progress bar, file count, or ETA.
- No empty state design. When no folder is set, the main area is blank.
- No favicon or Open Graph metadata for when links are shared.

### CLI (`__main__.py`)

**Looks like:** Competent argparse CLI with clear subcommands.

**Should look like:** This is actually fine for the audience. The `--help` output is clean and the search result formatting (file path, page range, scope, snippet) is readable.

Minor nit: search results print "page X-Y" even for code files where they're line numbers, not pages. The label should adapt.

---

## 2. Content Quality -- 8 / 10

### Technical Documentation

The technical writing is the strongest asset. ARCHITECTURE.md, COMPARISON.md, and the business specs are genuinely excellent:

- ARCHITECTURE.md is a model guided tour. ASCII diagrams, clear data flow, "What NOT to Change" section. This is better than most production repos at 100x the team size.
- COMPARISON.md is ruthlessly honest. "CodeSight is ~40% of what Cursor does." "Embeddings for code search are real but overhyped." This kind of writing builds trust.
- Business specs (005-money-model.md, 006-go-to-market.md) are detailed and credible. The financial model with per-tier breakdowns by company size is investor-grade analysis.

Issues:
- README.md Section "Workflow: Explore -> Plan -> Execute -> Review" describes an obsolete agent workflow using `claude -p` with shell pipes. This contradicts the workspace rules that say "Never use `claude -p`." Stale docs are liars (as COMPARISON.md itself notes).
- The `justfile` references `semantic_search_mcp` (the old package name) in the `dev` and `inspect` commands. This is a post-rename artifact.
- Duplicate ADRs: `0001-lancedb-over-chromadb.md` AND `0001-two-deployment-modes.md` both use number 0001. Same for 0002, 0003. The numbering system has collisions.
- `docs/MARKET.md`, `docs/RESEARCH.md`, `docs/STACK-VALIDATION.md` violate the repo's own structure rules (`.claude/rules/structure.md` says these are "legacy violations" that should be migrated to `specs/`).

### Business Content

- Proposal templates are solid, practical, and client-ready.
- The one-pager template uses "Camilo Martinez" as the consultant name but the repo brand is "CodeSight." The personal name should match whatever brand identity is chosen.
- Pricing pages use clear comparison tables with callout boxes (`> [!IMPORTANT]`, `> [!TIP]`). This is good GitHub-native formatting.

---

## 3. Brand Alignment -- 5 / 10

### Name Confusion

The project has an identity crisis across three names:
1. **"codesight"** -- Python package name, CLI name, data directory (`~/.codesight/`)
2. **"CodeSight"** -- Used in docs, README, ARCHITECTURE.md, demo UI title
3. **"Holusight"** -- The repo name and (presumably) the intended product name

The repo is called `holusight` but the package is `codesight`, the storage dir is `~/.codesight/`, and the UI says "CodeSight." If the product is being rebranded to Holusight, nothing in the code reflects this.

### Positioning Mismatch

- Vision.md positions this as an "enterprise knowledge search appliance" for finance, defense, legal, healthcare.
- The demo UI is a Streamlit chat with a folder path text input. These two things are separated by about $500K of product development.
- The README positions it as a developer tool ("AI-powered document search engine"). The business specs position it as enterprise software. The pitch template positions it as a consulting engagement. Pick one voice.

### Design Language

- No color palette, typography, or design tokens defined anywhere.
- The magnifying glass emoji is the only visual identity.
- Enterprise customers in finance and healthcare expect visual sobriety. The Streamlit default theme and emoji icons signal "hackathon project."

---

## 4. Code Aesthetics -- 7 / 10

### What's Good

- Consistent module structure: every file has a docstring, clear section headers with `# -----`, and logical function ordering.
- Clean separation of concerns: `api.py` -> `indexer.py` -> `chunker.py`/`parsers.py` -> `store.py`. Each module has a single responsibility.
- Lazy loading pattern used consistently (embedder, LLM, store, LanceDB table). Good for startup time.
- Type hints everywhere. Pydantic models for all data structures. Protocol classes for embedder and LLM backends.
- The `config.py` is well-organized with clear defaults, a model registry, and a single `ServerConfig` Pydantic model.

### What Needs Work

- `store.py` has a SQL injection vector in `upsert_chunks`: `f'chunk_id = "{cid}"'` constructs filter strings by interpolation. If a chunk_id contains a quote, this breaks. Should use parameterized queries or escape the IDs.
- The `_embed_and_store_batch` function in `indexer.py` silently swallows exceptions during LanceDB delete (`except Exception: pass`). Failed deletes could leave orphaned vectors that pollute search results.
- `embeddings.py` uses `@lru_cache(maxsize=1)` on `get_embedder`, but the cache key includes `expected_dim` which is a mutable int. If someone calls with different dims, the first cached result wins silently.
- No `__all__` exports in most modules. Only `__init__.py` has one.
- The `_launch_demo` function resolves the demo path with `Path(__file__).parent.parent.parent / "demo" / "app.py"` -- this breaks if the package is installed as a wheel (no `demo/` directory in the wheel).

---

## 5. Information Architecture -- 7 / 10

### Strengths

- The four-category docs rule (vision, roadmap, decisions, playbooks) is clean and enforced.
- Specs are numbered and flat. Good convention.
- The `ARCHITECTURE.md` as a standalone root file (not buried in `docs/`) is the right call for discoverability.

### Weaknesses

- The `business/` directory duplicates content from `docs/playbooks/` (client-onboarding.md, pitch-prep.md, sales-process.md appear in both places).
- `docs/research/domain/` exists with INDEX.md and overview.md -- this violates the four-category rule and the structure.md rules.
- The `tasks/` directory has old files (`consulting-proposal-knowledge-platform.md`, `mvp-demo-and-proposal.md`, `next.md`) that were supposed to be temporary per structure.md ("Temporary session task files -- delete when done").

---

## Summary Table

| Dimension | Score | Looks Like | Should Look Like |
|-----------|-------|-----------|-----------------|
| Visual Craft | 4/10 | Default Streamlit prototype with emoji favicon | Branded enterprise UI with custom theme, progress indicators, empty states |
| Content Quality | 8/10 | Honest, detailed technical writing with some stale sections | Same quality, but purge stale references and fix ADR numbering |
| Brand Alignment | 5/10 | Three names (codesight/CodeSight/holusight), mixed positioning | One name, one voice, consistent enterprise identity |
| Code Aesthetics | 7/10 | Clean architecture with good separation; some injection risks | Fix SQL injection in store.py, add error handling for silent swallows |
| Info Architecture | 7/10 | Good structure rules, partially enforced | Remove duplicates, enforce the four-category doc rule, clean tasks/ |

---

## Top 5 Taste Fixes (If Only 5 Things Change)

1. **Rename everything to one name.** Package, CLI, storage dir, UI title, repo -- all one name. Either "codesight" or "holusight," not both.
2. **Custom Streamlit theme.** Dark sidebar, brand color, logotype instead of emoji. 30 minutes of CSS via `st.markdown(unsafe_allow_html=True)` or a `.streamlit/config.toml`.
3. **Fix the SQL interpolation in store.py.** This is a correctness bug, not just taste.
4. **Delete stale content.** Remove `docs/MARKET.md`, `docs/RESEARCH.md`, `docs/STACK-VALIDATION.md`, `docs/research/`. Clean `tasks/` of old files. Fix README workflow section.
5. **Fix the justfile.** The `dev` and `inspect` commands reference the old `semantic_search_mcp` package name.
