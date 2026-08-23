"""Evidence providers backing the ``holus`` AXI command surface.

Every job in :mod:`codesight.cli_axi` is a thin wrapper over the functions
in this module, which are themselves thin wrappers over already-landed
production code - :mod:`codesight.consistency` (Phase 1 consistency
engine, PR #16) and :mod:`codesight.search` (hybrid BM25 + vector search).
This module adds no new retrieval mechanism; it adds routing, budget
limits, and explicit provider-state reporting on top of what already
exists, per specs/015-holusight-axi-command-surface.md.

Provider kinds (matching :class:`codesight.consistency.ProviderKind` plus
one CLI-native addition):

- ``exact`` - literal/token substring search over the gitignore-aware
  repository file list (:func:`codesight.consistency.discover_artifacts`).
  Deterministic, no network, no model call.
- ``structural`` - the tracked Graphify graph
  (:func:`codesight.consistency._load_structural_index`), matched by
  path/node-id token containment. Reuses the exact same staleness check
  PR #17's ``graphify`` eval baseline reuses
  (:func:`codesight.consistency.structural_graph_freshness`) so the two
  subsystems agree on what "stale" means - see
  ``.../holusight-axi-pr17-preflight/report.md``.
- ``consistency`` - the Phase 1 concept/claim/health-flag cache
  (``.holusight/consistency.db``), matched by concept scope/id containment.
- ``semantic`` - :func:`codesight.search.hybrid_search` against an
  *already-built* local index. Never triggers an index build (that would
  be a surprising, potentially slow, potentially network-calling side
  effect of a read-only evidence job) and never allows Voyage egress
  unless the caller passes ``allow_egress=True``.

Every provider returns a :class:`ProviderResult` with an explicit
``state`` - ``ok``, ``no_evidence``, ``unavailable``, ``stale``,
``denied``, ``unsupported``, or ``budget_exceeded`` - never a fabricated
answer when evidence is absent (acceptance criterion 5).
"""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from . import consistency

# Bounded work per provider per call. These are wall-clock/scan budgets, not
# a dollar cost - there is no billing surface in this local-only CLI. A
# provider that hits its budget before finishing a full scan reports
# state=budget_exceeded with whatever it found so far, rather than either
# blocking indefinitely or silently truncating without saying so.
_EXACT_SCAN_FILE_BUDGET = 400
_EXACT_MATCH_BUDGET = 30
_STRUCTURAL_MATCH_BUDGET = 30
_SEMANTIC_TOP_K = 5
_EXCERPT_TRUNCATE_CHARS = 500

_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "of", "in", "on", "at", "to", "for", "and", "or",
    "what", "where", "when", "who", "why", "how", "this", "that", "it",
    "does", "with", "by", "from", "as",
}


class ProviderState(str, Enum):
    OK = "ok"
    NO_EVIDENCE = "no_evidence"
    UNAVAILABLE = "unavailable"
    STALE = "stale"
    DENIED = "denied"
    UNSUPPORTED = "unsupported"
    BUDGET_EXCEEDED = "budget_exceeded"


class EvidenceItem(BaseModel):
    provider: str
    source: str
    location: str
    excerpt: str
    excerpt_truncated: bool = False
    excerpt_total_chars: int | None = None
    confidence: float | None = None
    score: float | None = None
    relation: str | None = None


class ProviderResult(BaseModel):
    provider: str
    state: ProviderState
    detail: str
    route_reason: str
    egress: bool = False
    items: list[EvidenceItem] = Field(default_factory=list)


def _tokenize(question: str) -> list[str]:
    raw = re.findall(r"[A-Za-z0-9_./-]+", question.lower())
    return [t for t in raw if len(t) >= 3 and t not in _STOPWORDS]


def _truncate(text: str, limit: int | None = _EXCERPT_TRUNCATE_CHARS) -> tuple[str, bool, int]:
    total = len(text)
    if limit is None or total <= limit:
        return text, False, total
    return text[:limit], True, total


