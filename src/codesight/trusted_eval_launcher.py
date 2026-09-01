"""Launch a pinned evaluator only under an external, one-shot acceptance authority.

The candidate repository is evidence, never authority. The acceptance record lives
outside the candidate worktree and is authenticated by a capability held only by
this launcher process. No evaluator module is imported into this process.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import hmac
import json
import os
import re
import resource
import secrets
import shutil
import signal
import stat
import struct
import subprocess
import sys
import sysconfig
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

ACCEPTANCE_SCHEMA = "holus-external-evaluator-acceptance/v2"
AUTHORITY_SCHEMA = "holus-supervisor-evaluator-authority/v2"
REPLAY_STATE_SCHEMA = "holus-supervisor-replay-state/v1"
PREPARED_SCHEMA = "holus-prepared-trusted-evaluation/v1"
FINALIZATION_SCHEMA = "holus-trusted-evaluation-finalization/v2"
PIN_SCHEMA = "holus-evaluator-subject-pin/v1"
RECEIPT_SCHEMA = "holus-trusted-evaluation-receipt/v1"
PROTOCOL_REVISION = "holus-g2-external-acceptance/v2"
LAUNCHER_PATH = "src/codesight/trusted_eval_launcher.py"
EVALUATOR_PATHS = (
    "src/codesight/control_storage.py",
    "src/codesight/eval_pilot.py",
    LAUNCHER_PATH,
)
CANONICAL_CASES_PATH = "tests/fixtures/holusight_eval_pilot_cases.jsonl"
PROTOCOL_PIN_PATH = "specs/023-g2-external-acceptance.protocol.json"
_OID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_KEY_ID = re.compile(r"^[A-Za-z0-9._/-]{1,80}$")
_MAX_AUTHORITY_BYTES = 1_048_576
_MAX_ACCEPTANCE_LIFETIME = 3_600
_SAFE_GIT_CONFIG = (
    ("core.fsmonitor", "false"),
    ("core.hooksPath", os.devnull),
    ("core.sshCommand", "false"),
    ("credential.helper", ""),
    ("diff.external", ""),
    ("interactive.diffFilter", ""),
    ("pager.config", "false"),
    ("pager.diff", "false"),
    ("pager.log", "false"),
    ("pager.show", "false"),
)
_AUTHORITY_CONSTRUCTOR_SEAL = object()
_CANDIDATE_ADAPTER = r"""
import json
import os
import sys
import tempfile
import types
from pathlib import Path

package = types.ModuleType("codesight")
package.__path__ = [sys.argv.pop(1)]
package.__package__ = "codesight"
sys.modules["codesight"] = package
payload = json.load(sys.stdin)
operation = payload["operation"]
if operation == "display":
    from codesight import axi_providers, cli_axi

    results = []
    for name in axi_providers.MODE_PROVIDERS["auto"]:
        items = [
            axi_providers.EvidenceItem(
                provider=name,
                source=f"synthetic/{name}.txt",
                location=f"L{index + 1}",
                excerpt="synthetic fixture item",
            )
            for index in range(payload["counts"].get(name, 0))
        ]
        results.append(
            axi_providers.ProviderResult(
                provider=name,
                state=axi_providers.ProviderState.OK,
                detail="synthetic fixture",
                route_reason="synthetic fixture",
                items=items,
            )
        )
    selected = cli_axi._select_display_items(results, payload["cap"])
    output = {"providers": [item.provider for item in selected]}
elif operation == "dangling":
    from codesight import consistency

    _edges, dangling = consistency.extract_exact_references(payload["doc_path"], Path.cwd())
    output = {"is_dangling": payload["expected_token"] in dangling}
elif operation == "refresh_check":
    from codesight import consistency

    with tempfile.TemporaryDirectory(prefix="holus-eval-pilot-") as temporary:
        root = Path(temporary)
        spec_path = root / "specs" / "001-alpha.md"
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(payload["spec_body"], encoding="utf-8")
        impl_path = root / "src" / "pkg" / "mod.py"
        impl_path.parent.mkdir(parents=True, exist_ok=True)
        impl_path.write_text(payload["impl_body"], encoding="utf-8")
        consistency.refresh(root)
        report = consistency.check_consistency(root, "specs/001-alpha.md")
    output = {"status": report.status.value}
elif operation == "no_egress":
    from codesight import axi_providers

    sentinel = "sk-eval-pilot-sentinel-value"
    saved = os.environ.get("VOYAGE_API_KEY")
    os.environ["VOYAGE_API_KEY"] = sentinel
    try:
        with axi_providers._no_egress_env():
            stripped = "VOYAGE_API_KEY" not in os.environ
        restored = os.environ.get("VOYAGE_API_KEY") == sentinel
    finally:
        if saved is None:
            os.environ.pop("VOYAGE_API_KEY", None)
        else:
            os.environ["VOYAGE_API_KEY"] = saved
    output = {"stripped": stripped, "restored": restored}
else:
    raise ValueError("unsupported candidate adapter operation")
print(json.dumps(output, sort_keys=True))
"""
_BOOTSTRAP = r"""
import importlib
import sys
import types

