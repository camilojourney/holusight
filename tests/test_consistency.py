"""Tests for the Phase 1 Holusight-AXI documentation-code consistency system.

See specs/013-holusight-axi-consistency-architecture.md for the contract
these tests exercise: purpose-aware classification, the concept registry,
canonical authority selection, claim/relationship provenance across
exact/structural/semantic providers, the incremental cache, the pre-change
evidence packet, and the post-change consistency check.

Most tests build a small synthetic repository under ``tmp_path`` so they
stay fast and never mutate this actual repository. A few tests run directly
against this repository's own real ``ARCHITECTURE.md``, source files, and
``graphify-out/graph.json`` to prove the claim registry and structural
provider work on real content — these are read-only and create no
``.holusight/`` state (they call the extraction functions directly rather
than the full ``refresh()`` pipeline).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codesight import consistency
from codesight.consistency_store import ConsistencyStore

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write(root: Path, rel_path: str, text: str) -> Path:
    full = root / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(text, encoding="utf-8")
    return full


def _minimal_repo(tmp_path: Path) -> Path:
    """A synthetic repo with one spec that references one real impl file."""
    _write(
        tmp_path,
        "specs/001-alpha.md",
        "# Alpha Feature\n\nImplemented by `src/pkg/mod.py`.\n"
        "Also mentions `src/pkg/missing.py`, which does not exist.\n",
    )
    _write(tmp_path, "src/pkg/mod.py", "VALUE = 1\n")
    return tmp_path


# ---------------------------------------------------------------------------
# 1. Purpose-aware artifact classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,expected_kind,expected_authority",
    [
        ("specs/013-foo.md", consistency.ArtifactKind.SPECIFICATION,
         consistency.ArtifactAuthority.CANONICAL),
        ("docs/decisions/0011-foo.md", consistency.ArtifactKind.DECISION,
         consistency.ArtifactAuthority.CANONICAL),
        ("ARCHITECTURE.md", consistency.ArtifactKind.ARCHITECTURE,
         consistency.ArtifactAuthority.CANONICAL),
        ("docs/roadmap.md", consistency.ArtifactKind.VISION_ROADMAP,
         consistency.ArtifactAuthority.CANONICAL),
        ("docs/playbooks/deploy.md", consistency.ArtifactKind.PLAYBOOK,
         consistency.ArtifactAuthority.SUPPORTING),
        ("src/codesight/search.py", consistency.ArtifactKind.IMPLEMENTATION,
         consistency.ArtifactAuthority.SUPPORTING),
        ("tests/test_search.py", consistency.ArtifactKind.TEST,
         consistency.ArtifactAuthority.SUPPORTING),
        ("devlog/2026-08-22.md", consistency.ArtifactKind.DEVLOG,
         consistency.ArtifactAuthority.HISTORICAL),
        (".self-improvement/reports/manager/2026-08-22.md", consistency.ArtifactKind.REPORT,
         consistency.ArtifactAuthority.GENERATED),
        ("graphify-out/graph.json", consistency.ArtifactKind.REPORT,
         consistency.ArtifactAuthority.GENERATED),
        ("README.md", consistency.ArtifactKind.DOCUMENTATION,
         consistency.ArtifactAuthority.SUPPORTING),
        ("random-notes.txt", consistency.ArtifactKind.OTHER,
         consistency.ArtifactAuthority.SUPPORTING),
    ],
)
def test_classify_artifact(path, expected_kind, expected_authority):
    kind, authority = consistency.classify_artifact(path)
    assert kind == expected_kind
    assert authority == expected_authority


# ---------------------------------------------------------------------------
# 2 & 3. Concept registry + canonical authority selection
# ---------------------------------------------------------------------------


def test_build_concepts_one_per_spec_and_decision(tmp_path):
    _write(tmp_path, "specs/001-alpha.md", "# Alpha Feature\n\nbody\n")
    _write(tmp_path, "docs/decisions/0001-alpha-choice.md", "# Alpha Choice\n\nbody\n")
    _write(tmp_path, "README.md", "# Not a concept\n")  # documentation, not canonical

    artifacts = {
        path: consistency.Artifact(
            path=path, kind=kind, authority=authority, content_hash="x", classified_at="t"
        )
        for path, (kind, authority) in {
            "specs/001-alpha.md": consistency.classify_artifact("specs/001-alpha.md"),
            "docs/decisions/0001-alpha-choice.md": consistency.classify_artifact(
                "docs/decisions/0001-alpha-choice.md"
            ),
            "README.md": consistency.classify_artifact("README.md"),
        }.items()
    }

    concepts = consistency.build_concepts(artifacts, tmp_path)

    assert {c.concept_id for c in concepts} == {
        "specs/001-alpha.md",
        "docs/decisions/0001-alpha-choice.md",
    }
    by_id = {c.concept_id: c for c in concepts}
    assert by_id["specs/001-alpha.md"].scope == "Alpha Feature"
    assert by_id["specs/001-alpha.md"].canonical_path == "specs/001-alpha.md"
    assert by_id["specs/001-alpha.md"].status == "active"


def test_build_concepts_detects_superseded(tmp_path):
    _write(
        tmp_path,
        "docs/decisions/0002-old.md",
        "# Old Decision\n\nStatus: Superseded\n\nbody\n",
    )
    kind, authority = consistency.classify_artifact("docs/decisions/0002-old.md")
    artifacts = {
        "docs/decisions/0002-old.md": consistency.Artifact(
            path="docs/decisions/0002-old.md", kind=kind, authority=authority,
            content_hash="x", classified_at="t",
        )
    }
    concepts = consistency.build_concepts(artifacts, tmp_path)
    assert concepts[0].status == "superseded"


# ---------------------------------------------------------------------------
# 5a. Exact-reference provider (and dangling-reference detection)
# ---------------------------------------------------------------------------


def test_extract_exact_references_resolves_real_file_and_flags_dangling(tmp_path):
    _minimal_repo(tmp_path)
    edges, dangling = consistency.extract_exact_references("specs/001-alpha.md", tmp_path)

    assert len(edges) == 1
    edge = edges[0]
    assert edge.from_ref == "artifact:specs/001-alpha.md"
    assert edge.to_ref == "artifact:src/pkg/mod.py"
    assert edge.relation == "references"
    assert edge.provider == consistency.ProviderKind.EXACT
    assert edge.confidence == 1.0

    assert dangling == ["src/pkg/missing.py"]


def test_extract_exact_references_real_repo_finds_known_dangling_link():
    """Regression proof: this repository has one genuine, deliberately
    unfixed dangling reference, found by the very first real run of this
    system (`docs/decisions/0010-graphify-extension-contract.md`'s dangling
    `docs/capabilities.md` reference was fixed in this same PR — see
    specs/013-holusight-axi-consistency-architecture.md section 4). This
    one is left as-is because the right fix requires a human product
    decision (is the whole ADR superseded, and by what?), not a guess."""
    _, dangling_0006 = consistency.extract_exact_references(
        "docs/decisions/0006-two-deployment-modes.md", REPO_ROOT
    )
    assert any("specs/002-deployment-modes.md" in token for token in dangling_0006)

    edges_0010, dangling_0010 = consistency.extract_exact_references(
        "docs/decisions/0010-graphify-extension-contract.md", REPO_ROOT
    )
    assert "docs/capabilities.md" not in dangling_0010
    assert any(e.to_ref == "artifact:specs/010-capability-inventory.md" for e in edges_0010)


# ---------------------------------------------------------------------------
# 4. Claim provenance: known-invariant registry
# ---------------------------------------------------------------------------


def test_evaluate_known_claims_real_repo_currently_all_match():
    """This repo's ARCHITECTURE.md invariants currently agree with the
    code they describe; this is the intended steady state, and a failure
    here means either the doc or the code drifted (see ARCHITECTURE.md's
    "What NOT to Change Without Discussion" section)."""
    claims = consistency.evaluate_known_claims(REPO_ROOT)
    by_name = {c.name: c for c in claims}

    assert by_name["rrf_k"].doc_value == "60"
    assert by_name["rrf_k"].code_value == "60"
    assert by_name["rrf_k"].status == consistency.ClaimStatus.MATCH

    assert by_name["ast_min_lines"].doc_value == "5"
    assert by_name["ast_min_lines"].code_value == "5"
    assert by_name["ast_min_lines"].status == consistency.ClaimStatus.MATCH

    assert by_name["content_hash_length"].status == consistency.ClaimStatus.MATCH
    assert by_name["data_dir_location"].status == consistency.ClaimStatus.MATCH


def test_evaluate_known_claims_missing_files_returns_unknown(tmp_path):
    claims = consistency.evaluate_known_claims(tmp_path)
    assert all(c.status == consistency.ClaimStatus.UNKNOWN for c in claims)
    assert all(c.doc_value is None and c.code_value is None for c in claims)


def test_evaluate_known_claims_detects_drift(tmp_path):
    _write(tmp_path, "ARCHITECTURE.md", "RRF k=60 constant\n")
    _write(
        tmp_path,
        "src/codesight/search.py",
        "def rrf_merge(\n    ranked_lists,\n    k: int = 99,\n):\n    pass\n",
    )
    claims = consistency.evaluate_known_claims(tmp_path)
    rrf = next(c for c in claims if c.name == "rrf_k")
    assert rrf.doc_value == "60"
    assert rrf.code_value == "99"
    assert rrf.status == consistency.ClaimStatus.DRIFT


# ---------------------------------------------------------------------------
# 5b. Structural provider (Graphify)
# ---------------------------------------------------------------------------


def test_structural_graph_freshness_self_consistent_on_real_repo():
    """Doesn't assert a specific commit (that would break on the next
    `graphify update .`); asserts the staleness computation is internally
    consistent with the graph's own declared commit and current HEAD."""
    from codesight.git_utils import current_commit

    index = consistency._load_structural_index(REPO_ROOT)
    assert index.available is True
    assert index.built_at_commit is not None

    stale, commit = consistency.structural_graph_freshness(index, REPO_ROOT)
    assert commit == index.built_at_commit
    head = current_commit(REPO_ROOT)
    assert stale == (head is None or commit != head)


