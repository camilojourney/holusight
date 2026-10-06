"""Repository path and Markdown helpers shared by the source scanner and selectors."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path


def _repo_path(value: str | Path) -> Path:
    try:
        return Path(value).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        raise ValueError("Repository path cannot be resolved") from exc


def _safe_path(repo: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    path = Path(value)
    if path.is_absolute() or any(part in ("..", ".") for part in path.parts):
        return None
    try:
        target = (repo / path).resolve()
    except (OSError, RuntimeError):
        return None
    return target if target.is_relative_to(repo) else None


def _markdown_lines(text: str) -> Iterator[tuple[int, str | None]]:
    """Bounded Markdown prose: exclude fences and indented example lines.

    None is a block boundary so examples cannot join surrounding paragraphs.
    This is not a complete Markdown renderer (lists/quotes are not interpreted).
    """
    fence: tuple[str, int] | None = None
    for number, line in enumerate(text.splitlines(), 1):
        prefix = re.match(r"[ \t]*", line).group()
        indent = len(prefix.expandtabs(4))
        stripped = line[len(prefix) :]
        delimiter = re.match(r"^(`{3,}|~{3,})(.*)$", stripped)
        if fence:
            if indent <= 3 and delimiter:
                run, tail = delimiter.groups()
                if run[0] == fence[0] and len(run) >= fence[1] and re.fullmatch(r"[ \t]*", tail):
                    fence = None
            yield number, None
        elif indent >= 4:
            yield number, None
        elif delimiter and not (delimiter.group(1)[0] == "`" and "`" in delimiter.group(2)):
            run = delimiter.group(1)
            fence = (run[0], len(run))
            yield number, None
        else:
            yield number, line
