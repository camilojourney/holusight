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
import shutil
import sys
import time
from enum import Enum
from pathlib import Path
from typing import Any

from . import axi_providers, consistency
from .axi_schema import AXI_COMMANDS, AXI_SCHEMA_VERSION, AxiCommand, command_by_name
from .toon import to_toon

logger = logging.getLogger(__name__)

_JOB_NAMES = {"evidence", "check", "status", "providers"}
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
    values: dict[str, Any] = {
        f.name: (f.default if f.takes_value else False) for f in cmd.flags
    }
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
                    raise UsageError(
                        f"{name} requires a value", help_text=_command_help_text(cmd)
                    )
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
            {"name": s.name, "available": s.available, "freshness": s.freshness}
            for s in statuses
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
    displayed = all_items[:_MAX_DISPLAY_ITEMS]
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
            [f"{len(reports) - len(displayed)} more concept(s) not shown; "
             'run `holus check "<concept_id>"` for any specific one.']
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
        payload = _error_payload("USAGE_ERROR", usage_exc.message, usage_exc.help_text)
        print(_render(payload, usage_exc.format))
        sys.exit(2)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001 - never leak a raw traceback to stdout
        logger.debug("Unhandled exception", exc_info=True)
        payload = _error_payload("INTERNAL_ERROR", f"{exc.__class__.__name__}: {exc}")
        print(_render(payload, "toon"))
        sys.exit(1)
    else:
        print(_render(payload, fmt))
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
