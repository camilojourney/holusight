"""Read-only adapter for Holus's versioned lineage export.

The adapter consumes an already-fetched, validated Holus export. It never reads
Holus files or databases, imports Holus code, or fetches a producer URL.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from pydantic import BaseModel

HOLUS_SCHEMA_VERSION = "1.0"
HOLUS_SOURCE = "holus"
HOLUS_SOURCE_LABEL = "Holus lineage"
HOLUS_CHUNK_PREFIX = "holus:"

_PRIVATE_KEY = re.compile(
    r"(?:raw|text|content|input|body|prompt|summary|url|uri|path|filename|"
    r"api[_-]?key|token|secret|password|authorization)",
    re.IGNORECASE,
)
_SECRET_VALUE = re.compile(r"(?:sk-|bearer\s+|ghp_)[A-Za-z0-9_-]+", re.IGNORECASE)
_URL_VALUE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")
_ABSOLUTE_REF = re.compile(r"^(?:[A-Za-z]:[\\/]|[\\/]|[A-Za-z][A-Za-z0-9+.-]*://)")

_NODE_FIELDS = frozenset(
    {
        "schema_version",
        "node_id",
        "artifact_type",
        "artifact_id",
        "producer",
        "created_at",
        "run_id",
        "correlation_id",
        "status",
        "artifact_ref",
        "content_hash",
        "config_hash",
        "model_hash",
        "checksum",
        "metadata",
    }
)
_EDGE_FIELDS = frozenset(
    {
        "schema_version",
        "edge_id",
        "from_node_id",
        "to_node_id",
        "relation",
        "created_at",
        "run_id",
        "metadata",
    }
)
_REQUIRED_NODE_FIELDS = frozenset(
    {
        "node_id",
        "artifact_type",
        "artifact_id",
        "producer",
        "created_at",
        "run_id",
        "correlation_id",
        "status",
    }
)
_REQUIRED_EDGE_FIELDS = frozenset(
    {
        "edge_id",
        "from_node_id",
        "to_node_id",
        "relation",
        "created_at",
        "run_id",
    }
)


class HolusImportStats(BaseModel):
    """Result of one idempotent local import of a Holus export snapshot."""

    source: str = HOLUS_SOURCE
    source_schema_version: str = HOLUS_SCHEMA_VERSION
    records_imported: int = 0
    records_skipped_unchanged: int = 0
    total_records: int = 0


@dataclass(frozen=True)
class HolusLineageRecord:
    """Validated, safe data needed to index one producer lineage node."""

    node_id: str
    chunk_id: str
    file_path: str
    content_hash: str
    summary: str
    edge_ids: tuple[str, ...]
    provenance: dict[str, Any]


def parse_holus_lineage_export(payload: Mapping[str, Any]) -> list[HolusLineageRecord]:
    """Validate a Holus v1 export fully before returning data for storage."""
    if not isinstance(payload, Mapping):
        raise ValueError("Holus lineage export must be an object")
    _require_schema_version(payload, "export")

    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("Holus lineage export must contain a records list")

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_ids: set[str] = set()
    edge_ids: set[str] = set()

    for position, record in enumerate(records, start=1):
        if not isinstance(record, Mapping):
            raise ValueError(f"Holus record {position} must be an object")
        _require_schema_version(record, f"record {position}")
        node = _validate_node(record.get("node"), position)
        node_id = node["node_id"]
        if node_id in node_ids:
            raise ValueError(f"duplicate Holus lineage node_id: {node_id}")
        node_ids.add(node_id)
        nodes.append(node)

        record_edges = record.get("edges", [])
        if not isinstance(record_edges, list):
            raise ValueError(f"Holus record {position} edges must be a list")
        for edge in record_edges:
            validated_edge = _validate_edge(edge, position)
            edge_id = validated_edge["edge_id"]
            if edge_id in edge_ids:
                raise ValueError(f"duplicate Holus lineage edge_id: {edge_id}")
            edge_ids.add(edge_id)
            edges.append(validated_edge)

    for edge in edges:
        if edge["from_node_id"] not in node_ids or edge["to_node_id"] not in node_ids:
            raise ValueError(f"edge {edge['edge_id']} references an unknown lineage node")

    edge_ids_by_node: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        edge_ids_by_node[edge["from_node_id"]].append(edge["edge_id"])
        if edge["to_node_id"] != edge["from_node_id"]:
            edge_ids_by_node[edge["to_node_id"]].append(edge["edge_id"])

    return [
        _to_lineage_record(node, sorted(edge_ids_by_node[node["node_id"]]))
        for node in nodes
    ]


def _require_schema_version(value: Mapping[str, Any], location: str) -> None:
    if value.get("schema_version") != HOLUS_SCHEMA_VERSION:
        raise ValueError(
            f"{location} schema_version must be exactly {HOLUS_SCHEMA_VERSION!r}"
        )


def _validate_node(value: Any, position: int) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"Holus record {position} node must be an object")
    _require_schema_version(value, f"node in record {position}")
    _reject_unknown_fields(value, _NODE_FIELDS, "node")
    _require_fields(value, _REQUIRED_NODE_FIELDS, "node")
    _validate_identity_fields(value, "node")
    _validate_artifact_ref(value.get("artifact_ref"))
    _validate_safe_metadata(value.get("metadata", {}), "node metadata")
    return dict(value)


def _validate_edge(value: Any, position: int) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"Holus record {position} edge must be an object")
    _require_schema_version(value, f"edge in record {position}")
    _reject_unknown_fields(value, _EDGE_FIELDS, "edge")
    _require_fields(value, _REQUIRED_EDGE_FIELDS, "edge")
    _validate_identity_fields(value, "edge")
    _validate_safe_metadata(value.get("metadata", {}), "edge metadata")
    return dict(value)


def _reject_unknown_fields(value: Mapping[str, Any], allowed: frozenset[str], label: str) -> None:
    extra_fields = sorted(set(value) - allowed)
    if extra_fields:
        raise ValueError(f"{label} contains unsupported field(s): {', '.join(extra_fields)}")


def _require_fields(value: Mapping[str, Any], fields: frozenset[str], label: str) -> None:
    missing = sorted(
        field for field in fields if not isinstance(value.get(field), str) or not value[field]
    )
    if missing:
        raise ValueError(f"{label} is missing required field(s): {', '.join(missing)}")


def _validate_identity_fields(value: Mapping[str, Any], label: str) -> None:
    for key, item in value.items():
        if key in {"metadata", "artifact_ref", "schema_version"} or item is None:
            continue
        if isinstance(item, str) and (
            _URL_VALUE.search(item) or _SECRET_VALUE.search(item) or _ABSOLUTE_REF.search(item)
        ):
            raise ValueError(f"{label} field {key} contains an unsafe value")


def _validate_artifact_ref(value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise ValueError("artifact_ref must be a string")
    if _ABSOLUTE_REF.search(value) or ".." in re.split(r"[/\\]", value):
        raise ValueError("artifact_ref must be a stable relative path")


def _validate_safe_metadata(value: Any, label: str) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError(f"{label} keys must be strings")
        if _PRIVATE_KEY.search(key):
            raise ValueError(f"{label} contains a private field: {key}")
        if not isinstance(item, (str, int, float, bool)) and item is not None:
            raise ValueError(f"{label} values must be scalar")
        if isinstance(item, str):
            if (
                len(item) > 512
                or _SECRET_VALUE.search(item)
                or _URL_VALUE.search(item)
                or _ABSOLUTE_REF.search(item)
            ):
                raise ValueError(f"{label} contains an unsafe value")


def _to_lineage_record(node: dict[str, Any], edge_ids: list[str]) -> HolusLineageRecord:
    node_id = node["node_id"]
    identity_hash = hashlib.sha256(node_id.encode("utf-8")).hexdigest()[:32]
    safe_node = {
        key: value
        for key, value in node.items()
        if key != "artifact_ref"
    }
    content_hash = hashlib.sha256(
        json.dumps(
            {"schema_version": HOLUS_SCHEMA_VERSION, "node": safe_node, "edge_ids": edge_ids},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    summary = _safe_summary(node, edge_ids)
    return HolusLineageRecord(
        node_id=node_id,
        chunk_id=f"{HOLUS_CHUNK_PREFIX}{identity_hash}",
        file_path=f"holus-lineage/{identity_hash}.json",
        content_hash=content_hash,
        summary=summary,
        edge_ids=tuple(edge_ids),
        provenance={
            "source": HOLUS_SOURCE,
            "source_label": HOLUS_SOURCE_LABEL,
            "source_schema_version": HOLUS_SCHEMA_VERSION,
            "lineage_node_id": node_id,
            "lineage_edge_ids": edge_ids,
            "artifact_type": node["artifact_type"],
            "artifact_id": node["artifact_id"],
            "producer": node["producer"],
            "run_id": node["run_id"],
            "correlation_id": node["correlation_id"],
            "status": node["status"],
        },
    )


def _safe_summary(node: Mapping[str, Any], edge_ids: list[str]) -> str:
    parts = [
        "Holus lineage",
        f"artifact type: {node['artifact_type']}",
        f"status: {node['status']}",
        f"producer: {node['producer']}",
        f"node: {node['node_id']}",
    ]
    metadata = node.get("metadata", {})
    if metadata:
        parts.extend(f"{key}: {value}" for key, value in sorted(metadata.items()))
    if edge_ids:
        parts.append(f"related lineage edges: {', '.join(edge_ids)}")
    return ". ".join(parts) + "."