def test_structural_edges_for_missing_graph_returns_empty(tmp_path):
    index = consistency._load_structural_index(tmp_path)
    assert index.available is False
    edges = consistency.structural_edges_for(index, "src/pkg/mod.py", stale=True)
    assert edges == []


# ---------------------------------------------------------------------------
# 5c. Semantic provider (local embeddings, opt-in)
# ---------------------------------------------------------------------------


def test_semantic_similarity_edges_thresholds_and_tags_provider(tmp_path):
    _write(tmp_path, "specs/001-alpha.md", "# Alpha\n\nbody\n")
    _write(tmp_path, "specs/002-beta.md", "# Beta\n\nbody\n")

    concepts = [
        consistency.Concept(
            concept_id="specs/001-alpha.md", scope="Alpha",
            canonical_path="specs/001-alpha.md",
            source_kind=consistency.ArtifactKind.SPECIFICATION,
        )
    ]
    artifacts = {
        "specs/001-alpha.md": consistency.Artifact(
            path="specs/001-alpha.md", kind=consistency.ArtifactKind.SPECIFICATION,
            authority=consistency.ArtifactAuthority.CANONICAL,
            content_hash="x", classified_at="t",
        ),
        "specs/002-beta.md": consistency.Artifact(
            path="specs/002-beta.md", kind=consistency.ArtifactKind.SPECIFICATION,
            authority=consistency.ArtifactAuthority.CANONICAL,
            content_hash="x", classified_at="t",
        ),
    }

    # Deterministic fake embedder: identical vectors -> similarity 1.0.
    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    edges = consistency.semantic_similarity_edges(
        concepts, artifacts, tmp_path, fake_embed, threshold=0.55
    )
    assert len(edges) == 1
    edge = edges[0]
    assert edge.provider == consistency.ProviderKind.SEMANTIC
    assert edge.from_ref == "concept:specs/001-alpha.md"
    assert edge.to_ref == "artifact:specs/002-beta.md"
    assert edge.confidence == pytest.approx(1.0)


