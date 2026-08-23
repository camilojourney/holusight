"""``holus`` - the Holusight-AXI job-oriented command surface.

Implements the smallest stable command surface from
``specs/011-holusight-product-architecture-research.md`` ("holus-axi") and
``specs/015-holusight-axi-command-surface.md``:

    holus                       content-first repository home view
    holus evidence "<question>" routed evidence packet
    holus check [scope]         post-change consistency check
    holus status                repository/provider status
    holus providers             provider availability/freshness/egress

Provider selection (``--mode``, ``--provider``, ``--explain-route``) is a
diagnostic flag *beneath* these five jobs, not a parallel API - see
:mod:`codesight.axi_providers`. Every job wraps already-landed production
code (:mod:`codesight.consistency`, :mod:`codesight.search`); this module
adds routing, argument parsing, and output projection only.

Follows the installed AXI skill (``~/.claude/skills/axi/SKILL.md``):
JSON is the lossless canonical payload; ``--format toon`` (default) and
``--format text`` are projections of the same payload at the output
boundary. Unknown flags/commands are rejected (exit 2) rather than
silently ignored. Structured errors go to stdout. Exit codes: 0 = success
(including definitive empty/no-evidence answers), 1 = runtime error,
2 = usage error.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import sys
import time
from collections import Counter
from enum import Enum
from pathlib import Path
from typing import Any

from . import axi_providers, consistency
from .axi_schema import AXI_COMMANDS, AXI_SCHEMA_VERSION, AxiCommand, command_by_name
from .control_storage import (
    RESULTS_ROOT,
    UnsafeStoragePath,
    safe_atomic_write,
    validate_output_path,
)
from .toon import to_toon

logger = logging.getLogger(__name__)

_JOB_NAMES = {
    "",
    "evidence",
    "check",
    "status",
    "providers",
    "improve-status",
    "improve-intake",
    "improve-run",
    "improve-placement",
    "improve-review",
    "improve-history",
    "improve-integration",
}
_MAX_DISPLAY_ITEMS = 20
_MAX_DISPLAY_CONCEPTS = 20


# ---------------------------------------------------------------------------
# Control-flow exceptions
# ---------------------------------------------------------------------------


class UsageError(Exception):
    """Raised for anything AXI section 6 calls a usage error: unknown
    command/flag, missing required argument, invalid flag value. Always
    exit code 2."""

    def __init__(self, message: str, help_text: str = "", format: str = "toon") -> None:
        super().__init__(message)
        self.message = message
        self.help_text = help_text
        self.format = format


class _HelpRequested(Exception):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.text = text


# ---------------------------------------------------------------------------
# Flag parsing (schema-driven - see axi_schema.AXI_COMMANDS)
# ---------------------------------------------------------------------------


def _split_command(argv: list[str]) -> tuple[str, list[str]]:
    if not argv:
        return "", argv
    first = argv[0]
    if first in _JOB_NAMES:
        return first, argv[1:]
    if first.startswith("-"):
        return "", argv
    raise UsageError(
        f"unknown command {first!r}",
        help_text=_top_level_help_text(),
    )


def _parse_command_args(cmd: AxiCommand, argv: list[str]) -> tuple[dict[str, Any], list[str]]:
    valid_names = {f.name for f in cmd.flags}
    values: dict[str, Any] = {f.name: (f.default if f.takes_value else False) for f in cmd.flags}
    positionals: list[str] = []

    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok.startswith("--"):
            name, has_eq, inline_value = tok.partition("=")
            if name not in valid_names:
                raise UsageError(
                    f"unknown flag {name} for `holus{' ' + cmd.name if cmd.name else ''}`",
                    help_text=_command_help_text(cmd),
                )
            flag = next(f for f in cmd.flags if f.name == name)
            if name == "--help":
                raise _HelpRequested(_command_help_text(cmd))
            if not flag.takes_value:
                if has_eq:
                    raise UsageError(
                        f"{name} does not take a value", help_text=_command_help_text(cmd)
                    )
                values[name] = True
                i += 1
                continue
            if has_eq:
                value = inline_value
                i += 1
            else:
                if i + 1 >= len(argv):
                    raise UsageError(f"{name} requires a value", help_text=_command_help_text(cmd))
                value = argv[i + 1]
                i += 2
            if flag.choices and value not in flag.choices:
                raise UsageError(
                    f"invalid value {value!r} for {name}; choices: {', '.join(flag.choices)}",
                    help_text=_command_help_text(cmd),
                )
            values[name] = value
            continue
        positionals.append(tok)
        i += 1

    return values, positionals


# ---------------------------------------------------------------------------
# Help text
# ---------------------------------------------------------------------------


def _bin_path() -> str:
    exe = shutil.which("holus")
    path = Path(exe).resolve() if exe else Path(sys.argv[0]).resolve()
    try:
        home = Path.home()
        if path.is_relative_to(home):
            return "~/" + str(path.relative_to(home))
    except (ValueError, OSError):
        pass
    return str(path)


def _top_level_help_text() -> str:
    lines = [
        f"bin: {_bin_path()}",
        "description: Agent-facing repository evidence CLI for this Holusight-tracked repo.",
        "",
        "commands:",
    ]
    for cmd in AXI_COMMANDS:
        label = cmd.usage
        lines.append(f"  {label:<45} {cmd.description}")
    lines.append("")
    lines.append("Run `holus <command> --help` for that command's full reference.")
    return "\n".join(lines)


def _command_help_text(cmd: AxiCommand) -> str:
    lines = [f"usage: {cmd.usage}", "", cmd.description, ""]
    if cmd.flags:
        lines.append("flags:")
        for f in cmd.flags:
            choice_str = f" ({'/'.join(f.choices)})" if f.choices else ""
            default_str = f" [default: {f.default}]" if f.default else ""
            lines.append(f"  {f.name}{choice_str}{default_str}  {f.help}")
        lines.append("")
    if cmd.examples:
        lines.append("examples:")
        for ex in cmd.examples:
            lines.append(f"  {ex}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Rendering: json (canonical) / toon (agent default) / text (human)
# ---------------------------------------------------------------------------


def _scalar_text(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _text_lines(obj: Any, indent: int) -> list[str]:
    pad = "  " * indent
    lines: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, dict) and value:
                lines.append(f"{pad}{key}:")
                lines.extend(_text_lines(value, indent + 1))
            elif isinstance(value, list) and value:
                lines.append(f"{pad}{key}:")
                lines.extend(_text_lines(value, indent + 1))
            elif isinstance(value, (dict, list)):
                lines.append(f"{pad}{key}: (none)")
            else:
                lines.append(f"{pad}{key}: {_scalar_text(value)}")
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}-")
                lines.extend(_text_lines(item, indent + 1))
            else:
                lines.append(f"{pad}- {_scalar_text(item)}")
    return lines


def _render(payload: dict, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(payload, indent=2)
    if fmt == "toon":
        return to_toon(payload).rstrip("\n")
    if fmt == "text":
        return "\n".join(_text_lines(payload, 0))
    raise ValueError(f"unsupported format: {fmt!r}")


def _public_error_message(message: str) -> str:
    """Keep host paths and secrets out of public error payloads."""
    message = re.sub(r"(?:/[^\s:'\"]+)+", "<redacted-path>", message)
    return message


def _requested_format(argv: list[str]) -> str:
    for index, value in enumerate(argv):
        if value.startswith("--format="):
            return (
                value.partition("=")[2]
                if value.partition("=")[2] in {"json", "toon", "text"}
                else "toon"
            )
        if (
            value == "--format"
            and index + 1 < len(argv)
            and argv[index + 1] in {"json", "toon", "text"}
        ):
            return argv[index + 1]
    return "toon"


def _error_payload(code: str, message: str, help_text: str | list[str] = "") -> dict:
    payload: dict[str, Any] = {
        "schema_version": AXI_SCHEMA_VERSION,
        "error": {"code": code, "message": message},
    }
    if help_text:
        payload["help"] = help_text.splitlines() if isinstance(help_text, str) else list(help_text)
    return payload


# ---------------------------------------------------------------------------
# --fields projection
# ---------------------------------------------------------------------------

_MISSING = object()


def _group_by_head(paths: list[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for path in paths:
        head, _, rest = path.partition(".")
        groups.setdefault(head, []).append(rest)
    return groups


def _project_value(value: Any, subpaths: list[str]) -> Any:
    if isinstance(value, dict):
        return _project_dict(value, _group_by_head(subpaths))
    return value


def _project_dict(obj: dict, groups: dict[str, list[str]]) -> dict:
    result: dict[str, Any] = {}
    for key, subpaths in groups.items():
        if key not in obj:
            continue
        value = obj[key]
        if any(sp == "" for sp in subpaths):
            result[key] = value
            continue
        if isinstance(value, list):
            result[key] = [_project_value(item, subpaths) for item in value]
        elif isinstance(value, dict):
            result[key] = _project_value(value, subpaths)
        else:
            result[key] = value
    return result


def project_fields(payload: dict, field_paths: list[str]) -> dict:
    """Dotted-path projection over a JSON-shaped payload (spec 011's
    ``--fields snapshot,evidence.source,evidence.location`` example)."""
    return _project_dict(payload, _group_by_head(field_paths))


def _apply_fields(payload: dict, fields_arg: str | None) -> dict:
    if not fields_arg:
        return payload
    field_paths = [f.strip() for f in fields_arg.split(",") if f.strip()]
    if not field_paths:
        return payload
    projected = project_fields(payload, field_paths)
    projected.setdefault("schema_version", payload.get("schema_version", AXI_SCHEMA_VERSION))
    return projected


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _public_path(repo_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except (ValueError, OSError):
        return "external-corpus"


def _snapshot(repo_root: Path) -> tuple[str | None, bool]:
    from .git_utils import current_commit, is_git_repo

    head = current_commit(repo_root) if is_git_repo(repo_root) else None
    dirty = consistency._is_dirty(repo_root) if head else False
    return head, dirty


def _ensure_cache_bootstrapped(repo_root: Path) -> None:
    """Refresh the consistency cache exactly once, only if it has never
    been built. Never re-refreshes an existing cache - that would erase
    the very drift baseline `check` exists to detect."""
    db_path = consistency.consistency_db_path(repo_root)
    if db_path.exists():
        return
    try:
        consistency.refresh(repo_root, run_semantic=False)
    except Exception:
        logger.debug("bootstrap refresh failed", exc_info=True)


def _claims_summary(repo_root: Path) -> dict[str, int]:
    db_path = consistency.consistency_db_path(repo_root)
    if not db_path.exists():
        return {"pass": 0, "fail": 0, "unknown": 0}
    from .consistency_store import ConsistencyStore

    store = ConsistencyStore(db_path)
    try:
        claims = store.all_claims()
    finally:
        store.close()
    summary = {"pass": 0, "fail": 0, "unknown": 0}
    for c in claims:
        if c["status"] == "match":
            summary["pass"] += 1
        elif c["status"] == "drift":
            summary["fail"] += 1
        else:
            summary["unknown"] += 1
    return summary


def _health_flags_summary(repo_root: Path) -> dict[str, int]:
    db_path = consistency.consistency_db_path(repo_root)
    if not db_path.exists():
        return {"info": 0, "warning": 0, "high": 0, "total": 0}
    from .consistency_store import ConsistencyStore

    store = ConsistencyStore(db_path)
    try:
        flags = store.all_health_flags()
    finally:
        store.close()
    summary = {"info": 0, "warning": 0, "high": 0}
    for f in flags:
        summary[f["severity"]] = summary.get(f["severity"], 0) + 1
    summary["total"] = len(flags)
    return summary


def _resolve_concept(repo_root: Path, scope: str) -> tuple[str | None, list[str]]:
    """Resolve a `check` scope argument to a concept_id. Returns
    (concept_id_or_None, candidate_suggestions)."""
    db_path = consistency.consistency_db_path(repo_root)
    if not db_path.exists():
        return None, []
    from .consistency_store import ConsistencyStore

    store = ConsistencyStore(db_path)
    try:
        concepts = store.all_concepts()
    finally:
        store.close()

    for c in concepts:
        if c["concept_id"] == scope or c["canonical_path"] == scope:
            return c["concept_id"], []

    needle = scope.lower()
    candidates = [
        c["concept_id"]
        for c in concepts
        if needle in c["concept_id"].lower() or needle in c["scope"].lower()
    ]
    return None, candidates


def _read_structure_rules(repo_root: Path) -> str:
    paths = [
        repo_root / ".claude" / "rules" / "structure.md",
        repo_root / "AGENTS.md",
    ]
    for path in paths:
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise UsageError(
        "structure rules file is missing",
        help_text="Repository placement checks cannot run safely.",
    )


def _artifact_type_roots(artifact_type: str) -> tuple[str, ...]:
    return {
        "case": ("tests/fixtures",),
        "fixture": ("tests/fixtures",),
        "test": ("tests",),
        "spec": ("specs",),
        "adr": ("docs/decisions",),
        "decision": ("docs/decisions",),
        "playbook": ("docs/playbooks",),
        "source": ("src/codesight",),
        "skill": (".claude/skills",),
        "agent": (".claude/agents",),
        "docs": ("docs",),
    }[artifact_type]


# `.claude/rules/structure.md` states "specs/" is "Flat structure only. No
# subdirectories." for artifact types placed directly under it.
_FLAT_ONLY_ARTIFACT_TYPES = frozenset({"spec"})

# `.claude/rules/structure.md` states docs/ has "Exactly four categories --
# no others" and explicitly forbids ad-hoc files at the docs/ root (the
# `docs/RESEARCH.md`/`docs/MARKET.md` legacy violations it calls out by
# name). `adr`/`decision`/`playbook` cover the two subdirectory categories;
# the generic "docs" artifact type may only ever propose one of the two
# remaining fixed top-level files.
_FIXED_DOCS_ROOT_FILES = frozenset({"docs/README.md", "docs/vision.md", "docs/roadmap.md"})

# `.claude/rules/structure.md` states "tests/test_*.py" is the filename
# convention for the `test` artifact type, placed directly under `tests/`
# (not `tests/fixtures/`, which is its own `case`/`fixture` artifact type).
_TEST_FILENAME_PATTERN = "test_*.py"


def _safe_repo_relative_path(repo_root: Path, raw_path: str) -> Path | None:
    """Resolve ``raw_path`` to a path strictly inside ``repo_root``, or
    ``None`` if it is empty, absolute, or escapes the repository (``..``).

    Every filesystem check placement evidence performs (``.exists()``,
    duplicate-name scans, canonical-location membership) must go through
    this guard first -- an absolute or traversal-crafted ``--proposed-path``
    must never cause a stat/read against the real host filesystem outside
    this repository, even for a read-only existence check."""
    proposed = Path(raw_path)
    if not str(raw_path).strip() or str(proposed) == "." or proposed.is_absolute():
        return None
    if ".." in proposed.parts:
        return None
    normalized = (repo_root / proposed).resolve()
    repo = repo_root.resolve()
    if not normalized.is_relative_to(repo):
        return None
    return normalized.relative_to(repo)


def _proposed_path_within_canonical_location(
    repo_root: Path, artifact_type: str, raw_path: str
) -> bool:
    safe = _safe_repo_relative_path(repo_root, raw_path)
    if safe is None:
        return False
    relative = str(safe).replace("\\", "/")

    if artifact_type == "docs":
        return relative in _FIXED_DOCS_ROOT_FILES

    roots = _artifact_type_roots(artifact_type)
    in_root = any(relative == root or relative.startswith(root.rstrip("/") + "/") for root in roots)
    if not in_root:
        return False

    if artifact_type in _FLAT_ONLY_ARTIFACT_TYPES:
        # Exactly one path segment below the root -- no subdirectories.
        if Path(relative).parent != Path(roots[0]):
            return False

    if artifact_type == "case" and Path(relative).suffix != ".jsonl":
        return False

    if artifact_type == "test":
        if Path(relative).parent != Path(roots[0]):
            return False
        import fnmatch

        if not fnmatch.fnmatch(Path(relative).name, _TEST_FILENAME_PATTERN):
            return False

    return True


def _find_duplicate_artifacts(repo_root: Path, artifact_type: str, raw_path: str) -> list[str]:
    proposed = Path(raw_path)
    target_name = proposed.name
    if not target_name:
        return []
    roots = [repo_root / root for root in _artifact_type_roots(artifact_type)]
    hits: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for candidate in root.rglob("*"):
            if not candidate.is_file():
                continue
            if candidate.name == target_name and candidate.name != (repo_root / proposed).name:
                try:
                    hits.append(str(candidate.relative_to(repo_root)))
                except ValueError:
                    pass
    return sorted(set(hits))[:8]


def _recommended_new_path(repo_root: Path, root: str, base_path: Path) -> str:
    """Compute an available path under ``root`` for a proposed artifact.

    Read-only: this only inspects existing paths to steer clear of a name
    collision. It never creates a directory or file -- placement checks
    must never edit the repository.
    """
    fallback_root = repo_root / root
    stem = base_path.stem or "proposed-artifact"
    suffix = base_path.suffix or ".txt"
    candidate = Path(f"{stem}{suffix}")

    counter = 1
    while (fallback_root / candidate).exists():
        candidate = Path(f"{stem}-{counter}{suffix}")
        counter += 1
    return str(Path(root) / candidate)


def _placement_recommendation(repo_root: Path, artifact_type: str, raw_path: str) -> dict[str, Any]:
    structure_text = _read_structure_rules(repo_root)
    allowed_roots = _artifact_type_roots(artifact_type)
    safe_relative = _safe_repo_relative_path(repo_root, raw_path)
    # An absolute or repo-escaping --proposed-path must never reach a
    # filesystem check against anything outside this repository -- not
    # even a read-only .exists()/.is_dir() probe.
    if safe_relative is not None and (repo_root / safe_relative).is_dir():
        raise ValueError("proposed-path must point to a file")

    in_canonical = _proposed_path_within_canonical_location(repo_root, artifact_type, raw_path)
    duplicates = _find_duplicate_artifacts(repo_root, artifact_type, raw_path)
    if artifact_type == "docs":
        canonical_locations: tuple[str, ...] = tuple(sorted(_FIXED_DOCS_ROOT_FILES))
        canonical_hits = [
            path for path in canonical_locations if path.rsplit("/", 1)[-1] in structure_text
        ]
    else:
        canonical_locations = allowed_roots
        canonical_hits = [
            root
            for root in allowed_roots
            if f"`{root}`" in structure_text or f"{root}/" in structure_text
        ]

    guidance: str | None = None
    if in_canonical:
        recommendation: str | None = str(Path(raw_path))
    elif artifact_type == "docs":
        # docs/ is not an open-ended bucket -- `.claude/rules/structure.md`
        # names exactly four categories and forbids ad-hoc files at its
        # root. There is no safe auto-generated fallback path here; the
        # caller needs to pick a different artifact type instead.
        recommendation = None
        guidance = (
            "docs/ only holds README.md, vision.md, roadmap.md, "
            "docs/decisions/*, and docs/playbooks/*; propose this artifact "
            "with --artifact-type adr, decision, playbook, or spec instead"
        )
    else:
        fallback_root = Path(allowed_roots[0])
        fallback_name = Path(raw_path).name or f"{artifact_type}-proposal"
        if artifact_type == "test" and not fallback_name.startswith("test_"):
            fallback_name = f"test_{fallback_name}"
        recommendation = _recommended_new_path(repo_root, str(fallback_root), Path(fallback_name))

    exists = safe_relative is not None and (repo_root / safe_relative).exists()
    if exists and str(Path(raw_path)) not in duplicates:
        duplicates.append(str(Path(raw_path)))
    duplicates = sorted(set(duplicates))

    result = {
        "artifact_type": artifact_type,
        "proposed_path": str(Path(raw_path)),
        "canonical_locations": canonical_locations,
        "canonical_roots_documented": canonical_hits,
        "in_canonical_location": in_canonical,
        "duplicate_hits": duplicates,
        "recommended_path": recommendation,
        "proposed_file_exists": exists,
    }
    if guidance is not None:
        result["guidance"] = guidance
    return result


def _intake_status_payload(repo_root: Path, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": AXI_SCHEMA_VERSION,
        "lifecycle": {
            "command": "improve-intake",
            "status": result["intake_policy"]["status"],
            "content_minimized": result["intake_policy"]["content_minimized"],
        },
        "intake": result["intake"],
        "intake_policy": result["intake_policy"],
    }


# ---------------------------------------------------------------------------
# Job handlers - each returns (payload, exit_code)
# ---------------------------------------------------------------------------


def _reject_extra_positionals(cmd_name: str, positionals: list[str]) -> None:
    if positionals:
        cmd = command_by_name(cmd_name)
        suffix = f" {cmd_name}" if cmd_name else ""
        raise UsageError(
            f"unexpected argument {positionals[0]!r} for `holus{suffix}`",
            help_text=_command_help_text(cmd),
        )


def _cmd_home(repo_root: Path, values: dict, positionals: list[str]) -> tuple[dict, int]:
    _reject_extra_positionals("", positionals)
    _ensure_cache_bootstrapped(repo_root)
    head, dirty = _snapshot(repo_root)
    statuses = axi_providers.provider_statuses(repo_root)
    claims = _claims_summary(repo_root)
    any_egress_capable = any(s.egress != "none" for s in statuses)

    payload: dict[str, Any] = {
        "schema_version": AXI_SCHEMA_VERSION,
        "bin": _bin_path(),
        "description": "Agent-facing repository evidence CLI for this Holusight-tracked repo.",
        "repo": repo_root.name,
        "snapshot": {"commit": head, "dirty": dirty},
        "egress": "available" if any_egress_capable else "off",
        "providers": [
            {"name": s.name, "available": s.available, "freshness": s.freshness} for s in statuses
        ],
        "contracts": claims,
        "help": [
            'Run `holus evidence "<question>"` for repository evidence.',
            "Run `holus check` to verify all tracked concepts.",
            "Run `holus status` for full provider/freshness detail.",
            "Run `holus --help` for all commands.",
        ],
    }
    return payload, 0


def _cmd_status(repo_root: Path, values: dict, positionals: list[str]) -> tuple[dict, int]:
    _reject_extra_positionals("status", positionals)
    _ensure_cache_bootstrapped(repo_root)
    head, dirty = _snapshot(repo_root)
    statuses = axi_providers.provider_statuses(repo_root)
    payload: dict[str, Any] = {
        "schema_version": AXI_SCHEMA_VERSION,
        "snapshot": {"commit": head, "dirty": dirty},
        "providers": [s.model_dump() for s in statuses],
        "contracts": _claims_summary(repo_root),
        "health_flags": _health_flags_summary(repo_root),
    }
    return _apply_fields(payload, values.get("--fields")), 0


def _cmd_providers(repo_root: Path, values: dict, positionals: list[str]) -> tuple[dict, int]:
    _reject_extra_positionals("providers", positionals)
    _ensure_cache_bootstrapped(repo_root)
    statuses = axi_providers.provider_statuses(repo_root)
    payload = {
        "schema_version": AXI_SCHEMA_VERSION,
        "providers": [s.model_dump() for s in statuses],
    }
    return payload, 0


def _cmd_improve_status(repo_root: Path, values: dict, positionals: list[str]) -> tuple[dict, int]:
    from . import eval_pilot

    _reject_extra_positionals("improve-status", positionals)
    cases_path = values.get("--cases") or str(eval_pilot.DEFAULT_CASES_PATH)
    path = Path(cases_path)
    if not path.exists():
        raise UsageError(
            f"cases file not found: {cases_path}",
            help_text="Pass --cases with an existing JSONL file.",
        )
    cases = eval_pilot.load_cases(path)
    origins = Counter(case["provenance"]["origin"] for case in cases)
    types = Counter(case["kind"] for case in cases)
    comparative = types["comparative"]
    corpus_trust = (
        "canonical" if eval_pilot._is_canonical_cases(path, repo_root) else "untrusted_advisory"
    )
    payload = {
        "schema_version": AXI_SCHEMA_VERSION,
        "lifecycle": {
            "command": "improve-status",
            "status_quo_control": "included" if comparative > 0 else "not_applicable",
            "cases_file": _public_path(repo_root, path),
            "cases_file_hash": eval_pilot.cases_file_hash(path),
            "canonical_case_schema": eval_pilot.SCHEMA_CASE,
            "corpus_trust": corpus_trust,
        },
        "coverage": {
            "cases_total": len(cases),
            "provenance_origins": dict(origins),
            "kind_distribution": dict(types),
            "comparative_cases": comparative,
            "status_quo_supported": comparative > 0,
        },
        "placement_support": {
            "canonical_paths_documented_in_structure": list(
                dict.fromkeys(_artifact_type_roots("case") + _artifact_type_roots("fixture"))
            ),
            "placement_checks_available": True,
            "requires_human_review_for_creation": True,
        },
    }
    return _apply_fields(payload, values.get("--fields")), 0


def _cmd_improve_intake(repo_root: Path, values: dict, positionals: list[str]) -> tuple[dict, int]:
    from . import eval_pilot

    cmd = command_by_name("improve-intake")
    if not positionals:
        raise UsageError(
            'missing required argument "summary" for `holus improve-intake`',
            help_text=_command_help_text(cmd),
        )
    summary = " ".join(positionals)

    try:
        result = eval_pilot.build_intake_proposal(
            summary,
            origin=values.get("--origin") or "reproduced_usage_gap",
            kind=values.get("--kind") or "regression",
            diagnosis_ref=values.get("--diagnosis-ref"),
            fix_ref=values.get("--fix-ref"),
            cases_path=Path(values["--cases"]) if values.get("--cases") else None,
            admitted_by=values.get("--admitted-by"),
            admitted_at=values.get("--admitted-at"),
            case_id=values.get("--case-id"),
        )
    except ValueError as exc:
        raise UsageError(str(exc), help_text=_command_help_text(cmd)) from exc
    return _intake_status_payload(repo_root, result), 0


def _cmd_improve_run(repo_root: Path, values: dict, positionals: list[str]) -> tuple[dict, int]:
    from . import eval_pilot
    from .git_utils import current_commit, is_git_repo

    _reject_extra_positionals("improve-run", positionals)
    cases_path = Path(values.get("--cases") or str(eval_pilot.DEFAULT_CASES_PATH))
    compare_path_raw = values.get("--compare-result")
    candidate_id = values.get("--candidate-id") or "current-worktree"
    if not cases_path.exists():
        raise UsageError(
            f"cases file not found: {cases_path}",
            help_text="Pass --cases with an existing JSONL file.",
        )
    try:
        previous = None
        if compare_path_raw:
            compare_path = validate_output_path(
                repo_root, Path(compare_path_raw), allowed_repo_root=RESULTS_ROOT
            )
            previous = eval_pilot.load_prior_run(compare_path)
    except (ValueError, OSError, json.JSONDecodeError, UnsafeStoragePath) as exc:
        raise UsageError(f"invalid comparison result: {exc}") from exc
    repo_commit = current_commit(repo_root) if is_git_repo(repo_root) else None
    workflow = values.get("--workflow") or "manual"
    tool = values.get("--tool") or "holus-cli"
    try:
        for label, value in (
            ("candidate_id", candidate_id),
            ("workflow", workflow),
            ("tool", tool),
        ):
            eval_pilot._validate_identifier(label, value)
        if values.get("--model") is not None:
            eval_pilot._validate_identifier("model", values["--model"])
    except ValueError as exc:
        raise UsageError(str(exc)) from exc
    lineage = eval_pilot.CandidateLineage(
        candidate_id=candidate_id,
        repo_commit=repo_commit,
        workflow=workflow,
        tool=tool,
        model=values.get("--model"),
    )
    try:
        result = eval_pilot.run_pilot(
            repo_root,
            cases_path=cases_path,
            lineage=lineage,
            allow_egress=bool(values.get("--allow-egress")),
            allow_semantic=bool(values.get("--allow-semantic")),
        )
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise UsageError(f"invalid case corpus: {exc}") from exc
    progress = eval_pilot.evaluate_progress(result, previous)

    run_payload = result.model_dump(mode="json")
    run_payload["cases_file"] = _public_path(repo_root, cases_path)
    if values.get("--output"):
        try:
            safe_atomic_write(
                repo_root,
                Path(values["--output"]),
                (json.dumps(run_payload, indent=2) + "\n").encode("utf-8"),
                allowed_repo_root=RESULTS_ROOT,
            )
        except UnsafeStoragePath as exc:
            raise UsageError(f"output rejected: {exc}") from exc

    payload = {
        "schema_version": AXI_SCHEMA_VERSION,
        "lifecycle": {
            "command": "improve-run",
            "candidate_id": result.lineage.candidate_id,
            "cases_file": _public_path(repo_root, cases_path),
            "cases_file_hash": result.cases_file_hash,
            "promotion": {
                "allowed": False,
                "status": "human_review_required",
                "reason": "no automatic promotion or rollback",
            },
        },
        "run": run_payload,
        "progress": progress,
    }

    if compare_path_raw:
        payload["compare_result"] = {
            "reference": str(compare_path_raw),
            "previous_run_id": previous.run_id if previous else None,
        }
    if bool(values.get("--scorecard")):
        payload["scorecard"] = eval_pilot.build_pilot_aggregate_scorecard(
            result, repo="holusight", repo_commit=repo_commit or "unknown"
        )

    evaluation_failed = result.counts["failed"] > 0 or result.counts["errored"] > 0
    return _apply_fields(payload, values.get("--fields")), (1 if evaluation_failed else 0)


def _cmd_improve_review(repo_root: Path, values: dict, positionals: list[str]) -> tuple[dict, int]:
    from . import improvement_control

    cmd = command_by_name("improve-review")
    if len(positionals) != 1:
        raise UsageError(
            "`holus improve-review` requires exactly one change manifest path",
            help_text=_command_help_text(cmd),
        )
    try:
        payload = improvement_control.review_change(
            repo_root,
            positionals[0],
            phase=values.get("--phase") or "before_change",
            record=bool(values.get("--record")),
        )
    except ValueError as exc:
        raise UsageError(str(exc), help_text=_command_help_text(cmd)) from exc
    payload = {"schema_version": AXI_SCHEMA_VERSION, **payload}
    return _apply_fields(payload, values.get("--fields")), 0


def _cmd_improve_history(repo_root: Path, values: dict, positionals: list[str]) -> tuple[dict, int]:
    from . import improvement_control

    cmd = command_by_name("improve-history")
    if len(positionals) != 1:
        raise UsageError(
            "`holus improve-history` requires exactly one change id",
            help_text=_command_help_text(cmd),
        )
    try:
        history = improvement_control.review_history(repo_root, positionals[0])
    except ValueError as exc:
        raise UsageError(str(exc), help_text=_command_help_text(cmd)) from exc
    payload = {"schema_version": AXI_SCHEMA_VERSION, **history}
    return _apply_fields(payload, values.get("--fields")), 0


def _cmd_improve_integration(
    repo_root: Path, values: dict, positionals: list[str]
) -> tuple[dict, int]:
    from . import improvement_control

    cmd = command_by_name("improve-integration")
    if len(positionals) != 1:
        raise UsageError(
            "`holus improve-integration` requires exactly one change manifest path",
            help_text=_command_help_text(cmd),
        )
    try:
        integration = improvement_control.integration_review(
            repo_root, positionals[0], phase=values.get("--phase") or "before_change"
        )
    except ValueError as exc:
        raise UsageError(str(exc), help_text=_command_help_text(cmd)) from exc
    payload = {"schema_version": AXI_SCHEMA_VERSION, **integration}
    return _apply_fields(payload, values.get("--fields")), 0


def _cmd_improve_placement(
    repo_root: Path, values: dict, positionals: list[str]
) -> tuple[dict, int]:
    _reject_extra_positionals("improve-placement", positionals)
    artifact_type = values.get("--artifact-type")
    proposed_path = values.get("--proposed-path")
    if not artifact_type or not proposed_path:
        cmd = command_by_name("improve-placement")
        raise UsageError(
            "both --artifact-type and --proposed-path are required",
            help_text=_command_help_text(cmd),
        )
    try:
        placement = _placement_recommendation(repo_root, artifact_type, proposed_path)
    except ValueError as exc:
        cmd = command_by_name("improve-placement")
        raise UsageError(str(exc), help_text=_command_help_text(cmd)) from exc

    status = "ok"
    reasons: list[str] = []
    if not placement["in_canonical_location"]:
        status = "blocked"
        reasons.append("proposed path is outside canonical location")
        if placement.get("guidance"):
            reasons.append(placement["guidance"])
    if placement["proposed_file_exists"]:
        status = "blocked"
        reasons.append("proposed file already exists")
    if placement["duplicate_hits"]:
        status = "blocked"
        reasons.append("duplicate artifact names already exist in canonical locations")

    payload = {
        "schema_version": AXI_SCHEMA_VERSION,
        "lifecycle": {
            "command": "improve-placement",
            "status": status,
            "reasons": reasons,
        },
        "placement": placement,
        "recommended_action": (
            "adjust_path_and_retry"
            if reasons
            else (
                "reuse_existing_path"
                if placement["proposed_file_exists"]
                else "create_at_recommended_path"
            )
        ),
    }
    return _apply_fields(payload, values.get("--fields")), 0


def _select_display_items(
    results: list[axi_providers.ProviderResult], cap: int
) -> list[axi_providers.EvidenceItem]:
    """Bounded, deterministic per-provider display quota for `evidence`'s
    merged item list.

    This is an anti-starvation *display* safeguard only - not provider
    routing or promotion (spec 015 SS8 still applies unchanged: which
    providers run, and in what fixed order, is untouched here; so are
    `evidence_total`/`truncated`, which always cover every item every
    provider found, not just what ends up displayed). Without it, one
    provider's own scan budget - e.g. `exact_provider`'s 30-match cap,
    which a single early-alphabetical file can exhaust on its own - could
    by itself exceed `cap` and silently push every other provider's items
    out of the displayed list, even ones that reported state "ok".

    Providers are visited round-robin in `results`' order (the same fixed
    order `MODE_PROVIDERS` declares - `exact, structural, consistency,
    semantic` for auto mode), taking at most one item per provider per
    round. A provider with no items left is simply skipped that round,
    letting the next provider in the fixed order use the slot instead -
    this is how "unused slots" get filled deterministically. Items are
    never sorted, scored, or ranked across providers; only their arrival
    order within a round-robin over a fixed provider sequence decides
    which appear first. With a single nonempty provider (or a single
    explicit `--provider`) this degenerates exactly to the prior slicing
    behavior: that provider's own items, in its own order, up to `cap`.
    """
    queues = [list(r.items) for r in results]
    displayed: list[axi_providers.EvidenceItem] = []
    while len(displayed) < cap and any(queues):
        for queue in queues:
            if not queue:
                continue
            displayed.append(queue.pop(0))
            if len(displayed) >= cap:
                break
    return displayed


def _cmd_evidence(repo_root: Path, values: dict, positionals: list[str]) -> tuple[dict, int]:
    cmd = command_by_name("evidence")
    if not positionals:
        raise UsageError(
            'missing required argument "question" for `holus evidence`',
            help_text=_command_help_text(cmd),
        )
    question = " ".join(positionals)

    mode = values.get("--mode") or "auto"
    provider_name = values.get("--provider")
    explain = bool(values.get("--explain-route"))
    allow_egress = bool(values.get("--allow-egress"))
    full = bool(values.get("--full"))

    if provider_name and mode != "auto" and provider_name not in axi_providers.MODE_PROVIDERS[mode]:
        raise UsageError(
            f"--provider {provider_name} is not valid with --mode {mode} "
            f"(--mode {mode} only runs: {', '.join(axi_providers.MODE_PROVIDERS[mode])})",
            help_text=_command_help_text(cmd),
        )

    _ensure_cache_bootstrapped(repo_root)
    head, dirty = _snapshot(repo_root)
    start = time.monotonic()

    if not question.strip():
        payload = {
            "schema_version": AXI_SCHEMA_VERSION,
            "answerable": False,
            "question": question,
            "snapshot": {"commit": head, "dirty": dirty},
            "route": [],
            "evidence": [],
            "evidence_total": 0,
            "coverage": "unknown",
            "reason": "unsupported_question",
            "providers_checked": [],
            "egress": {"occurred": False, "destination": None},
            "truncated": False,
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
            "warnings": ["question is empty"],
        }
        return _apply_fields(payload, values.get("--fields")), 0

    provider_list = [provider_name] if provider_name else axi_providers.MODE_PROVIDERS[mode]
    results = [
        axi_providers.PROVIDERS[name](repo_root, question, full=full, allow_egress=allow_egress)
        for name in provider_list
    ]

    all_items = [item for r in results for item in r.items]
    total_items = len(all_items)
    displayed = _select_display_items(results, _MAX_DISPLAY_ITEMS)
    list_truncated = total_items > _MAX_DISPLAY_ITEMS
    excerpt_truncated = any(item.excerpt_truncated for item in displayed)

    states = [r.state for r in results]
    hit_budget = any(s == axi_providers.ProviderState.BUDGET_EXCEEDED for s in states)
    egress_occurred = any(r.egress for r in results)

    if all_items:
        answerable = True
        reason = None
        coverage = "partial" if (hit_budget or list_truncated) else "sufficient"
    else:
        answerable = False
        all_unreachable = all(
            s
            in (
                axi_providers.ProviderState.UNAVAILABLE,
                axi_providers.ProviderState.DENIED,
                axi_providers.ProviderState.UNSUPPORTED,
            )
            for s in states
        )
        if all_unreachable:
            coverage = "unknown"
            reason = "no_provider_available"
        else:
            coverage = "none"
            reason = "no_matching_evidence"

    providers_checked = []
    for r in results:
        entry = {"provider": r.provider, "state": r.state.value, "detail": r.detail}
        if explain:
            entry["route_reason"] = r.route_reason
        providers_checked.append(entry)

    warnings: list[str] = []
    if hit_budget:
        warnings.append("one or more providers hit their scan budget; results are partial")
    if list_truncated:
        warnings.append(
            f"showing {len(displayed)} of {total_items} evidence items; "
            "narrow the question or pass --provider to see more of one provider"
        )

    payload = {
        "schema_version": AXI_SCHEMA_VERSION,
        "answerable": answerable,
        "question": question,
        "snapshot": {"commit": head, "dirty": dirty},
        "route": sorted({item.provider for item in displayed}),
        # Every EvidenceItem shares the same field set (nulls included, not
        # omitted) so mixed-provider evidence lists stay a uniform table
        # under --format toon instead of falling back to a per-item block.
        "evidence": [item.model_dump() for item in displayed],
        "evidence_total": total_items,
        "coverage": coverage,
        "reason": reason,
        "providers_checked": providers_checked,
        "egress": {
            "occurred": egress_occurred,
            "destination": "voyage" if egress_occurred else None,
        },
        "truncated": bool(list_truncated or excerpt_truncated),
        "latency_ms": round((time.monotonic() - start) * 1000, 1),
        "warnings": warnings,
    }
    return _apply_fields(payload, values.get("--fields")), 0


def _cmd_check(repo_root: Path, values: dict, positionals: list[str]) -> tuple[dict, int]:
    cmd = command_by_name("check")
    if len(positionals) > 1:
        raise UsageError(
            "`holus check` accepts at most one scope argument",
            help_text=_command_help_text(cmd),
        )
    scope = positionals[0] if positionals else None
    do_refresh = bool(values.get("--refresh"))

    if do_refresh:
        consistency.refresh(repo_root, run_semantic=False)
    else:
        _ensure_cache_bootstrapped(repo_root)

    if scope:
        concept_id, candidates = _resolve_concept(repo_root, scope)
        if concept_id is None:
            payload = {
                "schema_version": AXI_SCHEMA_VERSION,
                "scope": scope,
                "status": "unknown_concept",
                "notes": "no cached concept matches this scope; run `holus check --refresh` first",
                "candidates": candidates[:10],
                "help": (
                    [f'Run `holus check "{candidates[0]}"` - closest cached concept match.']
                    if candidates
                    else ["Run `holus check` with no scope to list every tracked concept."]
                ),
            }
            return _apply_fields(payload, values.get("--fields")), 0

        report = consistency.check_consistency(repo_root, concept_id)
        payload = {
            "schema_version": AXI_SCHEMA_VERSION,
            # mode="json" so the ConsistencyStatus enum serializes to its
            # plain string value (e.g. "up_to_date"), not "ConsistencyStatus.UP_TO_DATE".
            **report.model_dump(mode="json"),
        }
        return _apply_fields(payload, values.get("--fields")), 0

    db_path = consistency.consistency_db_path(repo_root)
    if not db_path.exists():
        payload = {
            "schema_version": AXI_SCHEMA_VERSION,
            "concepts_checked": 0,
            "summary": {},
            "concepts": [],
            "reason": "no_evidence",
            "notes": "consistency cache has never been refreshed",
        }
        return _apply_fields(payload, values.get("--fields")), 0

    from .consistency_store import ConsistencyStore

    store = ConsistencyStore(db_path)
    try:
        concepts = store.all_concepts()
    finally:
        store.close()

    reports = [consistency.check_consistency(repo_root, c["concept_id"]) for c in concepts]
    summary: dict[str, int] = {}
    for r in reports:
        summary[r.status.value] = summary.get(r.status.value, 0) + 1

    displayed = reports[:_MAX_DISPLAY_CONCEPTS]
    truncated = len(reports) > _MAX_DISPLAY_CONCEPTS

    payload = {
        "schema_version": AXI_SCHEMA_VERSION,
        "concepts_checked": len(reports),
        "summary": summary,
        "concepts": [
            {
                "concept_id": r.concept_id,
                "status": r.status.value,
                "canonical_changed": r.canonical_changed,
            }
            for r in displayed
        ],
        "truncated": truncated,
        "help": (
            [
                f"{len(reports) - len(displayed)} more concept(s) not shown; "
                'run `holus check "<concept_id>"` for any specific one.'
            ]
            if truncated
            else ['Run `holus check "<concept_id>"` for full evidence on any one concept.']
        ),
    }
    return _apply_fields(payload, values.get("--fields")), 0


_HANDLERS = {
    "": _cmd_home,
    "evidence": _cmd_evidence,
    "check": _cmd_check,
    "status": _cmd_status,
    "providers": _cmd_providers,
    "improve-status": _cmd_improve_status,
    "improve-intake": _cmd_improve_intake,
    "improve-run": _cmd_improve_run,
    "improve-placement": _cmd_improve_placement,
    "improve-review": _cmd_improve_review,
    "improve-history": _cmd_improve_history,
    "improve-integration": _cmd_improve_integration,
}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _dispatch(argv: list[str]) -> tuple[dict, str, int]:
    repo_root = Path.cwd().resolve()
    cmd_name, cmd_argv = _split_command(argv)
    cmd = command_by_name(cmd_name)
    values, positionals = _parse_command_args(cmd, cmd_argv)
    fmt = values.get("--format") or "toon"
    payload, exit_code = _HANDLERS[cmd_name](repo_root, values, positionals)
    payload.setdefault("schema_version", AXI_SCHEMA_VERSION)
    return payload, fmt, exit_code


def main(argv: list[str] | None = None) -> None:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    try:
        payload, fmt, exit_code = _dispatch(raw_argv)
    except _HelpRequested as help_exc:
        print(help_exc.text)
        sys.exit(0)
    except UsageError as usage_exc:
        payload = _error_payload(
            "USAGE_ERROR", _public_error_message(usage_exc.message), usage_exc.help_text
        )
        print(_render(payload, _requested_format(raw_argv)))
        sys.exit(2)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001 - never leak a raw traceback to stdout
        logger.debug("Unhandled exception", exc_info=True)
        payload = _error_payload(
            "INTERNAL_ERROR", _public_error_message(f"{exc.__class__.__name__}: {exc}")
        )
        print(_render(payload, _requested_format(raw_argv)))
        sys.exit(1)
    else:
        print(_render(payload, fmt))
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
