"""Read-only checks of a Graphify graph against the repository it describes.

Only graph integrity and source-backed facts are checked. An edge alone does not
prove that documentation prose is true. No Graphify process, model, index or cache
is started or written by this module.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

_GRAPH = Path("graphify-out/graph.json")
_LINE = re.compile(r"^L([1-9][0-9]*)(?:-L?([1-9][0-9]*))?$")
_PATH = re.compile(
    r"(?:^|\s|[`(])((?:(?:src|tests|specs|docs|business|\.claude|\.github)/"
    r"[\w./-]+\.[a-zA-Z0-9]+|(?:README|ARCHITECTURE|AGENTS|CLAUDE|COMPARISON)\.md))"
    r"(?=[:#\s`)]|$)"
)


def _git(repo: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _safe_path(repo: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    path = Path(value)
    if path.is_absolute() or any(part in ("..", ".") for part in path.parts):
        return None
    target = (repo / path).resolve()
    return target if target.is_relative_to(repo) else None


def load_graph(repo_path: str | Path) -> dict[str, Any]:
    """Load a local graph, raising on absence/invalid structure (never fake empty)."""
    repo = Path(repo_path).resolve()
    path = _safe_path(repo, str(_GRAPH))
    if path is None or not path.is_file():
        raise FileNotFoundError("graphify-out/graph.json is missing or unsafe")
    if path.stat().st_size > 100_000_000:
        raise ValueError("graphify-out/graph.json exceeds 100 MB limit")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("nodes"), (list, dict)):
        raise ValueError("Graphify graph has no valid nodes collection")
    if not isinstance(data.get("links"), list):
        raise ValueError("Graphify graph has no valid links collection")
    return data


def provenance(repo_path: str | Path, graph: dict[str, Any]) -> dict[str, Any]:
    """Current only for an exact Git HEAD match and clean repository snapshot."""
    repo = Path(repo_path).resolve()
    built = graph.get("built_at_commit")
    git_root = _git(repo, "rev-parse", "--show-toplevel")
    head = _git(repo, "rev-parse", "HEAD")
    dirty = _git(repo, "status", "--porcelain", "--untracked-files=normal")
    if not isinstance(built, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", built):
        state = "unknown"
        reason = "graph built_at_commit is missing or invalid"
    elif head is None or dirty is None or git_root is None or Path(git_root).resolve() != repo:
        state = "unknown"
        reason = "Repository Git root, HEAD, or working tree state could not be verified"
    elif built != head or dirty:
        state = "stale"
        reason = "graph commit differs from HEAD or repository has local changes"
    else:
        state = "current"
        reason = "graph commit equals HEAD and working tree is clean"
    return {"state": state, "reason": reason, "built_at_commit": built, "head_commit": head}


def check(
    repo_path: str | Path, *, scope: str | None = None, refresh: bool = False
) -> dict[str, Any]:
    """Check graph provenance, node/edge integrity and explicit path claims.

    ``refresh`` is retained for callers, but never executes Graphify or writes
    indexed files. A request to refresh is reported as unavailable, not ignored.
    Findings are bounded to 100 examples; counts are for the complete scan.
    """
    repo = Path(repo_path).expanduser().resolve()
    if not repo.is_dir():
        raise ValueError(f"Not a directory: {repo}")
    if scope is not None and _safe_path(repo, scope) is None:
        raise ValueError("scope must be a repository-relative path inside the repository")
    if refresh:
        return {
            "status": "unavailable",
            "reason": "Graph refresh is unsupported; run Graphify separately",
            "errors": 0,
            "findings": [],
            "checked": 0,
        }
    try:
        graph = load_graph(repo)
    except (OSError, ValueError, json.JSONDecodeError, UnicodeError) as exc:
        return {
            "status": "unavailable",
            "reason": str(exc),
            "errors": 0,
            "findings": [],
            "checked": 0,
        }

    proof = provenance(repo, graph)
    nodes = graph["nodes"]
    if isinstance(nodes, dict):
        nodes = [
            dict(value, id=key) if isinstance(value, dict) else value
            for key, value in nodes.items()
        ]
    links = graph["links"]
    if scope and not any(
        isinstance(item, dict) and item.get("source_file") == scope for item in [*nodes, *links]
    ):
        return {
            "status": "unknown",
            "reason": "scope has no graph-backed source evidence",
            "scope": scope,
            "provenance": proof,
            "errors": 0,
            "checked": 0,
            "findings": [],
        }
    ids = {n.get("id") for n in nodes if isinstance(n, dict) and isinstance(n.get("id"), str)}
    findings: list[dict[str, Any]] = []
    error_types: dict[str, int] = {}
    errors = 0
    checked = 0
    unverified = 0
    line_counts: dict[Path, int | None] = {}

    def record(kind: str, file: str, line: int | None, message: str, evidence: str) -> None:
        nonlocal errors
        errors += 1
        error_types[kind] = error_types.get(kind, 0) + 1
        if len(findings) < 100 and error_types[kind] <= 15:
            findings.append(
                {
                    "severity": "error",
                    "type": kind,
                    "file": file,
                    "line": line,
                    "message": message,
                    "evidence": evidence,
                }
            )

    def inspect_file(file: object, location: object, evidence: str) -> None:
        nonlocal checked, unverified
        if not isinstance(file, str) or (scope and file != scope):
            return
        checked += 1
        path = _safe_path(repo, file)
        if path is None:
            record("unsafe_path", file, None, "Graph source path escapes repository", evidence)
            return
        if not path.is_file():
            record("missing_source", file, None, "Graph references a missing source file", evidence)
            return
        if location is not None and (
            not isinstance(location, str) or not _LINE.fullmatch(location)
        ):
            record(
                "invalid_source_location",
                file,
                None,
                "Graph source location must be L<positive line> or a positive line range",
                evidence,
            )
            return
        if isinstance(location, str) and (match := _LINE.fullmatch(location)):
            lineno = int(match.group(1))
            end_line = int(match.group(2) or match.group(1))
            if end_line < lineno:
                record(
                    "invalid_line_range",
                    file,
                    lineno,
                    "Graph source line range is reversed",
                    evidence,
                )
                return
            # Source-location checks are factual even for stale graphs; an edge
            # relation's semantic truth is not inferred from the line.
            if path not in line_counts:
                try:
                    line_counts[path] = (
                        len(path.read_text(encoding="utf-8").splitlines())
                        if path.stat().st_size <= 2_000_000
                        else None
                    )
                except (OSError, UnicodeError):
                    line_counts[path] = None
            if line_counts[path] is None:
                unverified += 1
                return
            if end_line > line_counts[path]:
                record(
                    "missing_line",
                    file,
                    end_line,
                    "Graph source line is beyond end of current file",
                    evidence,
                )

    seen_ids: set[str] = set()
    for n in nodes:
        if not isinstance(n, dict) or not isinstance(n.get("id"), str) or not n["id"]:
            record("invalid_node", str(_GRAPH), None, "Graph node has no valid ID", "nodes")
            continue
        if n["id"] in seen_ids:
            record(
                "duplicate_node",
                str(_GRAPH),
                None,
                f"Duplicate graph node ID: {n['id']}",
                f"node:{n['id']}",
            )
        seen_ids.add(n["id"])
        inspect_file(n.get("source_file"), n.get("source_location"), f"node:{n['id']}")
    for index, edge in enumerate(links):
        if not isinstance(edge, dict):
            record(
                "invalid_edge", str(_GRAPH), None, "Graph edge is not an object", f"links[{index}]"
            )
            continue
        for endpoint in ("source", "target"):
            if not isinstance(edge.get(endpoint), str) or edge[endpoint] not in ids:
                record(
                    "dangling_edge",
                    str(_GRAPH),
                    None,
                    f"Edge {endpoint} is not a graph node: {edge.get(endpoint)!r}",
                    f"links[{index}]",
                )
        inspect_file(edge.get("source_file"), edge.get("source_location"), f"links[{index}]")

    # Only explicit repository paths in graph-backed documentation are claims.
    # No fuzzy symbols or generic prose assertions are treated as proven drift.
    doc_files = {
        n.get("source_file")
        for n in nodes
        if isinstance(n, dict)
        and n.get("file_type") == "document"
        and isinstance(n.get("source_file"), str)
    }
    for file in sorted(doc_files):
        if scope and file != scope:
            continue
        path = _safe_path(repo, file)
        if path is None or not path.is_file() or path.suffix != ".md":
            continue
        try:
            if path.stat().st_size > 2_000_000:
                unverified += 1
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            unverified += 1
            continue
        in_fence = False
        for lineno, line in enumerate(lines, 1):
            if line.lstrip().startswith(("```", "~~~")):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            for match in _PATH.finditer(line):
                ref = match.group(1)
                checked += 1
                target = _safe_path(repo, ref)
                if target is None or not target.is_file():
                    record(
                        "missing_path_claim",
                        file,
                        lineno,
                        f"Explicit repository path does not exist: {ref}",
                        f"path:{ref}",
                    )

    status = proof["state"]
    if status == "current":
        status = "error" if errors else "unknown" if unverified else "current"
    return {
        "status": status,
        "provenance": proof,
        "errors": errors,
        "error_types": error_types,
        "checked": checked,
        "unverified": unverified,
        "findings": findings,
        "truncated": errors > len(findings),
        "notes": "Stale/unknown provenance prevents a current verdict; "
        "edges do not prove prose claims.",
    }
