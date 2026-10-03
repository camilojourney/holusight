"""Validated finding selectors; scope never authorizes broader source discovery."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


class Focus:
    def __init__(
        self,
        repo: Path,
        scope: str | None,
        docs: bool,
        *,
        allowed: Iterable[str] = (),
        excluded: Iterable[str] = (),
    ) -> None:
        from .consistency import _safe_path

        if type(docs) is not bool:
            raise ValueError("docs must be a boolean")
        self.repo = repo
        self.docs = docs
        self.allowed = set(allowed)
        self.excluded = set(excluded)
        self.scope = None
        self.kind = "all"
        self.parts: tuple[str, ...] = ()
        if scope is not None:
            target = _safe_path(repo, scope)
            try:
                unsafe = target is None or self.symlink_source(scope)
                directory = target is not None and (
                    target.is_dir() or (not target.exists() and scope.endswith("/"))
                )
            except (OSError, RuntimeError):
                unsafe = True
                directory = False
            if unsafe:
                raise ValueError("scope must be a repository-relative path inside the repository")
            self.scope = Path(scope).as_posix()
            self.parts = Path(scope).parts
            self.kind = "directory" if directory else "file"

    @property
    def filtered(self) -> bool:
        return self.scope is not None or self.docs

    def symlink_source(self, name: str) -> bool:
        parts = Path(name).parts
        try:
            return any(
                (self.repo / Path(*parts[:i])).is_symlink() for i in range(1, len(parts) + 1)
            )
        except (OSError, RuntimeError):
            return True

    def matches(self, name: object) -> bool:
        if not self.filtered:
            return True
        if not isinstance(name, str) or not name:
            return False
        path = Path(name)
        parts = path.parts
        if set(parts) & self.excluded:
            return False
        if self.docs and (path.suffix != ".md" or path.as_posix() not in self.allowed):
            return False
        if self.scope is None:
            return True
        return (
            parts[: len(self.parts)] == self.parts
            if self.kind == "directory"
            else parts == self.parts
        )

    def describe(self) -> dict:
        return {"scope": self.scope, "kind": self.kind, "docs": self.docs}
