# UX Review -- CodeSight v0.3

**Date:** 2026-03-26
**Auditor:** Claude Opus 4.6 (automated, read-only)
**Scope:** API endpoints, CLI, Streamlit web UI, docs

---

## P0 -- Critical (Blocks Demo / First Client)

### P0-1: Streamlit UI requires raw folder path input

**Where:** `demo/app.py`, sidebar `st.text_input("Document folder path")`

**Problem:** The vision.md says the target user is "non-technical." The demo UI requires typing an absolute filesystem path like `/path/to/your/documents`. Non-technical users do not know filesystem paths. Enterprise users expect to connect to SharePoint, not type paths.

**Impact:** The demo fails to demonstrate the product as described in sales materials. A client watching a pitch would see a text field asking for a Unix path and immediately lose confidence.

**Fix plan:**
- Add a file browser (Streamlit `st.file_uploader` for drag-and-drop, or list recently-indexed folders as buttons).
- For enterprise demos, pre-configure a demo folder and show it pre-indexed.
- Long-term: replace folder path with connector config (SharePoint URL, Google Drive link).

### P0-2: No error recovery on missing API key

**Where:** `api.py` -> `llm.py`, `embeddings.py`

**Problem:** When a user types a question and hits enter, if `ANTHROPIC_API_KEY` is not set, the `ask()` call raises a `ValueError` with a raw traceback. The Streamlit UI catches it with `st.error(f"Error: {e}")` but the message is technical: "ANTHROPIC_API_KEY environment variable is required for the Claude backend."

**Impact:** Non-technical users see a Python error message. They have no idea what an environment variable is or how to set one.

**Fix plan:**
- Show a friendly onboarding wizard in the sidebar: "To enable AI answers, add your API key" with a masked text input and a link to get a key.
- Separate search (which is 100% local) from ask (which needs an API key). Let users search even without a key.
- When no key is set, disable the ask functionality with a clear message rather than erroring.

### P0-3: Stale justfile commands

**Where:** `justfile`, lines 8-9 and 16-17

**Problem:** `just dev` runs `python -m semantic_search_mcp` and `just inspect` runs the MCP inspector on `semantic_search_mcp`. The package was renamed to `codesight` in v0.2. These commands crash with `ModuleNotFoundError`.

**Impact:** Any developer (or agent) running `just dev` or `just inspect` gets an error. This breaks the development workflow.

**Fix plan:**
- Update `just dev` to `python -m codesight demo` (or whatever the correct dev server command is).
- Update `just inspect` or remove it if MCP is no longer the interface.

---

## P1 -- High (Degrades First Impression / Usability)

### P1-1: No progress feedback during indexing

**Where:** `demo/app.py` lines 117-127, `indexer.py`

**Problem:** Clicking "Index" shows `st.spinner("Indexing documents...")` with no progress bar, file count, or ETA. For a 50K-document enterprise folder, indexing takes minutes to hours. The user sees a spinner and nothing else.

**Impact:** Users think the app is frozen. They close the tab. Or they click "Index" again, potentially corrupting state.

**Fix plan:**
- Add a `progress_callback` parameter to `index_repo()` that reports (files_processed, total_files).
- In the UI, show a `st.progress()` bar with a counter: "Indexing 142 / 1,234 files..."
- Show the elapsed time.

### P1-2: Chat history lost on page refresh

**Where:** `demo/app.py`, `st.session_state.messages`

**Problem:** Streamlit session state is in-memory. Refreshing the page or opening a new tab loses all chat history. Enterprise users expect persistence.

**Impact:** A user who found a useful answer cannot retrieve it after a page refresh. This is especially painful during demos.

**Fix plan:**
- Store conversation history in the SQLite metadata DB (new `conversations` table).
- On load, show the last N conversations in the sidebar.
- Long-term: move to a proper backend (FastAPI + database) as planned in v0.4 roadmap.

### P1-3: Search results show "page X-Y" for code files

**Where:** `__main__.py` line 71: `print(f"--- {r.file_path} (page {r.start_line}-{r.end_line}, ...)")`

