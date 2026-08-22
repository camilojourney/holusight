"""Holusight-AXI documentation-code consistency engine (Phase 1).

Implements the vertical slice defined in
``specs/013-holusight-axi-consistency-architecture.md``:

- purpose-aware artifact classification (:func:`classify_artifact`)
- a concept registry seeded from canonical specs/ADRs (:func:`build_concepts`)
- canonical authority selection (one concept per spec/ADR file, plus a
  ``MULTIPLE_CANONICAL_SCOPE`` health flag when scopes collide)
- claim provenance for a small, explicit registry of named invariants
  (:func:`evaluate_known_claims`)
- relationship provenance across three distinguishable provider kinds:
  exact (:func:`extract_exact_references`), structural
  (:func:`structural_edges_for`, sourced from the tracked Graphify graph),
  and semantic (:func:`semantic_similarity_edges`, local embeddings, opt-in)
- an incremental local cache (:func:`refresh`, gated by content hash at the
  artifact-classification layer)
- a pre-change evidence packet (:func:`build_evidence_packet`)
- a post-change consistency check (:func:`check_consistency`)

All state this module writes lives in ``.holusight/consistency.db`` — see
``consistency_store.py``. Canonical repository content (specs, ADRs,
architecture docs, source, tests) is only ever read.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Protocol

from pydantic import BaseModel, Field

from .consistency_store import ConsistencyStore
from .git_utils import current_commit, is_git_repo
from .indexer import walk_repo_files

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ArtifactKind(str, Enum):
    SPECIFICATION = "specification"
    DECISION = "decision"
    ARCHITECTURE = "architecture"
    VISION_ROADMAP = "vision_roadmap"
    PLAYBOOK = "playbook"
    IMPLEMENTATION = "implementation"
    TEST = "test"
    DEVLOG = "devlog"
    REPORT = "report"
    BUSINESS = "business"
    DOCUMENTATION = "documentation"
    OTHER = "other"


class ArtifactAuthority(str, Enum):
    CANONICAL = "canonical"
    SUPPORTING = "supporting"
    GENERATED = "generated"
    HISTORICAL = "historical"


class ProviderKind(str, Enum):
    EXACT = "exact"
    STRUCTURAL = "structural"
    SEMANTIC = "semantic"


class ClaimStatus(str, Enum):
    MATCH = "match"
    DRIFT = "drift"
    UNKNOWN = "unknown"


class ConsistencyStatus(str, Enum):
    UP_TO_DATE = "up_to_date"
    SPEC_CHANGED_AWAITING_IMPLEMENTATION = "spec_changed_awaiting_implementation"
    POSSIBLE_UNDOCUMENTED_DRIFT = "possible_undocumented_drift"
    COORDINATED_CHANGE = "coordinated_change"
    UNKNOWN_CONCEPT = "unknown_concept"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Artifact(BaseModel):
    path: str
    kind: ArtifactKind
    authority: ArtifactAuthority
    content_hash: str
    classified_at: str


class Concept(BaseModel):
    concept_id: str
    scope: str
    canonical_path: str
    source_kind: ArtifactKind
    status: str = "active"


class Edge(BaseModel):
    from_ref: str
    to_ref: str
    relation: str
    provider: ProviderKind
    confidence: float
    evidence: dict = Field(default_factory=dict)
    created_at: str


class Claim(BaseModel):
    name: str
    description: str
    doc_path: str
    doc_value: str | None
    code_path: str
    code_value: str | None
    status: ClaimStatus
    evaluated_at: str


class HealthFlag(BaseModel):
    flag_type: str
    concept_id: str | None
    detail: str
    severity: str  # "info" | "warning" | "high"
    detected_at: str


class RepoSnapshot(BaseModel):
    head_commit: str | None
    dirty: bool


class RefreshResult(BaseModel):
    repo_snapshot: RepoSnapshot
    artifacts_scanned: int
    artifacts_reclassified: int
    artifacts_unchanged: int
    concepts: int
    edges: int
    claims: int
    health_flags: int
    structural_graph_stale: bool
    structural_graph_commit: str | None


class EvidencePacket(BaseModel):
    repo_snapshot: RepoSnapshot
    concept: Concept
    canonical_artifact: Artifact | None
    edges: list[Edge]
    claims: list[Claim]
    health_flags: list[HealthFlag]
    structural_graph_stale: bool
    structural_graph_commit: str | None


class ConsistencyReport(BaseModel):
    concept_id: str
    status: ConsistencyStatus
    canonical_changed: bool
    linked_changed: list[str]
    linked_unchanged: list[str]
    notes: str


# ---------------------------------------------------------------------------
# Paths and small helpers
# ---------------------------------------------------------------------------


def consistency_db_path(repo_root: str | Path) -> Path:
    """Path to the single atomic SQLite cache for a given repository root."""
    return Path(repo_root) / ".holusight" / "consistency.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _content_hash(path: Path) -> str:
    """sha256[:16] of file bytes, matching this repo's existing convention
    (see ``src/codesight/chunker.py`` and ARCHITECTURE.md's content-hashing
    invariant)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _is_dirty(repo_root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


# ---------------------------------------------------------------------------
# 1. Purpose-aware artifact classification
# ---------------------------------------------------------------------------

_SPEC_RE = re.compile(r"^specs/\d{3}-.+\.md$")
_DECISION_RE = re.compile(r"^docs/decisions/\d{4}-.+\.md$")


def classify_artifact(rel_path: str) -> tuple[ArtifactKind, ArtifactAuthority]:
    """Classify one repo-relative path by purpose, deterministically.

    Rules mirror this repository's own documented structure contract
    (``.claude/rules/structure.md``) rather than inspecting file content:
    this answers "why does this file exist," not "what words are inside
    it."
    """
    p = rel_path.replace("\\", "/")
    if _SPEC_RE.match(p):
        return ArtifactKind.SPECIFICATION, ArtifactAuthority.CANONICAL
    if _DECISION_RE.match(p):
        return ArtifactKind.DECISION, ArtifactAuthority.CANONICAL
    if p == "ARCHITECTURE.md":
        return ArtifactKind.ARCHITECTURE, ArtifactAuthority.CANONICAL
    if p in ("docs/vision.md", "docs/roadmap.md"):
        return ArtifactKind.VISION_ROADMAP, ArtifactAuthority.CANONICAL
    if p.startswith("docs/playbooks/"):
        return ArtifactKind.PLAYBOOK, ArtifactAuthority.SUPPORTING
    if p.startswith("src/") and p.endswith(".py"):
        return ArtifactKind.IMPLEMENTATION, ArtifactAuthority.SUPPORTING
    if p.startswith("tests/") and p.endswith(".py"):
        return ArtifactKind.TEST, ArtifactAuthority.SUPPORTING
    if p.startswith("devlog/"):
        return ArtifactKind.DEVLOG, ArtifactAuthority.HISTORICAL
    if p.startswith(".self-improvement/reports/"):
        return ArtifactKind.REPORT, ArtifactAuthority.GENERATED
    if p.startswith("graphify-out/"):
        return ArtifactKind.REPORT, ArtifactAuthority.GENERATED
    if p.startswith("business/"):
        return ArtifactKind.BUSINESS, ArtifactAuthority.SUPPORTING
    if p in ("README.md", "COMPARISON.md"):
        return ArtifactKind.DOCUMENTATION, ArtifactAuthority.SUPPORTING
    return ArtifactKind.OTHER, ArtifactAuthority.SUPPORTING


def discover_artifacts(repo_root: Path) -> list[str]:
    """Gitignore-aware discovery, reusing the existing indexer file walker."""
    files = walk_repo_files(repo_root)
    repo_root = Path(repo_root).resolve()
    return sorted(str(f.relative_to(repo_root)) for f in files)


# ---------------------------------------------------------------------------
# 2 & 3. Concept registry + canonical authority selection
# ---------------------------------------------------------------------------

_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_SUPERSEDED_RE = re.compile(r"(?im)^\**status\**\s*:?\s*superseded")


def _extract_scope_title(text: str, fallback: str) -> str:
    match = _H1_RE.search(text)
    return match.group(1).strip() if match else fallback


def build_concepts(artifacts: dict[str, Artifact], repo_root: Path) -> list[Concept]:
    """One concept per canonical spec/ADR file — this repository already
    enforces one-feature-per-numbered-spec, so the file *is* the concept
    scope by construction."""
    repo_root = Path(repo_root)
    concepts: list[Concept] = []
    for path, artifact in sorted(artifacts.items()):
        if artifact.kind not in (ArtifactKind.SPECIFICATION, ArtifactKind.DECISION):
            continue
        try:
            text = (repo_root / path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        scope = _extract_scope_title(text, fallback=path)
        status = "superseded" if _SUPERSEDED_RE.search(text) else "active"
        concepts.append(
            Concept(
                concept_id=path,
                scope=scope,
                canonical_path=path,
                source_kind=artifact.kind,
                status=status,
            )
        )
    return concepts


# ---------------------------------------------------------------------------
# 5a. Relationship provenance: exact provider
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"https?://\S+")
_PATH_TOKEN_RE = re.compile(
    r"(?<![\w./-])((?:\.\./|[\w.-]+/)+[\w.-]+\.(?:py|md|json|ya?ml|toml))(?![\w/-])"
)
_REFERABLE_KINDS = (
    ArtifactKind.SPECIFICATION,
    ArtifactKind.DECISION,
    ArtifactKind.ARCHITECTURE,
)


def _resolve_candidate(raw: str, doc_dir: Path, repo_root: Path) -> Path | None:
    """Resolve a prose path token against the doc's own directory first
    (markdown-link convention), then the repo root (bare repo-relative
    mention convention). Returns None if it escapes the repo or doesn't
    exist on disk — a dangling reference, not a fabricated edge."""
    for base in (doc_dir, repo_root):
        candidate = (base / raw).resolve()
        try:
            candidate.relative_to(repo_root)
        except ValueError:
            continue
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def extract_exact_references(
    doc_path: str, repo_root: Path
) -> tuple[list[Edge], list[str]]:
    """Extract file-path references from one doc's prose, resolved against
    the filesystem. Returns (edges, dangling_tokens): a token that looks
    like a path but doesn't resolve to a real file is reported as dangling
    rather than silently dropped or fabricated into an edge."""
    repo_root = Path(repo_root).resolve()
    full_path = repo_root / doc_path
    try:
        text = full_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], []

    doc_dir = full_path.parent
    now = _now()
    seen: set[str] = set()
    edges: list[Edge] = []
    dangling: list[str] = []

    # Strip URLs first so a GitHub blob URL's path segment (e.g.
    # "github.com/org/repo/blob/main/specs/010-x.md") is never mistaken for
    # a repo-relative file reference.
    scan_text = _URL_RE.sub(" ", text)

    for match in _PATH_TOKEN_RE.finditer(scan_text):
        raw = match.group(1)
        if raw in seen:
            continue
        seen.add(raw)

        resolved = _resolve_candidate(raw, doc_dir, repo_root)
        if resolved is None:
            dangling.append(raw)
            continue

        rel_str = str(resolved.relative_to(repo_root)).replace("\\", "/")
        if rel_str == doc_path:
            continue

        edges.append(
            Edge(
                from_ref=f"artifact:{doc_path}",
                to_ref=f"artifact:{rel_str}",
                relation="references",
                provider=ProviderKind.EXACT,
                confidence=1.0,
                evidence={"pattern": "path-token", "raw_token": raw},
                created_at=now,
            )
        )

    return edges, dangling


