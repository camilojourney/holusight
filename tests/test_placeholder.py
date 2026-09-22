"""Public package export contract tests."""

import holusight
from holusight.api import Holusight
from holusight.config import ServerConfig
from holusight.types import Answer, IndexStats, RepoStatus, SearchResult

EXPECTED_PUBLIC_EXPORTS = [
    "Holusight",
    "ServerConfig",
    "Answer",
    "IndexStats",
    "RepoStatus",
    "SearchResult",
]


def test_package_declares_expected_public_exports():
    """The package root exposes a stable public import surface."""
    assert holusight.__all__ == EXPECTED_PUBLIC_EXPORTS


def test_package_exports_resolve_to_canonical_objects():
    """Root exports point at the implementation classes callers should import."""
    expected_objects = {
        "Holusight": Holusight,
        "ServerConfig": ServerConfig,
        "Answer": Answer,
        "IndexStats": IndexStats,
        "RepoStatus": RepoStatus,
        "SearchResult": SearchResult,
    }

    for export_name, canonical_object in expected_objects.items():
        assert getattr(holusight, export_name) is canonical_object
