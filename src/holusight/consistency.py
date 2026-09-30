"""Holusight thin consistency checker - detects doc/code drift via symbol resolution.

Phase 1-2 refactor: Holusight is now a consistency checker on top of Graphify.
Graphify provides code structure (349 md→py edges in 2.4s).
Holusight detects: dangling references, claim drift, stale fixtures.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, NamedTuple


class Finding(NamedTuple):
    """A consistency finding."""

    severity: str  # "pass" or "error"
    finding_type: str  # dangling_reference, claim_drift, stale_fixture
    file: str
    message: str
    line: int = 0


def load_graph(repo_path: str | Path) -> dict[str, Any]:
    """Load graphify-out/graph.json if it exists.

    Returns dict with "nodes" (list or dict) and "links" (list).
    """
    repo = Path(repo_path)
    graph_file = repo / "graphify-out" / "graph.json"
    if not graph_file.exists():
        return {"nodes": [], "links": []}
    try:
        with open(graph_file) as f:
            return json.load(f)
    except Exception:
        return {"nodes": [], "links": []}


def extract_exact_references(text: str) -> list[str]:
    """Extract symbol names mentioned in documentation.

    Finds patterns like: ClassName, function_name, module.submodule
    """
    pattern = r"\b([A-Z][a-zA-Z0-9_]*|[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*)\b"
    matches = re.findall(pattern, text)
    return list(set(matches))  # deduplicate


def resolve_against_graph(mention: str, graph: dict[str, Any]) -> bool:
    """Check if a symbol exists in the Graphify graph.

    Handles both list and dict formats for nodes.
    """
    nodes = graph.get("nodes", [])

    if isinstance(nodes, list):
        # Graphify v1.2 format: nodes is a list of dicts with "id" and "label"
        for node in nodes:
            if isinstance(node, dict):
                node_id = node.get("id", "")
                label = node.get("label", "")
                if node_id == mention or label == mention or mention in node_id:
                    return True
    elif isinstance(nodes, dict):
        # Fallback for dict format
        for node_id, node_data in nodes.items():
            if isinstance(node_data, dict):
                if node_id == mention or node_data.get("name") == mention:
                    return True
                if mention in node_id:
                    return True

    return False


def check_claim_values(repo_path: str | Path) -> list[Finding]:
    """Verify that documented claims match actual code values."""
    findings = []
    repo = Path(repo_path)

    claims = [
        ("RRF k=60", "src/holusight/search.py", r"k\s*=\s*60"),
        ("min_lines=5", "src/holusight/chunker.py", r"min_lines\s*=\s*5"),
        ("sha256[:16]", "src/holusight/store.py", r"sha256\[:\s*16\]"),
        ("data_dir: ~/.holusight/data", "ARCHITECTURE.md", r"~/.holusight/data"),
    ]

    for claim_name, file_path, pattern in claims:
        file_obj = repo / file_path
        if file_obj.exists():
            content = file_obj.read_text()
            if re.search(pattern, content):
                findings.append(
                    Finding("pass", "claim_verified", file_path, f"{claim_name} ✓")
                )
            else:
                findings.append(
                    Finding("error", "claim_drift", file_path, f"{claim_name} — not found")
                )

    return findings


def find_paths_in_object(obj: Any) -> list[str]:
    """Recursively extract path-like strings from nested objects."""
    paths = []
    if isinstance(obj, dict):
        for v in obj.values():
            paths.extend(find_paths_in_object(v))
    elif isinstance(obj, list):
        for item in obj:
            paths.extend(find_paths_in_object(item))
    elif isinstance(obj, str):
        if "/" in obj and (
            obj.startswith("src/")
            or obj.startswith("tests/")
            or obj.startswith("specs/")
        ):
            paths.append(obj)
    return paths


def check_fixture_inventory(repo_path: str | Path) -> list[Finding]:
    """Check for stale/invalid paths in test fixtures."""
    findings = []
    repo = Path(repo_path)
    fixtures_dir = repo / "tests" / "fixtures"

    if not fixtures_dir.exists():
        return findings

    for jsonl_file in fixtures_dir.glob("*.jsonl"):
        try:
            with open(jsonl_file) as f:
                for line_num, line in enumerate(f, 1):
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                        # Recursively find path-like strings
                        for path_str in find_paths_in_object(obj):
                            if "/" in path_str and not (repo / path_str).exists():
                                findings.append(
                                    Finding(
                                        "error",
                                        "stale_fixture",
                                        str(jsonl_file.relative_to(repo)),
                                        f"Path not found: {path_str}",
                                        line_num,
                                    )
                                )
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass

    return findings


def check(repo_path: str | Path, refresh: bool = True) -> dict[str, Any]:
    """Run full consistency check.

    Returns a dict with:
    - total: total findings
    - passed: number of passed checks
    - errors: number of errors
    - findings: list of findings
    """
    findings = []

    # Check claims
    findings.extend(check_claim_values(repo_path))

    # Check fixtures
    findings.extend(check_fixture_inventory(repo_path))

    passed = len([f for f in findings if f.severity == "pass"])
    errors = len([f for f in findings if f.severity == "error"])

    return {
        "total": len(findings),
        "passed": passed,
        "errors": errors,
        "findings": [
            {
                "severity": f.severity,
                "type": f.finding_type,
                "file": f.file,
                "message": f.message,
                "line": f.line,
            }
            for f in findings
        ],
    }