def _excerpt_limit(full: bool) -> int | None:
    return None if full else _EXCERPT_TRUNCATE_CHARS


@contextmanager
def _no_egress_env():
    """Temporarily hide VOYAGE_API_KEY so semantic queries stay local-only
    unless the caller explicitly opts into egress. Restores the prior
    environment afterward, including for a KeyError-raising restore path."""
    saved = os.environ.pop("VOYAGE_API_KEY", None)
    try:
        yield
    finally:
        if saved is not None:
            os.environ["VOYAGE_API_KEY"] = saved


# ---------------------------------------------------------------------------
# exact
# ---------------------------------------------------------------------------


def exact_provider(
    repo_root: Path, question: str, *, full: bool = False, allow_egress: bool = False
) -> ProviderResult:
    tokens = _tokenize(question)
    if not tokens:
        return ProviderResult(
            provider="exact",
            state=ProviderState.UNSUPPORTED,
            detail="question has no searchable tokens (all stopwords or too short)",
            route_reason="skipped: no tokenizable terms",
        )

    try:
        files = consistency.discover_artifacts(repo_root)
    except OSError as exc:
        return ProviderResult(
            provider="exact",
            state=ProviderState.UNAVAILABLE,
            detail=f"could not walk repository: {exc.__class__.__name__}",
            route_reason="attempted: repository walk failed",
        )

    literal = question.strip().lower()
    items: list[EvidenceItem] = []
    scanned = 0
    budget_hit = False
    for rel_path in files:
        if scanned >= _EXACT_SCAN_FILE_BUDGET:
            budget_hit = True
            break
        scanned += 1
        full_path = Path(repo_root) / rel_path
        try:
            text = full_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            low = line.lower()
            matched = literal in low or any(tok in low for tok in tokens)
            if not matched:
                continue
            excerpt, truncated, total = _truncate(line.strip(), _excerpt_limit(full))
            items.append(
                EvidenceItem(
                    provider="exact",
                    source=rel_path,
                    location=f"line {lineno}",
                    excerpt=excerpt,
                    excerpt_truncated=truncated,
                    excerpt_total_chars=total if truncated else None,
                    confidence=1.0,
                )
            )
            if len(items) >= _EXACT_MATCH_BUDGET:
                budget_hit = True
                break
        if budget_hit:
            break

    if budget_hit:
        return ProviderResult(
            provider="exact",
            state=ProviderState.BUDGET_EXCEEDED,
            detail=(
                f"stopped after scanning {scanned} files / {len(items)} matches "
                "(scan budget reached); results are partial"
            ),
            route_reason="attempted: literal/token substring scan, hit scan budget",
            items=items,
        )
    if not items:
        return ProviderResult(
            provider="exact",
            state=ProviderState.NO_EVIDENCE,
            detail=f"no literal/token match for {tokens!r} in {scanned} scanned files",
            route_reason="attempted: literal/token substring scan over full repo",
        )
    return ProviderResult(
        provider="exact",
        state=ProviderState.OK,
        detail=f"{len(items)} line match(es) across {scanned} scanned files",
        route_reason="attempted: literal/token substring scan over full repo",
        items=items,
    )


# ---------------------------------------------------------------------------
# structural (Graphify)
# ---------------------------------------------------------------------------


