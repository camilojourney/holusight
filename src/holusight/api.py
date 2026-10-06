"""Read-only Python entry point for source duplication and fact-drift scans."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .paths import _repo_path


class Holusight:
    """Scan current repository source; never mutate it."""

    def __init__(self, folder_path: str | Path) -> None:
        self.folder_path = _repo_path(folder_path)
        if not self.folder_path.is_dir():
            raise ValueError(f"Not a directory: {self.folder_path}")

    def align(
        self, scope: str | None = None, against: str | None = None, *, docs: bool = False
    ) -> dict[str, Any]:
        """Rescan current source for duplication candidates and explicit fact drift."""
        from .alignment import align

        return align(self.folder_path, scope=scope, docs=docs, against=against)
