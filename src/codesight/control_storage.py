"""No-follow, atomic storage primitives for Holusight derived control-plane data.

Canonical repository content is never a destination.  This module is the only
writer used by public control-plane commands.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import stat
import subprocess
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


def _prepare_destination(
    repo_root: Path, raw_path: Path, *, allowed_repo_root: Path
) -> tuple[Path, Path]:
    destination = validate_output_path(repo_root, raw_path, allowed_repo_root=allowed_repo_root)
    return destination, destination.parent


def _directory_flags() -> int:
    return os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


def _open_child_directories(parent_fd: int, parts: tuple[str, ...]) -> int:
    current_fd = os.dup(parent_fd)
    try:
        for part in parts:
            if part in {"", ".", ".."}:
                raise UnsafeStoragePath("output path contains an unsafe directory component")
            try:
                child_fd = os.open(part, _directory_flags(), dir_fd=current_fd)
            except FileNotFoundError:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=current_fd)
                except FileExistsError:
                    pass
                child_fd = os.open(part, _directory_flags(), dir_fd=current_fd)
            os.close(current_fd)
            current_fd = child_fd
        metadata = os.fstat(current_fd)
        if not stat.S_ISDIR(metadata.st_mode):
            raise UnsafeStoragePath("output parent is not a directory")
        return current_fd
    except (OSError, UnsafeStoragePath) as exc:
        os.close(current_fd)
        if isinstance(exc, UnsafeStoragePath):
            raise
        raise UnsafeStoragePath("output parent cannot be opened safely") from exc


def _open_repo_root(repo_root: Path) -> int:
    try:
        before = os.lstat(repo_root)
        root_fd = os.open(repo_root, _directory_flags())
        after = os.fstat(root_fd)
    except OSError as exc:
        raise UnsafeStoragePath("repository root cannot be opened safely") from exc
    if not stat.S_ISDIR(after.st_mode) or (before.st_dev, before.st_ino) != (
        after.st_dev,
        after.st_ino,
    ):
        os.close(root_fd)
        raise UnsafeStoragePath("repository root changed during validation")
    return root_fd


def _lexical_repo_destination(
    repo_root: Path,
    resolved_repo: Path,
    raw_path: Path,
    *,
    allowed_repo_root: Path,
) -> tuple[Path, Path] | None:
    if raw_path.is_absolute():
        absolute = Path(os.path.abspath(raw_path))
        relative = None
        for root in dict.fromkeys((Path(os.path.abspath(repo_root)), resolved_repo)):
            try:
                relative = absolute.relative_to(root)
                break
            except ValueError:
                continue
        if relative is None:
            return None
    else:
        relative = raw_path
    allowed = allowed_repo_root
    if allowed.is_absolute() or any(part in {"", ".", ".."} for part in allowed.parts):
        raise UnsafeStoragePath("allowed repository root is unsafe")
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise UnsafeStoragePath("output path contains an unsafe repository component")
    if relative == allowed or allowed not in relative.parents:
        raise UnsafeStoragePath("output path must be under gitignored derived state")
    if any(relative == prefix or prefix in relative.parents for prefix in _PROTECTED_PREFIXES):
        raise UnsafeStoragePath("output path targets protected repository content")
    destination = resolved_repo / relative
    if destination.exists() and _tracked(resolved_repo, destination):
        raise UnsafeStoragePath("output path targets tracked repository content")
    return destination, relative.parent


def _open_prepared_parent(
    repo_root: Path, raw_path: Path, *, allowed_repo_root: Path
) -> tuple[Path, int]:
    resolved_repo = repo_root.resolve(strict=True)
    repo_fd = _open_repo_root(resolved_repo)
    try:
        repository_destination = _lexical_repo_destination(
            repo_root,
            resolved_repo,
            raw_path,
            allowed_repo_root=allowed_repo_root,
        )
        if repository_destination is not None:
            destination, relative_parent = repository_destination
            parent_fd = _open_child_directories(repo_fd, relative_parent.parts)
        else:
            destination, parent = _prepare_destination(
                resolved_repo, raw_path, allowed_repo_root=allowed_repo_root
            )
            if not parent.is_absolute():
                raise UnsafeStoragePath("external output parent must be absolute")
            filesystem_fd = os.open(parent.anchor, _directory_flags())
            try:
                external_parts = tuple(
                    part for part in parent.parts if part not in {parent.anchor, ""}
                )
                parent_fd = _open_child_directories(filesystem_fd, external_parts)
            finally:
                os.close(filesystem_fd)
    finally:
        os.close(repo_fd)
    return destination, parent_fd


def _create_temporary_file(parent_fd: int, mode: int) -> tuple[int, str]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    for _ in range(128):
        name = f".tmp-{secrets.token_hex(12)}"
        try:
            return os.open(name, flags, mode, dir_fd=parent_fd), name
        except FileExistsError:
            continue
    raise UnsafeStoragePath("could not allocate a unique temporary output")


def _write_temporary(parent_fd: int, content: bytes, mode: int) -> str:
    fd, temp_name = _create_temporary_file(parent_fd, mode)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        os.unlink(temp_name, dir_fd=parent_fd)
        raise
    return temp_name


def _read_regular_bytes(parent_fd: int, name: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise UnsafeStoragePath("immutable output cannot be reopened safely") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise UnsafeStoragePath("immutable output is not a regular file")
        chunks: list[bytes] = []
        while chunk := os.read(fd, 131_072):
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _atomic_create(
    repo_root: Path,
    raw_path: Path,
    content: bytes,
    *,
    allowed_repo_root: Path,
    read_only: bool,
    accept_identical: bool,
) -> tuple[Path, bytes]:
    destination, parent_fd = _open_prepared_parent(
        repo_root, raw_path, allowed_repo_root=allowed_repo_root
    )
    temp_name: str | None = None
    try:
        temp_name = _write_temporary(parent_fd, content, 0o400 if read_only else 0o600)
        try:
            os.link(
                temp_name,
                destination.name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
            os.fsync(parent_fd)
        except FileExistsError as exc:
            if not accept_identical:
                raise UnsafeStoragePath("immutable output already exists") from exc
        persisted = _read_regular_bytes(parent_fd, destination.name)
        if persisted != content:
            raise UnsafeStoragePath("immutable output already contains different bytes")
        return destination, persisted
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        os.close(parent_fd)


def safe_atomic_create(
    repo_root: Path,
    raw_path: Path,
    content: bytes,
    *,
    allowed_repo_root: Path,
    read_only: bool = True,
) -> Path:
    """Durably create a validated result without replacing existing bytes."""
    destination, _ = _atomic_create(
        repo_root,
        raw_path,
        content,
        allowed_repo_root=allowed_repo_root,
        read_only=read_only,
        accept_identical=False,
    )
    return destination


def safe_atomic_create_or_read_identical(
    repo_root: Path,
    raw_path: Path,
    content: bytes,
    *,
    allowed_repo_root: Path,
    read_only: bool = True,
) -> tuple[Path, bytes]:
    """Create immutable bytes or return identical bytes through the held directory."""
    return _atomic_create(
        repo_root,
        raw_path,
        content,
        allowed_repo_root=allowed_repo_root,
        read_only=read_only,
        accept_identical=True,
    )


def safe_atomic_write(
    repo_root: Path, raw_path: Path, content: bytes, *, allowed_repo_root: Path
) -> Path:
    """Durably create or replace a validated derived/external result file."""
    destination, parent_fd = _open_prepared_parent(
        repo_root, raw_path, allowed_repo_root=allowed_repo_root
    )
    temp_name: str | None = None
    try:
        temp_name = _write_temporary(parent_fd, content, 0o600)
        try:
            destination_stat = os.stat(
                destination.name, dir_fd=parent_fd, follow_symlinks=False
            )
        except FileNotFoundError:
            destination_stat = None
        if destination_stat is not None and stat.S_ISLNK(destination_stat.st_mode):
            raise UnsafeStoragePath("storage destination is a symbolic link")
        os.replace(
            temp_name,
            destination.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        temp_name = None
        os.fsync(parent_fd)
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        os.close(parent_fd)
    return destination


def opaque_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]
