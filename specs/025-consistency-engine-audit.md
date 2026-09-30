# Holusight documentation-code consistency engine: implemented state vs. real consistency

All paths are relative to the repo root
`/Users/camiloslaptop/.treehouse/firstmate-7bab20/5/firstmate/projects/holusight`.
All command output below was produced live on 2026-09-29 at HEAD
`c51870c3b0c058ca8ed756ee3fbb9d0a78afe4c0` (worktree dirty: `.gitignore` modified).

---

## Q1. What does `src/holusight/consistency.py` actually implement?

### Takeaway

It is a single 1,223-line module implementing five genuinely working, deterministic
things: path-based artifact classification, a concept registry keyed on spec/ADR
filenames, a three-provider edge model, a 4-entry regex claim registry, and a
content-hash diff. None of it reads or compares the *meaning* of prose against the
*behavior* of code — every output is derived from file paths, file existence, file
hashes, and four hand-written regexes.

### Cited Findings

- Public surface, verified by reading the module: `classify_artifact` (L234),
  `discover_artifacts` (L274), `build_concepts` (L294), `extract_exact_references`
  (L357), `_load_structural_index` (L436), `structural_graph_freshness` (L463),
  `structural_edges_for` (L474), `semantic_similarity_edges` (L542),
  `evaluate_known_claims` (L694), `compute_health_flags` (L749), `refresh` (L956),
  `build_evidence_packet` (L1096), `check_consistency` (L1148) —
  [src/holusight/consistency.py](src/holusight/consistency.py)
