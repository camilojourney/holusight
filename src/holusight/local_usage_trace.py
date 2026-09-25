"""Privacy-safe, local-only usage evidence for the ``holus`` CLI.

Events deliberately contain operation metadata only. They never contain the
repository path, arguments, questions, excerpts, credentials, or source
content. Token deltas are reported as unknown unless a caller supplies a
measured value; this module never estimates them.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EVENT_VERSION = "1.0"
EVENT_FILENAME = "events.jsonl"


def is_enabled() -> bool:
    """Return whether local usage events are enabled (enabled by default)."""
    return os.environ.get("HOLUSIGHT_LOCAL_TRACE", "1").strip().lower() not in {
        "0", "false", "off", "no",
    }


def event_path() -> Path:
    configured = os.environ.get("HOLUSIGHT_LOCAL_TRACE_DIR")
    root = Path(configured).expanduser() if configured else Path.home() / ".holusight" / "usage"
    return root / EVENT_FILENAME


def _provider_events(payload: dict[str, Any]) -> list[dict[str, Any]]:
    checked = {
        str(item.get("provider")): item
        for item in payload.get("providers_checked", [])
        if isinstance(item, dict) and item.get("provider")
    }
    statuses = {
        str(item.get("name")): item
        for item in payload.get("providers", [])
        if isinstance(item, dict) and item.get("name")
    }
    names = sorted(set(checked) | set(statuses))
    events: list[dict[str, Any]] = []
    for name in names:
        item = checked.get(name, statuses.get(name, {}))
        state = str(item.get("state", "unknown"))
        if state in {"ok", "no_evidence"}:
            freshness = "current"
        elif state in {"budget_exceeded"}:
            freshness = "partial"
        elif state in {"stale"}:
            freshness = "stale"
        elif state in {"unavailable", "denied", "unsupported"}:
            freshness = "unavailable"
        else:
            freshness = str(item.get("freshness", "unknown"))
        events.append({
            "name": name,
            "invoked": name in checked,
            "freshness": freshness,
            "partial": freshness == "partial",
        })
    return events


def build_event(command: str, payload: dict[str, Any], *, exit_code: int = 0) -> dict[str, Any]:
    """Build a content-minimized event; token values stay explicitly unknown."""
    providers = _provider_events(payload)
    partial = any(item["partial"] for item in providers) or payload.get("coverage") == "partial"
    freshness = "partial" if partial else (
        "unknown" if any(item["freshness"] == "unknown" for item in providers) else "current"
    )
    return {
        "schema_version": "holusight.local_usage.v1",
        "event_version": EVENT_VERSION,
        "event_type": "local_usage",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "command": command or "home",
        "invoked": True,
        "exit_code": int(exit_code),
        "freshness": freshness,
        "partial": partial,
        "providers": providers,
        "token_delta": {"status": "unknown", "input": None, "output": None, "total": None},
    }


def record(command: str, payload: dict[str, Any], *, exit_code: int = 0) -> Path | None:
    """Append one event locally, returning its path; tracing never breaks CLI use."""
    if not is_enabled():
        return None
    try:
        path = event_path()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path.parent, 0o700)
        encoded = json.dumps(
            build_event(command, payload, exit_code=exit_code), separators=(",", ":")
        )
        line = (encoded + "\n").encode()
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
