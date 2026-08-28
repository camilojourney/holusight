"""AVO leakage-boundary validation for persisted and exportable records.

Enforces the visible Git export boundary from ``docs/avo/leakage-boundary.md``.
This module rejects unsafe persisted values before they can be written to ledger,
checkpoint, or other Git-exportable artifacts. It does not read hidden holdout
payloads, open network paths, or touch G2 code.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LEAKAGE_BOUNDARY_DOC = Path("docs/avo/leakage-boundary.md")

# Keys that must never appear in Git-exportable AVO artifacts (leakage-boundary.md).
FORBIDDEN_EXPORT_KEYS = frozenset(
    {
        "prompt",
        "raw_prompt",
        "snippet",
        "api_key",
        "token",
        "telemetry",
        "path_absolute",
        "source_content",
        "private_data",
        "customer_data",
        "credentials",
        "credential",
        "production_telemetry",
    }
)

_SECRET_LIKE_RE = re.compile(
    r"(?i)(?:sk-[a-z0-9_-]{8,}|api[_ -]?key|authorization|bearer|password|"
    r"raw\s+prompt|private\s+key|ssh-rsa\s|BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY)"
)

_ABSOLUTE_PATH_RE = re.compile(
    r"(?:^|[\s\"'])"
    r"(?:/[A-Za-z0-9._-]+)+"
    r"|(?:^|[\s\"'])"
    r"[A-Za-z]:\\[^\"'\s]+"
)

_MAX_STRING_SCAN = 4096
_DEFAULT_MAX_RECORD_BYTES = 16 * 1024


@dataclass(frozen=True, slots=True)
class LeakageViolation:
    code: str
    evidence: str


class AvoLeakageError(ValueError):
    """Closed failure for AVO leakage-boundary validation."""


def _scan_value(value: Any, *, path: str = "$") -> list[LeakageViolation]:
    violations: list[LeakageViolation] = []

    if isinstance(value, dict):
        for key, child in value.items():
            key_lower = str(key).lower()
            if key_lower in FORBIDDEN_EXPORT_KEYS:
                violations.append(
                    LeakageViolation(
                        code="forbidden_export_key",
                        evidence=f"{path}.{key}",
                    )
                )
            if _SECRET_LIKE_RE.search(str(key)):
                violations.append(
                    LeakageViolation(
                        code="secret_like_key",
                        evidence=f"{path}.{key}",
                    )
                )
            violations.extend(_scan_value(child, path=f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_scan_value(child, path=f"{path}[{index}]"))
    elif isinstance(value, str):
        sample = value[:_MAX_STRING_SCAN]
        if _SECRET_LIKE_RE.search(sample):
            violations.append(
                LeakageViolation(
                    code="secret_like_value",
                    evidence=path,
                )
            )
        if _ABSOLUTE_PATH_RE.search(sample):
            violations.append(
                LeakageViolation(
                    code="absolute_path",
                    evidence=path,
                )
            )
    return violations


def scan_for_leakage(value: Any) -> list[LeakageViolation]:
    """Return every leakage-boundary violation found in *value*."""
    return _scan_value(value)


def validate_export_record(
    record: dict[str, Any],
    *,
    max_bytes: int = _DEFAULT_MAX_RECORD_BYTES,
) -> None:
    """Reject *record* when it violates the visible export boundary."""
    violations = scan_for_leakage(record)
    if violations:
        first = violations[0]
        raise AvoLeakageError(f"{first.code}: {first.evidence}")

    serialized = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(serialized) > max_bytes:
        raise AvoLeakageError(
            f"record_bytes_exceeded: {len(serialized)} > {max_bytes}",
        )


def validate_export_bytes(payload: bytes, *, max_bytes: int = _DEFAULT_MAX_RECORD_BYTES) -> None:
    """Reject raw serialized bytes that exceed the export size cap."""
    if len(payload) > max_bytes:
        raise AvoLeakageError(
            f"record_bytes_exceeded: {len(payload)} > {max_bytes}",
        )
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AvoLeakageError("invalid_export_json") from exc
    if not isinstance(parsed, dict):
        raise AvoLeakageError("export_record_must_be_object")
    validate_export_record(parsed, max_bytes=max_bytes)


def leakage_boundary_doc_exists(repo_root: Path) -> bool:
    """Return True when the published leakage-boundary doc is present."""
    return (repo_root / LEAKAGE_BOUNDARY_DOC).is_file()