def test_refresh_default_never_produces_semantic_edges(tmp_path):
    """Semantic provider is opt-in; a default refresh() must never call it
    or persist semantic edges, even though this synthetic repo's two specs
    would be identical (and thus maximally "similar") if it were enabled."""
    _write(tmp_path, "specs/001-alpha.md", "# Alpha\n\nsame body\n")
    _write(tmp_path, "specs/002-beta.md", "# Beta\n\nsame body\n")

    consistency.refresh(tmp_path)
    store = ConsistencyStore(consistency.consistency_db_path(tmp_path))
    try:
        providers = {row["provider"] for row in store.all_edges()}
    finally:
        store.close()
    assert consistency.ProviderKind.SEMANTIC.value not in providers


# ---------------------------------------------------------------------------
# Incremental local cache
# ---------------------------------------------------------------------------


def test_refresh_incremental_skips_unchanged_artifacts(tmp_path):
    _minimal_repo(tmp_path)

    first = consistency.refresh(tmp_path)
    assert first.artifacts_reclassified == first.artifacts_scanned
    assert first.artifacts_unchanged == 0

    second = consistency.refresh(tmp_path)
    assert second.artifacts_scanned == first.artifacts_scanned
    assert second.artifacts_reclassified == 0
    assert second.artifacts_unchanged == first.artifacts_scanned