def structural_provider(
    repo_root: Path, question: str, *, full: bool = False, allow_egress: bool = False
) -> ProviderResult:
    tokens = _tokenize(question)
    if not tokens:
        return ProviderResult(
            provider="structural",
            state=ProviderState.UNSUPPORTED,
            detail="question has no searchable tokens (all stopwords or too short)",
            route_reason="skipped: no tokenizable terms",
        )

    index = consistency._load_structural_index(repo_root)
    if not index.available:
        return ProviderResult(
            provider="structural",
            state=ProviderState.UNAVAILABLE,
            detail="graphify-out/graph.json not found; run `graphify update .` to build it",
            route_reason="attempted: no tracked structural graph on disk",
        )

    stale, built_at_commit = consistency.structural_graph_freshness(index, repo_root)

    items: list[EvidenceItem] = []
    seen_paths: set[str] = set()
    budget_hit = False
    for path, node_ids in index.file_nodes.items():
        haystack = path.lower() + " " + " ".join(node_ids).lower()
        if not any(tok in haystack for tok in tokens):
            continue
        if path in seen_paths:
            continue
        seen_paths.add(path)
        matched_nodes = [n for n in node_ids if any(tok in n.lower() for tok in tokens)]
        excerpt, truncated, total = _truncate(
            ", ".join(matched_nodes) if matched_nodes else ", ".join(node_ids[:5]),
            _excerpt_limit(full),
        )
        items.append(
            EvidenceItem(
                provider="structural",
                source=path,
                location=f"{len(node_ids)} graph node(s)",
                excerpt=excerpt,
                excerpt_truncated=truncated,
                excerpt_total_chars=total if truncated else None,
                confidence=0.5,
                relation="graphify:node_match",
            )
        )
        if len(items) >= _STRUCTURAL_MATCH_BUDGET:
            budget_hit = True
            break

    detail_suffix = (
        f" (graph built_at_commit={built_at_commit!r}, {'stale' if stale else 'current'})"
    )
    if budget_hit:
        return ProviderResult(
            provider="structural",
            state=ProviderState.BUDGET_EXCEEDED,
            detail=f"stopped after {len(items)} matches (match budget reached)" + detail_suffix,
            route_reason="attempted: path/node-id token match over tracked graph, hit budget",
            items=items,
        )
    if not items:
        return ProviderResult(
            provider="structural",
            state=ProviderState.NO_EVIDENCE if not stale else ProviderState.STALE,
            detail=(
                f"no path/node-id match for {tokens!r} in the tracked graph" + detail_suffix
            ),
            route_reason="attempted: path/node-id token match over tracked graph",
        )
    return ProviderResult(
        provider="structural",
        state=ProviderState.STALE if stale else ProviderState.OK,
        detail=f"{len(items)} file(s) matched" + detail_suffix,
        route_reason="attempted: path/node-id token match over tracked graph",
        items=items,
    )


# ---------------------------------------------------------------------------
# consistency (Phase 1 concept/claim/health-flag cache)
# ---------------------------------------------------------------------------


def consistency_provider(
    repo_root: Path, question: str, *, full: bool = False, allow_egress: bool = False
) -> ProviderResult:
    tokens = _tokenize(question)
    db_path = consistency.consistency_db_path(repo_root)
    if not db_path.exists():
        return ProviderResult(
            provider="consistency",
            state=ProviderState.UNAVAILABLE,
            detail=".holusight/consistency.db has never been refreshed for this repository",
            route_reason="skipped: no consistency cache on disk",
        )
    if not tokens:
        return ProviderResult(
            provider="consistency",
            state=ProviderState.UNSUPPORTED,
            detail="question has no searchable tokens (all stopwords or too short)",
            route_reason="skipped: no tokenizable terms",
        )

    from .consistency_store import ConsistencyStore

    store = ConsistencyStore(db_path)
    try:
        concepts = store.all_concepts()
        matched = [
            c
            for c in concepts
            if any(
                tok in (c["scope"] + " " + c["concept_id"]).lower() for tok in tokens
            )
        ]
        items: list[EvidenceItem] = []
        for c in matched:
            flags = store.health_flags_for_concept(c["concept_id"])
            claims = store.claims_for_doc_path(c["canonical_path"])
            summary_bits = [f"status={c['status']}"]
            if flags:
                summary_bits.append(f"{len(flags)} open health flag(s)")
            if claims:
                drift = sum(1 for cl in claims if cl["status"] == "drift")
                summary_bits.append(f"{len(claims)} claim(s), {drift} drift")
            excerpt, truncated, total = _truncate(
                "; ".join(summary_bits), _excerpt_limit(full)
            )
            items.append(
                EvidenceItem(
                    provider="consistency",
                    source=c["canonical_path"],
                    location=f"concept {c['concept_id']!r}",
                    excerpt=excerpt,
                    excerpt_truncated=truncated,
                    excerpt_total_chars=total if truncated else None,
                    confidence=1.0,
                    relation="concept_match",
                )
            )
    finally:
        store.close()

    if not items:
        return ProviderResult(
            provider="consistency",
            state=ProviderState.NO_EVIDENCE,
            detail=f"no concept scope/id match for {tokens!r} in the cached registry",
            route_reason="attempted: concept scope/id token match over consistency cache",
        )
    return ProviderResult(
        provider="consistency",
        state=ProviderState.OK,
        detail=f"{len(items)} concept(s) matched",
        route_reason="attempted: concept scope/id token match over consistency cache",
        items=items,
    )