- `classify_artifact` is pure path-pattern matching with **zero content inspection**;
  its own docstring says so: "Rules mirror this repository's own documented structure
  contract (`.claude/rules/structure.md`) rather than inspecting file content: this
  answers 'why does this file exist,' not 'what words are inside it.'" —
  [consistency.py:234-271](src/holusight/consistency.py#L234)
- The concept registry is literally one concept per canonical spec/ADR/governance
  file, with `concept_id == canonical_path` and `scope` = the file's first `# H1`
  line (`_H1_RE`, L285). "Superseded" status is one regex against
  `^**status**: superseded` (L286) — [consistency.py:285-322](src/holusight/consistency.py#L285)
- Real `refresh` output on this repo (live, first run):
  `artifacts_scanned: 218, artifacts_reclassified: 218, concepts: 43, edges: 831,
  claims: 4, health_flags: 103, structural_graph_stale: true,
  structural_graph_commit: "292e35f7729f548829af08d240df13254a5ab4f5"` —
  `uv run python -m holusight consistency refresh .`
- Edge breakdown from the live cache: `exact=229`, `structural=602`, `semantic=0`
  (`sqlite3 .holusight/consistency.db "SELECT provider, COUNT(*) FROM edges GROUP BY provider"`).
  All 602 structural edges carry `graph_stale: true` in their evidence payload
  because the tracked Graphify graph is at a different commit than HEAD —
  [consistency.py:504-520](src/holusight/consistency.py#L504)
- Health-flag breakdown from the live cache: `DANGLING_REFERENCE=42 (warning)`,
  `STALE_RELATIONSHIP=42 (warning)`, `ORPHAN_CONCEPT=18 (info)`,
  `STALE_STRUCTURAL_GRAPH=1 (info)`. **Zero** `CLAIM_DRIFT` and **zero**
  `CLAIM_UNKNOWN` — `sqlite3 .holusight/consistency.db "SELECT flag_type, severity, COUNT(*) FROM health_flags GROUP BY flag_type, severity"`
- `DANGLING_REFERENCE` and `STALE_RELATIONSHIP` are emitted as a **1:1 pair from the
  same loop over the same tokens** — [consistency.py:834-859](src/holusight/consistency.py#L834).
  The 103 flag count is therefore 61 distinct findings presented as 103.
- `ORPHAN_CONCEPT` fires when a concept's canonical file has **no outgoing exact
  edges at all** (L817-832). 18 of 43 concepts (42%) are orphans — meaning 42% of
  this repo's specs/ADRs mention no resolvable file path, so the engine knows nothing
  about what code they govern.
- `build_evidence_packet` reads only from the SQLite cache (L1102-1138); it never
  re-reads the repository. Its `repo_snapshot` is the snapshot **as of the last
  refresh**, not now — [consistency.py:1104-1108](src/holusight/consistency.py#L1104)
- `semantic_similarity_edges` (L542) compares a concept's **entire file text** to
  other whole doc files via cosine at `threshold=0.55`, doc-to-doc only. It never
  compares a doc to code. `refresh(run_semantic=False)` is the default (L959) and
  `tests/test_consistency.py:304` asserts default refresh produces zero semantic edges.

### Inferences

- The three "providers" are asymmetric in a way that matters: `exact` is doc→anything,
  `structural` is code→code (only `ArtifactKind.IMPLEMENTATION` files get structural
  edges, L1032-1034), and `semantic` is doc→doc. **No provider produces a doc→code
  edge based on anything other than a literal path string appearing in prose.** The
  entire doc-code linkage rests on authors having typed real file paths into their specs.
- `ORPHAN_CONCEPT=18/43` is the single most honest number in the system: for 42% of
  canonical documents, `check_consistency` can only ever report `up_to_date` (no linked
  artifacts to diff), regardless of how badly they have drifted.

### Gaps

- `EvidenceClass` (L77-83: verified/declared/inferred/unknown) is persisted on every
  edge/claim/flag, but I found no consumer that changes behavior based on it — it is
  recorded metadata, not a control signal.

---

## Q2. The claim registry: how brittle is it really?

### Takeaway

Four claims, four hand-written regex pairs, all four currently `match`, producing
**zero signal**. It is the only part of the system that compares a *value in a doc*
to a *value in code*, and it is a fixed 4-item allowlist that silently covers none
of the ~60 other numeric or behavioral invariants this repo documents.

### Cited Findings

- `_KNOWN_CLAIMS` is a 4-element tuple — [consistency.py:639-672](src/holusight/consistency.py#L639).
  Exactly four claims: `rrf_k`, `ast_min_lines`, `content_hash_length`,
  `data_dir_location`.
- Live values from the cache — all four `match`, all `evidence_class=verified`:
  ```
  rrf_k|60|60|match|verified
  ast_min_lines|5|5|match|verified
  content_hash_length|16|16|match|verified
  data_dir_location|~/.holusight/data/|~/.holusight/data/|match|verified
  ```
  (`sqlite3 -header .holusight/consistency.db "SELECT name, doc_value, code_value, status, evidence_class FROM claims"`)
- Extraction is `re.Pattern.search()` returning `match.group(1)` — first match only,
  whole-file scan, no scoping — [`_search_first_group`, consistency.py:681-691](src/holusight/consistency.py#L681)
- The doc side is pinned to **one hardcoded file path and one exact prose phrasing**.
  E.g. `rrf_k` requires the literal string `RRF k=60 constant` in `ARCHITECTURE.md`:
  ```python
  doc_pattern=re.compile(r"RRF k=(\d+) constant"),
  code_path="src/holusight/search.py",
  code_pattern=re.compile(r"def rrf_merge\([\s\S]*?k:\s*int\s*=\s*(\d+)"),
  ```
  — [consistency.py:640-647](src/holusight/consistency.py#L640).
  Rewording `ARCHITECTURE.md` to "the RRF constant k is 60" makes `doc_value=None`.
- When a pattern misses, `status = ClaimStatus.UNKNOWN` (L714-715) and the flag becomes
  `CLAIM_UNKNOWN` at severity **`warning`** — [consistency.py:876-889](src/holusight/consistency.py#L876) —
  whereas real drift is severity `high` (L862-875). So a *silently unmonitored* claim
  degrades to a lower-severity flag than a detected one, and there are currently zero
  of either, so the degradation is invisible.
- `code_pattern` for `ast_min_lines` is `min_lines:\s*int\s*=\s*(\d+)` against the whole
  of `chunker.py` — the first such parameter anywhere in a 633-line file wins. Same for
  `content_hash_length`: `hexdigest\(\)\[:(\d+)\]`, first occurrence in `chunker.py`.
  Adding an unrelated `min_lines: int = 3` helper earlier in that file silently retargets
  the claim — [consistency.py:648-663](src/holusight/consistency.py#L648)
- `data_dir_location` does not actually compare values: the code pattern
  `Path\.home\(\)\s*/\s*"\.holusight"\s*/\s*"data"` has **no capture group**, so
  `_search_first_group` returns `match.group(0)`, which is then **overwritten by a
  hardcoded normalizer** that returns the constant string the doc is expected to say:
  ```python
  _CLAIM_NORMALIZERS: dict[str, Callable[[str], str]] = {
      "data_dir_location": lambda _raw: "~/.holusight/data/",
  }
  ```
  — [consistency.py:676-678](src/holusight/consistency.py#L676). This claim can only
  ever be `match` or `unknown`; it is structurally incapable of reporting drift, because
  the "code value" is a literal chosen to equal the doc value.
- The drift path *is* tested, but only on a synthetic 2-file tmpdir where the author
  writes `k: int = 99` by hand — [tests/test_consistency.py:217-228](tests/test_consistency.py#L217)
- The comment above the registry sets the extension bar explicitly: "Extend this list
  only with claims that have an unambiguous, regex-extractable value on both sides." —
  [consistency.py:635-638](src/holusight/consistency.py#L635)
- `specs/013` names this as a deliberate non-goal: expanding beyond the hand-registered
  list "would require model inference that is not yet built or evaluated" —
  [specs/013-holusight-axi-consistency-architecture.md:170-172](specs/013-holusight-axi-consistency-architecture.md#L170)

### Inferences

- The claim registry is the **only** genuine doc-code semantic check in the repo, and
  three of its four entries are numeric constants in one file (`ARCHITECTURE.md`) while
  the fourth is a no-op. Its current yield after months of commits is 0 findings.
- Its brittleness is asymmetric in the dangerous direction: a *doc rewording* silently
  removes monitoring (`unknown`, warning), while *code drift* is what it is supposed to
  catch. An agent rewriting `ARCHITECTURE.md` prose therefore disarms the check it was
  meant to be held to, and nothing blocks or highlights that.
- `ARCHITECTURE.md`'s "What NOT to Change Without Discussion" section lists **6** items
  (RRF k, data dir location, content hash algorithm, FTS5 trigger schema, LLM system
  prompt, AST min_lines). Only 4 are registered; "FTS5 trigger schema" and "LLM system
  prompt" have no regex-extractable scalar, so the two highest-consequence invariants
  ("incorrect triggers cause silent search failures") are unmonitored.

### Gaps

- I found no mechanism, test, or CI step that detects a claim *silently falling out of
  monitoring* (doc reworded → `unknown`). The only surface is a `warning` health flag
  that nothing reads.

---

## Q3. `check_consistency` and the structural limit of hash-diffing

### Takeaway

`check_consistency` answers exactly one question: "did the bytes of these files change
since the last time I recorded their hashes?" It can never establish that a doc's
*content* agrees with code's *behavior*. Worse, on this real repository it currently
returns **5 false `possible_undocumented_drift` findings out of 43 concepts — 100% of
its non-`up_to_date` output is wrong**, and re-refreshing does not clear them.

### Cited Findings

- The docstring is honest about the mechanism: "This is deterministic hash-diffing, not
  semantic value comparison: it reports *that* something changed since the cache was
  last refreshed, not *what* changed within the text." —
  [consistency.py:1148-1153](src/holusight/consistency.py#L1148)
- The four statuses are decided by a 2x2 of two booleans (`canonical_changed`,
  `linked_changed`) and nothing else — [consistency.py:1188-1202](src/holusight/consistency.py#L1188)
- The comparison baseline is the cache, not git: `_artifact_changed` returns
  `_content_hash(full) != row["content_hash"]` — [consistency.py:1216-1223](src/holusight/consistency.py#L1216).
  So "drift" means "differs from whenever someone last ran refresh," an arbitrary
  local timestamp, not "differs from the commit that introduced the doc."
- `_artifact_changed` returns `True` for two non-change cases: file missing (L1219-1220)
  and **file absent from the artifacts table** — `if not row: return True  # never seen
  before counts as changed` — [consistency.py:1221-1222](src/holusight/consistency.py#L1221)
- **Live, reproducible false-positive bug.** Immediately after a successful `refresh`,
  `holus check` reports:
  ```
  "concepts_checked": 43,
  "summary": {"possible_undocumented_drift": 5, "up_to_date": 38}
  ```
  (`uv run python -m holusight.cli_axi check --format json`)
  Enumerating them directly gives all five with `canonical_changed=False` and
  linked paths that are **all** under `.claude/` or `.self-improvement/`:
  ```
  AGENTS.md → .claude/rules/structure.md, .claude/rules/workflow.md,
              .claude/settings.json, .claude/skills/holus/SKILL.md,
              .self-improvement/MEMORY.md, .self-improvement/NEXT.md,
              .self-improvement/memory/lessons.json, .self-improvement/workers.yaml
  docs/decisions/0014-...md → .claude/rules/structure.md, .claude/skills/holus/SKILL.md
  specs/013-...md → .claude/rules/structure.md, .claude/rules/workflow.md
  specs/015-...md → .claude/skills/holus/SKILL.md
  specs/018-...md → .claude/rules/structure.md, .claude/skills/holus/SKILL.md
  ```
- **Root cause, verified.** Two different file enumerations disagree.
  `extract_exact_references` resolves tokens against the raw filesystem via
  `_resolve_candidate` (`candidate.exists() and candidate.is_file()`) —
  [consistency.py:341-354](src/holusight/consistency.py#L341) — so it happily creates
  edges into `.claude/`. But `discover_artifacts` delegates to
  `walk_repo_files`, which drops every dot-directory and dot-file:
  ```python
  dirnames[:] = [d for d in dirnames
                 if d not in ALWAYS_SKIP_DIRS and not d.startswith(".")]
  ...
  if fname.startswith(".") or fname in ALWAYS_SKIP_FILES: continue
  ```
  — [src/holusight/indexer.py:68-84](src/holusight/indexer.py#L68).
  Confirmed against the live cache: `.claude/rules/structure.md`,
  `.claude/rules/workflow.md`, `.claude/settings.json`,
  `.claude/skills/holus/SKILL.md`, `.self-improvement/NEXT.md` are all **MISSING**
  from the 218-row `artifacts` table, while `AGENTS.md` and `ARCHITECTURE.md` are present.
  `_artifact_changed` therefore hits its `if not row: return True` branch forever.
- **Consequence for the classifier: two branches are dead code.**
  `classify_artifact` has explicit rules for `.self-improvement/reports/` →
  `REPORT/GENERATED` (L259-260) and `.claude/rules/*.md` → `GOVERNANCE/CANONICAL`
  (L261-264). Neither can ever fire, because discovery never yields those paths. Live
  kind distribution confirms `governance: 2` (only `AGENTS.md` + `CLAUDE.md`) and the
  16 `report` rows are all `graphify-out/` files (L265-266), not worker reports.
  Artifact path prefixes actually present in the cache:
  `['AGENTS.md','ARCHITECTURE.md','CLAUDE.md','COMPARISON.md','README.md','agentic',
  'business','demo','docker-compose.yml','docs','graphify-out','landing',
  'pyproject.toml','specs','src','tests','vercel.json']` — no dot-directories.
- **The test suite cannot see this.** `test_check_consistency_up_to_date_immediately_after_refresh`
  runs on a `tmp_path` fixture with two hand-written files —
  [tests/test_consistency.py:504](tests/test_consistency.py#L504). The eval-pilot's
  regression case for the same property also builds a synthetic 2-file tmpdir
  (`specs/001-alpha.md` + `src/pkg/mod.py`) —
  [src/holusight/eval_pilot.py:767-793](src/holusight/eval_pilot.py#L767). Neither
  fixture contains a `.claude/` reference, so the frozen "continuous evaluation" corpus
  stays green while the production repo emits 5/5 false drifts.

### What hash-diffing can and cannot prove

- **Can prove:** file bytes differ from a previously recorded hash; a file was deleted;
  a file was never cached. That is all.
- **Cannot prove, structurally:**
  - That a doc's *statements* match code behavior. Two files changing together
    (`coordinated_change`) is equally consistent with a correct coordinated edit and
    with an agent editing a spec to *match a bug it just introduced*.
  - That an unchanged doc is *correct*. `up_to_date` means "nobody touched it," which is
    precisely the state a stale, lying doc sits in. For the 18 orphan concepts,
    `up_to_date` is guaranteed by construction and carries zero information.
  - That `possible_undocumented_drift` is drift. It fires whenever any linked file's
    bytes moved — a typo fix, a reformat, a `ruff` autofix, or (as shown above) a file
    the walker simply never indexed.
  - Direction or blame. `linked_changed` is set-membership; the engine cannot say whether
    the doc or the code is the one that is now wrong.

### Inferences

- The one signal that runs on every PR (`holus check`, CI) currently has **precision 0**
  on this repo: every non-green finding is a false positive, and it is permanent rather
  than transient. An agent following the repo's own rule ("Never treat a stale, partial,
  or unavailable provider state as current, authoritative evidence") learns within one
  session to ignore the output entirely — which is worse than no check, for exactly the
  reason the owner cares about.
- The fix is small and local, not architectural: make `extract_exact_references` and
  `discover_artifacts` use the **same** file set (either stop creating edges to
  undiscovered paths, or stop treating "not in cache" as "changed"). One of the two
  branches at `consistency.py:1221` is the whole bug.

### Gaps

- I did not measure how often `possible_undocumented_drift` would fire for a *legitimate*
  reason on real commits, because the false-positive floor of 5 masks it. That
  measurement is unavailable until the walker asymmetry is fixed.

---

## Q4. `DANGLING_REFERENCE` in practice: 79% noise

### Takeaway

42 dangling-reference findings on this repo. I classified every one against the
filesystem: **9 are arguably genuine (21%), 33 are structural noise (79%)**, and each
is double-reported as a second `STALE_RELATIONSHIP` flag. Two of the nine "genuine"
ones exist only because `ARCHITECTURE.md` and `specs/013` narrate the finding in prose.

### Cited Findings

- Full list obtained live:
  `sqlite3 .holusight/consistency.db "SELECT detail FROM health_flags WHERE flag_type='DANGLING_REFERENCE'"`
  → 42 rows. Classification (mine, each verified against the filesystem):

| Category | Count | Examples |
|---|---|---|
| Template placeholder syntax | 5 | `specs/NNN-name.md`, `docs/decisions/NNNN-name.md`, `docs/playbooks/name.md`, `devlog/YYYY-MM-DD.md` (all in `AGENTS.md`); `research/file.md` (`specs/000-template.md`) |
| Deliberately fictional illustrative paths | 8 | `src/payments/service.py` (`ARCHITECTURE.md`, `specs/011`), `src/payments/routes.py`, `docs/payments.md` (`specs/011`), `src/a.py`, `src/b.py` (`specs/012`), `src/auth/jwt.py` (`specs/004`), `tests/fixtures/example-result.json` (`specs/019`) |
| Paths in *other* repos / gitignored generated output | 13 | 8x `system/shared/contracts/agentic/*.schema.json` etc. (`specs/016`, all Fleet-repo files), 3x `fleet-system/system/shared/scripts/fleet_graphify.py` (`AGENTS.md`, `specs/019`, `specs/022`), `graphify-out/wiki/index.md`, `graphify-out/GRAPH_REPORT.md` |
| Anti-pattern mentions of intentionally-deleted files | 7 | 4x `docs/RESEARCH.md`, 3x `docs/MARKET.md` — every one is prose saying *"do not create files like these"* (`AGENTS.md`, `ARCHITECTURE.md`, `ADR-0014`, `specs/018`) |
| **Genuine unresolved references** | **9** | 5x `specs/002-deployment-modes.md` (`ARCHITECTURE.md`, `ADR-0006` twice — bare and `../../` form, `specs/013`, `specs/017`); 2x `docs/capabilities.md` (`ARCHITECTURE.md`, `specs/013`); `web/server.py` (`specs/010`, real path is `src/holusight/web/server.py`); `src/holusight/vector_store_impl.py` (`specs/009`, no such module) |

- `specs/002-deployment-modes.md` genuinely does not exist — `ls specs/` shows spec 002
  is `002-embedding-model-config.md`. This is real, and the repo has known about it since
  the first run: `tests/test_consistency.py:166-177` asserts it as a *deliberately
  unfixed* regression fixture.
- The `../../specs/002-deployment-modes.md` and bare `specs/002-deployment-modes.md`
  forms in `ADR-0006` are counted as two separate findings, because `seen` dedupes on the
  raw token string, not the resolved target — [consistency.py:383-386](src/holusight/consistency.py#L383)
- `docs/capabilities.md` still dangles from `ARCHITECTURE.md` even though `ARCHITECTURE.md`
  claims it was "fixed in this PR — repointed to the real `specs/010-capability-inventory.md`".
  The fix landed in `ADR-0010` (verified: `tests/test_consistency.py:179-183` asserts
  `docs/capabilities.md` is no longer dangling from `ADR-0010`), but the *narration* of
  the fix in `ARCHITECTURE.md` and `specs/013` re-created the dangling token.
- The URL-stripping guard works: `_URL_RE.sub(" ", text)` before scanning
  ([consistency.py:380](src/holusight/consistency.py#L380)) is why no `github.com/...`
  blob path appears in the 42.
- The known-limitation admission in `ARCHITECTURE.md` is accurate as far as it goes
  ("cannot distinguish a real path reference from a fictional illustrative path inside
  research prose"), but understates the problem: illustrative paths are only 8 of 33 noise
  items. The larger sources are **cross-repo references (13)** and **anti-pattern mentions
  (7)**, neither of which `ARCHITECTURE.md` mentions.

### Inferences

- Three of the four noise categories are cheaply separable with no model inference:
  (a) placeholder tokens containing `NNN`/`NNNN`/`YYYY-MM-DD`/`name.md`;
  (b) tokens whose first segment is not a real top-level directory of *this* repo
  (`system/`, `fleet-system/`, `research/`, `web/`, `src/payments/`, `src/auth/`);
  (c) tokens inside a gitignored path (`graphify-out/wiki/`). That alone would cut 42
  findings to roughly 12 without any new machinery.
- The self-referential failure mode is the interesting one: **documenting a broken
  reference creates a broken reference.** Any doc that quotes a dangling path as evidence
  becomes a new dangling-path source. This is a property of scanning prose for path
  tokens, and it will recur every time the engine's own findings are written down.
- Because `DANGLING_REFERENCE` is `severity: warning` and nothing consumes severity, the
  9 real findings and the 33 noise findings are indistinguishable at the point of use.
  One of the 9 (`specs/009` → `src/holusight/vector_store_impl.py`) is exactly the class
  of error that would mislead an agent, and it has been sitting in the warning pile.

### Gaps

- I could not determine how long each genuine dangling reference has existed (no
  per-flag first-seen timestamp; `replace_health_flags` wipes and rewrites the table on
  every refresh — [consistency_store.py:305-316](src/holusight/consistency_store.py#L305)).
  There is no history, so "is this getting better or worse" is unanswerable.

---

## Q5. `consistency_store.py`: what is cached, what is content-hash-gated, where the scale limit is

### Takeaway

One WAL-mode SQLite file with six tables. **Only artifact classification is
content-hash-gated**; concepts, all 831 edges, all 4 claims and all 103 health flags are
`DELETE`-then-`INSERT` wholesale on every refresh. That is fine at this size — warm
refresh is 0.75s — but the spec's own stated Phase-2 trigger on corpus size has already
fired unnoticed.

### Cited Findings

- Six tables: `schema_meta`, `repo_state`, `artifacts`, `concepts`, `edges`, `claims`,
  `health_flags` — [consistency_store.py:26-91](src/holusight/consistency_store.py#L26).
  `SCHEMA_VERSION = "1"` (L24), never bumped.
- The only incremental path: if the cached `content_hash` equals the recomputed one, the
  cached `kind`/`authority`/`classified_at` are reused and `unchanged += 1`; otherwise
  `classify_artifact` re-runs — [consistency.py:990-999](src/holusight/consistency.py#L990).
  Since classification is a pure function of the *path*, this gate saves a few regex
  matches per file and nothing else.
- Everything else is a full replace: `replace_concepts` (L231), `replace_edges` (L253),
  `replace_claims` (L279), `replace_health_flags` (L305) each begin with
  `self.conn.execute("DELETE FROM <table>")` — [consistency_store.py:231-316](src/holusight/consistency_store.py#L231)
- `refresh` re-reads and re-scans **every** referable doc for exact references and
  **every** implementation file for structural edges, unconditionally —
  [consistency.py:1019-1034](src/holusight/consistency.py#L1019). Its own docstring
  concedes this: "Edge/claim/health-flag recomputation is currently a full pass each
  refresh."
- Measured timing, live: cold run (includes a `uv` venv build) 6.8s wall; **warm second
  run 0.745s** with `artifacts_reclassified: 0, artifacts_unchanged: 218`. So trigger #1's
  wall-clock arm is not met.
- **But the corpus arm of the same trigger is met.** `specs/013` says partial
  recomputation is justified when "the tracked artifact count materially exceeds the
  current ~127-file corpus" —
  [specs/013-...md:194-198](specs/013-holusight-axi-consistency-architecture.md#L194),
  and the same spec states the scale as "~127 files" at L176. The live count is **218**
  artifacts — 72% over the documented figure. Nothing detected this: there is no
  registered claim for corpus size, so the spec's own stated number has drifted from
  reality inside the very document that defines the consistency engine.
- Security hardening is real and tested: `_reject_symlinked_holusight` refuses a
  symlinked `.holusight/` or db file, checked twice (before and after `mkdir`) —
  [consistency_store.py:94-127](src/holusight/consistency_store.py#L94)
- Additive migration exists for `evidence_class` on `edges`/`claims`/`health_flags`, so
  old caches stay readable without being upgraded to `verified` —
  [consistency_store.py:133-148](src/holusight/consistency_store.py#L133)
- `edges` has `UNIQUE(from_ref, to_ref, relation, provider)` and inserts use
  `INSERT OR IGNORE` (L258), so a duplicate edge from two providers is kept but a
  duplicate within one provider is silently dropped.

### Inferences

- The real scale limit is not SQLite or wall-clock; it is that **every refresh discards
  all history**. Because `health_flags` is wiped and rewritten, the system cannot answer
  "is drift accumulating," "how long has this dangled," or "did my change introduce
  this" — which are the questions that would make the signal actionable. Trigger #2 in
  `specs/013` ("health flags demonstrate recurring value... over several weeks of real
  commits") is literally unmeasurable with the current storage design.
- `ADR-0011`'s one-database decision holds up; nothing I found argues for splitting it.

### Gaps

- `specs/013` L176's "~127 files" vs. the measured 218 is a genuine doc-code drift I
  found by hand. I did not audit the other numeric claims in `specs/013` for the same
  problem.

---

## Q6. Which control-plane modules actually run, and which are scaffolding?

### Takeaway

Of the seven modules asked about, **two run automatically** (`spec_duplication` and,
indirectly via `improve_iterate`, `proper_eval`/`eval_pilot`/`fleet_scorecard`), one runs
as the only blocking CI gate (`agent_focus`, and it gates nothing about doc-code
consistency), and **`improvement_control.py` (1,224 lines) and `retrieval_variation.py`
(772 lines) are invoked by nothing outside their own tests.**

### Cited Findings

- `.github/workflows/` contains exactly two files: `ci.yml` and `improve-iterate.yml`
  (`ls .github/workflows/`).
- `ci.yml` steps, in order: `ruff check`, `pytest tests/ -q`,
  `pytest tests/test_axi_skill_drift.py -q`, **Agent focus harness**,
  **Consistency check (advisory)**, **Spec neighbor check (advisory)** —
  [.github/workflows/ci.yml](.github/workflows/ci.yml)
- `improve-iterate.yml` runs `python -m holusight.improve_iterate` on
  `cron: "0 13 * * *"` plus `workflow_dispatch`, caches
  `.holusight/improvement-runs` between runs, and uploads the receipt as an artifact.
  It is a **scheduled job, not a PR gate** — [.github/workflows/improve-iterate.yml](.github/workflows/improve-iterate.yml)
- Module-by-module invocation status (grep across `justfile`, `.github/workflows/`,
  `tests/`, excluding `src/` and `specs/`):

| Module | LOC | Automated invocation | `just` target | Own tests |
|---|---|---|---|---|
| `spec_duplication.py` | 185 | **Yes** — `ci.yml` on PRs touching `specs/` | `specs-check-neighbors` | `test_spec_duplication.py` (10) |
| `agent_focus.py` | 492 | **Yes** — `ci.yml`, every run, `if: always()`, **can fail the build** | `agent-focus` | `test_agent_focus.py` (4) |
| `improve_iterate.py` | 215 | **Yes** — daily schedule only | `improve-iterate` | `test_improve_iterate.py` (5) |
| `proper_eval.py` | 255 | Indirect — called by `improve_iterate` | `proper-eval` | `test_proper_eval.py` (4) |
| `eval_pilot.py` | 1,372 | Indirect — called by `proper_eval` | `eval-pilot` | `test_eval_pilot.py` (32) |
| `fleet_scorecard.py` | 317 | Indirect — called by `proper_eval` | `fleet-smoke` | `test_fleet_scorecard.py` (12) |
| `eval_suite.py` | 961 | **No** | `eval-suite` | `test_eval_suite.py` (19) |
| `council.py` | 370 | **No** | `council` | `test_council.py` (4) |
| `improvement_control.py` | 1,224 | **No — no `just` target, no CI step, no non-test caller** | *(none)* | `test_improvement_control.py` (12) |
| `retrieval_variation.py` | 772 | **No — no `just` target, no CI step, no non-test caller** | *(none)* | `test_retrieval_variation.py` (15) |

- `improvement_control.py` and `retrieval_variation.py` have **no entry in the justfile
  at all** (verified against the full `justfile` text) and appear in `.github/workflows/`
  zero times. Outside `src/`, `tests/`, `specs/` and the doc tables in
  `AGENTS.md`/`ARCHITECTURE.md`, they are referenced nowhere.
- `improvement_control.py` is reachable only through `holus improve-review` /
  `improve-history` / `improve-integration` in `cli_axi.py`, which a human must type. No
  automation calls them.
- The frozen "continuous evaluation" corpus is **4 cases**, 1 comparative and 3
  regression (live `improve-status`):
  `cli-axi-provider-starvation-display-quota`, `consistency-known-dangling-reference-0006`,
  `consistency-refresh-then-check-is-up-to-date`, `axi-providers-no-egress-by-default`
  (`uv run python -m holusight.cli_axi improve-status --format json`;
  `tests/fixtures/holusight_eval_pilot_cases.jsonl`).
- Live `just fleet-smoke` (the manifest's declared `eval_entrypoint`) with dev extras:
  `20 passed in 0.81s`, then
  `{"hidden_correctness": {"status": "pass", ...}, "scores": {"smoke_tasks_passed": 20}, "total_cost_usd": 0.0}`.
- **Real failure worth reporting:** running the same entrypoint *without* dev extras
  (`uv run python -m holusight.fleet_scorecard smoke`) prints
  `No module named pytest` to stderr and then emits a scorecard with
  `"hidden_correctness": {"status": "fail", ..., "exit_code=1"}` and
  `"smoke_tasks_passed": 0`. A missing test-runner dependency is reported in the same
  shape as a genuine evaluation failure, with no `unavailable`/`indeterminate`
  distinction — the opposite of the explicit-degradation discipline the exact/structural
  providers follow.
- Live provider state, right now: `exact` = `live`; `structural` = **`stale`**
  (`graphify@292e35f...` vs HEAD `c51870c...`); `consistency` = **`stale`**;
  `semantic` = **`unavailable`** ("repository not indexed; run
  `python -m holusight index .`") —
  `uv run python -m holusight.cli_axi providers --format json`. Three of four providers
  are non-authoritative in this checkout.
- The `consistency` provider reports `stale` **even when cached HEAD equals current
  HEAD**, because a dirty worktree alone flips it:
  ```python
  current = state is not None and cached_head == head and not (state and state["dirty"])
  ```
  — [src/holusight/axi_providers.py:612-614](src/holusight/axi_providers.py#L612).
  The live detail line confirms it:
  `cached head='c51870c...', current head='c51870c...'` yet `freshness: "stale"`.

### Inferences

- ~2,000 lines (`improvement_control.py` + `retrieval_variation.py`) are governance
  machinery with tests and specs and ADRs but **no caller**. Combined with
  `eval_suite.py` (961, no automation) and `council.py` (370, no automation), roughly
  3,300 lines of the control plane are reachable only by a human typing a command that
  nothing reminds them to type.
- The provider-freshness rule interacts badly with the owner's actual use case. An agent
  is *by definition* mid-change — worktree dirty — whenever it most needs doc-code
  evidence. At that exact moment the consistency provider self-reports `stale`, and the
  project's own instruction ("Never treat a `stale` … provider state as current,
  authoritative evidence") tells the agent to disregard it. The subsystem is configured
  to be unusable during the only situation it was built for.

### Gaps

- I did not verify whether the daily `improve-iterate` workflow has ever actually
  succeeded on GitHub (no `gh` run history checked); its cache-restore-then-compare design
  means the first run of each day may legitimately have no prior receipt.

---

## Q7. Is there any enforcement? Does a drifted doc ever block anything?

### Takeaway

No. Every doc-code consistency signal in CI is explicitly non-blocking. The only
CI step that can fail the build on a non-test condition is `agent_focus`, and it checks
promotion-boundary invariants, not doc-code agreement.

### Cited Findings

- The consistency step is doubly de-fanged — `continue-on-error: true` **and** a heading
  that says so:
  ```yaml
  - name: Consistency check (advisory)
    if: always()
    continue-on-error: true
  ...
  print("## Holusight consistency check (advisory -- never blocks)")
  ```
  — [.github/workflows/ci.yml:82-112](.github/workflows/ci.yml#L82)
- The spec-neighbor step is likewise `continue-on-error: true` and prints
  "advisory -- ranked, not pass/fail" — [.github/workflows/ci.yml:104-135](.github/workflows/ci.yml#L104)
- The only non-test `exit 1` in either workflow is the agent-focus block branch:
  ```
  if [ "$code" -eq 1 ]; then echo "agent-focus blocked (exit 1)" >&2; exit 1; fi
  ```
  — [.github/workflows/ci.yml:75-78](.github/workflows/ci.yml#L75).
  Live `agent_focus` run exits **0** and its council lenses check `structure_authority`
  ("AGENTS.md, structure rules, and agentic manifest present") and
  `promotion_boundary` ("promotion denied across ADR, runners, and Fleet manifest") —
  not whether any doc matches any code.
- Non-blockingness is a *deliberate, recorded* decision, not an oversight. `specs/013`
  lists as a non-goal: "CI enforcement / merge blocking on health flags. This PR adds
  tests and a CLI surface; it does not wire a CI gate. That is a human decision..." —
  [specs/013-...md:179-182](specs/013-holusight-axi-consistency-architecture.md#L179).
  `ADR-0019` is titled `0019-local-advisory-evaluator-promotion-denied.md`.
- The one thing that *does* block on a doc/code relationship is unrelated to this
  subsystem: `pytest tests/test_axi_skill_drift.py` fails the build if
  `.claude/skills/holus/SKILL.md` diverges from `axi_schema.py` —
  [.github/workflows/ci.yml:53-54](.github/workflows/ci.yml#L53), 7 tests in
  `tests/test_axi_skill_drift.py`.
- `tests/test_consistency.py:191-208` (`test_evaluate_known_claims_real_repo_currently_all_match`)
  hard-asserts all four real-repo claims match, and it runs inside the blocking
  `pytest tests/ -q` step. So the 4 registered claims *are* enforced — by a normal test,
  not by the consistency engine's own reporting path.

### Inferences

- There are exactly **two** enforcing mechanisms for doc-code agreement in this repo, and
  neither is the consistency engine: (1) the generated-skill drift test, and (2) an
  ordinary `assert` in `test_consistency.py` pinning 4 constants. Both are simple,
  blocking, and have zero false positives. That contrast is the finding: the 1,223-line
  engine's output is advisory and currently 0%-precision, while two small hardcoded tests
  do real work.
- The `test_evaluate_known_claims_real_repo_currently_all_match` pattern is the
  cheapest available path to real enforcement — it needs no control plane, no records, no
  CI policy change. Extending that one test is a strictly smaller change than anything
  the control plane offers.

### Gaps

- Branch-protection settings (whether `check` is a required status check on `master`) are
  a GitHub-side config I did not query, so "advisory in the workflow" does not by itself
  prove "cannot block a merge" for the blocking steps.

---

## Q8. Honest assessment: load-bearing for agent context, vs. records nobody reads

### Takeaway

The load-bearing parts are small and mostly *not* the consistency engine: the retrieval
index, `graphify-out/graph.json`, the generated `/holus` skill, and the two hardcoded
enforcement tests. The consistency engine's own outputs are currently net-negative for
agent context quality — 0% precision on drift, 79% noise on dangling references, and
3 of 4 providers self-reporting non-authoritative.

### Cited Findings

- What an agent actually gets from `holus` today in this checkout: one live provider
  (`exact`, "literal/token substring scan"), a `stale` structural graph, a `stale`
  consistency cache, and an `unavailable` semantic provider (live `providers` output).
- The consistency engine's live findings, in full: 42 dangling (9 genuine), 42 duplicate
  stale-relationship, 18 orphan concepts, 1 stale graph, 0 claim drift, 0 claim unknown,
  5 drift reports (0 genuine). Total genuine actionable findings: **9**, all of them
  broken path references, 4 of which are the same missing spec.
- Of 43 concepts, 18 (42%) have no exact edges at all — so for 42% of canonical docs the
  engine has no opinion that could ever help an agent.
- Documented-but-unreachable code confirmed: `classify_artifact`'s
  `.self-improvement/reports/` (L259) and `.claude/rules/` (L261) branches, blocked by
  `walk_repo_files`'s dot-filter at `indexer.py:68-84`. The `.claude/rules/structure.md`
  file the *classifier is specifically written to recognize as canonical governance* is
  not in the 218-row artifacts table.
- `specs/013`'s own stated corpus size ("~127 files", L176) vs. the measured 218 is an
  uncaught doc-code drift **inside the consistency engine's own specification**.
- Warm refresh cost is trivial: 0.745s (measured). Cost is not the problem.
- ~3,300 lines across `improvement_control.py` (1,224), `retrieval_variation.py` (772),
  `eval_suite.py` (961), `council.py` (370) have no automated caller — verified by grep
  across `justfile`, `.github/workflows/`, and non-test sources.

### Inferences — highest-leverage concrete gaps, in order

These are gaps, framed as the smallest change that closes each. None require new
modules, layers, or records.

1. **The walker asymmetry is the whole false-positive problem.** `extract_exact_references`
   resolves against the filesystem; `discover_artifacts` uses a dot-filtering walker.
   Making the two agree — or removing the `if not row: return True` branch at
   [consistency.py:1221](src/holusight/consistency.py#L1221) — takes `holus check` from
   0%-precision to 0 false findings, unblocks the CI advisory step's usefulness, and
   simultaneously revives the two dead `classify_artifact` branches. This is a one-symptom,
   one-cause, few-line fix and it is the only thing on this list that is unambiguously a bug.

2. **The claim registry is the only real doc-code check, and it has 4 entries, 0 of which
   currently fire, and 1 of which (`data_dir_location`) is incapable of firing** because
   its "code value" is a hardcoded constant equal to the doc value
   ([consistency.py:676-678](src/holusight/consistency.py#L676)). The gap is coverage and
   honesty of the four existing entries, not a new extraction engine. `ARCHITECTURE.md`'s
   own list of 6 must-not-change invariants has 2 unregistered, and they are the two with
   the worst failure modes ("FTS5 trigger schema… incorrect triggers cause silent search
   failures", "LLM system prompt").

3. **Hash-diffing cannot be made into consistency checking.** `up_to_date` is guaranteed
   for the 18 orphan concepts and for every stale-but-untouched doc; `coordinated_change`
   cannot distinguish a correct joint edit from a spec edited to match a new bug. No
   amount of work on the 2x2 at [consistency.py:1188-1202](src/holusight/consistency.py#L1188)
   changes that. The gap is that the repo's headline consistency status is derived from a
   signal that is structurally incapable of the claim, and `possible_undocumented_drift`
   is the only one of the four statuses that ever means anything.

4. **Dangling-reference noise is separable without inference.** 26 of the 33 noise items
   fall into three mechanical buckets: placeholder tokens (`NNN`, `NNNN`, `YYYY-MM-DD`,
   `name.md`), tokens whose first path segment is not a real top-level directory of this
   repo, and tokens under a gitignored path. Filtering those leaves ~12 findings of which
   9 are genuine.

5. **No history means the value question is unanswerable.** `replace_health_flags`
   ([consistency_store.py:305](src/holusight/consistency_store.py#L305)) wipes the table
   every refresh, so `specs/013`'s own trigger #2 ("health flags… continue to surface
   genuine drift over several weeks") can never be evaluated. Also: the *doc side* is the
   silent-failure direction — a reworded `ARCHITECTURE.md` turns a monitored claim into a
   `warning`-severity `CLAIM_UNKNOWN` that nothing reads.

6. **The dirty-worktree staleness rule makes the subsystem unusable exactly when it is
   needed.** `axi_providers.py:612-614` marks the consistency provider `stale` on any
   uncommitted change, and the repo's own agent instructions forbid treating `stale` as
   authoritative. An agent mid-edit is told to ignore the only doc-drift evidence available.

7. **The two mechanisms that actually enforce doc-code agreement are both tiny hardcoded
   tests** (`test_axi_skill_drift.py`, and `test_evaluate_known_claims_real_repo_currently_all_match`
   at [tests/test_consistency.py:191](tests/test_consistency.py#L191)) — blocking, zero
   false positives, no control plane. The ~3,300 uninvoked control-plane lines produce no
   signal at all. The evidence in this repo favors more small blocking assertions over
   more advisory reporting.

### Gaps

- I did not evaluate whether *any* agent session has ever consumed a health flag or an
  evidence packet and changed its behavior; there is no usage telemetry for the
  consistency surface that I could find, so "records nobody reads" is an inference from
  the absence of callers and the 0%-precision output, not a measurement.
- Whether the 9 genuine dangling references have ever caused an actual agent error is
  unknown — no incident record exists, and `specs/013`'s trigger #3 ("a concrete, observed
  'agent missed a required update' incident") appears never to have been logged.
