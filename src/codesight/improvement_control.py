"""Deterministic, local review control for the existing ``holus improve-*`` loop.

This module is deliberately a validator and derived-state recorder, not a second
workflow engine. Canonical truth stays in tracked specs, ADRs, source, tests,
and fixtures. It reads a small tracked JSON change manifest, verifies its
repository-relative links, and can opt in to write a content-minimized review
record under the already-gitignored ``.holusight/`` state directory.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CHANGE_SCHEMA = "holus-improvement-change/v1"
RECORD_SCHEMA = "holus-improvement-record/v1"
INTEGRATION_SCHEMA = "holus-improvement-integration/v1"

CLASSIFICATIONS = frozenset(
    {"research_only", "proposed", "accepted", "implemented", "evaluated", "rejected", "superseded"}
)
PHASES = ("before_change", "after_implementation", "after_test", "pre_promotion")
LINK_ROLES = (
    "governing",
    "implementation",
    "tests",
    "documentation",
    "evaluation_case",
    "evaluation_result",
)
_REQUIRED_SECTIONS = frozenset({"context", "evidence", "decision"})
_FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "raw_prompt",
        "prompt",
        "source_content",
        "private_data",
        "customer_data",
        "credentials",
        "credential",
        "telemetry",
        "production_telemetry",
    }
)
_CHANGE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
_EVALUATOR_PATHS = frozenset(
    {"src/codesight/eval_pilot.py", "tests/fixtures/holusight_eval_pilot_cases.jsonl"}
)
_ALLOWED_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "change_id",
        "classification",
        "classification_evidence",
        "evidence_state",
        "structured_sections",
        "links",
        "link_hashes",
        "lineage",
        "proposed_artifacts",
    }
)
_ALLOWED_SECTIONS = frozenset(
    {"context", "evidence", "decision", "implementation", "test", "evaluation"}
)
_ALLOWED_LINEAGE_FIELDS = frozenset({"candidate_id", "workflow", "tool", "model"})
_SAFE_LINEAGE_VALUE_RE = re.compile(r"^[A-Za-z0-9._/-]{1,80}$")


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _json_hash(value: Any) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    )


def _safe_relative(repo_root: Path, raw_path: str) -> Path | None:
    path = Path(raw_path)
    if not raw_path.strip() or path.is_absolute() or ".." in path.parts:
        return None
    try:
        resolved = (repo_root / path).resolve()
        return resolved.relative_to(repo_root.resolve())
    except ValueError:
        return None


def _blocked(code: str, evidence: str, *, role: str | None = None) -> dict[str, str]:
    item = {"code": code, "evidence": evidence}
    if role:
        item["role"] = role
    return item


def _has_forbidden_field(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in _FORBIDDEN_FIELD_NAMES:
                return key
            found = _has_forbidden_field(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _has_forbidden_field(child)
            if found:
                return found
    return None


def _load_manifest(repo_root: Path, raw_path: str) -> tuple[dict[str, Any], Path]:
    relative = _safe_relative(repo_root, raw_path)
    if relative is None:
        raise ValueError(
            "change manifest path must be repository-relative and cannot escape the repository"
        )
    path = repo_root / relative
    if not path.is_file():
        raise ValueError(f"change manifest does not exist: {relative}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"change manifest must be valid JSON: {relative}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != CHANGE_SCHEMA:
        raise ValueError(f"change manifest must declare schema_version {CHANGE_SCHEMA!r}")
    forbidden = _has_forbidden_field(manifest)
    if forbidden:
        raise ValueError(f"forbidden field in change manifest: {forbidden}")
    unknown_fields = set(manifest) - _ALLOWED_MANIFEST_FIELDS
    if unknown_fields:
        raise ValueError(f"unsupported field in change manifest: {sorted(unknown_fields)[0]}")
    sections = manifest.get("structured_sections", [])
    if not isinstance(sections, list) or not all(
        section in _ALLOWED_SECTIONS for section in sections
    ):
        raise ValueError("structured_sections must use the closed deterministic section vocabulary")
    lineage = manifest.get("lineage", {})
    if not isinstance(lineage, dict) or set(lineage) - _ALLOWED_LINEAGE_FIELDS:
        raise ValueError("lineage must use only candidate_id, workflow, tool, and model")
    if not all(
        (key == "model" and value is None)
        or (isinstance(value, str) and _SAFE_LINEAGE_VALUE_RE.fullmatch(value))
        for key, value in lineage.items()
    ):
        raise ValueError("lineage values must be bounded identifier strings")
    classification_evidence = manifest.get("classification_evidence")
    if classification_evidence is not None and classification_evidence not in CLASSIFICATIONS:
        raise ValueError("classification_evidence must use the classification vocabulary")
    link_hashes = manifest.get("link_hashes", {})
    if not isinstance(link_hashes, dict) or not all(
        isinstance(path, str)
        and isinstance(value, str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", value)
        for path, value in link_hashes.items()
    ):
        raise ValueError("link_hashes must contain only full SHA-256 values")
    evidence_state = manifest.get("evidence_state", "familiar")
    if evidence_state not in {"familiar", "unfamiliar"}:
        raise ValueError("evidence_state must be familiar or unfamiliar")
    change_id = manifest.get("change_id")
    if not isinstance(change_id, str) or not _CHANGE_ID_RE.fullmatch(change_id):
        raise ValueError("change_id must be a lowercase stable slug")
    classification = manifest.get("classification")
    if classification not in CLASSIFICATIONS:
        raise ValueError(f"classification must be one of {sorted(CLASSIFICATIONS)}")
    return manifest, relative


def _role_path_is_canonical(role: str, path: str) -> bool:
    if role == "governing":
        return path.startswith("specs/") or path.startswith("docs/decisions/")
    if role == "implementation":
        return path.startswith("src/")
    if role == "tests":
        return path.startswith("tests/test_") and path.endswith(".py")
    if role == "documentation":
        return path == "ARCHITECTURE.md" or path.startswith("docs/")
    if role == "evaluation_case":
        return path.startswith("tests/fixtures/") and path.endswith(".jsonl")
    if role == "evaluation_result":
        return path.startswith("tests/fixtures/") or path.startswith(".holusight/improvement-runs/")
    return False


def _status_classification(path: Path) -> str | None:
    """Read only the structured ``**Status:**`` marker, never prose inference."""
    if path.suffix.lower() != ".md":
        return None
    match = re.search(
        r"^\*\*Status:\*\*\s*([^\n]+)$", path.read_text(encoding="utf-8"), re.MULTILINE
    )
    if not match:
        return None
    normalized = match.group(1).strip().lower().replace("-", "_").replace(" ", "_")
    return normalized if normalized in CLASSIFICATIONS else None


def _placement(repo_root: Path, artifact_type: str, raw_path: str) -> list[dict[str, str]]:
    roots = {
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
    }
    if artifact_type not in roots:
        return [_blocked("invalid_artifact_type", artifact_type)]
    relative = _safe_relative(repo_root, raw_path)
    if relative is None:
        return [_blocked("misplaced_artifact", raw_path)]
    path = relative.as_posix()
    in_root = any(path.startswith(root + "/") for root in roots[artifact_type])
    if artifact_type == "spec":
        in_root = in_root and relative.parent == Path("specs")
    elif artifact_type == "test":
        in_root = in_root and relative.parent == Path("tests") and relative.name.startswith("test_")
    elif artifact_type == "docs":
        in_root = path in {"docs/README.md", "docs/vision.md", "docs/roadmap.md"}
    if not in_root:
        return [_blocked("misplaced_artifact", path)]
    if (repo_root / relative).exists():
        return [_blocked("duplicate_artifact", path)]
    for root in roots[artifact_type]:
        candidate_root = repo_root / root
        if candidate_root.exists() and any(
            p.is_file() and p.name == relative.name for p in candidate_root.rglob("*")
        ):
            return [_blocked("duplicate_artifact", path)]
    return []


def _review_links(
    repo_root: Path, manifest: dict[str, Any]
) -> tuple[list[dict[str, str]], list[str]]:
    blockers: list[dict[str, str]] = []
    missing: list[str] = []
    links = manifest.get("links", {})
    if not isinstance(links, dict):
        return [_blocked("invalid_links", "links must be an object")], list(LINK_ROLES)
    classification = manifest["classification"]
    requires_full_evidence = classification in {"accepted", "implemented", "evaluated"}
    hashes = manifest.get("link_hashes", {})
    if not isinstance(hashes, dict):
        blockers.append(_blocked("invalid_link_hashes", "link_hashes must be an object"))
        hashes = {}

    seen: dict[str, str] = {}
    for role in LINK_ROLES:
        paths = links.get(role, [])
        if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
            blockers.append(_blocked("invalid_link_role", role, role=role))
            continue
        if requires_full_evidence and not paths:
            missing.append(role)
            blockers.append(_blocked(f"missing_{role}", role, role=role))
        for raw_path in paths:
            relative = _safe_relative(repo_root, raw_path)
            if relative is None:
                blockers.append(_blocked("unsafe_link", raw_path, role=role))
                continue
            path = relative.as_posix()
            if path in seen:
                blockers.append(_blocked("duplicate_link", path, role=role))
                if seen[path] != role:
                    blockers.append(_blocked("wrong_link_role", path, role=role))
            else:
                seen[path] = role
            if not _role_path_is_canonical(role, path):
                blockers.append(_blocked("wrong_link_role", path, role=role))
            full_path = repo_root / relative
            if not full_path.is_file():
                blockers.append(_blocked(f"dangling_{role}", path, role=role))
                continue
            expected_hash = hashes.get(path)
            if requires_full_evidence and not expected_hash:
                blockers.append(_blocked("missing_link_hash", path, role=role))
            elif expected_hash and expected_hash != _sha256(full_path):
                blockers.append(_blocked("stale_link", path, role=role))
            if role == "governing":
                doc_classification = _status_classification(full_path)
                if doc_classification and doc_classification != classification:
                    blockers.append(
                        _blocked(
                            "contradictory_classification",
                            f"{path}:{doc_classification}",
                            role=role,
                        )
                    )

    explicit_evidence = manifest.get("classification_evidence")
    if explicit_evidence is not None:
        if explicit_evidence not in CLASSIFICATIONS or explicit_evidence != classification:
            blockers.append(_blocked("contradictory_classification", str(explicit_evidence)))
    if requires_full_evidence:
        sections = manifest.get("structured_sections", [])
        if not isinstance(sections, list) or not _REQUIRED_SECTIONS <= set(sections):
            blockers.append(_blocked("missing_structured_section", "context,evidence,decision"))
    return blockers, missing


def _stage(classification: str, links: dict[str, Any], blockers: list[dict[str, str]]) -> str:
    if classification in {"research_only", "rejected", "superseded"}:
        return classification
    if classification == "proposed":
        return "proposed"
    implementation = links.get("implementation") or []
    all_roles_present = all(links.get(role) for role in LINK_ROLES)
    integrity_codes = {item["code"] for item in blockers}
    if all_roles_present and not any(
        code.startswith(("missing_", "dangling_", "stale_", "unsafe_", "wrong_", "duplicate_"))
        for code in integrity_codes
    ):
        return "evaluated"
    if implementation:
        return "implemented"
    return "accepted"


def _history_records(repo_root: Path, change_id: str) -> list[dict[str, Any]]:
    records_dir = repo_root / ".holusight" / "improvement-runs" / change_id
    records: list[dict[str, Any]] = []
    if not records_dir.is_dir():
        return records
    for path in sorted(records_dir.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if record.get("schema_version") == RECORD_SCHEMA and record.get("change_id") == change_id:
            records.append(record)
    return records


def _research_packet(
    blockers: list[dict[str, str]], history: list[dict[str, Any]], evidence_state: str
) -> dict[str, str] | None:
    codes = {item["code"] for item in blockers}
    if {"contradictory_classification", "wrong_link_role"} & codes:
        return {
            "reason": "contradictory_evidence",
            "recommended_research": "normal_review",
            "question": (
                "Which tracked canonical reference resolves the contradictory classification "
                "or link role?"
            ),
            "external_action": "not_launched",
        }
    if any(code.startswith(("missing_", "dangling_", "stale_", "unsafe_")) for code in codes):
        return {
            "reason": "materially_incomplete_evidence",
            "recommended_research": "normal_review",
            "question": (
                "Which repository-owned artifact supplies the missing or current deterministic "
                "evidence?"
            ),
            "external_action": "not_launched",
        }
    if evidence_state == "unfamiliar":
        return {
            "reason": "unfamiliar_evidence",
            "recommended_research": "normal_review",
            "question": (
                "Which local, deterministic evidence source can make this unfamiliar finding "
                "reproducible?"
            ),
            "external_action": "not_launched",
        }
    if len(history) >= 2:
        last_two = history[-2:]
        if all(record.get("outcome") == "blocked" for record in last_two):
            return {
                "reason": "repeated_stagnation",
                "recommended_research": "gpt_deep_research",
                "question": (
                    "What deterministic, repository-local evidence would distinguish the repeated "
                    "blocked candidate from its status-quo control?"
                ),
                "external_action": "not_launched",
            }
    return None


def _next_action(phase: str, blockers: list[dict[str, str]], classification: str) -> str:
    codes = {item["code"] for item in blockers}
    if classification in {"research_only", "rejected", "superseded"}:
        return "retain_as_non_authoritative_record"
    if {"duplicate_artifact", "misplaced_artifact", "invalid_artifact_type"} & codes:
        return "resolve_placement"
    if blockers:
        return "add_required_evidence"
    return {
        "before_change": "implement_change",
        "after_implementation": "run_deterministic_tests",
        "after_test": "run_pre_promotion_review",
        "pre_promotion": "human_promotion_review",
    }[phase]


def _record_review(
    repo_root: Path, manifest: dict[str, Any], review: dict[str, Any], phase: str
) -> dict[str, str]:
    change_id = manifest["change_id"]
    directory = repo_root / ".holusight" / "improvement-runs" / change_id
    directory.mkdir(parents=True, exist_ok=True)
    existing = _history_records(repo_root, change_id)
    metadata_hash = _json_hash(manifest)
    outcome = "ready" if review["next_permitted_action"] == "human_promotion_review" else "blocked"
    record = {
        "schema_version": RECORD_SCHEMA,
        "record_id": f"{change_id}-{len(existing) + 1}",
        "change_id": change_id,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "phase": phase,
        "classification": review["classification"],
        "stage": review["stage"],
        "outcome": outcome,
        "metadata_hash": metadata_hash,
        "link_hashes": dict(manifest.get("link_hashes", {})),
        "references": {role: list(manifest.get("links", {}).get(role, [])) for role in LINK_ROLES},
        "lineage": dict(manifest.get("lineage", {})),
        "blocker_codes": [item["code"] for item in review["blockers"]],
    }
    path = directory / f"{len(existing) + 1:04d}-{phase}.json"
    path.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return {"path": str(path.relative_to(repo_root)), "schema_version": RECORD_SCHEMA}


def review_change(
    repo_root: Path, change_path: str, *, phase: str = "before_change", record: bool = False
) -> dict[str, Any]:
    """Review one tracked manifest without egress or canonical writes."""
    if phase not in PHASES:
        raise ValueError(f"phase must be one of {PHASES}")
    manifest, manifest_relative = _load_manifest(repo_root, change_path)
    blockers, missing = _review_links(repo_root, manifest)
    for artifact in manifest.get("proposed_artifacts", []):
        if not isinstance(artifact, dict):
            blockers.append(_blocked("invalid_proposed_artifact", "entry must be an object"))
            continue
        artifact_type = artifact.get("artifact_type")
        raw_path = artifact.get("path")
        if not isinstance(artifact_type, str) or not isinstance(raw_path, str):
            blockers.append(
                _blocked("invalid_proposed_artifact", "artifact_type and path are required")
            )
            continue
        blockers.extend(_placement(repo_root, artifact_type, raw_path))
        if raw_path in _EVALUATOR_PATHS:
            blockers.append(_blocked("evaluator_mutation", raw_path))

    # Stable ordering makes results and derived records comparable across runs.
    blockers = sorted(
        blockers, key=lambda item: (item["code"], item.get("role", ""), item["evidence"])
    )
    links = manifest.get("links", {})
    stage = _stage(manifest["classification"], links, blockers)
    existing_history = _history_records(repo_root, manifest["change_id"])
    next_action = _next_action(phase, blockers, manifest["classification"])
    review = {
        "change_id": manifest["change_id"],
        "change_path": str(manifest_relative),
        "classification": manifest["classification"],
        "stage": stage,
        "phase": phase,
        "missing_evidence": missing,
        "blockers": blockers,
        "next_permitted_action": next_action,
        "promotion": {
            "allowed": False,
            "status": "human_review_required",
            "blockers": (
                ["human_promotion_required"]
                if not blockers
                else [item["code"] for item in blockers] + ["human_promotion_required"]
            ),
        },
    }
    payload: dict[str, Any] = {
        "review": review,
        "research_needed": _research_packet(
            blockers, existing_history, manifest.get("evidence_state", "familiar")
        ),
        "safety": {
            "external_egress": "denied",
            "automatic_promotion": "denied",
            "evaluator_mutation": "blocked"
            if any(b["code"] == "evaluator_mutation" for b in blockers)
            else "not_requested",
            "raw_private_export": "denied",
        },
    }
    if record:
        payload["record"] = _record_review(repo_root, manifest, review, phase)
    return payload


def review_history(repo_root: Path, change_id: str) -> dict[str, Any]:
    if not _CHANGE_ID_RE.fullmatch(change_id):
        raise ValueError("change_id must be a lowercase stable slug")
    records = _history_records(repo_root, change_id)
    return {
        "history": {
            "change_id": change_id,
            "records_total": len(records),
            "records": [
                {
                    key: record.get(key)
                    for key in (
                        "record_id",
                        "phase",
                        "classification",
                        "stage",
                        "outcome",
                        "metadata_hash",
                        "blocker_codes",
                    )
                }
                for record in records
            ],
            "derived_state": ".holusight/improvement-runs/",
            "delete_rebuild": (
                "safe_to_delete; rerun improve-review --record without changing canonical truth"
            ),
        }
    }


def integration_review(repo_root: Path, change_path: str, *, phase: str) -> dict[str, Any]:
    """Stable, local-only payload intended for a future consumer, not a Fleet integration."""
    payload = review_change(repo_root, change_path, phase=phase, record=False)
    return {
        "integration_contract": INTEGRATION_SCHEMA,
        "consumer": "local_advisory_only",
        "integration_complete": False,
        **payload,
    }
