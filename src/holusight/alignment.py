"""Deterministic source duplication candidates and explicitly linked scalar facts.

No imports of analyzed code, eval, model calls, caches, or Graphify execution.
A candidate is not a semantic equivalence or a recommendation to delete code.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import platform
import re
import subprocess
import tokenize
from collections import defaultdict
from io import StringIO
from pathlib import Path
from typing import Any

from .consistency import _markdown_lines, _repo_path, _safe_path, load_graph, provenance
from .focus import Focus

RULES = "holus-alignment/v2"
SCHEMA = "holus-alignment-report/v1"
MAX_FILES = 500
MAX_BYTES = 256_000
MAX_TOTAL_BYTES = 10_000_000
MAX_UNITS = 2_000
MAX_FACTS = 1_000
MAX_PAIRS = 5_000
_EXCLUDED = {
    ".git",
    ".venv",
    "venv",
    ".holusight",
    "graphify-out",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    "vendor",
    "third_party",
    "tasks",
    ".self-improvement",
    "agent-memory",
}
_KEY = r"[a-z][a-z0-9_.-]{0,63}"
_DOC_FACT = re.compile(rf"^\s*<!--\s*holus:fact\s+({_KEY})\s*=\s*(.*?)\s*-->\s*$")
_CODE_FACT = re.compile(rf"^\s*#\s*holus:fact\s+({_KEY})\s*=\s*([A-Za-z_]\w*)\s*$")


def _hash(data: bytes | str) -> str:
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def _encoded(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _inventory(repo: Path) -> list[str]:
    try:
        proc = subprocess.run(
            [
                "git",
                "--no-optional-locks",
                "-c",
                "core.fsmonitor=false",
                "-C",
                str(repo),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        proc = None
    if proc and proc.returncode == 0:
        names = proc.stdout.split("\0")
    else:
        if (repo / ".git").exists():
            raise ValueError("Git inventory unavailable; ignore rules cannot be verified")
        names = []
        for base, dirs, files in os.walk(repo, followlinks=False):
            dirs[:] = sorted(
                d for d in dirs if d not in _EXCLUDED and not (Path(base) / d).is_symlink()
            )
            names.extend(str((Path(base) / f).relative_to(repo)) for f in sorted(files))
            if len(names) > 20_000:
                raise ValueError("inventory exceeds 20000 files")
    return sorted(
        {
            n
            for n in names
            if Path(n).suffix in {".py", ".md"}
            and not set(Path(n).parts) & _EXCLUDED
            and ((repo / n).is_symlink() or (repo / n).is_file())
        },
        key=lambda n: (0 if n.startswith("src/") else 1 if "/" not in n else 2, n),
    )


def _source(repo: Path, name: str) -> bytes:
    path = _safe_path(repo, name)
    if path is None or any(
        (repo / Path(*Path(name).parts[:i])).is_symlink()
        for i in range(1, len(Path(name).parts) + 1)
    ):
        raise ValueError("source path is unsafe or a symlink")
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("source exceeds byte budget")
    return data


def _occurrence(name: str, line: int, end: int, digest: str, unit: str) -> dict[str, Any]:
    return {"file": name, "line": line, "end_line": end, "source_hash": digest, "unit": unit}


def _scalar(node: ast.AST | None) -> Any:
    if isinstance(node, ast.Constant) and type(node.value) in {str, int, float, bool, type(None)}:
        _encoded(node.value)  # rejects NaN/infinity
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _scalar(node.operand)
        if type(value) in {int, float}:
            return -value if isinstance(node.op, ast.USub) else value
    raise ValueError("only scalar literal declarations can be verified")


def _written_names(node: ast.AST | None) -> set[str]:
    """Conservative syntactic binding invalidation, never data-flow execution."""
    if node is None:
        return set()
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        names = {node.name}
        headers = [*node.decorator_list, *getattr(node, "type_params", [])]
        if isinstance(node, ast.ClassDef):
            headers.extend([*node.bases, *node.keywords])
        else:
            headers.append(node.args)
            if node.returns:
                headers.append(node.returns)
        for header in headers:
            names |= _written_names(header)
        # Local bodies do not bind module names, but declared global mutation
        # makes those names unverifiable even if we never execute the function.
        for child in ast.walk(node):
            if isinstance(child, ast.Global):
                names.update(child.names)
        return names
    names = set()
    if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
        names.add(node.id)
    elif isinstance(node, ast.alias):
        names.add(node.asname or node.name.split(".")[0])  # '*' invalidates all facts
    elif isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)) and node.name:
        names.add(node.name)
    elif isinstance(node, ast.MatchMapping) and node.rest:
        names.add(node.rest)
    for child in ast.iter_child_nodes(node):
        names |= _written_names(child)
    return names


def _bindings(tree: ast.Module) -> dict[str, tuple[Any, int] | None]:
    """Only direct, unrebound module scalar declarations are supported."""
    result: dict[str, tuple[Any, int] | None] = {}
    invalid = set()
    for item in tree.body:
        if isinstance(item, (ast.Assign, ast.AnnAssign)):
            targets = item.targets if isinstance(item, ast.Assign) else [item.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    try:
                        value = (_scalar(item.value), item.lineno)
                    except (ValueError, RecursionError):
                        value = None
                    if target.id in result:
                        invalid.add(target.id)
                    result[target.id] = value
                else:
                    invalid |= _written_names(target)
            invalid |= _written_names(item.value)
            if isinstance(item, ast.AnnAssign):
                invalid |= _written_names(item.annotation)
        else:
            invalid |= _written_names(item)
    for name in set(result) if "*" in invalid else invalid:
        result[name] = None
    return result


class _Rename(ast.NodeTransformer):
    def __init__(self, mapping: dict[str, str]):
        self.mapping = mapping

    def visit_Name(self, node: ast.Name) -> ast.Name:
        if node.id in self.mapping:
            node.id = self.mapping[node.id]
        return node

    def visit_arg(self, node: ast.arg) -> ast.arg:
        node.arg = self.mapping.get(node.arg, node.arg)
        return node


def _fingerprints(function: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, str | None]:
    node = copy.deepcopy(function)
    node.name = "FUNCTION"
    if (
        node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    ):
        if isinstance(node.body[0].value.value, str):
            node.body = node.body[1:]
    exact = _hash(ast.dump(node, include_attributes=False))
    body_nodes = [sub for stmt in node.body for sub in ast.walk(stmt)]
    unsafe = (
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.Lambda,
        ast.ListComp,
        ast.SetComp,
        ast.DictComp,
        ast.GeneratorExp,
        ast.Global,
        ast.Nonlocal,
        ast.NamedExpr,
    )
    if any(isinstance(sub, unsafe) for sub in body_nodes):
        return exact, None
    locals_ = [arg.arg for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)]
    if node.args.vararg:
        locals_.append(node.args.vararg.arg)
    if node.args.kwarg:
        locals_.append(node.args.kwarg.arg)
    locals_.extend(
        sub.id for sub in body_nodes if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store)
    )
    # Never normalize externally bound names or attributes/literals/operators.
    mapping = {name: f"local_{i}" for i, name in enumerate(dict.fromkeys(locals_))}
    transformer = _Rename(mapping)
    node.body = [transformer.visit(statement) for statement in node.body]
    # Defaults, annotations and decorators resolve in outer scope; preserve them.
    for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
        arg.arg = mapping.get(arg.arg, arg.arg)
    for arg in (node.args.vararg, node.args.kwarg):
        if arg:
            arg.arg = mapping.get(arg.arg, arg.arg)
    return exact, _hash(ast.dump(node, include_attributes=False))


def _python(name: str, text: str, digest: str) -> tuple[list[dict], list[dict], list[dict]]:
    tree = ast.parse(text)
    nodes = list(ast.walk(tree))
    if len(nodes) > 20_000:
        raise ValueError("AST exceeds node budget")
    units, facts, skipped = [], [], []
    binding = _bindings(tree)
    for node in nodes:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if len(list(ast.walk(node))) < 20 or len(node.body) < 3:
                continue
            exact, renamed = _fingerprints(node)
            units.append(
                {
                    "kind": "code",
                    "exact": exact,
                    "renamed": renamed,
                    "occurrence": _occurrence(
                        name,
                        node.lineno,
                        node.end_lineno or node.lineno,
                        digest,
                        f"function:{node.name}:{node.lineno}",
                    ),
                }
            )
    source_lines = text.splitlines()
    nonmodule_ranges = [
        (node.lineno, node.end_lineno or node.lineno)
        for node in nodes
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    module_declarations = [
        (node.lineno, node.end_lineno or node.lineno)
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
    ]
    comments = (
        token
        for token in tokenize.generate_tokens(StringIO(text).readline)
        if token.type == tokenize.COMMENT
    )
    for token in comments:
        line, value = token.start[0], token.string
        match = _CODE_FACT.fullmatch(value)
        if not match:
            if re.match(r"^\s*#\s*holus:fact\b", value):
                skipped.append({"file": name, "line": line, "reason": "invalid fact marker"})
            continue
        key, symbol = match.groups()
        column = token.start[1]
        in_scope = any(start <= line <= end for start, end in nonmodule_ranges)
        inline_module_declaration = any(
            start <= line <= end for start, end in module_declarations
        ) and bool(source_lines[line - 1][:column].strip())
        if in_scope or (column and not inline_module_declaration):
            skipped.append(
                {
                    "file": name,
                    "line": line,
                    "reason": "fact marker is not a supported module-level reference",
                }
            )
            continue
        declared = binding.get(symbol)
        if declared is None:
            skipped.append(
                {
                    "file": name,
                    "line": line,
                    "reason": f"fact {key}: {symbol} is missing, dynamic or ambiguous",
                }
            )
            continue
        scalar, declaration_line = declared
        facts.append(
            {
                "key": key,
                "value": scalar,
                "kind": "code",
                "symbol": symbol,
                "declaration_line": declaration_line,
                "occurrence": _occurrence(name, line, line, digest, f"fact:{key}"),
            }
        )
    return units, facts, skipped


def _markdown(name: str, text: str, digest: str) -> tuple[list[dict], list[dict], list[dict]]:
    units, facts, skipped = [], [], []
    paragraph: list[tuple[int, str]] = []

    def flush() -> None:
        if not paragraph:
            return
        normalized = " ".join(" ".join(v for _, v in paragraph).split())
        words = re.findall(r"\b\w+\b", normalized.lower())
        if len(words) >= 30:
            exact = _hash(normalized)
            shingles = {tuple(words[i : i + 5]) for i in range(len(words) - 4)}
            units.append(
                {
                    "kind": "docs",
                    "exact": exact,
                    "shingles": shingles,
                    "occurrence": _occurrence(
                        name, paragraph[0][0], paragraph[-1][0], digest, f"paragraph:{exact}"
                    ),
                }
            )
        paragraph.clear()

    for line, value in _markdown_lines(text):
        if value is None:
            flush()
            continue
        stripped = value.lstrip()
        match = _DOC_FACT.fullmatch(value)
        if match:
            flush()
            key, raw = match.groups()
            try:
                scalar = json.loads(raw)
                if type(scalar) not in {str, int, float, bool, type(None)}:
                    raise ValueError("fact must be a JSON scalar")
                _encoded(scalar)
            except (ValueError, RecursionError):
                skipped.append({"file": name, "line": line, "reason": "invalid scalar fact"})
                continue
            facts.append(
                {
                    "key": key,
                    "value": scalar,
                    "kind": "docs",
                    "occurrence": _occurrence(name, line, line, digest, f"fact:{key}"),
                }
            )
        elif re.match(r"^<!--\s*holus:fact\b", stripped):
            flush()
            skipped.append({"file": name, "line": line, "reason": "invalid fact marker"})
        elif not stripped or stripped.startswith(("#", "<!--", "|")):
            flush()
        else:
            paragraph.append((line, value))
    flush()
    return units, facts, skipped


def _graph(repo: Path) -> tuple[dict[str, Any], dict[str, list[str]]]:
    try:
        graph = load_graph(repo)
        proof = provenance(repo, graph)
        proof["snapshot_hash"] = _hash(_encoded(graph))
        nodes = graph["nodes"]
        if isinstance(nodes, dict):
            nodes = [dict(value, id=key) for key, value in nodes.items() if isinstance(value, dict)]
        refs: dict[str, list[str]] = defaultdict(list)
        for node in nodes:
            if isinstance(node, dict) and isinstance(node.get("source_file"), str):
                if isinstance(node.get("id"), str):
                    refs[node["source_file"]].append(node["id"])
        return proof, refs
    except (OSError, ValueError, UnicodeError):
        return {"state": "unavailable", "reason": "no readable safe Graphify graph"}, {}


def align(
    repo_path: str | Path,
    *,
    scope: str | None = None,
    docs: bool = False,
    against: str | None = None,
) -> dict[str, Any]:
    repo = _repo_path(repo_path)
    if not repo.is_dir():
        raise ValueError(f"Not a directory: {repo}")
    names = _inventory(repo)
    focus = Focus(repo, scope, docs, allowed=names, excluded=_EXCLUDED)
    scope = focus.scope
    manifest, units, facts, skipped = {}, [], [], []
    total = 0
    for index, name in enumerate(names):
        if index >= MAX_FILES or total >= MAX_TOTAL_BYTES or len(units) >= MAX_UNITS:
            skipped.append({"reason": "scan budget exceeded"})
            break
        try:
            data = _source(repo, name)
            if total + len(data) > MAX_TOTAL_BYTES:
                skipped.append({"reason": "total source byte budget exceeded"})
                break
            digest = _hash(data)
            manifest[name] = digest
            total += len(data)
            text = data.decode("utf-8")
            source_units, source_facts, source_skipped = (
                _python(name, text, digest)
                if name.endswith(".py")
                else _markdown(name, text, digest)
            )
            if len(units) + len(source_units) > MAX_UNITS:
                skipped.append({"reason": "unit budget exceeded", "file": name})
            if len(facts) + len(source_facts) > MAX_FACTS:
                skipped.append({"reason": "fact budget exceeded", "file": name})
            units.extend(source_units[: MAX_UNITS - len(units)])
            facts.extend(source_facts[: MAX_FACTS - len(facts)])
            skipped.extend(source_skipped)
        except (OSError, ValueError, UnicodeError, SyntaxError, RecursionError) as exc:
            skipped.append({"file": name, "reason": f"source unverified: {type(exc).__name__}"})
    graph, refs = _graph(repo)
    findings: list[dict[str, Any]] = []

    def finding(kind: str, key: str, occurrences: list[dict], **extra: Any) -> None:
        if focus.filtered:
            anchors = [o for o in occurrences if focus.matches(o["file"])]
            if not anchors:
                return
            # Always retain the focus anchor even when partner locations are bounded.
            occurrences = anchors + [o for o in occurrences if not focus.matches(o["file"])]
        locations = []
        for occurrence in occurrences[:30]:
            locations.append(
                {**occurrence, "graph_nodes": sorted(refs.get(occurrence["file"], []))[:5]}
            )
        findings.append(
            {
                "id": _hash(kind + ":" + key)[:24],
                "type": kind,
                "locations": locations,
                "location_count": len(occurrences),
                "locations_truncated": len(occurrences) > len(locations),
                **extra,
            }
        )

    for kind, field in (("code", "exact"), ("code", "renamed"), ("docs", "exact")):
        groups: dict[str, list[dict]] = defaultdict(list)
        for unit in units:
            if unit["kind"] == kind and unit.get(field):
                groups[unit[field]].append(unit)
        for digest, group in sorted(groups.items()):
            if len(group) < 2:
                continue
            if field == "renamed" and len({u["exact"] for u in group}) == 1:
                continue  # already reported as exact structure
            finding(
                f"{kind}_duplicate",
                field + ":" + digest,
                [u["occurrence"] for u in group],
                severity="candidate",
                method=f"{kind}_{field}",
                similarity=1.0,
                action="inspect shared ownership and intentional differences before consolidating",
            )

    # Hash-bucket exact copies first, then compare only paragraph groups sharing
    # a five-word shingle. Disjoint groups cannot meet the Jaccard threshold.
    doc_groups: dict[str, list[dict]] = defaultdict(list)
    for unit in units:
        if unit["kind"] == "docs":
            doc_groups[unit["exact"]].append(unit)
    doc_units = [group[0] for _, group in sorted(doc_groups.items())]
    postings: dict[tuple[str, ...], list[int]] = defaultdict(list)
    pairs: set[tuple[int, int]] = set()
    over_budget = False
    for i, doc in enumerate(doc_units):
        for shingle in sorted(doc["shingles"]):
            for j in postings[shingle]:
                pairs.add((j, i))
                if len(pairs) > MAX_PAIRS:
                    over_budget = True
                    break
            postings[shingle].append(i)
            if over_budget:
                break
        if over_budget:
            skipped.append({"reason": "documentation comparison budget exceeded"})
            break
    for i, j in sorted(pairs)[:MAX_PAIRS]:
        left, right = doc_units[i], doc_units[j]
        union = left["shingles"] | right["shingles"]
        similarity = len(left["shingles"] & right["shingles"]) / len(union)
        if similarity >= 0.85:
            finding(
                "docs_similar",
                ":".join(sorted([left["exact"], right["exact"]])),
                [
                    u["occurrence"]
                    for key in (left["exact"], right["exact"])
                    for u in doc_groups[key]
                ],
                severity="candidate",
                method="five_word_shingle_jaccard",
                similarity=round(similarity, 4),
                action="inspect overlap; similarity alone does not prove duplication",
            )

    by_key: dict[str, list[dict]] = defaultdict(list)
    for fact in facts:
        by_key[fact["key"]].append(fact)
    for key, declarations in sorted(by_key.items()):
        if len({_encoded(f["value"]) for f in declarations}) < 2:
            continue
        finding(
            "alignment_mismatch",
            key,
            [f["occurrence"] for f in declarations],
            severity="error",
            fact=key,
            declarations=[{k: v for k, v in f.items() if k != "occurrence"} for f in declarations],
            action="align the explicitly linked declarations; prose itself is not verified",
        )

    # Check inputs again, including additions/deletions. Never return a complete
    # current-source receipt when edits occurred during scanning.
    changed = _inventory(repo) != names
    for name, digest in manifest.items():
        try:
            changed |= _hash(_source(repo, name)) != digest
        except (OSError, ValueError):
            changed = True
    graph_after, _ = _graph(repo)
    graph_changed = any(
        graph_after.get(key) != graph.get(key)
        for key in (
            "snapshot_hash",
            "state",
            "head_commit",
            "head_commit_before",
            "built_at_commit",
        )
    )
    changed |= graph_changed
    graph = graph_after
    if graph_changed:
        graph = {
            **graph,
            "state": "unknown",
            "reason": "Graph or revision evidence changed during scan",
        }
    findings.sort(key=lambda f: (f["severity"] != "error", f["type"], f["id"]))
    errors = sum(f["severity"] == "error" for f in findings)
    focused_files = sum(focus.matches(name) for name in manifest)
    complete = not skipped and not changed and (not focus.filtered or focused_files > 0)
    status = (
        "unknown"
        if changed
        else "partial"
        if not complete
        else "unavailable"
        if not manifest
        else "mismatch"
        if errors
        else "review"
        if findings
        else "ok"
    )
    identity = {
        "schema": SCHEMA,
        "rules": RULES,
        "python": platform.python_version(),
        "repo": str(repo),
        "scope": scope,
        "docs": docs,
    }
    result = {
        **identity,
        "status": status,
        "complete": complete,
        "selector": focus.describe(),
        "graph": graph,
        "source_snapshot": _hash(_encoded(manifest)),
        "sources": manifest,
        "coverage": {
            "files": len(manifest),
            "units": len(units),
            "facts": len(facts),
            "graph_mapped_files": len(set(manifest) & refs.keys()),
            "focused_files": focused_files,
        },
        "errors": errors,
        "candidates": len(findings) - errors,
        "findings": findings[:100],
        "truncated": len(findings) > 100,
        "finding_ids": [f["id"] for f in findings],
        "skipped": skipped[:100],
        "skipped_count": len(skipped),
        "inputs_changed_during_scan": changed,
        "notes": "Source scan is separate from graph freshness. Candidates need agent review; "
        "unlinked prose and runtime behavior are not verified. Rerun after edits.",
    }
    if against:
        path = _safe_path(repo, against)
        if path is None or path.stat().st_size > 2_000_000:
            raise ValueError("baseline must be a bounded report inside the repository")
        prior = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(prior, dict) or any(
            prior.get(k) != v for k, v in identity.items() if k != "docs"
        ):
            raise ValueError("baseline repository, scope or analyzer is incompatible")
        # Existing complete v2 all/file receipts have identical analysis semantics.
        # New selectors must match exactly; a file becoming a directory is not comparable.
        if prior.get("docs", False) is not docs or (
            prior.get("selector") != focus.describe()
            if "selector" in prior
            else docs or focus.kind == "directory"
        ):
            raise ValueError("baseline selector is incompatible")
        if prior.get("complete") is not True or not complete:
            raise ValueError("partial/unknown scans cannot establish resolved findings")
        previous_ids = prior.get("finding_ids")
        previous_sources = prior.get("sources")
        if (
            not isinstance(previous_ids, list)
            or not all(
                isinstance(v, str) and re.fullmatch(r"[0-9a-f]{24}", v) for v in previous_ids
            )
            or not isinstance(previous_sources, dict)
            or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in previous_sources.items()
            )
            or prior.get("source_snapshot") != _hash(_encoded(previous_sources))
        ):
            raise ValueError("baseline has invalid finding IDs or input manifest")
        old, new = set(previous_ids), set(result["finding_ids"])
        result["delta"] = {
            "new": sorted(new - old),
            "resolved": sorted(old - new),
            "persisting": sorted(old & new),
            "changed_sources": sorted(
                k
                for k in set(manifest) | set(previous_sources)
                if manifest.get(k) != previous_sources.get(k)
            ),
            "notes": "Resolved means no longer detected, not proof of behavioral repair.",
        }
    return result