def test_refresh_reclassifies_only_changed_file(tmp_path):
    _minimal_repo(tmp_path)
    consistency.refresh(tmp_path)

    _write(tmp_path, "src/pkg/mod.py", "VALUE = 2  # changed\n")
    result = consistency.refresh(tmp_path)

    assert result.artifacts_reclassified == 1
    assert result.artifacts_unchanged == result.artifacts_scanned - 1


def test_refresh_creates_single_sqlite_file_no_placeholder_dirs(tmp_path):
    """Enforces ADR-0011: one atomic SQLite database, no per-concern
    databases or empty placeholder directories."""
    _minimal_repo(tmp_path)
    consistency.refresh(tmp_path)

    holusight_dir = tmp_path / ".holusight"
    entries = list(holusight_dir.iterdir())
    db_entries = [e for e in entries if e.suffix == ".db"]
    assert [e.name for e in db_entries] == ["consistency.db"]
    # No other sqlite files (e.g. WAL/SHM sidecars are fine; separate
    # per-concern databases or embeddings/graph-cache/health directories
    # are not).
    assert not any(e.is_dir() for e in entries)


# ---------------------------------------------------------------------------
# Health flags
# ---------------------------------------------------------------------------


def test_refresh_flags_duplicate_canonical_scope(tmp_path):
    _write(tmp_path, "specs/001-alpha.md", "# Shared Title\n\nbody\n")
    _write(tmp_path, "specs/002-beta.md", "# Shared Title\n\nbody\n")

    result = consistency.refresh(tmp_path)
    assert result.health_flags > 0

    store = ConsistencyStore(consistency.consistency_db_path(tmp_path))
    try:
        flags = store.all_health_flags()
    finally:
        store.close()
    assert any(f["flag_type"] == "MULTIPLE_CANONICAL_SCOPE" for f in flags)


def test_refresh_flags_dangling_reference(tmp_path):
    _minimal_repo(tmp_path)
    consistency.refresh(tmp_path)

    store = ConsistencyStore(consistency.consistency_db_path(tmp_path))
    try:
        flags = store.all_health_flags()
    finally:
        store.close()
    dangling_flags = [f for f in flags if f["flag_type"] == "DANGLING_REFERENCE"]
    assert any("src/pkg/missing.py" in f["detail"] for f in dangling_flags)