**Problem:** The CLI always says "page X-Y" regardless of whether the result is from a PDF (where pages make sense) or a Python file (where they're line numbers). The Streamlit UI says "Lines/pages: X-Y" which is slightly better but still ambiguous.

**Impact:** Minor confusion. Users familiar with the codebase will understand, but it looks unpolished.

**Fix plan:**
- Check the `language` field: if `pdf`/`docx`/`pptx`, say "page"; otherwise say "lines."
- In SearchResult, add a computed property `location_label` that returns the appropriate string.

### P1-4: No keyboard shortcuts in Streamlit UI

**Where:** `demo/app.py`

**Problem:** The only interaction is typing in the chat input and pressing Enter. No shortcut to focus the search bar, no Cmd+K for quick search, no Escape to dismiss. Enterprise users expect keyboard-driven UIs.

**Impact:** Power users feel friction. But since this is Streamlit and keyboard shortcuts are hard to add, this is a limitation of the framework.

**Fix plan:**
- Accept this as a Streamlit limitation.
- When migrating to FastAPI + React (v0.4), build keyboard shortcuts from the start.

### P1-5: `demo/app.py` launch path fragile

**Where:** `__main__.py` line 94: `Path(__file__).parent.parent.parent / "demo" / "app.py"`

**Problem:** The demo launch command calculates the path relative to the installed package location. If the package is installed as a wheel (not editable), the `demo/` directory won't exist at that relative path.

**Impact:** `python -m codesight demo` fails for users who installed via `pip install codesight` (non-editable). Only works in dev mode.

**Fix plan:**
- Bundle `demo/app.py` as package data, or
- Use `importlib.resources` to locate the demo file, or
- Document that `demo` subcommand only works in development mode.

---

## P2 -- Medium (Polish / Professional Quality)

### P2-1: No empty state design

**Where:** `demo/app.py`

**Problem:** When the app loads with no folder configured, the main area is completely blank. No welcome message, no instructions, no sample query suggestions.

**Fix plan:**
- Show a welcome card: "Welcome to CodeSight. Point me at a document folder to get started."
- Show 3-4 sample questions as clickable chips once indexed.
- Show a "Getting Started" section with the 3-step workflow.

### P2-2: Source citations use `st.code()` for all content

**Where:** `demo/app.py` line 54: `st.code(snippet[:800], language=None)`

**Problem:** All source snippets are rendered as monospaced code blocks, even for natural language content from PDFs and DOCX files. Reading a contract clause in a code block feels wrong.

**Fix plan:**
- Check the chunk's `language` field. If it's a code language, use `st.code(snippet, language=lang)`. If it's a document format (pdf, docx, pptx, md), use `st.markdown(snippet)`.

### P2-3: Duplicate playbooks in `business/` and `docs/playbooks/`

**Where:** `business/playbooks/` and `docs/playbooks/`

**Problem:** `client-onboarding.md`, `pitch-prep.md`, and `sales-process.md` exist in both directories. It's unclear which is the source of truth. Changes to one won't propagate to the other.

**Fix plan:**
- Pick one location. Per structure.md, operational guides go in `docs/playbooks/`. Client-specific business ops go in `business/`.
- If the business versions are client-facing and the docs versions are internal, document this distinction.
- If they're duplicates, delete one set and add a symlink or cross-reference.

### P2-4: `.env.example` has `CODESIGHT_STALE_SECONDS` but config.py reads `stale_threshold_seconds`

**Where:** `.env.example` line 70, `config.py` line 70

**Problem:** The env example shows `CODESIGHT_STALE_SECONDS=300` but the config class uses `stale_threshold_seconds` with a hardcoded default of `STALE_THRESHOLD_SECONDS = 300`. The env var is never actually read. The README says `CODESIGHT_STALE_MINUTES=60` (a third name, in minutes not seconds).

**Impact:** Users who set `CODESIGHT_STALE_SECONDS` in their `.env` will find it has no effect. The README gives the wrong variable name AND the wrong unit.

**Fix plan:**
- Add `os.environ.get("CODESIGHT_STALE_SECONDS", "300")` to config.py to actually read the env var.
- Fix README to match the actual variable name and unit.

### P2-5: ADR numbering has collisions

**Where:** `docs/decisions/`

**Problem:** Two files are numbered 0001, two are 0002, two are 0003. The numbering system that should guarantee uniqueness has collisions:
- `0001-lancedb-over-chromadb.md` and `0001-two-deployment-modes.md`
- `0002-decision-boundaries.md` and `0002-hybrid-rrf-retrieval.md`
- `0003-read-only-invariant.md` and `0003-two-deployment-modes.md`

**Fix plan:**
- Renumber: keep the original decisions at 0001-0003, assign 0004-0005 to the newer ones (some already exist at 0004-0005).
- Add a check to CI or the ADR creation playbook that prevents duplicate numbers.

---

## P3 -- Low (Nice-to-Have / Future Polish)

### P3-1: No accessibility attributes in Streamlit UI

**Where:** `demo/app.py`

**Problem:** Streamlit generates its own HTML without ARIA labels. The chat interface has no screen reader support, no high-contrast mode, no focus indicators beyond browser defaults.

**Impact:** Low for current stage (single-user demo tool), but enterprise sales in healthcare and government may require WCAG 2.1 AA compliance.

**Fix plan:**
- Accept as Streamlit limitation for demo phase.
- When building FastAPI + React frontend (v0.4), design for WCAG 2.1 AA from day one.

### P3-2: No rate limiting on LLM calls

**Where:** `api.py` `ask()` method

**Problem:** Every call to `ask()` makes an LLM API call. No rate limiting, no caching of repeated questions, no cost tracking.

**Fix plan:**
- Add an LRU cache on (question_hash, corpus_version) -> answer.
- Add a cost estimator that logs estimated token usage per call.
- Add a configurable rate limit per user (relevant when multi-user FastAPI is built).

### P3-3: No `--version` flag in CLI

**Where:** `__main__.py`

**Problem:** `python -m codesight --version` fails. No way to check the installed version from the CLI.

**Fix plan:**
- Read version from `__init__.py` or `importlib.metadata` and add `parser.add_argument("-v", "--version", action="version", version=...)`.

### P3-4: No health check endpoint

**Where:** Not yet applicable (no web server), but relevant for v0.4.

**Problem:** When deployed as a Docker service, there's no `/health` endpoint for load balancers or Kubernetes liveness probes.

**Fix plan:**
- Add to the FastAPI server in v0.4: `GET /health` returns `{"status": "ok", "version": "0.4.0", "indexed": true}`.

### P3-5: Document the Python API more visibly

**Where:** `README.md`, docs

**Problem:** The Python API (`CodeSight` class) is the most flexible interface but gets only 8 lines in the README. The `ask()` docstring explains backend selection but there's no tutorial or cookbook.

**Fix plan:**
- Add a "Python API Guide" playbook in `docs/playbooks/`.
- Include examples for: custom config, switching backends, file glob filtering, checking staleness.

---

## Summary

| Priority | Count | Key Issues |
|----------|-------|------------|
| **P0** | 3 | Raw folder path input, missing API key UX, stale justfile |
| **P1** | 5 | No indexing progress, lost chat history, label mismatch, fragile demo path |
| **P2** | 5 | No empty state, code block for docs, duplicate playbooks, env var mismatch, ADR collisions |
| **P3** | 5 | Accessibility, rate limiting, version flag, health check, API docs |

### Recommended Fix Order

1. P0-3 (justfile) -- 5 minutes, removes developer friction
2. P0-2 (API key UX) -- 30 minutes, prevents demo embarrassment
3. P0-1 (folder path) -- 2 hours, needs design decision
4. P2-4 (env var mismatch) -- 10 minutes, correctness fix
5. P1-1 (progress feedback) -- 1 hour, major UX improvement
6. P2-5 (ADR renumbering) -- 15 minutes, hygiene