package = types.ModuleType("codesight")
package.__path__ = [sys.argv.pop(1)]
package.__package__ = "codesight"
sys.modules["codesight"] = package
module = importlib.import_module("codesight.eval_pilot")
raise SystemExit(module.main())
"""


class _DuplicateKey(ValueError):
    pass


def _closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_json(raw: bytes, *, label: str) -> dict[str, Any]:
    if len(raw) > _MAX_AUTHORITY_BYTES:
        raise ValueError(f"{label} exceeded the byte limit")
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_closed_object)
    except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateKey) as exc:
        raise ValueError(f"{label} is not unambiguous JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _require_keys(payload: dict[str, Any], expected: set[str], *, label: str) -> None:
    if set(payload) != expected:
        missing = sorted(expected - set(payload))
        extra = sorted(set(payload) - expected)
        raise ValueError(f"{label} fields are not closed (missing={missing}, extra={extra})")


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _canonical_git_env() -> dict[str, str]:
    """Build a Git environment with every executable config surface disabled."""
    env = {"PATH": os.defpath, "LANG": "C", "LC_ALL": "C"}
    env.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_COUNT": str(len(_SAFE_GIT_CONFIG)),
            "GIT_GRAFT_FILE": os.devnull,
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    for index, (key, value) in enumerate(_SAFE_GIT_CONFIG):
        env[f"GIT_CONFIG_KEY_{index}"] = key
        env[f"GIT_CONFIG_VALUE_{index}"] = value
    return env


def _git(
    repo: Path, *args: str, input_bytes: bytes | None = None
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "--no-replace-objects", "-C", str(repo), *args],
        input=input_bytes,
        capture_output=True,
        check=False,
        env=_canonical_git_env(),
    )


def _oid(repo: Path, revision: str) -> str | None:
    completed = _git(repo, "rev-parse", "--verify", revision)
    value = completed.stdout.decode("ascii", errors="ignore").strip()
    return value if completed.returncode == 0 and _OID.fullmatch(value) else None


def _blob_oid_for_bytes(repo: Path, content: bytes) -> str | None:
    completed = _git(repo, "hash-object", "--stdin", input_bytes=content)
    value = completed.stdout.decode("ascii", errors="ignore").strip()
    return value if completed.returncode == 0 and _OID.fullmatch(value) else None


def _git_blob_bytes(repo: Path, blob: str, *, label: str) -> bytes:
    if not _OID.fullmatch(blob):
        raise ValueError(f"{label} blob identity is invalid")
    loaded = _git(repo, "cat-file", "blob", blob)
    if loaded.returncode != 0 or _blob_oid_for_bytes(repo, loaded.stdout) != blob:
        raise ValueError(f"{label} blob bytes cannot be verified")
    return loaded.stdout


def _regular_bytes(path: Path, *, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        return _bounded_regular_fd_bytes(fd, label=label)
    finally:
        os.close(fd)


def _bounded_regular_fd_bytes(fd: int, *, label: str) -> bytes:
    metadata = os.fstat(fd)
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{label} must be a regular file")
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = os.read(fd, 65_536)
        if not chunk:
            break
        size += len(chunk)
        if size > _MAX_AUTHORITY_BYTES:
            raise ValueError(f"{label} exceeded the byte limit")
        chunks.append(chunk)
    return b"".join(chunks)


def _candidate_owner_uid(repo: Path) -> int:
    return os.stat(repo, follow_symlinks=False).st_uid


def _read_supervisor_descriptor(
    fd: int,
    *,
    label: str,
    candidate_uid: int,
    expected_owner: int | None = None,
) -> tuple[bytes, int]:
    """Read and close one supervisor-owned, held, immutable regular descriptor."""
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"{label} must be a supervisor-owned regular descriptor")
        if metadata.st_uid == candidate_uid:
            raise ValueError(f"{label} is requester-mintable")
        if expected_owner is not None and metadata.st_uid != expected_owner:
            raise ValueError(f"{label} has a different supervisor owner")
        if metadata.st_mode & 0o222:
            raise ValueError(f"{label} must be immutable while held by the launcher")
        return _bounded_regular_fd_bytes(fd, label=label), metadata.st_uid
    finally:
        os.close(fd)


def _validate_authority(payload: dict[str, Any]) -> tuple[str, str, bytes, int, int, str]:
    _require_keys(
        payload,
        {
            "schema_version",
            "authority_version",
            "protocol_revision",
            "authority_id",
            "key_id",
            "key_hex",
            "acceptance_record_sha256",
            "replay_epoch",
            "replay_sequence",
        },
        label="supervisor authority",
    )
    if (
        payload["schema_version"] != AUTHORITY_SCHEMA
        or type(payload["authority_version"]) is not int
        or payload["authority_version"] != 2
        or payload["protocol_revision"] != PROTOCOL_REVISION
    ):
        raise ValueError("supervisor authority protocol is unsupported")
    authority_id = payload["authority_id"]
    key_id = payload["key_id"]
    key_hex = payload["key_hex"]
    digest = payload["acceptance_record_sha256"]
    epoch = payload["replay_epoch"]
    sequence = payload["replay_sequence"]
    if not isinstance(authority_id, str) or not _KEY_ID.fullmatch(authority_id):
        raise ValueError("supervisor authority identity is invalid")
    if not isinstance(key_id, str) or not _KEY_ID.fullmatch(key_id):
        raise ValueError("supervisor key identity is invalid")
    if not isinstance(key_hex, str) or not re.fullmatch(r"[0-9a-f]{64,128}", key_hex):
        raise ValueError("supervisor authentication key is invalid")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise ValueError("supervisor authority record digest is invalid")
    if type(epoch) is not int or epoch < 1 or type(sequence) is not int or sequence < 1:
        raise ValueError("supervisor authority replay identity is invalid")
    return authority_id, key_id, bytes.fromhex(key_hex), epoch, sequence, digest


class _AuthenticatedLaunch:
    """Process-local one-use authority minted only after supervisor replay consumption."""

    __slots__ = (
        "_candidate_uid",
        "_marker_fd",
        "_marker_sha256",
        "_nonce",
        "_phase",
        "_supervisor_uid",
        "acceptance_digest",
        "authority_id",
        "configuration_digest",
        "expires_at",
        "replay_epoch",
        "replay_sequence",
    )

    def __init__(
        self,
        seal: object,
        *,
        authority_id: str,
        acceptance_digest: str,
        replay_epoch: int,
        replay_sequence: int,
        expires_at: int,
        marker_fd: int,
        marker_sha256: str,
        supervisor_uid: int,
        candidate_uid: int,
    ) -> None:
        if seal is not _AUTHORITY_CONSTRUCTOR_SEAL:
            raise TypeError("authenticated launch capabilities are launcher-minted only")
        self._candidate_uid = candidate_uid
        self._marker_fd = marker_fd
        self._marker_sha256 = marker_sha256
        self._nonce = secrets.token_bytes(32)
        self._phase = "authenticated"
        self._supervisor_uid = supervisor_uid
        self.authority_id = authority_id
        self.acceptance_digest = acceptance_digest
        self.replay_epoch = replay_epoch
        self.replay_sequence = replay_sequence
        self.expires_at = expires_at
        self.configuration_digest: str | None = None

    def _validate_marker(self, repo: Path) -> None:
        if self._marker_fd < 0 or _candidate_owner_uid(repo) != self._candidate_uid:
            raise ValueError("authenticated launch capability is not bound to this requester")
        metadata = os.fstat(self._marker_fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != self._supervisor_uid
            or metadata.st_uid == self._candidate_uid
            or metadata.st_mode & 0o222
        ):
            raise ValueError("authenticated launch capability is requester-mintable")
        marker = _bounded_regular_fd_bytes(self._marker_fd, label="replay capability marker")
        if not hmac.compare_digest(_sha256(marker), self._marker_sha256):
            raise ValueError("authenticated launch capability marker changed")

    def authorize_receipt_construction(self, repo: Path) -> None:
        if self._phase != "authenticated":
            raise ValueError("authenticated launch capability was already consumed")
        self._validate_marker(repo)
        if int(time.time()) >= self.expires_at:
            raise ValueError("acceptance expired during evaluation")
        self._phase = "constructed"

    def consume_for_persistence(self, repo: Path) -> None:
        if self._phase != "constructed":
            raise ValueError("authenticated launch capability cannot persist a receipt")
        self._validate_marker(repo)
        if int(time.time()) >= self.expires_at:
            raise ValueError("acceptance expired during evaluation")
        self._phase = "consumed"
        self._nonce = b""
        os.close(self._marker_fd)
        self._marker_fd = -1

    def __del__(self) -> None:
        marker_fd = getattr(self, "_marker_fd", -1)
        if marker_fd >= 0:
            try:
                os.close(marker_fd)
            except OSError:
                pass


def _consume_replay(
    fd: int,
    *,
    supervisor_uid: int,
    candidate_uid: int,
    authority_id: str,
    record_digest: str,
    replay_epoch: int,
    replay_sequence: int,
    expires_at: int,
) -> _AuthenticatedLaunch:
    """Atomically burn one replay identity in a held supervisor state directory."""
    marker_fd: int | None = None
    metadata = os.fstat(fd)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != supervisor_uid
        or metadata.st_uid == candidate_uid
        or metadata.st_mode & 0o077
    ):
        raise ValueError("replay state must be a private supervisor-owned directory descriptor")
    identity = _canonical_bytes(
        {
            "authority_id": authority_id,
            "record_sha256": record_digest,
            "replay_epoch": replay_epoch,
            "replay_sequence": replay_sequence,
        }
    )
    marker_name = "replay-" + hashlib.sha256(identity).hexdigest() + ".used"
    capability: _AuthenticatedLaunch | None = None
    try:
        if int(time.time()) >= expires_at:
            raise ValueError("acceptance record is stale")
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            marker_fd = os.open(marker_name, flags, 0o400, dir_fd=fd)
        except FileExistsError as exc:
            raise ValueError("acceptance replay identity was already consumed") from exc
        marker = _canonical_bytes(
            {
                "schema_version": REPLAY_STATE_SCHEMA,
                "authority_id": authority_id,
                "record_sha256": record_digest,
                "replay_epoch": replay_epoch,
                "replay_sequence": replay_sequence,
                "consumed_at": int(time.time()),
            }
        )
        written = os.write(marker_fd, marker)
        if written != len(marker):
            raise ValueError("supervisor replay marker could not be persisted")
        os.fsync(marker_fd)
        os.fsync(fd)
        capability = _AuthenticatedLaunch(
            _AUTHORITY_CONSTRUCTOR_SEAL,
            authority_id=authority_id,
            acceptance_digest=record_digest,
            replay_epoch=replay_epoch,
            replay_sequence=replay_sequence,
            expires_at=expires_at,
            marker_fd=marker_fd,
            marker_sha256=_sha256(marker),
            supervisor_uid=supervisor_uid,
            candidate_uid=candidate_uid,
        )
        marker_fd = None
    finally:
        if marker_fd is not None:
            os.close(marker_fd)
        os.close(fd)
    if capability is None:
        raise ValueError("supervisor replay capability was not created")
    return capability


def _validate_acceptance_shape(payload: dict[str, Any]) -> None:
    _require_keys(
        payload,
        {
            "schema_version",
            "record_version",
            "authority",
            "candidate",
            "evaluator",
            "launcher",
            "manifest",
            "corpus",
            "configuration",
            "decision",
            "replay",
            "attestation",
        },
        label="acceptance record",
    )
    if (
        payload["schema_version"] != ACCEPTANCE_SCHEMA
        or type(payload["record_version"]) is not int
        or payload["record_version"] != 2
    ):
        raise ValueError("acceptance record version is unsupported")
    closed = {
        "authority": {"authority_id", "protocol_revision"},
        "candidate": {"commit", "tree"},
        "evaluator": {"pin_blob", "pin_sha256", "identity_sha256"},
        "launcher": {"path", "blob", "sha256"},
        "manifest": {"path", "blob", "sha256"},
        "corpus": {"path", "blob", "sha256"},
        "configuration": {
            "identity_sha256",
            "cases_path",
            "egress_allowed",
            "semantic_allowed",
            "candidate_id",
            "workflow",
            "tool",
            "model",
            "compare_result_path",
            "compare_result_sha256",
        },
        "replay": {"replay_version", "epoch", "sequence", "issued_at", "expires_at"},
        "attestation": {"algorithm", "authority_id", "key_id", "payload_sha256", "mac"},
    }
    for name, expected in closed.items():
        value = payload[name]
        if not isinstance(value, dict):
            raise ValueError(f"acceptance record {name} must be an object")
        _require_keys(value, expected, label=f"acceptance record {name}")


def _unsigned_acceptance(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "attestation"}


def _validate_attestation(
    acceptance: dict[str, Any], authority: dict[str, Any], raw: bytes
) -> tuple[str, str, int, int, int]:
    authority_id, key_id, key, epoch, sequence, expected_digest = _validate_authority(authority)
    if raw != _canonical_bytes(acceptance):
        raise ValueError("acceptance record bytes are ambiguous or noncanonical")
    record_digest = _sha256(raw)
    if record_digest != expected_digest:
        raise ValueError("acceptance record was substituted or rolled back")
    if acceptance["authority"] != {
        "authority_id": authority_id,
        "protocol_revision": PROTOCOL_REVISION,
    }:
        raise ValueError("acceptance record names a different supervisor authority")
    replay = acceptance["replay"]
    if (
        type(replay["replay_version"]) is not int
        or replay["replay_version"] != 1
        or type(replay["epoch"]) is not int
        or replay["epoch"] != epoch
        or type(replay["sequence"]) is not int
        or replay["sequence"] != sequence
    ):
        raise ValueError("acceptance record replay version was rolled back or substituted")
    attestation = acceptance["attestation"]
    unsigned = _canonical_bytes(_unsigned_acceptance(acceptance))
    payload_digest = _sha256(unsigned)
    expected_mac = hmac.new(key, unsigned, hashlib.sha256).hexdigest()
    if (
        attestation["algorithm"] != "hmac-sha256-supervisor-fd-v2"
        or attestation["authority_id"] != authority_id
        or attestation["key_id"] != key_id
        or attestation["payload_sha256"] != payload_digest
        or not isinstance(attestation["mac"], str)
        or not hmac.compare_digest(attestation["mac"], expected_mac)
    ):
        raise ValueError("acceptance record attestation is absent or invalid")
    now = int(time.time())
    issued = replay["issued_at"]
    expires = replay["expires_at"]
    if (
        type(issued) is not int
        or type(expires) is not int
        or issued > now
        or expires <= now
        or expires <= issued
        or expires - issued > _MAX_ACCEPTANCE_LIFETIME
    ):
        raise ValueError("acceptance record is stale")
    if acceptance["decision"] != "accepted":
        raise ValueError("acceptance decision does not authorize evaluation")
    return record_digest, authority_id, epoch, sequence, expires


def _require_oid(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _OID.fullmatch(value):
        raise ValueError(f"{label} is invalid")
    return value


def _require_sha(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{label} is invalid")
    return value


def _validate_pin(repo: Path, acceptance: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    evaluator = acceptance["evaluator"]
    pin_blob = _require_oid(evaluator["pin_blob"], label="evaluator pin blob")
    pin_bytes = _git_blob_bytes(repo, pin_blob, label="evaluator pin")
    if _sha256(pin_bytes) != _require_sha(evaluator["pin_sha256"], label="pin digest"):
        raise ValueError("evaluator pin bytes do not match acceptance")
    pin = _strict_json(pin_bytes, label="evaluator pin")
    _require_keys(
        pin,
        {
            "schema_version",
            "protocol_revision",
            "subject",
            "evaluator_blobs",
            "protocol_path",
            "protocol_blob",
            "corpus_path",
            "corpus_blob",
        },
        label="evaluator pin",
    )
    if pin["schema_version"] != PIN_SCHEMA:
        raise ValueError("evaluator pin schema is invalid")
    if pin["protocol_revision"] != PROTOCOL_REVISION:
        raise ValueError("evaluator pin does not match the reviewed G2 protocol revision")
    subject = pin["subject"]
    blobs = pin["evaluator_blobs"]
    if not isinstance(subject, dict) or not isinstance(blobs, dict):
        raise ValueError("evaluator pin identity is incomplete")
    _require_keys(
        subject,
        {"repository_id", "commit", "tree", "clean", "branch"},
        label="evaluator subject",
    )
    if set(blobs) != set(EVALUATOR_PATHS) or subject["clean"] is not True:
        raise ValueError("evaluator pin closed identity is invalid")
    commit = _require_oid(subject["commit"], label="evaluator subject commit")
    tree = _require_oid(subject["tree"], label="evaluator subject tree")
    if _oid(repo, f"{commit}^{{tree}}") != tree:
        raise ValueError("evaluator subject tree does not resolve")
    protocol_path = pin["protocol_path"]
    protocol_blob = _require_oid(pin["protocol_blob"], label="G2 protocol pin blob")
    if protocol_path != PROTOCOL_PIN_PATH or _oid(repo, f"{commit}:{protocol_path}") != protocol_blob:
        raise ValueError("G2 protocol pin does not match the evaluator subject")
    protocol = _strict_json(_git_blob_bytes(repo, protocol_blob, label="G2 protocol pin"), label="G2 protocol pin")
    _require_keys(
        protocol,
        {
            "schema_version",
            "protocol_revision",
            "acceptance_schema",
            "authority_schema",
            "replay_state_schema",
            "prepared_evaluation_schema",
            "finalization_schema",
            "receipt_schema",
            "authority_owner",
            "authority_transport",
            "acceptance_transport",
            "replay_transport",
            "replay_consumption",
            "candidate_import_sandbox",
            "network_egress",
            "semantic_provider",
            "promotion",
            "canonical_cases_path",
            "evaluator_paths",
        },
        label="G2 protocol pin",
    )
    if protocol != {
        "schema_version": "holus-g2-protocol-pin/v1",
        "protocol_revision": PROTOCOL_REVISION,
        "acceptance_schema": ACCEPTANCE_SCHEMA,
        "authority_schema": AUTHORITY_SCHEMA,
        "replay_state_schema": REPLAY_STATE_SCHEMA,
        "prepared_evaluation_schema": PREPARED_SCHEMA,
        "finalization_schema": FINALIZATION_SCHEMA,
        "receipt_schema": RECEIPT_SCHEMA,
        "authority_owner": "distinct_from_candidate_worktree_owner",
        "authority_transport": "held_immutable_regular_descriptor",
        "acceptance_transport": "held_immutable_regular_descriptor",
        "replay_transport": "held_private_directory_descriptor",
        "replay_consumption": "atomic_create_only_marker",
        "candidate_import_sandbox": "required_fail_closed",
        "network_egress": "denied",
        "semantic_provider": "denied",
        "promotion": "denied",
        "canonical_cases_path": CANONICAL_CASES_PATH,
        "evaluator_paths": list(EVALUATOR_PATHS),
    }:
        raise ValueError("G2 protocol pin bytes are unsupported")
    identity_payload = {
        "protocol_revision": pin["protocol_revision"],
        "subject": subject,
        "evaluator_blobs": blobs,
        "protocol_path": protocol_path,
        "protocol_blob": protocol_blob,
    }
    if _sha256(_canonical_bytes(identity_payload)) != _require_sha(
        evaluator["identity_sha256"], label="evaluator identity digest"
    ):
        raise ValueError("evaluator identity bytes do not match acceptance")
    for path, expected in blobs.items():
        _require_oid(expected, label=f"evaluator blob {path}")
        if _oid(repo, f"{commit}:{path}") != expected:
            raise ValueError(f"evaluator pin blob does not match subject: {path}")
    if pin["corpus_path"] != CANONICAL_CASES_PATH:
        raise ValueError("evaluator corpus path is not canonical")
    corpus_blob = _require_oid(pin["corpus_blob"], label="evaluator corpus blob")
    if _oid(repo, f"{commit}:{CANONICAL_CASES_PATH}") != corpus_blob:
        raise ValueError("evaluator corpus blob does not match subject")
    return pin, pin_bytes


def _worktree_bytes(repo: Path, relative: str, *, label: str) -> bytes:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} path escapes the candidate")
    full = repo / path
    try:
        return _regular_bytes(full, label=label)
    except OSError as exc:
        raise ValueError(f"{label} bytes are absent") from exc


def _validate_candidate_bindings(
    repo: Path,
    acceptance: dict[str, Any],
    pin: dict[str, Any],
    record_digest: str,
    *,
    cases_path: Path,
) -> tuple[str, str]:
    candidate = acceptance["candidate"]
    commit = _require_oid(candidate["commit"], label="candidate commit")
    tree = _require_oid(candidate["tree"], label="candidate tree")
    evaluator_commit = pin["subject"]["commit"]
    if evaluator_commit == commit:
        raise ValueError("acceptance record is self-referential")
    head = _oid(repo, "HEAD")
    if head != commit or _oid(repo, "HEAD^{tree}") != tree:
        raise ValueError("acceptance record is stale for the candidate commit/tree")
    status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    if status.returncode != 0 or status.stdout:
        raise ValueError("accepted candidate worktree is dirty")
    if _git(repo, "merge-base", "--is-ancestor", evaluator_commit, commit).returncode != 0:
        raise ValueError("accepted evaluator is not an ancestor of the candidate")

    for path, expected in (
        *pin["evaluator_blobs"].items(),
        (pin["protocol_path"], pin["protocol_blob"]),
        (pin["corpus_path"], pin["corpus_blob"]),
    ):
        committed = _oid(repo, f"{commit}:{path}")
        worktree = _blob_oid_for_bytes(repo, _worktree_bytes(repo, path, label=path))
        if committed != expected or worktree != expected:
            raise ValueError(f"accepted candidate substituted pinned bytes: {path}")

    corpus = acceptance["corpus"]
    if corpus["path"] != pin["corpus_path"] or corpus["blob"] != pin["corpus_blob"]:
        raise ValueError("accepted corpus identity was substituted")
    corpus_bytes = _git_blob_bytes(repo, pin["corpus_blob"], label="corpus")
    if _sha256(corpus_bytes) != _require_sha(corpus["sha256"], label="corpus digest"):
        raise ValueError("accepted corpus bytes do not match their digest")
    try:
        actual_cases = cases_path.resolve(strict=True).relative_to(repo).as_posix()
    except (OSError, ValueError) as exc:
        raise ValueError("cases path does not resolve inside the candidate") from exc
    if actual_cases != pin["corpus_path"]:
        raise ValueError("runtime corpus path differs from acceptance")

    manifest = acceptance["manifest"]
    manifest_path = Path(str(manifest["path"]))
    if (
        manifest_path.is_absolute()
        or ".." in manifest_path.parts
        or manifest_path.parent != Path("specs")
        or not manifest_path.name.endswith(".change.json")
    ):
        raise ValueError("accepted manifest path is invalid")
    relative_manifest = manifest_path.as_posix()
    manifest_blob = _require_oid(manifest["blob"], label="manifest blob")
    committed_manifest = _git_blob_bytes(repo, manifest_blob, label="manifest")
    if (
        _oid(repo, f"{commit}:{relative_manifest}") != manifest_blob
        or _blob_oid_for_bytes(repo, _worktree_bytes(repo, relative_manifest, label="manifest"))
        != manifest_blob
        or _sha256(committed_manifest)
        != _require_sha(manifest["sha256"], label="manifest digest")
    ):
        raise ValueError("accepted manifest bytes do not match candidate evidence")
    if (
        record_digest.encode("ascii") in committed_manifest
        or ACCEPTANCE_SCHEMA.encode() in committed_manifest
    ):
        raise ValueError("acceptance record and candidate manifest are self-referential")
    return commit, tree


def _validate_launcher(repo: Path, acceptance: dict[str, Any]) -> str:
    launcher = acceptance["launcher"]
    if launcher["path"] != LAUNCHER_PATH:
        raise ValueError("accepted launcher path is invalid")
    blob = _require_oid(launcher["blob"], label="launcher blob")
    accepted_bytes = _git_blob_bytes(repo, blob, label="launcher")
    running_path = Path(__file__).resolve(strict=True)
    running_bytes = _regular_bytes(running_path, label="running launcher")
    if (
        _blob_oid_for_bytes(repo, running_bytes) != blob
        or running_bytes != accepted_bytes
        or _sha256(running_bytes) != _require_sha(launcher["sha256"], label="launcher digest")
    ):
        raise ValueError("running launcher bytes were substituted")
    return blob


def _accepted_compare_identity(
    repo: Path, compare_result: Path | None
) -> tuple[str | None, str | None]:
    if compare_result is None:
        return None, None
    candidate = compare_result if compare_result.is_absolute() else repo / compare_result
    lexical = Path(os.path.abspath(candidate))
    try:
        resolved = candidate.resolve(strict=True)
        if lexical != resolved:
            raise ValueError("comparison result path is symbolic or ambiguous")
        relative = resolved.relative_to(repo).as_posix()
    except (OSError, ValueError) as exc:
        raise ValueError("comparison result does not resolve inside the candidate") from exc
    if not Path(relative).is_relative_to(Path(".holusight/improvement-results")):
        raise ValueError("comparison result is outside derived results storage")
    raw = _regular_bytes(resolved, label="comparison result")
    return relative, _sha256(raw)


def _validate_configuration(
    acceptance: dict[str, Any],
    *,
    repo: Path,
    cases_path: str,
    candidate_id: str,
    workflow: str,
    tool: str,
    model: str | None,
    compare_result: Path | None,
) -> str:
    configuration = acceptance["configuration"]
    compare_path, compare_sha256 = _accepted_compare_identity(repo, compare_result)
    expected = {
        "cases_path": cases_path,
        "egress_allowed": False,
        "semantic_allowed": False,
        "candidate_id": candidate_id,
        "workflow": workflow,
        "tool": tool,
        "model": model,
        "compare_result_path": compare_path,
        "compare_result_sha256": compare_sha256,
    }
    if (
        configuration["egress_allowed"] is not False
        or configuration["semantic_allowed"] is not False
        or any(configuration[key] != value for key, value in expected.items())
    ):
        raise ValueError("runtime configuration differs from acceptance")
    digest = _sha256(_canonical_bytes(expected))
    if digest != _require_sha(configuration["identity_sha256"], label="configuration digest"):
        raise ValueError("configuration identity bytes do not match acceptance")
    return digest


def _executable_variants(executable: Path) -> set[Path]:
    variants = {executable, executable.resolve()}
    link = executable
    for _ in range(8):
        if not link.is_symlink():
            break
        target = Path(os.readlink(link))
        link = target if target.is_absolute() else link.parent / target
        variants.add(link)
        variants.add(link.resolve())
    return variants


def _runtime_read_paths() -> list[Path]:
    executable = Path(sys.executable)
    candidates = {*_executable_variants(executable), Path(sys.prefix), Path(sys.base_prefix)}
    for key in ("stdlib", "platstdlib", "purelib", "platlib"):
        value = sysconfig.get_paths().get(key)
        if value:
            candidates.add(Path(value))
    if git_path := shutil.which("git"):
        candidates.update((Path(git_path).parent, Path(git_path).resolve().parent))
    for value in (
        "/System/Library",
        "/System/Cryptexes/OS",
        "/usr/bin",
        "/usr/lib",
        "/usr/libexec",
        "/usr/share/locale",
        "/bin",
        "/lib",
        "/lib64",
        "/etc/ssl",
        "/private/etc/ssl",
        "/private/etc/localtime",
        "/private/var/db/timezone",
        "/private/var/select/developer_dir",
        "/Library/Developer/CommandLineTools",
        "/nix/store",
    ):
        candidates.add(Path(value))
    existing = sorted(
        {variant for path in candidates if path.exists() for variant in (path, path.resolve())},
        key=lambda path: len(path.parts),
    )
    roots: list[Path] = []
    for path in existing:
        if not any(path == root or path.is_relative_to(root) for root in roots):
            roots.append(path)
    return roots


def _linux_no_child_process_filter(scratch: Path) -> int:
    machine = os.uname().machine.lower()
    architecture = {
        "x86_64": (0xC000003E, (56, 57, 58, 435), True),
        "amd64": (0xC000003E, (56, 57, 58, 435), True),
        "aarch64": (0xC00000B7, (220, 435), False),
        "arm64": (0xC00000B7, (220, 435), False),
    }.get(machine)
    if architecture is None:
        raise ValueError("candidate adapter cannot deny child processes on this architecture")
    audit_arch, syscall_numbers, deny_x32 = architecture
    instructions = [
        (0x20, 0, 0, 4),
        (0x15, 1, 0, audit_arch),
        (0x06, 0, 0, 0x80000000),
        (0x20, 0, 0, 0),
    ]
    if deny_x32:
        instructions.extend(
            ((0x45, 0, 1, 0x40000000), (0x06, 0, 0, 0x00050000 | errno.EPERM))
        )
    for number in syscall_numbers:
        instructions.extend(
            ((0x15, 0, 1, number), (0x06, 0, 0, 0x00050000 | errno.EPERM))
        )
    instructions.append((0x06, 0, 0, 0x7FFF0000))
    filter_path = scratch / "candidate-no-child-processes.bpf"
    filter_path.write_bytes(b"".join(struct.pack("=HBBI", *item) for item in instructions))
    fd = os.open(filter_path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    os.set_inheritable(fd, True)
    return fd


def _sandboxed_candidate_command(
    command: list[str], *, candidate_snapshot: Path, scratch: Path
) -> tuple[list[str], tuple[int, ...]]:
    readonly = list(
        dict.fromkeys(
            variant
            for path in (candidate_snapshot, *_runtime_read_paths())
            for variant in (path, path.resolve())
        )
    )
    scratch_paths = list(dict.fromkeys((scratch, scratch.resolve())))
    if sys.platform == "darwin":
        sandbox_exec = shutil.which("sandbox-exec")
        if sandbox_exec is None:
            raise ValueError("candidate adapter requires an OS-enforced sandbox")
        metadata = {Path("/")}
        for path in (*readonly, *scratch_paths):
            metadata.add(path)
            metadata.update(path.parents)
        rules = [
            "(version 1)",
            "(deny default)",
            *(
                f"(allow process-exec* (literal {json.dumps(str(path))}))"
                for path in sorted(_executable_variants(Path(sys.executable)), key=str)
            ),
            "(allow signal (target same-sandbox))",
            *(
                f"(allow file-read-metadata (literal {json.dumps(str(path))}))"
                for path in sorted(metadata, key=str)
            ),
            *(
                f"(allow file-read* ({'literal' if path.is_file() else 'subpath'} "
                f"{json.dumps(str(path))}))"
                for path in (*readonly, *scratch_paths)
            ),
            "(allow file-map-executable)",
            *(f"(allow file-write* (subpath {json.dumps(str(path))}))" for path in scratch_paths),
            '(allow file-read-data (literal "/"))',
            '(allow file-read* (literal "/dev/null"))',
            '(allow file-write-data (literal "/dev/null"))',
            '(allow file-ioctl (literal "/dev/null"))',
            '(allow file-read* (literal "/dev/random"))',
            '(allow file-read* (literal "/dev/urandom"))',
            "(allow sysctl-read)",
            "(allow mach-lookup)",
        ]
        profile = scratch / "candidate.sb"
        profile.write_text("\n".join(rules) + "\n", encoding="utf-8")
        return [sandbox_exec, "-f", str(profile), *command], ()
    if sys.platform.startswith("linux"):
        bwrap = shutil.which("bwrap")
        if bwrap is None:
            raise ValueError("candidate adapter requires an OS-enforced sandbox")
        seccomp_fd = _linux_no_child_process_filter(scratch)
        sandbox = [
            bwrap,
            "--die-with-parent",
            "--unshare-all",
            "--new-session",
            "--seccomp",
            str(seccomp_fd),
        ]
        for path in readonly:
            sandbox.extend(("--ro-bind", str(path), str(path)))
        sandbox.extend(
            (
                "--bind",
                str(scratch),
                str(scratch),
                "--dev",
                "/dev",
                "--proc",
                "/proc",
                "--chdir",
                str(candidate_snapshot),
            )
        )
        return [*sandbox, *command], (seccomp_fd,)
    raise ValueError("candidate adapter requires an OS-enforced sandbox")


def _candidate_limit_setter() -> None:
    for name, soft, hard in (
        ("RLIMIT_CORE", 0, 0),
        ("RLIMIT_CPU", 30, 31),
        ("RLIMIT_FSIZE", 1_048_576, 1_048_576),
        ("RLIMIT_NOFILE", 64, 64),
        ("RLIMIT_NPROC", 1024, 1024),
        ("RLIMIT_AS", 1_610_612_736, 1_610_612_736),
        ("RLIMIT_DATA", 1_610_612_736, 1_610_612_736),
    ):
        if sys.platform == "darwin" and name in {"RLIMIT_AS", "RLIMIT_DATA"}:
            continue
        kind = getattr(resource, name, None)
        if kind is None:
            continue
        _, current_hard = resource.getrlimit(kind)
        bounded = hard if current_hard == resource.RLIM_INFINITY else min(hard, current_hard)
        resource.setrlimit(kind, (min(soft, bounded), bounded))


def _run_candidate_request(
    candidate_snapshot: Path,
    scratch: Path,
    operation: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    command = [
        sys.executable,
        "-I",
        "-B",
        "-c",
        _CANDIDATE_ADAPTER,
        str(candidate_snapshot / "src" / "codesight"),
    ]
    command, pass_fds = _sandboxed_candidate_command(
        command, candidate_snapshot=candidate_snapshot, scratch=scratch
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("HOLUS_")
        and not key.endswith(("_API_KEY", "_TOKEN", "_SECRET", "_PASSWORD"))
    }
    env.update(
        {
            "HOME": str(scratch),
            "TMPDIR": str(scratch),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        }
    )
    process = subprocess.Popen(
        command,
        cwd=candidate_snapshot,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        preexec_fn=_candidate_limit_setter,
        pass_fds=pass_fds,
    )
    stop = threading.Event()
    exceeded = threading.Event()
    monitor = None
    if sys.platform == "darwin":
        monitor = threading.Thread(
            target=_monitor_process_memory,
            args=(process, stop, exceeded),
            daemon=True,
        )
        monitor.start()
    try:
        stdout, stderr = process.communicate(
            json.dumps({"operation": operation, **payload}, sort_keys=True), timeout=35
        )
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        raise ValueError("candidate adapter timed out") from exc
    finally:
        stop.set()
        if monitor is not None:
            monitor.join(timeout=1)
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        for fd in pass_fds:
            os.close(fd)
    if exceeded.is_set() or len(stdout.encode()) > _MAX_AUTHORITY_BYTES:
        raise ValueError("candidate adapter exceeded resource limits")
    if process.returncode != 0:
        raise ValueError("candidate adapter failed under isolation: " + stderr.strip())
    output = _strict_json(stdout.encode(), label="candidate adapter output")
    return output


def _candidate_adapter_broker(
    request_fd: int,
    response_fd: int,
    *,
    candidate_snapshot: Path,
    scratch: Path,
) -> None:
    with os.fdopen(request_fd, "rb") as requests, os.fdopen(response_fd, "wb") as responses:
        for line in requests:
            response: dict[str, Any]
            try:
                request = _strict_json(line, label="candidate broker request")
                _require_keys(
                    request,
                    {"operation", "payload", "allow_egress"},
                    label="candidate broker request",
                )
                if (
                    request["allow_egress"] is not False
                    or not isinstance(request["operation"], str)
                    or not isinstance(request["payload"], dict)
                ):
                    raise ValueError("candidate broker request is invalid")
                output = _run_candidate_request(
                    candidate_snapshot,
                    scratch,
                    request["operation"],
                    request["payload"],
                )
                response = {"ok": True, "output": output}
            except (KeyError, OSError, TypeError, ValueError):
                response = {"ok": False}
            try:
                responses.write(_canonical_bytes(response))
                responses.flush()
            except BrokenPipeError:
                return


def _sandboxed_evaluator_command(
    command: list[str],
    *,
    evaluator_snapshot: Path,
    candidate_snapshot: Path,
    candidate_repo: Path,
    scratch: Path,
) -> list[str]:
    readonly = list(
        dict.fromkeys(
            variant
            for path in (
                evaluator_snapshot,
                candidate_snapshot,
                candidate_repo,
                *_runtime_read_paths(),
            )
            for variant in (path, path.resolve())
        )
    )
    scratch_paths = list(dict.fromkeys((scratch, scratch.resolve())))
    if sys.platform == "darwin":
        sandbox_exec = shutil.which("sandbox-exec")
        if sandbox_exec is None:
            raise ValueError("trusted evaluator requires an OS-enforced sandbox")
        metadata = {Path("/")}
        for path in (*readonly, *scratch_paths):
            metadata.add(path)
            metadata.update(path.parents)
        executables = _executable_variants(Path(sys.executable))
        for executable in (
            shutil.which("sandbox-exec"),
            shutil.which("git"),
            "/usr/bin/xcrun",
        ):
            if executable and Path(executable).exists():
                executables.update(_executable_variants(Path(executable)))
        rules = [
            "(version 1)",
            "(deny default)",
            "(allow process-fork)",
            "(allow process-info*)",
            *(
                f"(allow process-exec* (literal {json.dumps(str(path))}))"
                for path in sorted(executables, key=str)
            ),
            "(allow signal (target same-sandbox))",
            *(
                f"(allow file-read-metadata (literal {json.dumps(str(path))}))"
                for path in sorted(metadata, key=str)
            ),
            *(
                f"(allow file-read* ({'literal' if path.is_file() else 'subpath'} "
                f"{json.dumps(str(path))}))"
                for path in (*readonly, *scratch_paths)
            ),
            "(allow file-map-executable)",
            *(f"(allow file-write* (subpath {json.dumps(str(path))}))" for path in scratch_paths),
            '(allow file-read-data (literal "/"))',
            '(allow file-read* (literal "/dev/null"))',
            '(allow file-write-data (literal "/dev/null"))',
            '(allow file-ioctl (literal "/dev/null"))',
            '(allow file-read* (literal "/dev/random"))',
            '(allow file-read* (literal "/dev/urandom"))',
            "(allow sysctl-read)",
            "(allow mach-lookup)",
        ]
        profile = scratch / "outer-evaluator.sb"
        profile.write_text("\n".join(rules) + "\n", encoding="utf-8")
        return [sandbox_exec, "-f", str(profile), *command]
    if sys.platform.startswith("linux"):
        bwrap = shutil.which("bwrap")
        if bwrap is None:
            raise ValueError("trusted evaluator requires an OS-enforced sandbox")
        sandbox = [bwrap, "--die-with-parent", "--unshare-all", "--new-session"]
        for path in readonly:
            sandbox.extend(("--ro-bind", str(path), str(path)))
        sandbox.extend(
            (
                "--bind",
                str(scratch),
                str(scratch),
                "--dev",
                "/dev",
                "--proc",
                "/proc",
                "--chdir",
                str(evaluator_snapshot),
            )
        )
        return [*sandbox, *command]
    raise ValueError("trusted evaluator requires an OS-enforced sandbox")


def _monitor_process_memory(
    process: subprocess.Popen[str], stop: threading.Event, exceeded: threading.Event
) -> None:
    while not stop.wait(0.2):
        if process.poll() is not None:
            return
        measured = subprocess.run(
            ["ps", "-o", "pid=,rss=", "-g", str(process.pid)],
            capture_output=True,
            text=True,
            check=False,
        )
        if measured.returncode != 0:
            exceeded.set()
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            return
        rss_kib = 0
        for line in measured.stdout.splitlines():
            columns = line.split()
            if len(columns) != 2:
                continue
            try:
                rss_kib += int(columns[1])
            except ValueError:
                exceeded.set()
                break
        if rss_kib * 1024 > 2_147_483_648 or exceeded.is_set():
            exceeded.set()
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            return


def _set_limits() -> None:
    for name, soft, hard in (
        ("RLIMIT_CORE", 0, 0),
        ("RLIMIT_CPU", 150, 151),
        ("RLIMIT_FSIZE", 2_097_152, 2_097_152),
        ("RLIMIT_NOFILE", 96, 96),
        ("RLIMIT_NPROC", 1024, 1024),
        ("RLIMIT_AS", 2_147_483_648, 2_147_483_648),
        ("RLIMIT_DATA", 2_147_483_648, 2_147_483_648),
    ):
        if sys.platform == "darwin" and name in {"RLIMIT_AS", "RLIMIT_DATA"}:
            continue
        kind = getattr(resource, name, None)
        if kind is None:
            continue
        _, current_hard = resource.getrlimit(kind)
        bounded = hard if current_hard == resource.RLIM_INFINITY else min(hard, current_hard)
        resource.setrlimit(kind, (min(soft, bounded), bounded))


def _run_pinned_entrypoint(
    repo: Path,
    pin: dict[str, Any],
    pin_bytes: bytes,
    forwarded: list[str],
) -> subprocess.CompletedProcess[str]:
    evaluator_subject = pin["subject"]["commit"]
    with tempfile.TemporaryDirectory(prefix="holus-approved-evaluator-") as temporary:
        root = Path(temporary)
        snapshot = root / "evaluator"
        candidate_snapshot = root / "candidate"
        scratch = root / "scratch"
        scratch.mkdir()
        candidate_commit = _oid(repo, "HEAD")
        if candidate_commit is None:
            raise ValueError("candidate snapshot requires a committed subject")
        for destination, subject, label in (
            (snapshot, evaluator_subject, "evaluator"),
            (candidate_snapshot, candidate_commit, "candidate"),
        ):
            clone = subprocess.run(
                [
                    "git",
                    "--no-replace-objects",
                    "clone",
                    "--quiet",
                    "--no-local",
                    "--no-hardlinks",
                    "--no-checkout",
                    str(repo),
                    str(destination),
                ],
                capture_output=True,
                text=True,
                check=False,
                env=_canonical_git_env(),
            )
            checkout = (
                subprocess.run(
                    [
                        "git",
                        "--no-replace-objects",
                        "-C",
                        str(destination),
                        "checkout",
                        "--quiet",
                        "--detach",
                        subject,
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                    env=_canonical_git_env(),
                )
                if clone.returncode == 0
                else None
            )
            if clone.returncode != 0 or checkout is None or checkout.returncode != 0:
                raise ValueError(f"approved {label} snapshot could not be created")
            subprocess.run(
                [
                    "git",
                    "--no-replace-objects",
                    "-C",
                    str(destination),
                    "remote",
                    "remove",
                    "origin",
                ],
                capture_output=True,
                check=False,
                env=_canonical_git_env(),
            )
        repository_id = pin["subject"]["repository_id"]
        if repository_id != "local-no-remote":
            subprocess.run(
                [
                    "git",
                    "--no-replace-objects",
                    "-C",
                    str(candidate_snapshot),
                    "remote",
                    "add",
                    "origin",
                    repository_id,
                ],
                capture_output=True,
                check=True,
                env=_canonical_git_env(),
            )
        pin_path = scratch / "accepted-pin.json"
        pin_path.write_bytes(pin_bytes)
        sandbox_home = scratch / "home"
        sandbox_home.mkdir()
        discovered_git = shutil.which("git")
        trusted_git = Path(discovered_git).resolve() if discovered_git else None
        trusted_path = (
            f"{trusted_git.parent}{os.pathsep}{os.defpath}"
            if trusted_git is not None
            else os.defpath
        )
        env = {
            **_canonical_git_env(),
            "PATH": trusted_path,
            "HOME": str(sandbox_home),
            "LANG": "C",
            "TMPDIR": str(scratch),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        }
        command = [
            sys.executable,
            "-I",
            "-B",
            "-c",
            _BOOTSTRAP,
            str(snapshot / "src" / "codesight"),
            "trusted-evaluation-worker",
            "--accepted-pin",
            str(pin_path),
            "--approved-pin-blob",
            pin["_accepted_blob"],
            "--evaluator-subject",
            str(evaluator_subject),
            *forwarded,
        ]
        command = _sandboxed_evaluator_command(
            command,
            evaluator_snapshot=snapshot,
            candidate_snapshot=candidate_snapshot,
            candidate_repo=repo,
            scratch=scratch,
        )
        process = subprocess.Popen(
            command,
            cwd=snapshot,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            preexec_fn=_set_limits,
        )
        monitor_stop = threading.Event()
        memory_exceeded = threading.Event()
        monitor = None
        if sys.platform == "darwin":
            monitor = threading.Thread(
                target=_monitor_process_memory,
                args=(process, monitor_stop, memory_exceeded),
                daemon=True,
            )
            monitor.start()
        try:
            stdout, stderr = process.communicate(timeout=180)
        except subprocess.TimeoutExpired as exc:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            raise ValueError("approved evaluator entrypoint timed out") from exc
        finally:
            monitor_stop.set()
            if monitor is not None:
                monitor.join(timeout=1)
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if memory_exceeded.is_set():
            raise ValueError("approved evaluator entrypoint exceeded memory limits")
        if len(stdout.encode()) > 2_097_152 or len(stderr.encode()) > 2_097_152:
            raise ValueError("approved evaluator entrypoint exceeded output limits")
        return subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)


def _validate_prepared_evaluation(
    raw: str,
    *,
    candidate_commit: str,
    candidate_tree: str,
    pin: dict[str, Any],
    compare_result_path: str | None,
    compare_result_sha256: str | None,
) -> dict[str, Any]:
    prepared = _strict_json(raw.encode("utf-8"), label="trusted evaluator prepared result")
    _require_keys(
        prepared,
        {
            "schema_version",
            "result",
            "evaluator_pin",
            "evaluator_pin_source",
            "baseline_result",
            "baseline_anchor",
            "progress",
        },
        label="trusted evaluator prepared result",
    )
    if prepared["schema_version"] != PREPARED_SCHEMA:
        raise ValueError("trusted evaluator prepared-result schema is invalid")
    expected_pin = {key: value for key, value in pin.items() if key != "_accepted_blob"}
    if prepared["evaluator_pin"] != expected_pin or prepared["evaluator_pin_source"] != "explicit":
        raise ValueError("trusted evaluator substituted the evaluator pin")
    baseline_result = prepared["baseline_result"]
    baseline_anchor = prepared["baseline_anchor"]
    if compare_result_sha256 is None:
        if baseline_result is not None or baseline_anchor is not None:
            raise ValueError("trusted evaluator substituted comparison evidence")
    elif (
        not isinstance(baseline_result, dict)
        or not isinstance(baseline_anchor, dict)
        or baseline_anchor.get("result_path") != compare_result_path
        or baseline_anchor.get("result_bytes_hash") != compare_result_sha256
    ):
        raise ValueError("trusted evaluator comparison bytes differ from acceptance")
    result = prepared["result"]
    subject = result.get("subject") if isinstance(result, dict) else None
    if not isinstance(subject, dict) or (
        subject.get("commit") != candidate_commit
        or subject.get("tree") != candidate_tree
        or subject.get("clean") is not True
    ):
        raise ValueError("trusted evaluator result substituted the candidate subject")
    if result.get("egress_allowed") is not False or result.get("semantic_allowed") is not False:
        raise ValueError("trusted evaluator result weakened the accepted sandbox configuration")
    progress = prepared["progress"]
    if not isinstance(progress, dict):
        raise ValueError("trusted evaluator progress is invalid")
    _require_keys(
        progress,
        {
            "outcome",
            "reason",
            "research_needed",
            "stagnated",
            "recommended_research",
            "next_step",
            "comparison",
        },
        label="trusted evaluator progress",
    )
    comparison = progress["comparison"]
    if not isinstance(comparison, dict):
        raise ValueError("trusted evaluator comparison progress is invalid")
    _require_keys(
        comparison,
        {"classification", "review_eligible", "promotion_relevant", "automatic_promotion"},
        label="trusted evaluator comparison progress",
    )
    if (
        comparison["promotion_relevant"] is not False
        or comparison["automatic_promotion"] is not False
    ):
        raise ValueError("trusted evaluator attempted to authorize promotion")
    return prepared


def _construct_finalization(
    capability: _AuthenticatedLaunch,
    prepared: dict[str, Any],
    *,
    repo: Path,
    configuration_digest: str,
) -> tuple[dict[str, Any], bytes]:
    """Construct authoritative bytes only inside the authenticated launcher process."""
    if capability.configuration_digest != configuration_digest:
        raise ValueError("authenticated launch configuration changed")
    capability.authorize_receipt_construction(repo)
    acceptance = {
        "record_sha256": capability.acceptance_digest,
        "replay_version": 1,
        "replay_epoch": capability.replay_epoch,
        "replay_sequence": capability.replay_sequence,
        "configuration_sha256": configuration_digest,
        "decision": "accepted",
    }
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "evaluator_pin": prepared["evaluator_pin"],
        "evaluator_pin_source": "explicit",
        "baseline_result": prepared["baseline_result"],
        "baseline_anchor": prepared["baseline_anchor"],
        "configuration": {"egress_allowed": False, "semantic_allowed": False},
        "acceptance": acceptance,
        "result": prepared["result"],
        "promotion_allowed": False,
    }
    receipt["receipt_id"] = _sha256(json.dumps(receipt, sort_keys=True).encode("utf-8"))
    receipt_bytes = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
    finalized = {
        "schema_version": FINALIZATION_SCHEMA,
        "acceptance": {
            "authority_id": capability.authority_id,
            "record_sha256": capability.acceptance_digest,
            "replay_epoch": capability.replay_epoch,
            "replay_sequence": capability.replay_sequence,
            "configuration_sha256": configuration_digest,
        },
        "receipt": receipt,
        "progress": prepared["progress"],
        "promotion": {"allowed": False, "status": "human_review_required"},
    }
    return finalized, receipt_bytes


def _directory_flags() -> int:
    return os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)


def _open_receipt_parent(repo: Path) -> int:
    repo_before = os.lstat(repo)
    current_fd = os.open(repo, _directory_flags())
    try:
        repo_after = os.fstat(current_fd)
        if (repo_before.st_dev, repo_before.st_ino) != (repo_after.st_dev, repo_after.st_ino):
            raise ValueError("repository root changed while receipt storage was opened")
        for part in (".holusight", "improvement-results", "receipts"):
            try:
                child_fd = os.open(part, _directory_flags(), dir_fd=current_fd)
            except FileNotFoundError:
                try:
                    os.mkdir(part, 0o700, dir_fd=current_fd)
                except FileExistsError:
                    pass
                child_fd = os.open(part, _directory_flags(), dir_fd=current_fd)
            os.close(current_fd)
            current_fd = child_fd
        return current_fd
    except Exception:
        os.close(current_fd)
        raise


def _receipt_parent_matches(repo: Path, expected_fd: int) -> bool:
    """Reopen the no-follow chain and compare it with the held destination directory."""
    current_fd: int | None = None
    try:
        current_fd = os.open(repo, _directory_flags())
        for part in (".holusight", "improvement-results", "receipts"):
            child_fd = os.open(part, _directory_flags(), dir_fd=current_fd)
            os.close(current_fd)
            current_fd = child_fd
        expected = os.fstat(expected_fd)
        actual = os.fstat(current_fd)
        return (expected.st_dev, expected.st_ino) == (actual.st_dev, actual.st_ino)
    except OSError:
        return False
    finally:
        if current_fd is not None:
            os.close(current_fd)


def _persist_receipt(
    repo: Path,
    receipt: dict[str, Any],
    receipt_bytes: bytes,
    *,
    capability: _AuthenticatedLaunch,
    expires_at: int,
) -> Path:
    """Persist through one held no-follow directory chain without path re-resolution."""
    receipt_id = receipt["receipt_id"]
    if not isinstance(receipt_id, str) or not _SHA256.fullmatch(receipt_id):
        raise ValueError("trusted receipt identity is invalid")
    name = receipt_id.removeprefix("sha256:") + ".json"
    parent_fd = _open_receipt_parent(repo)
    temp_name = f".tmp-{secrets.token_hex(16)}"
    temp_fd: int | None = None
    linked = False
    try:
        if not _receipt_parent_matches(repo, parent_fd):
            raise ValueError("receipt parent changed while held")
        if int(time.time()) >= expires_at:
            raise ValueError("acceptance expired during evaluation")
        capability.consume_for_persistence(repo)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        temp_fd = os.open(temp_name, flags, 0o400, dir_fd=parent_fd)
        view = memoryview(receipt_bytes)
        while view:
            view = view[os.write(temp_fd, view) :]
        os.fsync(temp_fd)
        os.close(temp_fd)
        temp_fd = None
        if not _receipt_parent_matches(repo, parent_fd):
            raise ValueError("receipt parent changed while held")
        try:
            os.link(
                temp_name,
                name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
            linked = True
        except FileExistsError as exc:
            raise ValueError("trusted receipt already exists") from exc
        if not _receipt_parent_matches(repo, parent_fd):
            os.unlink(name, dir_fd=parent_fd)
            linked = False
            raise ValueError("receipt parent changed during persistence")
        os.fsync(parent_fd)
    finally:
        if temp_fd is not None:
            os.close(temp_fd)
        try:
            os.unlink(temp_name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        if linked and not _receipt_parent_matches(repo, parent_fd):
            try:
                os.unlink(name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        os.close(parent_fd)
    return repo / ".holusight" / "improvement-results" / "receipts" / name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="holus-trusted-eval-launcher")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--acceptance-record-fd", type=int, required=True)
    parser.add_argument("--supervisor-authority-fd", type=int, required=True)
    parser.add_argument("--supervisor-state-fd", type=int, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--compare-result", type=Path, default=None)
    parser.add_argument("--candidate-id", default="current-worktree")
    parser.add_argument("--workflow", default="manual")
    parser.add_argument("--tool", default="external-acceptance-launcher")
    parser.add_argument("--model", default=None)
    args = parser.parse_args(argv)
    state_fd = args.supervisor_state_fd
    try:
        repo = args.repo_root.resolve(strict=True)
        top = _git(repo, "rev-parse", "--show-toplevel")
        if top.returncode != 0 or Path(top.stdout.decode().strip()).resolve() != repo:
            raise ValueError("repo root must be the resolved Git worktree root")
        candidate_uid = _candidate_owner_uid(repo)
        raw_authority, supervisor_uid = _read_supervisor_descriptor(
            args.supervisor_authority_fd,
            label="supervisor authority",
            candidate_uid=candidate_uid,
        )
        raw_record, _ = _read_supervisor_descriptor(
            args.acceptance_record_fd,
            label="external acceptance record",
            candidate_uid=candidate_uid,
            expected_owner=supervisor_uid,
        )
        authority = _strict_json(raw_authority, label="supervisor authority")
        acceptance = _strict_json(raw_record, label="acceptance record")
        _validate_acceptance_shape(acceptance)
        record_digest, authority_id, replay_epoch, replay_sequence, expires_at = (
            _validate_attestation(acceptance, authority, raw_record)
        )
        pin, pin_bytes = _validate_pin(repo, acceptance)
        pin["_accepted_blob"] = acceptance["evaluator"]["pin_blob"]
        launcher_blob = _validate_launcher(repo, acceptance)
        if pin["evaluator_blobs"][LAUNCHER_PATH] != launcher_blob:
            raise ValueError("accepted launcher differs from evaluator identity")
        candidate_commit, candidate_tree = _validate_candidate_bindings(
            repo,
            acceptance,
            pin,
            record_digest,
            cases_path=args.cases,
        )
        configuration_digest = _validate_configuration(
            acceptance,
            repo=repo,
            cases_path=pin["corpus_path"],
            candidate_id=args.candidate_id,
            workflow=args.workflow,
            tool=args.tool,
            model=args.model,
            compare_result=args.compare_result,
        )
        capability = _consume_replay(
            state_fd,
            supervisor_uid=supervisor_uid,
            candidate_uid=candidate_uid,
            authority_id=authority_id,
            record_digest=record_digest,
            replay_epoch=replay_epoch,
            replay_sequence=replay_sequence,
            expires_at=expires_at,
        )
        state_fd = -1
        capability.configuration_digest = configuration_digest
        forwarded = [
            "--repo-root",
            str(repo),
            "--cases",
            str(args.cases),
            "--candidate-id",
            args.candidate_id,
            "--workflow",
            args.workflow,
            "--tool",
            args.tool,
        ]
        if args.compare_result is not None:
            forwarded.extend(("--compare-result", str(args.compare_result)))
        if args.model is not None:
            forwarded.extend(("--model", args.model))
        completed = _run_pinned_entrypoint(repo, pin, pin_bytes, forwarded)
        if completed.returncode not in {0, 1}:
            sys.stderr.write(completed.stderr)
            return completed.returncode
        prepared = _validate_prepared_evaluation(
            completed.stdout,
            candidate_commit=candidate_commit,
            candidate_tree=candidate_tree,
            pin=pin,
            compare_result_path=acceptance["configuration"]["compare_result_path"],
            compare_result_sha256=acceptance["configuration"]["compare_result_sha256"],
        )
        post_commit, post_tree = _validate_candidate_bindings(
            repo,
            acceptance,
            pin,
            record_digest,
            cases_path=args.cases,
        )
        post_configuration = _validate_configuration(
            acceptance,
            repo=repo,
            cases_path=pin["corpus_path"],
            candidate_id=args.candidate_id,
            workflow=args.workflow,
            tool=args.tool,
            model=args.model,
            compare_result=args.compare_result,
        )
        if (
            (post_commit, post_tree) != (candidate_commit, candidate_tree)
            or post_configuration != configuration_digest
        ):
            raise ValueError("acceptance bindings changed during evaluation")
        if int(time.time()) >= expires_at:
            raise ValueError("acceptance expired during evaluation")
        finalized, receipt_bytes = _construct_finalization(
            capability,
            prepared,
            repo=repo,
            configuration_digest=configuration_digest,
        )
        receipt_path = _persist_receipt(
            repo,
            finalized["receipt"],
            receipt_bytes,
            capability=capability,
            expires_at=expires_at,
        )
        finalized["receipt_path"] = receipt_path.relative_to(repo).as_posix()
    except (KeyError, OSError, TypeError, ValueError) as exc:
        print(f"trusted evaluation rejected: {exc}", file=sys.stderr)
        return 2
    finally:
        if state_fd >= 0:
            try:
                os.close(state_fd)
            except OSError:
                pass
    sys.stdout.write(json.dumps(finalized, indent=2, sort_keys=True) + "\n")
    sys.stderr.write(completed.stderr)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
