"""Read-only Python entry point for Graphify/repository mismatch checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .consistency import _repo_path, check, load_graph, provenance


class Holusight:
    """Inspect an existing Graphify graph; never build or mutate it."""

    def __init__(self, folder_path: str | Path) -> None:
        self.folder_path = _repo_path(folder_path)
        if not self.folder_path.is_dir():
            raise ValueError(f"Not a directory: {self.folder_path}")

    def check(self, scope: str | None = None, *, docs: bool = False) -> dict[str, Any]:
        return check(self.folder_path, scope=scope, docs=docs)

    def align(
        self, scope: str | None = None, against: str | None = None, *, docs: bool = False
    ) -> dict[str, Any]:
        """Rescan current source for duplication candidates and explicit fact drift."""
        from .alignment import align

        return align(self.folder_path, scope=scope, docs=docs, against=against)

    def status(self) -> dict[str, Any]:
        try:
            graph = load_graph(self.folder_path)
        except (OSError, ValueError) as exc:
            return {"status": "unavailable", "reason": str(exc)}
        proof = provenance(self.folder_path, graph)
        return {
            "status": proof["state"],
            "provenance": proof,
            "nodes": len(graph["nodes"]),
            "links": len(graph["links"]),
        }
