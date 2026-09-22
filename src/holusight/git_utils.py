"""Git utilities for detecting changed files and current commit."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def current_commit(repo_path: str | Path) -> str | None:
    """Return the current HEAD commit hash, or None if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def changed_files(repo_path: str | Path, since_commit: str) -> list[Path]:
    """Return list of files changed between *since_commit* and HEAD.

    Falls back to returning all files if git diff fails.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMR", f"{since_commit}..HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return [Path(repo_path) / f for f in result.stdout.strip().split("\n") if f]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.warning("git diff failed for %s, treating all files as changed", repo_path)
    return []


def deleted_files(repo_path: str | Path, since_commit: str) -> list[str]:
    """Return list of files deleted between *since_commit* and HEAD."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=D", f"{since_commit}..HEAD"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return [f for f in result.stdout.strip().split("\n") if f]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return []


def is_git_repo(repo_path: str | Path) -> bool:
    """Check if the given path is inside a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
