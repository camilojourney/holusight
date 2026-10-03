"""Read-only checks of a Graphify graph against the repository it describes.

Only graph integrity and source-backed facts are checked. An edge alone does not
prove that documentation prose is true. No Graphify process, model, index or cache
is started or written by this module.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .focus import Focus

_GRAPH = Path("graphify-out/graph.json")
_LINE = re.compile(r"^L([1-9][0-9]*)(?:-L?([1-9][0-9]*))?$")
_PATH = re.compile(
    r"(?:^|\s|[`(])((?:(?:src|tests|specs|docs|business|\.claude|\.github)/"
    r"[\w./-]+\.[a-zA-Z0-9]+|(?:README|ARCHITECTURE|AGENTS|CLAUDE|COMPARISON)\.md))"
    r"(?=[:#\s`)]|$)"
)
# A literal, path-local annotation, not a classifier of future/proposed prose.
_PLANNED_PATH = re.compile(r"^`?\s+\(not created yet\)", re.IGNORECASE)


def _git(repo: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


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


def load_graph(repo_path: str | Path) -> dict[str, Any]:
    """Load a local graph, raising on absence/invalid structure (never fake empty)."""
    repo = _repo_path(repo_path)
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
    repo = _repo_path(repo_path)
    built = graph.get("built_at_commit")
    git_root = _git(repo, "rev-parse", "--show-toplevel")
    head = _git(repo, "rev-parse", "HEAD")
    dirty = _git(repo, "status", "--porcelain", "--untracked-files=normal")
    head_after = _git(repo, "rev-parse", "HEAD")
    try:
        verified_root = _repo_path(git_root) if git_root else None
    except ValueError:
        verified_root = None
    if not isinstance(built, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", built):
        state = "unknown"
        reason = "graph built_at_commit is missing or invalid"
    elif head is None or head_after is None or dirty is None or verified_root != repo:
        state = "unknown"
        reason = "Repository Git root, HEAD, or working tree state could not be verified"
    elif head != head_after:
        state = "unknown"
        reason = "Repository HEAD changed while verifying provenance"
    elif built != head or dirty:
        state = "stale"
        reason = "graph commit differs from HEAD or repository has local changes"
    else:
        state = "current"
        reason = "graph commit equals HEAD and working tree is clean"
    return {
        "state": state,
        "reason": reason,
        "built_at_commit": built,
        "head_commit": head_after,
        "head_commit_before": head,
    }


def check(
    repo_path: str | Path, *, scope: str | None = None, docs: bool = False, refresh: bool = False
) -> dict[str, Any]:
    """Check graph provenance, node/edge integrity and explicit path claims.

    ``refresh`` is retained for callers, but never executes Graphify or writes
    indexed files. A request to refresh is reported as unavailable, not ignored.
    Findings are bounded to 100 examples; counts are for the complete scan.
    """
    repo = _repo_path(repo_path)
    if not repo.is_dir():
        raise ValueError(f"Not a directory: {repo}")
    # Reuse existing enumeration/exclusions only when a selector is requested.
    # This lazy import avoids a module cycle; alignment already uses this checker.
    if scope is not None or docs:
        from .alignment import _EXCLUDED, _inventory

        focus = Focus(
            repo, scope, docs, allowed=_inventory(repo) if docs else (), excluded=_EXCLUDED
        )
    else:
        focus = Focus(repo, scope, docs)
    selection = {"scope": focus.scope, "docs": docs, "selector": focus.describe()}
    if refresh:
        return {
            "status": "unavailable",
            "reason": "Graph refresh is unsupported; run Graphify separately",
            **selection,
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
            **selection,
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
    selected_files = {
        item["source_file"]
        for item in [*nodes, *links]
        if isinstance(item, dict)
        and isinstance(item.get("source_file"), str)
        and focus.matches(item["source_file"])
    }
    selected_ids = {
        n["id"]
        for n in nodes
        if isinstance(n, dict)
        and isinstance(n.get("id"), str)
        and focus.matches(n.get("source_file"))
    }
    coverage = {"graph_files": len(selected_files), "global_integrity": not focus.filtered}
    if focus.filtered and not selected_files:
        return {
            "status": "unknown",
            "reason": "selector has no graph-backed source evidence",
            **selection,
            "coverage": coverage,
            "provenance": proof,
            "errors": 0,
            "checked": 0,
            "findings": [],
        }
    ids = {n.get("id") for n in nodes if isinstance(n, dict) and isinstance(n.get("id"), str)}
    findings: list[dict[str, Any]] = []
    error_types: dict[str, int] = {}
    finding_types: dict[str, int] = {}
    errors = 0
    finding_count = 0
    checked = 0
    unverified = 0
    line_counts: dict[Path, int | None] = {}
    source_hashes: dict[Path, str] = {}
    resolved_paths: dict[str, Path | None] = {}
    path_states: dict[Path, bool] = {}
    inputs_changed = False

    def checked_path(value: str) -> Path | None:
        nonlocal inputs_changed
        path = _safe_path(repo, value)
        inputs_changed |= resolved_paths.setdefault(value, path) != path
        return path

    def is_file(path: Path) -> bool:
        nonlocal inputs_changed
        try:
            exists = path.is_file()
        except (OSError, RuntimeError):
            exists = False
        inputs_changed |= path_states.setdefault(path, exists) != exists
        return exists

    def read_lines(path: Path) -> list[str] | None:
        nonlocal inputs_changed
        try:
            if _safe_path(repo, str(path.relative_to(repo))) != path:
                return None
            with path.open("rb") as stream:
                data = stream.read(2_000_001)
            if len(data) > 2_000_000:
                return None
            lines = data.decode("utf-8").splitlines()
            digest = hashlib.sha256(data).hexdigest()
            inputs_changed |= source_hashes.setdefault(path, digest) != digest
            return lines
        except (OSError, UnicodeError):
            return None

    def record(
        kind: str,
        file: str,
        line: int | None,
        message: str,
        evidence: str,
        *,
        severity: str = "error",
    ) -> None:
        nonlocal errors, finding_count
        finding_count += 1
        finding_types[kind] = finding_types.get(kind, 0) + 1
        if severity == "error":
            errors += 1
            error_types[kind] = error_types.get(kind, 0) + 1
        if len(findings) < 100 and finding_types[kind] <= 15:
            findings.append(
                {
                    "severity": severity,
                    "type": kind,
                    "file": file,
                    "line": line,
                    "message": message,
                    "evidence": evidence,
                }
            )

    def inspect_file(file: object, location: object, evidence: str) -> None:
        nonlocal checked, unverified
        if focus.filtered and not focus.matches(file):
            return
        if not isinstance(file, str) or not file:
            unverified += 1
            record(
                "unavailable_source",
                str(_GRAPH),
                None,
                "Graph item has no usable source file; source evidence is unavailable",
                evidence,
                severity="info",
            )
            return
        checked += 1
        path = checked_path(file)
        if docs and focus.symlink_source(file):
            path = None
        if path is None:
            record(
                "unsafe_path",
                file,
                None,
                "Graph source path is unsafe or cannot be resolved",
                evidence,
            )
            return
        if not is_file(path):
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
                lines = read_lines(path)
                line_counts[path] = len(lines) if lines is not None else None
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
            if not focus.filtered or (isinstance(n, dict) and focus.matches(n.get("source_file"))):
                record("invalid_node", str(_GRAPH), None, "Graph node has no valid ID", "nodes")
            continue
        if n["id"] in seen_ids and (not focus.filtered or n["id"] in selected_ids):
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
            if not focus.filtered:
                record(
                    "invalid_edge",
                    str(_GRAPH),
                    None,
                    "Graph edge is not an object",
                    f"links[{index}]",
                )
            continue
        if focus.filtered and not (
            focus.matches(edge.get("source_file"))
            or any(
                isinstance(edge.get(k), str) and edge[k] in selected_ids
                for k in ("source", "target")
            )
        ):
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
        if focus.filtered and not focus.matches(file):
            continue
        path = checked_path(file)
        if docs and focus.symlink_source(file):
            continue  # already reported as unsafe by graph source inspection
        if path is None or not is_file(path) or path.suffix != ".md":
            continue
        lines = read_lines(path)
        if lines is None:
            unverified += 1
            continue
        for lineno, line in _markdown_lines("\n".join(lines)):
            if line is None:
                continue
            for match in _PATH.finditer(line):
                ref = match.group(1)
                checked += 1
                target = checked_path(ref)
                if target is None or not is_file(target):
                    if target is not None and _PLANNED_PATH.match(line[match.end() :]):
                        unverified += 1
                        record(
                            "planned_path_reference",
                            file,
                            lineno,
                            f"Absent path is annotated '(not created yet)': {ref}; "
                            "not a verified current-reference claim",
                            f"path:{ref}",
                            severity="info",
                        )
                    else:
                        record(
                            "missing_path_claim",
                            file,
                            lineno,
                            f"Explicit repository path does not exist: {ref}",
                            f"path:{ref}",
                        )

    # Bounded end-of-check resampling, not a monitor or an atomicity promise.
    if docs:
        try:
            inputs_changed |= set(_inventory(repo)) != focus.allowed
        except ValueError:
            inputs_changed = True
    for value, path in resolved_paths.items():
        inputs_changed |= _safe_path(repo, value) != path
    for path, existed in path_states.items():
        inputs_changed |= is_file(path) != existed
    for path in list(source_hashes):
        if read_lines(path) is None:
            inputs_changed = True
    try:
        graph_after = load_graph(repo)
        inputs_changed |= graph_after != graph
        proof_after = provenance(repo, graph_after)
        inputs_changed |= proof_after != proof
    except (OSError, ValueError, UnicodeError):
        inputs_changed = True
        proof_after = proof
    proof = proof_after
    if inputs_changed:
        proof = {
            **proof,
            "state": "unknown",
            "reason": "Graph, source or revision evidence changed during check",
        }
    status = proof["state"]
    if status == "current":
        status = "error" if errors else "unknown" if unverified else "current"
    return {
        "status": status,
        "provenance": proof,
        **selection,
        "coverage": {**coverage, "source_files_inspected": len(source_hashes)},
        "errors": errors,
        "error_types": error_types,
        "checked": checked,
        "unverified": unverified,
        "inputs_changed_during_check": inputs_changed,
        "findings": findings,
        "truncated": finding_count > len(findings),
        "notes": "Stale/unknown provenance prevents a current verdict; "
        "edges do not prove prose claims. Planned path annotations are unverified, "
        "not confirmed current-reference errors.",
    }