# ---------------------------------------------------------------------------
# Pre-change evidence packet
# ---------------------------------------------------------------------------


def test_build_evidence_packet_unknown_concept_raises(tmp_path):
    consistency.refresh(tmp_path)
    with pytest.raises(KeyError):
        consistency.build_evidence_packet(tmp_path, "specs/does-not-exist.md")


def test_build_evidence_packet_returns_concept_and_edges(tmp_path):
    _minimal_repo(tmp_path)
    consistency.refresh(tmp_path)

    packet = consistency.build_evidence_packet(tmp_path, "specs/001-alpha.md")
    assert packet.concept.concept_id == "specs/001-alpha.md"
    assert packet.canonical_artifact is not None
    assert packet.canonical_artifact.path == "specs/001-alpha.md"
    assert any(e.to_ref == "artifact:src/pkg/mod.py" for e in packet.edges)
    assert any(f.flag_type == "DANGLING_REFERENCE" for f in packet.health_flags)


# ---------------------------------------------------------------------------
# Post-change consistency check
# ---------------------------------------------------------------------------


def test_check_consistency_unknown_concept(tmp_path):
    consistency.refresh(tmp_path)
    report = consistency.check_consistency(tmp_path, "specs/does-not-exist.md")
    assert report.status == consistency.ConsistencyStatus.UNKNOWN_CONCEPT


def test_check_consistency_up_to_date_immediately_after_refresh(tmp_path):
    _minimal_repo(tmp_path)
    consistency.refresh(tmp_path)
    report = consistency.check_consistency(tmp_path, "specs/001-alpha.md")
    assert report.status == consistency.ConsistencyStatus.UP_TO_DATE
    assert report.canonical_changed is False
    assert report.linked_changed == []


def test_check_consistency_spec_changed_awaiting_implementation(tmp_path):
    _minimal_repo(tmp_path)
    consistency.refresh(tmp_path)

    _write(
        tmp_path, "specs/001-alpha.md",
        "# Alpha Feature\n\nImplemented by `src/pkg/mod.py`. New sentence.\n"
        "Also mentions `src/pkg/missing.py`, which does not exist.\n",
    )
    report = consistency.check_consistency(tmp_path, "specs/001-alpha.md")
    assert report.status == consistency.ConsistencyStatus.SPEC_CHANGED_AWAITING_IMPLEMENTATION
    assert report.canonical_changed is True
    assert report.linked_changed == []


def test_check_consistency_possible_undocumented_drift(tmp_path):
    _minimal_repo(tmp_path)
    consistency.refresh(tmp_path)

    _write(tmp_path, "src/pkg/mod.py", "VALUE = 999  # behavior changed\n")
    report = consistency.check_consistency(tmp_path, "specs/001-alpha.md")
    assert report.status == consistency.ConsistencyStatus.POSSIBLE_UNDOCUMENTED_DRIFT
    assert report.canonical_changed is False
    assert "src/pkg/mod.py" in report.linked_changed


def test_check_consistency_coordinated_change(tmp_path):
    _minimal_repo(tmp_path)
    consistency.refresh(tmp_path)

    _write(
        tmp_path, "specs/001-alpha.md",
        "# Alpha Feature\n\nImplemented by `src/pkg/mod.py`. Updated together.\n"
        "Also mentions `src/pkg/missing.py`, which does not exist.\n",
    )
    _write(tmp_path, "src/pkg/mod.py", "VALUE = 3  # coordinated update\n")
    report = consistency.check_consistency(tmp_path, "specs/001-alpha.md")
    assert report.status == consistency.ConsistencyStatus.COORDINATED_CHANGE
    assert report.canonical_changed is True
    assert "src/pkg/mod.py" in report.linked_changed
