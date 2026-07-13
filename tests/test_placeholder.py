"""Public package export contract tests."""

import codesight
from codesight.api import CodeSight
from codesight.config import ServerConfig
from codesight.types import Answer, IndexStats, RepoStatus, SearchResult

EXPECTED_PUBLIC_EXPORTS = [
    "CodeSight",
    "ServerConfig",
    "Answer",
    "IndexStats",
    "RepoStatus",
    "SearchResult",
]


def test_package_declares_expected_public_exports():
    """The package root exposes a stable public import surface."""
    assert codesight.__all__ == EXPECTED_PUBLIC_EXPORTS


def test_package_exports_resolve_to_canonical_objects():
    """Root exports point at the implementation classes callers should import."""
    expected_objects = {
        "CodeSight": CodeSight,
        "ServerConfig": ServerConfig,
        "Answer": Answer,
        "IndexStats": IndexStats,
        "RepoStatus": RepoStatus,
        "SearchResult": SearchResult,
    }

    for export_name, canonical_object in expected_objects.items():
        assert getattr(codesight, export_name) is canonical_object
