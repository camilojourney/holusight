"""Public Python API for Holusight.

Phase 1-2 refactor: Holusight is now a consistency checker on Graphify.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .config import ServerConfig
from .types import RepoStatus

logger = logging.getLogger(__name__)


class Holusight:
    """Holusight consistency checker (Phase 1-2 refactor).

    Detects documentation-code drift via symbol resolution against Graphify.
    """

    def __init__(
        self,
        folder_path: str | Path,
        config: ServerConfig | None = None,
    ) -> None:
        self.folder_path = Path(folder_path).expanduser().resolve()
        if not self.folder_path.is_dir():
            raise ValueError(f"Not a directory: {self.folder_path}")

        self.config = config or ServerConfig()

    def status(self) -> RepoStatus:
        """Check repository status (Graphify graph available)."""
        from .consistency import load_graph

        graph = load_graph(self.folder_path)
        nodes = graph.get("nodes", [])
        has_graph = bool(nodes)

        # Extract unique files from node IDs (format: "path/to/file.py:symbol")
        files_indexed = set()
        if isinstance(nodes, list):
            for node in nodes:
                if isinstance(node, dict) and "id" in node:
                    file_path = node["id"].split(":")[0]
                    if file_path:
                        files_indexed.add(file_path)
        elif isinstance(nodes, dict):
            for node_id in nodes.keys():
                file_path = node_id.split(":")[0]
                if file_path:
                    files_indexed.add(file_path)

        return RepoStatus(
            repo_path=str(self.folder_path),
            indexed=has_graph,
            chunk_count=len(nodes) if isinstance(nodes, list) else len(nodes),
            files_indexed=len(files_indexed),
            last_commit=None,
            last_indexed_at=None,
            stale=False,
        )