# ---------------------------------------------------------------------------
# semantic (hybrid BM25 + vector search, already-built index only)
# ---------------------------------------------------------------------------


def semantic_provider(
    repo_root: Path, question: str, *, full: bool = False, allow_egress: bool = False
) -> ProviderResult:
    from .api import CodeSight

    try:
        engine = CodeSight(repo_root)
    except ValueError as exc:
        return ProviderResult(
            provider="semantic",
            state=ProviderState.UNAVAILABLE,
            detail=str(exc),
            route_reason="attempted: could not construct engine",
        )

    if not engine.store.is_indexed:
        return ProviderResult(
            provider="semantic",
            state=ProviderState.UNAVAILABLE,
            detail=(
                "repository is not indexed for semantic search; run "
                "`python -m codesight index .` first (never auto-triggered by `holus`)"
            ),
            route_reason="skipped: no local index found",
        )

    stored_model = engine.store.fts.get_meta("embedding_model") or ""
    requires_egress = "voyage" in stored_model.lower()
    if requires_egress and not allow_egress:
        return ProviderResult(
            provider="semantic",
            state=ProviderState.DENIED,
            detail=(
                f"index was built with {stored_model!r} (external Voyage embeddings); "
                "pass --allow-egress to query it, or re-index locally"
            ),
            route_reason="attempted: index requires egress, --allow-egress not set",
        )

    is_stale = engine._is_stale()

    try:
        with _no_egress_env() if not allow_egress else _noop_ctx():
            results = engine.search(question, top_k=_SEMANTIC_TOP_K)
    except Exception as exc:  # noqa: BLE001 - never leak a raw dependency traceback
        return ProviderResult(
            provider="semantic",
            state=ProviderState.UNAVAILABLE,
            detail=f"semantic search failed: {exc.__class__.__name__}",
            route_reason="attempted: hybrid_search raised",
        )

    items: list[EvidenceItem] = []
    for r in results:
        excerpt, truncated, total = _truncate(r.snippet, _excerpt_limit(full))
        items.append(
            EvidenceItem(
                provider="semantic",
                source=r.file_path,
                location=f"lines {r.start_line}-{r.end_line}",
                excerpt=excerpt,
                excerpt_truncated=truncated,
                excerpt_total_chars=total if truncated else None,
                score=round(float(r.score), 4),
                relation=r.scope,
            )
        )

    egress_occurred = requires_egress and allow_egress
    if not items:
        return ProviderResult(
            provider="semantic",
            state=ProviderState.STALE if is_stale else ProviderState.NO_EVIDENCE,
            detail="hybrid search returned no results" + (" (index is stale)" if is_stale else ""),
            route_reason="attempted: hybrid_search over existing local index",
            egress=egress_occurred,
        )
    return ProviderResult(
        provider="semantic",
        state=ProviderState.STALE if is_stale else ProviderState.OK,
        detail=f"{len(items)} result(s)" + (" (index is stale)" if is_stale else ""),
        route_reason="attempted: hybrid_search over existing local index",
        egress=egress_occurred,
        items=items,
    )


@contextmanager
def _noop_ctx():
    yield


PROVIDERS = {
    "exact": exact_provider,
    "structural": structural_provider,
    "consistency": consistency_provider,
    "semantic": semantic_provider,
}

