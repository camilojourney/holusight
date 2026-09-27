"""Content-minimized, local-only usage events and deterministic summaries."""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EVENT_VERSION = "1.1"
EVENT_FILENAME = "events.jsonl"
PROJECT_OPT_OUT = ".holusight/local-usage.disabled"


def is_enabled() -> bool:
    return os.environ.get("HOLUSIGHT_LOCAL_TRACE", "1").strip().lower() not in {
        "0",
        "false",
        "off",
        "no",
    }


def event_path() -> Path:
    configured = os.environ.get("HOLUSIGHT_LOCAL_TRACE_DIR")
    root = Path(configured).expanduser() if configured else Path.home() / ".holusight" / "usage"
    return root / EVENT_FILENAME


def _project_opted_out(project_root: Path | None = None) -> bool:
    if not is_enabled():
        return True
    root = (project_root or Path.cwd()).resolve()
    return any((candidate / PROJECT_OPT_OUT).is_file() for candidate in (root, *root.parents))


def _project_id(project_root: Path | None) -> str:
    value = str((project_root or Path.cwd()).resolve()).encode()
    return "sha256:" + hashlib.sha256(value).hexdigest()[:16]


def _provider_events(payload: dict[str, Any]) -> list[dict[str, Any]]:
    checked = {
        str(i.get("provider")): i
        for i in payload.get("providers_checked", [])
        if isinstance(i, dict) and i.get("provider")
    }
    statuses = {
        str(i.get("name")): i
        for i in payload.get("providers", [])
        if isinstance(i, dict) and i.get("name")
    }
    events = []
    for name in sorted(set(checked) | set(statuses)):
        item = checked.get(name, statuses.get(name, {}))
        state = str(item.get("state", "unknown"))
        freshness = {
            "ok": "current",
            "no_evidence": "current",
            "budget_exceeded": "partial",
            "stale": "stale",
            "unavailable": "unavailable",
            "denied": "unavailable",
            "unsupported": "unavailable",
        }.get(state, str(item.get("freshness", "unknown")))
        events.append(
            {
                "name": name,
                "invoked": name in checked,
                "freshness": freshness,
                "partial": freshness == "partial",
            }
        )
    return events


def _token_delta(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("token_delta")
    if not isinstance(value, dict) or not all(
        type(value.get(k)) is int for k in ("input", "output", "total")
    ):
        return {"status": "unknown", "input": None, "output": None, "total": None}
    return {
        "status": "measured",
        "input": value["input"],
        "output": value["output"],
        "total": value["total"],
    }


def _feedback_outcome(payload: dict[str, Any]) -> dict[str, Any] | None:
    queue = payload.get("review_queue")
    if (
        not isinstance(queue, dict)
        or queue.get("signal") not in {"failure_case", "aggregate_outcome"}
        or type(queue.get("count")) is not int
    ):
        return None
    return {"signal": queue["signal"], "count": queue["count"]}


def build_event(
    command: str, payload: dict[str, Any], *, exit_code: int = 0, project_root: Path | None = None
) -> dict[str, Any]:
    providers = _provider_events(payload)
    partial = any(p["partial"] for p in providers) or payload.get("coverage") == "partial"
    return {
        "schema_version": "holusight.local_usage.v1",
        "event_version": EVENT_VERSION,
        "event_type": "local_usage",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "command": command or "home",
        "project_id": _project_id(project_root),
        "agent_id": os.environ.get("HOLUSIGHT_AGENT_ID", "unknown")[:64],
        "invoked": True,
        "exit_code": int(exit_code),
        "freshness": "partial"
        if partial
        else ("unknown" if any(p["freshness"] == "unknown" for p in providers) else "current"),
        "partial": partial,
        "providers": providers,
        "latency_ms": payload.get("latency_ms")
        if isinstance(payload.get("latency_ms"), (int, float))
        else None,
        "token_delta": _token_delta(payload),
        "feedback_outcome": _feedback_outcome(payload),
    }


def record(
    command: str, payload: dict[str, Any], *, exit_code: int = 0, project_root: Path | None = None
) -> Path | None:
    if _project_opted_out(project_root):
        return None
    try:
        path = event_path()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path.parent, 0o700)
        line = (
            json.dumps(
                build_event(command, payload, exit_code=exit_code, project_root=project_root),
                separators=(",", ":"),
            )
            + "\n"
        ).encode()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, line)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.chmod(path, 0o600)
        return path
    except (OSError, ValueError):
        return None


def summarize(path: Path | None = None) -> dict[str, Any]:
    target = path or event_path()
    events = []
    if target.is_file():
        for line in target.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(item, dict) and item.get("schema_version") == "holusight.local_usage.v1":
                events.append(item)
    providers: dict[str, dict[str, int]] = {}
    for event in events:
        for provider in event.get("providers", []):
            if not isinstance(provider, dict) or not provider.get("name"):
                continue
            row = providers.setdefault(
                str(provider["name"]),
                {
                    k: 0
                    for k in (
                        "invoked",
                        "not_used",
                        "current",
                        "partial",
                        "stale",
                        "unavailable",
                        "unknown",
                    )
                },
            )
            row["invoked" if provider.get("invoked") else "not_used"] += 1
            key = provider.get("freshness", "unknown")
            row[key if key in row else "unknown"] += 1
    latency = [e["latency_ms"] for e in events if isinstance(e.get("latency_ms"), (int, float))]
    tokens = [
        e["token_delta"] for e in events if e.get("token_delta", {}).get("status") == "measured"
    ]
    feedback = Counter()
    for e in events:
        if isinstance(e.get("feedback_outcome"), dict):
            feedback[e["feedback_outcome"]["signal"]] += e["feedback_outcome"]["count"]
    return {
        "schema_version": "holusight.local_usage_summary.v1",
        "enabled": is_enabled() and not _project_opted_out(),
        "events": len(events),
        "project_invocations": {
            "total": len(events),
            "projects": dict(Counter(str(e.get("project_id", "unknown")) for e in events)),
        },
        "agent_invocations": {
            "total": len(events),
            "agents": dict(Counter(str(e.get("agent_id", "unknown")) for e in events)),
        },
        "commands": dict(Counter(str(e.get("command", "unknown")) for e in events)),
        "providers": providers,
        "latency_ms": {"status": "measured", "count": len(latency), "total": round(sum(latency), 1)}
        if latency
        else {"status": "unknown", "count": 0, "total": None},
        "token_delta": {
            "status": "measured",
            "input": sum(e["input"] for e in tokens),
            "output": sum(e["output"] for e in tokens),
            "total": sum(e["total"] for e in tokens),
        }
        if tokens
        else {"status": "unknown", "input": None, "output": None, "total": None},
        "feedback_outcomes": dict(feedback),
        "limitations": [
            "raw prompts, source, audio, credentials, and paths are never retained",
            "local-only; fixtures are never promoted",
        ],
    }
