"""Hostile coverage for the G2 supervisor acceptance boundary."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import time
from pathlib import Path

import pytest

from codesight import eval_pilot
from codesight import trusted_eval_launcher as launcher


def _canonical(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        check=False,
    )


def test_requester_cannot_self_mint_supervisor_authority_descriptor(tmp_path: Path) -> None:
    authority = tmp_path / "self-minted-authority.json"
    authority.write_bytes(_canonical({"key_hex": "00" * 32}))
    authority.chmod(0o400)
    fd = os.open(authority, os.O_RDONLY)

    with pytest.raises(ValueError, match="requester-mintable"):
        launcher._read_supervisor_descriptor(
            fd,
            label="supervisor authority",
            candidate_uid=authority.stat().st_uid,
        )


def test_same_acceptance_bytes_cannot_replay_through_new_descriptor(tmp_path: Path) -> None:
    state = tmp_path / "supervisor-state"
    state.mkdir(mode=0o700)
    owner = state.stat().st_uid
    candidate_uid = owner + 1
    digest = "sha256:" + "1" * 64

    first_fd = os.open(state, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    first = launcher._consume_replay(
        first_fd,
        supervisor_uid=owner,
        candidate_uid=candidate_uid,
        authority_id="supervisor-v2",
        record_digest=digest,
        replay_epoch=20260827,
        replay_sequence=7,
        expires_at=int(time.time()) + 60,
    )
    assert first.acceptance_digest == digest

    second_fd = os.open(state, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    with pytest.raises(ValueError, match="already consumed"):
        launcher._consume_replay(
            second_fd,
            supervisor_uid=owner,
            candidate_uid=candidate_uid,
            authority_id="supervisor-v2",
            record_digest=digest,
            replay_epoch=20260827,
            replay_sequence=7,
            expires_at=int(time.time()) + 60,
        )


def test_caller_complete_old_internal_finalization_forgery_is_not_a_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("HOLUS_TRUSTED_LAUNCHER_SUBJECT", "a" * 40)
    monkeypatch.setenv("HOLUS_EVALUATOR_ALREADY_SANDBOXED", "1")

    with pytest.raises(SystemExit) as rejected:
        eval_pilot.main(
            [
                "trusted-evaluate-internal",
                "--repo-root",
                str(tmp_path),
                "--accepted-pin",
                str(tmp_path / "forged-pin.json"),
                "--approved-pin-blob",
                "b" * 40,
                "--acceptance-record-sha256",
                "sha256:" + "c" * 64,
                "--acceptance-replay-epoch",
                "1",
                "--acceptance-replay-sequence",
                "1",
                "--configuration-sha256",
                "sha256:" + "d" * 64,
            ]
        )

    assert rejected.value.code == 2
    assert "invalid choice" in capsys.readouterr().err
    assert not (tmp_path / ".holusight/improvement-results/receipts").exists()


def test_caller_cannot_forge_launcher_receipt_capability_from_own_descriptor(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    marker = tmp_path / "forged-marker"
    marker.write_bytes(b"forged\n")
    marker_fd = os.open(marker, os.O_RDWR)
    marker.chmod(0o400)
    owner = marker.stat().st_uid
    capability = launcher._AuthenticatedLaunch(
        launcher._AUTHORITY_CONSTRUCTOR_SEAL,
        authority_id="forged",
        acceptance_digest="sha256:" + "5" * 64,
        replay_epoch=1,
        replay_sequence=1,
        expires_at=int(time.time()) + 60,
        marker_fd=marker_fd,
        marker_sha256=launcher._sha256(b"forged\n"),
        supervisor_uid=owner,
        candidate_uid=owner,
    )
    capability.configuration_digest = "sha256:" + "6" * 64

    with pytest.raises(ValueError, match="requester-mintable"):
        launcher._construct_finalization(
            capability,
            {},
            repo=repo,
            configuration_digest="sha256:" + "6" * 64,
        )


def test_sandbox_environment_spoof_cannot_bypass_candidate_import_sandbox(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = tmp_path / "src/codesight"
    package.mkdir(parents=True)
    (package / "axi_providers.py").write_text("# hostile candidate\n", encoding="utf-8")
    monkeypatch.setenv("HOLUS_EVALUATOR_ALREADY_SANDBOXED", "1")
    monkeypatch.setenv("HOLUS_OUTER_RESOURCE_MONITOR", "1")
    monkeypatch.setenv("HOLUS_CANDIDATE_BROKER_REQUEST_FD", "0")
    monkeypatch.setenv("HOLUS_CANDIDATE_BROKER_RESPONSE_FD", "1")

    def required_sandbox(*args, **kwargs):
        raise ValueError("OS sandbox was still required")

    monkeypatch.setattr(eval_pilot, "_sandboxed_candidate_command", required_sandbox)
    with pytest.raises(ValueError, match="still required"):
        eval_pilot._run_candidate_adapter(
            tmp_path,
            "display",
            {"counts": {}, "cap": 1},
            allow_egress=False,
        )


def test_launcher_receipt_rejects_parent_symlink_and_swap_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    attacker = tmp_path / "attacker"
    attacker.mkdir()
    (repo / ".holusight").symlink_to(attacker, target_is_directory=True)
    receipt = {"receipt_id": "sha256:" + "2" * 64}

    with pytest.raises(OSError):
        launcher._persist_receipt(
            repo,
            receipt,
            b"{}\n",
            capability=object(),
            expires_at=int(time.time()) + 60,
        )
    assert list(attacker.iterdir()) == []

    (repo / ".holusight").unlink()
    real_open = launcher._open_receipt_parent
    moved = tmp_path / "moved-held-parent"

    def swap_after_open(candidate_repo: Path) -> int:
        fd = real_open(candidate_repo)
        (candidate_repo / ".holusight").rename(moved)
        (candidate_repo / ".holusight").symlink_to(attacker, target_is_directory=True)
        return fd

    monkeypatch.setattr(launcher, "_open_receipt_parent", swap_after_open)
    with pytest.raises(ValueError, match="parent changed"):
        launcher._persist_receipt(
            repo,
            receipt,
            b"{}\n",
            capability=object(),
            expires_at=int(time.time()) + 60,
        )
    assert not list(attacker.rglob("*.json"))
    assert not list(moved.rglob("*.json"))


def test_preflight_git_ignores_hostile_local_executable_configuration(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    assert _git(repo, "init", "-q").returncode == 0
    marker = tmp_path / "fsmonitor-executed"
    fsmonitor = tmp_path / "hostile-fsmonitor.sh"
    fsmonitor.write_text(
        f"#!/bin/sh\necho executed > {str(marker)!r}\nexit 1\n",
        encoding="utf-8",
    )
    fsmonitor.chmod(fsmonitor.stat().st_mode | stat.S_IXUSR)
    assert _git(repo, "config", "core.fsmonitor", str(fsmonitor)).returncode == 0

    launcher_status = launcher._git(repo, "status", "--porcelain=v1")
    evaluator_status = eval_pilot._git_run(repo, "status", "--porcelain=v1")

    assert launcher_status.returncode == 0
    assert evaluator_status.returncode == 0
    assert not marker.exists()


def test_expiration_is_rechecked_after_evaluation_before_receipt_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    state = tmp_path / "supervisor-state"
    state.mkdir(mode=0o700)
    owner = state.stat().st_uid
    candidate_uid = owner + 1
    expires_at = int(time.time()) + 60
    state_fd = os.open(state, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    capability = launcher._consume_replay(
        state_fd,
        supervisor_uid=owner,
        candidate_uid=candidate_uid,
        authority_id="supervisor-v2",
        record_digest="sha256:" + "3" * 64,
        replay_epoch=1,
        replay_sequence=1,
        expires_at=expires_at,
    )
    capability.configuration_digest = "sha256:" + "4" * 64
    monkeypatch.setattr(launcher, "_candidate_owner_uid", lambda _repo: candidate_uid)
    monkeypatch.setattr(launcher.time, "time", lambda: float(expires_at))

    with pytest.raises(ValueError, match="expired during evaluation"):
        launcher._construct_finalization(
            capability,
            {},
            repo=repo,
            configuration_digest="sha256:" + "4" * 64,
        )
