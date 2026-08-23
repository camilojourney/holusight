"""No-follow, atomic storage primitives for Holusight derived control-plane data.

Canonical repository content is never a destination.  This module is the only
writer used by public control-plane commands.
"""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import tempfile
from pathlib import Path

DERIVED_ROOT = Path(".holusight")
RESULTS_ROOT = DERIVED_ROOT / "improvement-results"
HISTORY_ROOT = DERIVED_ROOT / "improvement-runs"
_PROTECTED_PREFIXES = (
    Path("src"),
    Path("tests"),
    Path("specs"),
    Path("docs"),
    Path(".claude/skills"),
)


class UnsafeStoragePath(ValueError):
    """A caller tried to use a canonical, symlinked, or escaping destination."""


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _lstat_no_symlink(path: Path) -> None:
    """Reject every existing component that is a symlink."""
    current = Path(path.anchor) if path.is_absolute() else Path()
    for part in path.parts:
        if part in {"", os.sep}:
            continue
        current = current / part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise UnsafeStoragePath("storage path contains a symbolic link")


def _tracked(repo_root: Path, path: Path) -> bool:
    relative = path.relative_to(repo_root).as_posix()
    result = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "--error-unmatch", "--", relative],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def is_clean_tracked_file(repo_root: Path, path: Path) -> bool:
    """Return whether ``path`` exactly matches a blob in the current HEAD.

    This is deliberately stricter than index tracking: an unstaged or staged
    replacement is not a trustworthy anchor. Callers still validate their own
    schema before treating the blob as evidence.
    """
    try:
        repo_root = repo_root.resolve()
        path = path.resolve(strict=True)
        relative = path.relative_to(repo_root).as_posix()
        _lstat_no_symlink(path)
    except (OSError, ValueError, UnsafeStoragePath):
        return False
    if path.is_symlink() or not path.is_file():
        return False
    head_blob = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", f"HEAD:{relative}"],
        capture_output=True,
        text=True,
        check=False,
    )
    worktree_blob = subprocess.run(
        ["git", "-C", str(repo_root), "hash-object", "--", relative],
        capture_output=True,
        text=True,
        check=False,
    )
    return (
        head_blob.returncode == 0
        and worktree_blob.returncode == 0
        and head_blob.stdout.strip() == worktree_blob.stdout.strip()
    )


def validate_output_path(repo_root: Path, raw_path: Path, *, allowed_repo_root: Path) -> Path:
    """Validate a result destination before opening it.

    Repository destinations are restricted to one gitignored derived subtree.
    External destinations are permitted only when every existing component is
    non-symlinked.  Canonical content and aliases into it are always rejected.
    """
    original_repo_root = repo_root
    repo_root = repo_root.resolve()
    allowed = (repo_root / allowed_repo_root).resolve()
    if raw_path.is_absolute():
        # Preserve the worktree's resolved root while allowing hosts where
        # /var is a system alias for /private/var.
        try:
            candidate = repo_root / raw_path.relative_to(original_repo_root)
        except ValueError:
            candidate = raw_path
    else:
        candidate = repo_root / raw_path
    _lstat_no_symlink(candidate.parent)
    # resolve only after lstat checks, so aliases cannot bypass the boundary.
    resolved_parent = candidate.parent.resolve(strict=False)
    destination = resolved_parent / candidate.name
    if destination.exists() and destination.is_symlink():
        raise UnsafeStoragePath("storage destination is a symbolic link")
    if _is_within(destination, repo_root):
        if not _is_within(destination, allowed):
            raise UnsafeStoragePath("output path must be under gitignored derived state")
        relative = destination.relative_to(repo_root)
        if any(relative == prefix or prefix in relative.parents for prefix in _PROTECTED_PREFIXES):
            raise UnsafeStoragePath("output path targets protected repository content")
        if destination.exists() and _tracked(repo_root, destination):
            raise UnsafeStoragePath("output path targets tracked repository content")
    return destination


def safe_atomic_write(
    repo_root: Path, raw_path: Path, content: bytes, *, allowed_repo_root: Path
) -> Path:
    """Durably create or replace a validated derived/external result file."""
    destination = validate_output_path(repo_root, raw_path, allowed_repo_root=allowed_repo_root)
    parent = destination.parent
    # New repository directories are created only below the validated derived root.
    if not parent.exists():
        if _is_within(destination, repo_root) and not _is_within(
            destination, (repo_root / allowed_repo_root).resolve()
        ):
            raise UnsafeStoragePath("output parent is not derived state")
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _lstat_no_symlink(parent)
    fd, temp_name = tempfile.mkstemp(prefix=".tmp-", dir=parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if destination.exists() and destination.is_symlink():
            raise UnsafeStoragePath("storage destination is a symbolic link")
        os.replace(temp_name, destination)
        # Persist the rename where the platform supports directory fsync.
        directory_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    return destination


def opaque_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]