# Which providers each --mode value runs. "auto" runs every provider cheap
# enough to attempt unconditionally (exact/structural/consistency are all
# local, deterministic, sub-second); semantic only actually does work in
# auto mode when a local index already exists (see semantic_provider).
MODE_PROVIDERS: dict[str, list[str]] = {
    "exact": ["exact"],
    "semantic": ["semantic"],
    "structure": ["structural"],
    "auto": ["exact", "structural", "consistency", "semantic"],
}


# ---------------------------------------------------------------------------
# Provider status (availability/freshness/egress) - not question-driven.
# Backs the `providers` job, `status` job, and the no-arg home view.
# ---------------------------------------------------------------------------


class ProviderStatusEntry(BaseModel):
    name: str
    available: bool
    version: str | None
    freshness: str  # "live" | "current" | "stale" | "unavailable"
    egress: str  # "none" | "external:voyage"
    detail: str


def provider_statuses(repo_root: Path) -> list[ProviderStatusEntry]:
    entries: list[ProviderStatusEntry] = []

    entries.append(
        ProviderStatusEntry(
            name="exact",
            available=True,
            version="stdlib-scan",
            freshness="live",
            egress="none",
            detail="literal/token substring scan over the gitignore-aware file list",
        )
    )

    index = consistency._load_structural_index(repo_root)
    if not index.available:
        entries.append(
            ProviderStatusEntry(
                name="structural",
                available=False,
                version=None,
                freshness="unavailable",
                egress="none",
                detail="graphify-out/graph.json not found",
            )
        )
    else:
        stale, built_at_commit = consistency.structural_graph_freshness(index, repo_root)
        entries.append(
            ProviderStatusEntry(
                name="structural",
                available=True,
                version=f"graphify@{built_at_commit or 'unknown'}",
                freshness="stale" if stale else "current",
                egress="none",
                detail=f"{len(index.file_nodes)} file(s) with graph nodes",
            )
        )

    db_path = consistency.consistency_db_path(repo_root)
    if not db_path.exists():
        entries.append(
            ProviderStatusEntry(
                name="consistency",
                available=False,
                version=None,
                freshness="unavailable",
                egress="none",
                detail="never refreshed (.holusight/consistency.db does not exist)",
            )
        )
    else:
        from .consistency_store import ConsistencyStore
        from .git_utils import current_commit, is_git_repo

        store = ConsistencyStore(db_path)
        try:
            state = store.get_repo_state()
        finally:
            store.close()
        head = current_commit(repo_root) if is_git_repo(repo_root) else None
        cached_head = state["head_commit"] if state else None
        current = state is not None and cached_head == head and not (
            state and state["dirty"]
        )
        entries.append(
            ProviderStatusEntry(
                name="consistency",
                available=True,
                version="schema_v1",
                freshness="current" if current else "stale",
                egress="none",
                detail=(
                    f"last refreshed at {state['last_refreshed_at']!r}, "
                    f"cached head={cached_head!r}, current head={head!r}"
                    if state
                    else "cache exists but repo_state row missing"
                ),
            )
        )

    from .api import CodeSight

    try:
        engine = CodeSight(repo_root)
        indexed = engine.store.is_indexed
    except ValueError:
        indexed = False
        engine = None

    if not indexed or engine is None:
        entries.append(
            ProviderStatusEntry(
                name="semantic",
                available=False,
                version=None,
                freshness="unavailable",
                egress="none",
                detail="repository not indexed; run `python -m codesight index .`",
            )
        )
    else:
        stored_model = engine.store.fts.get_meta("embedding_model") or "unknown"
        egress = "external:voyage" if "voyage" in stored_model.lower() else "none"
        entries.append(
            ProviderStatusEntry(
                name="semantic",
                available=True,
                version=stored_model,
                freshness="stale" if engine._is_stale() else "current",
                egress=egress,
                detail=f"{engine.store.chunk_count} chunk(s) indexed",
            )
        )

    return entries