# ---------------------------------------------------------------------------
# 5b. Relationship provenance: structural provider (Graphify)
# ---------------------------------------------------------------------------


class _StructuralIndex:
    __slots__ = ("available", "built_at_commit", "node_file", "file_nodes", "links")

    def __init__(
        self,
        available: bool,
        built_at_commit: str | None,
        node_file: dict[str, str],
        file_nodes: dict[str, list[str]],
        links: list[dict],
    ) -> None:
        self.available = available
        self.built_at_commit = built_at_commit
        self.node_file = node_file
        self.file_nodes = file_nodes
        self.links = links


def _load_structural_index(repo_root: Path) -> _StructuralIndex:
    graph_path = Path(repo_root) / "graphify-out" / "graph.json"
    if not graph_path.exists():
        return _StructuralIndex(False, None, {}, {}, [])
    try:
        data = json.loads(graph_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _StructuralIndex(False, None, {}, {}, [])

    node_file: dict[str, str] = {}
    file_nodes: dict[str, list[str]] = {}
    for node in data.get("nodes", []):
        node_id = node.get("id")
        source_file = node.get("source_file")
        if node_id and source_file:
            node_file[node_id] = source_file
            file_nodes.setdefault(source_file, []).append(node_id)

    return _StructuralIndex(
        available=True,
        built_at_commit=data.get("built_at_commit"),
        node_file=node_file,
        file_nodes=file_nodes,
        links=data.get("links", []),
    )


def structural_graph_freshness(
    index: _StructuralIndex, repo_root: Path
) -> tuple[bool, str | None]:
    """Return (stale, built_at_commit). Unavailable graph counts as stale."""
    if not index.available:
        return True, None
    head = current_commit(repo_root)
    stale = head is None or index.built_at_commit is None or head != index.built_at_commit
    return stale, index.built_at_commit


def structural_edges_for(
    index: _StructuralIndex, artifact_path: str, stale: bool
) -> list[Edge]:
    """Edges sourced from the tracked Graphify graph for one implementation
    file, explicitly tagged `structural` with the graph's own confidence
    and a staleness flag — never presented as if it were exact evidence."""
    node_ids = set(index.file_nodes.get(artifact_path, []))
    if not node_ids:
        return []

    now = _now()
    seen: set[tuple[str, str]] = set()
    edges: list[Edge] = []
    for link in index.links:
        source, target = link.get("source"), link.get("target")
        if source in node_ids:
            other_file = index.node_file.get(target)
        elif target in node_ids:
            other_file = index.node_file.get(source)
        else:
            continue
        if not other_file or other_file == artifact_path:
            continue

        relation = link.get("relation", "related")
        key = (other_file, relation)
        if key in seen:
            continue
        seen.add(key)

        edges.append(
            Edge(
                from_ref=f"artifact:{artifact_path}",
                to_ref=f"artifact:{other_file}",
                relation=f"structural:{relation}",
                provider=ProviderKind.STRUCTURAL,
                confidence=float(link.get("confidence_score", 0.5)),
                evidence={
                    "graphify_relation": relation,
                    "graphify_confidence_label": link.get("confidence"),
                    "graph_built_at_commit": index.built_at_commit,
                    "graph_stale": stale,
                },
                created_at=now,
            )
        )
    return edges


# ---------------------------------------------------------------------------
# 5c. Relationship provenance: semantic provider (local embeddings, opt-in)
# ---------------------------------------------------------------------------


class EmbedFn(Protocol):
    def __call__(self, texts: list[str]) -> list[list[float]]: ...


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def semantic_similarity_edges(
    concepts: list[Concept],
    artifacts: dict[str, Artifact],
    repo_root: Path,
    embed_fn: EmbedFn,
    threshold: float = 0.55,
) -> list[Edge]:
    """Local-embedding similarity between each concept's canonical text and
    other documentation-kind artifacts not already linked by an exact
    reference. Opt-in only, never invoked by default. Confidence is the
    similarity score; never treated as canonical, only as a "possibly
    relates to" hint above ``threshold``."""
    repo_root = Path(repo_root)
    doc_kinds = (
        ArtifactKind.SPECIFICATION,
        ArtifactKind.DECISION,
        ArtifactKind.ARCHITECTURE,
        ArtifactKind.PLAYBOOK,
    )
    candidate_paths = [
        path for path, artifact in artifacts.items() if artifact.kind in doc_kinds
    ]
    if not concepts or not candidate_paths:
        return []

    texts_by_path: dict[str, str] = {}
    for path in {c.canonical_path for c in concepts} | set(candidate_paths):
        try:
            texts_by_path[path] = (repo_root / path).read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            texts_by_path[path] = ""

    ordered_paths = sorted(texts_by_path)
    vectors = embed_fn([texts_by_path[p] for p in ordered_paths])
    vector_by_path = dict(zip(ordered_paths, vectors))

    now = _now()
    edges: list[Edge] = []
    for concept in concepts:
        concept_vector = vector_by_path.get(concept.canonical_path)
        if concept_vector is None:
            continue
        for path in candidate_paths:
            if path == concept.canonical_path:
                continue
            other_vector = vector_by_path.get(path)
            if other_vector is None:
                continue
            score = _cosine(concept_vector, other_vector)
            if score < threshold:
                continue
            edges.append(
                Edge(
                    from_ref=f"concept:{concept.concept_id}",
                    to_ref=f"artifact:{path}",
                    relation="possibly_relates_to",
                    provider=ProviderKind.SEMANTIC,
                    confidence=round(score, 4),
                    evidence={"embedding_threshold": threshold},
                    created_at=now,
                )
            )
    return edges


# ---------------------------------------------------------------------------
# 4. Claim provenance: known-invariant registry
# ---------------------------------------------------------------------------


class _ClaimDef:
    __slots__ = ("name", "description", "doc_path", "doc_pattern", "code_path", "code_pattern")

    def __init__(
        self,
        name: str,
        description: str,
        doc_path: str,
        doc_pattern: re.Pattern,
        code_path: str,
        code_pattern: re.Pattern,
    ) -> None:
        self.name = name
        self.description = description
        self.doc_path = doc_path
        self.doc_pattern = doc_pattern
        self.code_path = code_path
        self.code_pattern = code_pattern


# Deliberately small and explicit — not a general natural-language claim
# extractor. Each entry mirrors one line of ARCHITECTURE.md's "What NOT to
# Change Without Discussion" section. Extend this list only with claims that
# have an unambiguous, regex-extractable value on both sides.
_KNOWN_CLAIMS: tuple[_ClaimDef, ...] = (
    _ClaimDef(
        name="rrf_k",
        description="Reciprocal Rank Fusion k constant",
        doc_path="ARCHITECTURE.md",
        doc_pattern=re.compile(r"RRF k=(\d+) constant"),
        code_path="src/codesight/search.py",
        code_pattern=re.compile(r"def rrf_merge\([\s\S]*?k:\s*int\s*=\s*(\d+)"),
    ),
    _ClaimDef(
        name="ast_min_lines",
        description="AST chunking merge-small-siblings threshold",
        doc_path="ARCHITECTURE.md",
        doc_pattern=re.compile(r"AST min_lines=(\d+) threshold"),
        code_path="src/codesight/chunker.py",
        code_pattern=re.compile(r"min_lines:\s*int\s*=\s*(\d+)"),
    ),
    _ClaimDef(
        name="content_hash_length",
        description="Content hash truncation length used for dedup",
        doc_path="ARCHITECTURE.md",
        doc_pattern=re.compile(r"sha256\(content\)\[:(\d+)\]"),
        code_path="src/codesight/chunker.py",
        code_pattern=re.compile(r"hexdigest\(\)\[:(\d+)\]"),
    ),
    _ClaimDef(
        name="data_dir_location",
        description="On-disk index storage root",
        doc_path="ARCHITECTURE.md",
        doc_pattern=re.compile(r"(~/\.codesight/data/)"),
        code_path="src/codesight/config.py",
        code_pattern=re.compile(r'Path\.home\(\)\s*/\s*"\.codesight"\s*/\s*"data"'),
    ),
)

# Per-claim raw-code-value normalizers, applied only when the code pattern
# matched. Explicit and documented, not inferred.
_CLAIM_NORMALIZERS: dict[str, Callable[[str], str]] = {
    "data_dir_location": lambda _raw: "~/.codesight/data/",
}


def _search_first_group(path: Path, pattern: re.Pattern) -> str | None:
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = pattern.search(text)
    if not match:
        return None
    return match.group(1) if match.groups() else match.group(0)


def evaluate_known_claims(repo_root: Path) -> list[Claim]:
    """Evaluate the small, explicit registry of named invariants: extract
    each side's value with a registered regex, compare, and classify as
    match/drift/unknown. Never fabricates a value when a pattern doesn't
    match — that is reported as ``unknown``, not silently skipped."""
    repo_root = Path(repo_root)
    now = _now()
    claims: list[Claim] = []
    for definition in _KNOWN_CLAIMS:
        doc_value = _search_first_group(repo_root / definition.doc_path, definition.doc_pattern)
        raw_code_value = _search_first_group(
            repo_root / definition.code_path, definition.code_pattern
        )
        normalizer = _CLAIM_NORMALIZERS.get(definition.name)
        code_value = (
            normalizer(raw_code_value)
            if raw_code_value is not None and normalizer
            else raw_code_value
        )

        if doc_value is None or code_value is None:
            status = ClaimStatus.UNKNOWN
        elif doc_value == code_value:
            status = ClaimStatus.MATCH
        else:
            status = ClaimStatus.DRIFT

        claims.append(
            Claim(
                name=definition.name,
                description=definition.description,
                doc_path=definition.doc_path,
                doc_value=doc_value,
                code_path=definition.code_path,
                code_value=code_value,
                status=status,
                evaluated_at=now,
            )
        )
    return claims


# ---------------------------------------------------------------------------
# Health flags
# ---------------------------------------------------------------------------


def compute_health_flags(
    concepts: list[Concept],
    claims: list[Claim],
    edges: list[Edge],
    dangling_by_doc: dict[str, list[str]],
    structural_stale: bool,
    structural_commit: str | None,
) -> list[HealthFlag]:
    now = _now()
    flags: list[HealthFlag] = []

    scopes: dict[str, list[str]] = {}
    for concept in concepts:
        scopes.setdefault(concept.scope.strip().lower(), []).append(concept.concept_id)
    for scope_key, concept_ids in scopes.items():
        if len(concept_ids) > 1:
            flags.append(
                HealthFlag(
                    flag_type="MULTIPLE_CANONICAL_SCOPE",
                    concept_id=sorted(concept_ids)[0],
                    detail=(
                        f"{len(concept_ids)} concepts share scope title "
                        f"{scope_key!r}: {', '.join(sorted(concept_ids))}"
                    ),
                    severity="warning",
                    detected_at=now,
                )
            )

    if structural_stale:
        flags.append(
            HealthFlag(
                flag_type="STALE_STRUCTURAL_GRAPH",
                concept_id=None,
                detail=(
                    f"graphify-out/graph.json built_at_commit={structural_commit!r} "
                    "does not match current HEAD; run `graphify update .`"
                ),
                severity="info",
                detected_at=now,
            )
        )

    exact_outgoing: dict[str, set[str]] = {}
    for edge in edges:
        if edge.provider == ProviderKind.EXACT:
            exact_outgoing.setdefault(edge.from_ref, set()).add(edge.to_ref)
    for concept in concepts:
        ref = f"artifact:{concept.canonical_path}"
        if not exact_outgoing.get(ref):
            flags.append(
                HealthFlag(
                    flag_type="ORPHAN_CONCEPT",
                    concept_id=concept.concept_id,
                    detail=(
                        f"{concept.canonical_path} has no exact references to "
                        "implementation/test/other artifacts"
                    ),
                    severity="info",
                    detected_at=now,
                )
            )

    for doc_path, tokens in dangling_by_doc.items():
        for token in tokens:
            flags.append(
                HealthFlag(
                    flag_type="DANGLING_REFERENCE",
                    concept_id=doc_path,
                    detail=f"{doc_path} references {token!r}, which does not resolve to a file",
                    severity="warning",
                    detected_at=now,
                )
            )

    for claim in claims:
        if claim.status == ClaimStatus.DRIFT:
            flags.append(
                HealthFlag(
                    flag_type="CLAIM_DRIFT",
                    concept_id=None,
                    detail=(
                        f"{claim.name}: {claim.doc_path} says {claim.doc_value!r}, "
                        f"{claim.code_path} says {claim.code_value!r}"
                    ),
                    severity="high",
                    detected_at=now,
                )
            )
        elif claim.status == ClaimStatus.UNKNOWN:
            flags.append(
                HealthFlag(
                    flag_type="CLAIM_UNKNOWN",
                    concept_id=None,
                    detail=(
                        f"{claim.name}: could not extract a value from "
                        f"{claim.doc_path} or {claim.code_path}"
                    ),
                    severity="warning",
                    detected_at=now,
                )
            )

    return flags


# ---------------------------------------------------------------------------
# Row <-> model conversion
# ---------------------------------------------------------------------------


def _edge_to_row(edge: Edge) -> dict:
    row = edge.model_dump()
    row["provider"] = edge.provider.value
    row["evidence"] = json.dumps(edge.evidence, sort_keys=True)
    return row


def _row_to_edge(row: dict) -> Edge:
    return Edge(
        from_ref=row["from_ref"],
        to_ref=row["to_ref"],
        relation=row["relation"],
        provider=ProviderKind(row["provider"]),
        confidence=row["confidence"],
        evidence=json.loads(row["evidence"]) if row["evidence"] else {},
        created_at=row["created_at"],
    )


def _claim_to_row(claim: Claim) -> dict:
    row = claim.model_dump()
    row["status"] = claim.status.value
    return row


def _row_to_claim(row: dict) -> Claim:
    return Claim(
        name=row["name"],
        description=row["description"],
        doc_path=row["doc_path"],
        doc_value=row["doc_value"],
        code_path=row["code_path"],
        code_value=row["code_value"],
        status=ClaimStatus(row["status"]),
        evaluated_at=row["evaluated_at"],
    )


def _flag_to_row(flag: HealthFlag) -> dict:
    return flag.model_dump()


def _row_to_flag(row: dict) -> HealthFlag:
    return HealthFlag(**row)


# ---------------------------------------------------------------------------
# Orchestration: incremental refresh
# ---------------------------------------------------------------------------


def refresh(
    repo_root: str | Path,
    *,
    run_semantic: bool = False,
    embed_fn: EmbedFn | None = None,
) -> RefreshResult:
    """Refresh the consistency cache for one repository.

    Incrementality is scoped to artifact classification: an artifact whose
    content hash is unchanged since the last refresh is not reclassified.
    Edge/claim/health-flag recomputation is currently a full pass each
    refresh (see spec 013 section 4/5 for the documented scope and the
    trigger for making that partially incremental too).
    """
    repo_root = Path(repo_root).resolve()
    store = ConsistencyStore(consistency_db_path(repo_root))
    try:
        now = _now()
        head = current_commit(repo_root) if is_git_repo(repo_root) else None
        dirty = _is_dirty(repo_root) if head else False

        discovered = discover_artifacts(repo_root)
        cached = store.all_artifacts()

        artifacts: dict[str, Artifact] = {}
        reclassified = 0
        unchanged = 0
        for rel_path in discovered:
            full = repo_root / rel_path
            try:
                content_hash = _content_hash(full)
            except OSError:
                continue

            cached_row = cached.get(rel_path)
            if cached_row and cached_row["content_hash"] == content_hash:
                kind = ArtifactKind(cached_row["kind"])
                authority = ArtifactAuthority(cached_row["authority"])
                classified_at = cached_row["classified_at"]
                unchanged += 1
            else:
                kind, authority = classify_artifact(rel_path)
                classified_at = now
                reclassified += 1

            artifact = Artifact(
                path=rel_path,
                kind=kind,
                authority=authority,
                content_hash=content_hash,
                classified_at=classified_at,
            )
            artifacts[rel_path] = artifact
            store.upsert_artifact(
                rel_path, kind.value, authority.value, content_hash, classified_at
            )

        store.delete_artifacts_not_in(set(artifacts))

        concepts = build_concepts(artifacts, repo_root)
        store.replace_concepts([c.model_dump() for c in concepts])

        edges: list[Edge] = []
        dangling_by_doc: dict[str, list[str]] = {}
        for path, artifact in artifacts.items():
            if artifact.kind in _REFERABLE_KINDS:
                doc_edges, dangling = extract_exact_references(path, repo_root)
                edges.extend(doc_edges)
                if dangling:
                    dangling_by_doc[path] = dangling

        structural_index = _load_structural_index(repo_root)
        structural_stale, structural_commit = structural_graph_freshness(
            structural_index, repo_root
        )
        for path, artifact in artifacts.items():
            if artifact.kind == ArtifactKind.IMPLEMENTATION:
                edges.extend(structural_edges_for(structural_index, path, structural_stale))

        if run_semantic:
            resolved_embed = embed_fn or _default_local_embed_fn()
            edges.extend(
                semantic_similarity_edges(concepts, artifacts, repo_root, resolved_embed)
            )

        store.replace_edges([_edge_to_row(e) for e in edges])

        claims = evaluate_known_claims(repo_root)
        store.replace_claims([_claim_to_row(c) for c in claims])

        health_flags = compute_health_flags(
            concepts, claims, edges, dangling_by_doc, structural_stale, structural_commit
        )
        store.replace_health_flags([_flag_to_row(f) for f in health_flags])

        store.set_repo_state(head, dirty, now, structural_stale, structural_commit)
        store.commit()

        return RefreshResult(
            repo_snapshot=RepoSnapshot(head_commit=head, dirty=dirty),
            artifacts_scanned=len(discovered),
            artifacts_reclassified=reclassified,
            artifacts_unchanged=unchanged,
            concepts=len(concepts),
            edges=len(edges),
            claims=len(claims),
            health_flags=len(health_flags),
            structural_graph_stale=structural_stale,
            structural_graph_commit=structural_commit,
        )
    finally:
        store.close()


def _default_local_embed_fn() -> EmbedFn:
    """Lazily construct a local (no-network) embedding function using this
    package's existing embedder, only when semantic edges are explicitly
    requested."""
    from .embeddings import LocalEmbedder

    embedder = LocalEmbedder()

    def _embed(texts: list[str]) -> list[list[float]]:
        return embedder.embed(texts).tolist()

    return _embed


# ---------------------------------------------------------------------------
# Pre-change evidence packet
# ---------------------------------------------------------------------------


def build_evidence_packet(repo_root: str | Path, concept_id: str) -> EvidencePacket:
    """Assemble everything known about one concept before a change: repo
    snapshot, canonical artifact, every edge/claim touching it, and open
    health flags. Never mutates anything — this is "Phase A — Understand,"
    not "Phase B — Decide/Act" (see spec 013 section 4)."""
    repo_root = Path(repo_root).resolve()
    store = ConsistencyStore(consistency_db_path(repo_root))
    try:
        state = store.get_repo_state()
        snapshot = RepoSnapshot(
            head_commit=state["head_commit"] if state else None,
            dirty=bool(state["dirty"]) if state else False,
        )

        concept_row = store.get_concept(concept_id)
        if not concept_row:
            raise KeyError(
                f"unknown concept_id: {concept_id!r}; run `consistency.refresh()` first"
            )
        concept = Concept(**concept_row)

        artifact_row = store.get_artifact(concept.canonical_path)
        canonical_artifact = Artifact(**artifact_row) if artifact_row else None

        ref = f"artifact:{concept.canonical_path}"
        edges = [_row_to_edge(r) for r in store.edges_for_ref(ref)]
        edges += [
            _row_to_edge(r) for r in store.edges_for_ref(f"concept:{concept.concept_id}")
        ]

        claims = [_row_to_claim(r) for r in store.claims_for_doc_path(concept.canonical_path)]
        health_flags = [_row_to_flag(r) for r in store.health_flags_for_concept(concept_id)]

        return EvidencePacket(
            repo_snapshot=snapshot,
            concept=concept,
            canonical_artifact=canonical_artifact,
            edges=edges,
            claims=claims,
            health_flags=health_flags,
            structural_graph_stale=bool(state["structural_graph_stale"]) if state else True,
            structural_graph_commit=state["structural_graph_commit"] if state else None,
        )
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Post-change consistency check
# ---------------------------------------------------------------------------


def check_consistency(repo_root: str | Path, concept_id: str) -> ConsistencyReport:
    """Compare currently-computed content hashes against the cache's
    last-refreshed hashes for a concept's canonical artifact and its linked
    artifacts. This is deterministic hash-diffing, not semantic value
    comparison: it reports *that* something changed since the cache was
    last refreshed, not *what* changed within the text."""
    repo_root = Path(repo_root).resolve()
    store = ConsistencyStore(consistency_db_path(repo_root))
    try:
        concept_row = store.get_concept(concept_id)
        if not concept_row:
            return ConsistencyReport(
                concept_id=concept_id,
                status=ConsistencyStatus.UNKNOWN_CONCEPT,
                canonical_changed=False,
                linked_changed=[],
                linked_unchanged=[],
                notes="concept not found in cache; run `consistency.refresh()` first",
            )
        concept = Concept(**concept_row)

        canonical_changed = _artifact_changed(store, repo_root, concept.canonical_path)

        ref = f"artifact:{concept.canonical_path}"
        linked_paths = sorted(
            {
                row["to_ref"].removeprefix("artifact:")
                for row in store.edges_for_ref(ref)
                if row["from_ref"] == ref and row["to_ref"].startswith("artifact:")
            }
        )

        linked_changed: list[str] = []
        linked_unchanged: list[str] = []
        for path in linked_paths:
            if _artifact_changed(store, repo_root, path):
                linked_changed.append(path)
            else:
                linked_unchanged.append(path)

        if not canonical_changed and not linked_changed:
            status = ConsistencyStatus.UP_TO_DATE
            notes = "cache matches disk for the canonical artifact and all linked artifacts"
        elif canonical_changed and not linked_changed:
            status = ConsistencyStatus.SPEC_CHANGED_AWAITING_IMPLEMENTATION
            notes = "canonical artifact changed since last refresh; linked artifacts unchanged"
        elif linked_changed and not canonical_changed:
            status = ConsistencyStatus.POSSIBLE_UNDOCUMENTED_DRIFT
            notes = (
                "linked artifact(s) changed since last refresh but the canonical artifact "
                f"did not: {', '.join(linked_changed)}"
            )
        else:
            status = ConsistencyStatus.COORDINATED_CHANGE
            notes = "canonical artifact and linked artifact(s) both changed since last refresh"

        return ConsistencyReport(
            concept_id=concept_id,
            status=status,
            canonical_changed=canonical_changed,
            linked_changed=linked_changed,
            linked_unchanged=linked_unchanged,
            notes=notes,
        )
    finally:
        store.close()


def _artifact_changed(store: ConsistencyStore, repo_root: Path, path: str) -> bool:
    row = store.get_artifact(path)
    full = repo_root / path
    if not full.exists():
        return True  # deleted since last refresh counts as changed
    if not row:
        return True  # never seen before counts as changed
    return _content_hash(full) != row["content_hash"]
