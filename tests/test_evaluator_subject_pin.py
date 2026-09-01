"""G2 evaluator-subject pin contract tests."""

from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from codesight import eval_pilot


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _case() -> dict:
    return {
        "schema_version": eval_pilot.SCHEMA_CASE,
        "case_id": "pin-case",
        "family": "regression",
        "kind": "regression",
        "provenance": {
            "origin": "spec_documented_contract",
            "description": "evaluator pin contract",
            "admitted_by": "human",
            "admitted_at": "2026-08-24",
        },
        "grader": "grade_no_egress_default",
        "fixture": {},
        "expected": {
            "key_stripped_without_allow_egress": True,
            "key_restored_after_context_exit": True,
        },
    }


def _repo(tmp_path: Path) -> Path:
    shutil.copytree(
        Path(eval_pilot.__file__).parent,
        tmp_path / "src/codesight",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (tmp_path / "tests/fixtures").mkdir(parents=True)
    (tmp_path / ".gitignore").write_text(".holusight/\n", encoding="utf-8")
    (tmp_path / "src/codesight/production.py").write_text("production-v1\n", encoding="utf-8")
    (tmp_path / eval_pilot.CANONICAL_EVALUATOR_CASES_PATH).write_text(
        json.dumps(_case()) + "\n", encoding="utf-8"
    )
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "g2@example.test")
    _git(tmp_path, "config", "user.name", "G2")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "baseline")
    return tmp_path


def _run(repo: Path, candidate: str = "candidate") -> eval_pilot.PilotRunResult:
    return eval_pilot.run_pilot(
        repo,
        cases_path=repo / eval_pilot.CANONICAL_EVALUATOR_CASES_PATH,
        lineage=eval_pilot.CandidateLineage(
            candidate_id=candidate, repo_commit=None, workflow="test", tool="pytest"
        ),
    )


def _canonical(payload: dict) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha256(raw: bytes) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _git_output(repo: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", "--no-replace-objects", *args],
        cwd=repo,
        input=input_bytes,
        capture_output=True,
        check=True,
    ).stdout


def _trusted_launcher(
    repo: Path,
    pin_path: Path,
    *,
    mutate_record=None,
    mutate_capability=None,
    transform_record_bytes=None,
    transform_launcher_bytes=None,
    before_launch=None,
    capability_as_regular_file: bool = False,
    record_mode: int = 0o400,
    record_inside_candidate: bool = False,
) -> subprocess.CompletedProcess[str]:
    import hashlib
    import hmac

    relative_pin = pin_path.relative_to(repo).as_posix()
    authority_subject = _git_output(
        repo,
        "log",
        "--diff-filter=A",
        "--format=%H",
        "--",
        relative_pin,
    ).decode().splitlines()[0]
    pin_blob = _git_output(
        repo, "rev-parse", f"{authority_subject}:{relative_pin}"
    ).decode().strip()
    pin_bytes = _git_output(repo, "cat-file", "blob", pin_blob)
    pin = json.loads(pin_bytes)

    manifests = _git_output(repo, "ls-files", "specs/*.change.json").decode().splitlines()
    if not manifests:
        manifest_path = repo / "specs/candidate.change.json"
        manifest_path.parent.mkdir(exist_ok=True)
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": "holus-improvement-change/v1",
                    "classification": "candidate",
                    "links": {},
                    "link_hashes": {},
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        _git(repo, "add", manifest_path.relative_to(repo).as_posix())
        _git(repo, "commit", "-q", "-m", "candidate evidence manifest")
        manifests = [manifest_path.relative_to(repo).as_posix()]
    manifest_path = manifests[0]
    candidate_commit = _git_output(repo, "rev-parse", "HEAD").decode().strip()
    candidate_tree = _git_output(repo, "rev-parse", "HEAD^{tree}").decode().strip()
    manifest_blob = _git_output(
        repo, "rev-parse", f"HEAD:{manifest_path}"
    ).decode().strip()
    manifest_bytes = _git_output(repo, "cat-file", "blob", manifest_blob)
    launcher_blob = pin["evaluator_blobs"]["src/codesight/trusted_eval_launcher.py"]
    launcher_bytes = _git_output(repo, "cat-file", "blob", launcher_blob)
    corpus_blob = pin["corpus_blob"]
    corpus_bytes = _git_output(repo, "cat-file", "blob", corpus_blob)
    evaluator_identity = {
        "protocol_revision": pin["protocol_revision"],
        "subject": pin["subject"],
        "evaluator_blobs": pin["evaluator_blobs"],
    }
    configuration_identity = {
        "cases_path": eval_pilot.CANONICAL_EVALUATOR_CASES_PATH,
        "egress_allowed": False,
        "semantic_allowed": False,
        "candidate_id": "trusted-entrypoint",
        "workflow": "manual",
        "tool": "external-acceptance-launcher",
        "model": None,
        "compare_result_path": None,
        "compare_result_sha256": None,
    }
    now = int(time.time())
    replay_epoch = 20260827
    replay_sequence = 1
    key = b"external-captain-attestation-key" * 2
    key_id = "captain-local-v1"
    unsigned = {
        "schema_version": "holus-external-evaluator-acceptance/v1",
        "record_version": 1,
        "candidate": {"commit": candidate_commit, "tree": candidate_tree},
        "evaluator": {
            "pin_blob": pin_blob,
            "pin_sha256": _sha256(pin_bytes),
            "identity_sha256": _sha256(_canonical(evaluator_identity)),
        },
        "launcher": {
            "path": "src/codesight/trusted_eval_launcher.py",
            "blob": launcher_blob,
            "sha256": _sha256(launcher_bytes),
        },
        "manifest": {
            "path": manifest_path,
            "blob": manifest_blob,
            "sha256": _sha256(manifest_bytes),
        },
        "corpus": {
            "path": pin["corpus_path"],
            "blob": corpus_blob,
            "sha256": _sha256(corpus_bytes),
        },
        "configuration": {
            **configuration_identity,
            "identity_sha256": _sha256(_canonical(configuration_identity)),
        },
        "decision": "accepted",
        "replay": {
            "replay_version": 1,
            "epoch": replay_epoch,
            "sequence": replay_sequence,
            "issued_at": now - 1,
            "expires_at": now + 600,
        },
    }
    if mutate_record is not None:
        mutate_record(unsigned)
    unsigned_bytes = _canonical(unsigned)
    record = {
        **unsigned,
        "attestation": {
            "algorithm": "hmac-sha256",
            "key_id": key_id,
            "payload_sha256": _sha256(unsigned_bytes),
            "mac": hmac.new(key, unsigned_bytes, hashlib.sha256).hexdigest(),
        },
    }
    record_bytes = _canonical(record)
    if transform_record_bytes is not None:
        record_bytes = transform_record_bytes(record_bytes)
    capability = {
        "schema_version": "holus-evaluator-attestation-capability/v1",
        "capability_version": 1,
        "key_id": key_id,
        "key_hex": key.hex(),
        "acceptance_record_sha256": _sha256(record_bytes),
        "replay_epoch": replay_epoch,
        "replay_sequence": replay_sequence,
    }
    if mutate_capability is not None:
        mutate_capability(capability)
    external_root = repo if record_inside_candidate else repo.parent
    record_path = external_root / f"{repo.name}-acceptance.json"
    if record_path.exists():
        record_path.chmod(0o600)
    record_path.write_bytes(record_bytes)
    record_path.chmod(record_mode)
    launcher_path = repo.parent / f"{repo.name}-trusted-launcher.py"
    running_launcher = (
        transform_launcher_bytes(launcher_bytes)
        if transform_launcher_bytes is not None
        else launcher_bytes
    )
    launcher_path.write_bytes(running_launcher)
    if before_launch is not None:
        before_launch(repo)
    if capability_as_regular_file:
        capability_path = repo.parent / f"{repo.name}-capability.json"
        capability_path.write_bytes(_canonical(capability))
        read_fd = os.open(capability_path, os.O_RDONLY)
    else:
        read_fd, write_fd = os.pipe()
        try:
            os.write(write_fd, _canonical(capability))
        finally:
            os.close(write_fd)
    try:
        return subprocess.run(
            [
                sys.executable,
                "-I",
                str(launcher_path),
                "--repo-root",
                str(repo),
                "--acceptance-record",
                str(record_path),
                "--attestation-capability-fd",
                str(read_fd),
                "--cases",
                str(repo / eval_pilot.CANONICAL_EVALUATOR_CASES_PATH),
                "--candidate-id",
                "trusted-entrypoint",
            ],
            cwd=repo,
            env={
                "PATH": (
                    f"{Path(sys.executable).parent}{os.pathsep}"
                    f"{Path(shutil.which('git')).resolve().parent}{os.pathsep}{os.defpath}"
                ),
                "PYTHONDONTWRITEBYTECODE": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_GRAFT_FILE": os.devnull,
                "GIT_NO_REPLACE_OBJECTS": "1",
            },
            pass_fds=(read_fd,),
            text=True,
            capture_output=True,
            check=False,
            timeout=210,
        )
    finally:
        os.close(read_fd)


def _anchor(repo: Path, result: eval_pilot.PilotRunResult) -> eval_pilot.BaselineAnchor:
    payload_hash = eval_pilot._sha256_hex(
        json.dumps(result.model_dump(mode="json"), sort_keys=True).encode("utf-8")
    )
    return eval_pilot.BaselineAnchor(
        result_path=".holusight/improvement-results/prior.json",
        result_bytes_hash=payload_hash,
        result_payload_hash=payload_hash,
        result_digest=result.result_digest,
        manifest_path="specs/baseline.change.json",
        manifest_commit=result.subject.commit,
        manifest_blob="0" * 40,
        repository_id=result.subject.repository_id,
    )


def test_production_only_candidate_remains_applicable_under_fixed_pin(tmp_path):
    repo = _repo(tmp_path)
    baseline = _run(repo)
    pin = eval_pilot.build_evaluator_pin(repo)

    (repo / "src/codesight/production.py").write_text("production-v2\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "production candidate")
    candidate = _run(repo)

    assert eval_pilot.evaluator_pin_blockers(repo, pin, candidate) == []
    progress = eval_pilot.evaluate_progress(
        candidate,
        baseline,
        trusted_anchor=_anchor(repo, baseline),
        repo_root=repo,
        evaluator_pin=pin,
    )
    assert progress["comparison"]["classification"] == "advisory"
    assert progress["comparison"]["promotion_relevant"] is False
    assert progress["comparison"]["automatic_promotion"] is False


def test_candidate_evaluator_revision_invalidates_prior_pin_even_with_consistent_result(tmp_path):
    repo = _repo(tmp_path)
    baseline = _run(repo)
    pin = eval_pilot.build_evaluator_pin(repo)

    (repo / "src/codesight/eval_pilot.py").write_text("evaluator-v2\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "candidate changed evaluator")
    candidate = _run(repo)

    blockers = eval_pilot.evaluator_pin_blockers(repo, pin, candidate)
    assert any("changed_evaluator_artifact" in item for item in blockers)
    progress = eval_pilot.evaluate_progress(
        candidate,
        baseline,
        trusted_anchor=_anchor(repo, baseline),
        repo_root=repo,
        evaluator_pin=pin,
    )
    assert progress["outcome"] == "invalid_comparison"
    assert progress["comparison"]["promotion_relevant"] is False


def test_frozen_corpus_revision_invalidates_prior_pin(tmp_path):
    repo = _repo(tmp_path)
    baseline = _run(repo)
    pin = eval_pilot.build_evaluator_pin(repo)

    corpus = repo / eval_pilot.CANONICAL_EVALUATOR_CASES_PATH
    corpus.write_text(corpus.read_text().replace("pin-case", "changed-case"), encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "candidate changed corpus")
    candidate = _run(repo)

    assert any("corpus" in item for item in eval_pilot.evaluator_pin_blockers(repo, pin, candidate))
    assert (
        eval_pilot.evaluate_progress(
            candidate,
            baseline,
            trusted_anchor=_anchor(repo, baseline),
            repo_root=repo,
            evaluator_pin=pin,
        )["outcome"]
        == "invalid_comparison"
    )


def test_legitimate_evaluator_revision_requires_new_protocol_pin_and_baseline(tmp_path):
    repo = _repo(tmp_path)
    baseline = _run(repo)
    old_pin = eval_pilot.build_evaluator_pin(repo, protocol_revision="holus-eval-pilot/v1")
    pin_path = repo / "specs/approved.evaluator-pin.json"
    pin_path.parent.mkdir()
    pin_path.write_text(json.dumps(old_pin.model_dump(mode="json")) + "\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "approve evaluator pin")

    (repo / "src/codesight/eval_pilot.py").write_text("evaluator-v2\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "reviewed evaluator revision")
    with pytest.raises(ValueError, match="new separately reviewed protocol revision"):
        eval_pilot.build_evaluator_pin(repo, protocol_revision="holus-eval-pilot/v1")
    revised_pin = eval_pilot.build_evaluator_pin(repo, protocol_revision="holus-eval-pilot/v2")
    revised_baseline = _run(repo)

    assert revised_pin.protocol_revision != old_pin.protocol_revision
    assert revised_pin.subject.commit != old_pin.subject.commit
    assert eval_pilot.evaluator_pin_blockers(repo, revised_pin, revised_baseline) == []
    assert (
        eval_pilot.evaluate_progress(
            revised_baseline,
            baseline,
            trusted_anchor=_anchor(repo, baseline),
            repo_root=repo,
            evaluator_pin=revised_pin,
        )["outcome"]
        == "invalid_comparison"
    )


def test_empty_self_declared_and_mismatched_pin_identity_fail_closed(tmp_path):
    repo = _repo(tmp_path)
    subject = eval_pilot._current_subject(repo)
    with pytest.raises(ValueError):
        eval_pilot.EvaluatorSubjectPin(
            protocol_revision="holus-eval-pilot/v1",
            subject=subject,
            evaluator_blobs={},
            corpus_blob="0" * 40,
        )

    pin = eval_pilot.build_evaluator_pin(repo)
    result = _run(repo)
    mismatched = result.model_copy(
        update={
            "subject": result.subject.model_copy(
                update={"repository_id": "https://example.test/other.git"}
            )
        }
    )
    assert "result_repository_subject_mismatch" in eval_pilot.evaluator_pin_blockers(
        repo, pin, mismatched
    )
    self_declared = result.model_copy(
        update={
            "lineage": result.lineage.model_copy(update={"evaluator_digest": "sha256:" + "f" * 64})
        }
    )
    assert eval_pilot.evaluator_pin_blockers(repo, pin, self_declared) == []


def test_pin_preserves_immutable_tree_and_blob_identity_and_public_command_denies_promotion(
    tmp_path,
):
    repo = _repo(tmp_path)
    pin = eval_pilot.build_evaluator_pin(repo)
    assert pin.subject.tree == eval_pilot._git_oid(repo, f"{pin.subject.commit}^{{tree}}")
    assert pin.evaluator_blobs["src/codesight/eval_pilot.py"] == eval_pilot._git_oid(
        repo, f"{pin.subject.commit}:src/codesight/eval_pilot.py"
    )

    # Pin emission remains read-only and advisory. The candidate repository
    # cannot turn these bytes into launch authority.
    assert pin.schema_version == eval_pilot.SCHEMA_EVALUATOR_PIN
    assert not list(repo.glob("specs/*.evaluator-pin.json"))


def test_pin_rejects_partial_evaluator_path_set(tmp_path):
    repo = _repo(tmp_path)
    pin = eval_pilot.build_evaluator_pin(repo).model_dump(mode="json")
    pin["evaluator_blobs"].pop("src/codesight/control_storage.py")

    with pytest.raises(ValueError, match="exact closed evaluator path set"):
        eval_pilot.EvaluatorSubjectPin.model_validate(pin)


def test_configuration_mismatch_is_not_promotion_relevant(tmp_path):
    repo = _repo(tmp_path)
    baseline = _run(repo)
    pin = eval_pilot.build_evaluator_pin(repo)
    candidate = _run(repo)
    candidate.semantic_allowed = True
    candidate.result_digest = eval_pilot.canonical_result_digest(candidate)

    progress = eval_pilot.evaluate_progress(
        candidate,
        baseline,
        trusted_anchor=_anchor(repo, baseline),
        repo_root=repo,
        evaluator_pin=pin,
    )

    assert progress["outcome"] == "invalid_comparison"
    assert progress["comparison"]["promotion_relevant"] is False


def test_candidate_cli_change_is_evaluated_without_changing_frozen_harness(tmp_path):
    repo = _repo(tmp_path)
    display_case = {
        "schema_version": eval_pilot.SCHEMA_CASE,
        "case_id": "display-candidate",
        "family": "regression",
        "kind": "comparative",
        "provenance": {
            "origin": "spec_documented_contract",
            "description": "candidate display behavior",
            "admitted_by": "human",
            "admitted_at": "2026-08-24",
        },
        "grader": "grade_display_quota_case",
        "fixture": {
            "cap": 4,
            "provider_item_counts": {
                "exact": 4,
                "structural": 1,
                "consistency": 1,
                "semantic": 1,
            },
        },
        "expected": {
            "candidate_min_distinct_providers": 4,
            "status_quo_max_distinct_providers": 1,
        },
    }
    corpus = repo / eval_pilot.CANONICAL_EVALUATOR_CASES_PATH
    corpus.write_text(json.dumps(display_case) + "\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "display baseline")
    pin = eval_pilot.build_evaluator_pin(repo)

    candidate_path = repo / "src/codesight/cli_axi.py"
    candidate_source = candidate_path.read_text(encoding="utf-8")
    candidate_source = candidate_source.replace(
        "    queues = [list(r.items) for r in results]\n"
        "    displayed: list[axi_providers.EvidenceItem] = []\n"
        "    while len(displayed) < cap and any(queues):\n"
        "        for queue in queues:\n"
        "            if not queue:\n"
        "                continue\n"
        "            displayed.append(queue.pop(0))\n"
        "            if len(displayed) >= cap:\n"
        "                break\n"
        "    return displayed\n",
        "    return [item for result in results for item in result.items][:cap]\n",
    )
    candidate_path.write_text(candidate_source, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "candidate display regression")

    result = eval_pilot.run_pinned_pilot(
        repo,
        pin=pin,
        cases_path=corpus,
        lineage=eval_pilot.CandidateLineage(
            candidate_id="display", repo_commit=None, workflow="test", tool="pytest"
        ),
    )

    assert eval_pilot.evaluator_pin_blockers(repo, pin, result) == []
    assert result.grades[0].verdict == "fail"


def test_candidate_no_egress_change_is_graded_under_fixed_harness(tmp_path):
    repo = _repo(tmp_path)
    pin = eval_pilot.build_evaluator_pin(repo)
    provider_path = repo / "src/codesight/axi_providers.py"
    provider_path.write_text(
        provider_path.read_text(encoding="utf-8").replace(
            '    saved = os.environ.pop("VOYAGE_API_KEY", None)\n',
            '    saved = os.environ.get("VOYAGE_API_KEY")\n',
            1,
        ),
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "candidate no-egress regression")

    result = eval_pilot.run_pinned_pilot(
        repo,
        pin=pin,
        cases_path=repo / eval_pilot.CANONICAL_EVALUATOR_CASES_PATH,
        lineage=eval_pilot.CandidateLineage(
            candidate_id="no-egress", repo_commit=None, workflow="test", tool="pytest"
        ),
    )

    assert eval_pilot.evaluator_pin_blockers(repo, pin, result) == []
    assert result.grades[0].verdict == "fail"


def test_candidate_cannot_replace_snapshot_files_during_evaluation(tmp_path):
    repo = _repo(tmp_path)
    pin = eval_pilot.build_evaluator_pin(repo)
    provider_path = repo / "src/codesight/axi_providers.py"
    provider_path.write_text(
        provider_path.read_text(encoding="utf-8").replace(
            '    saved = os.environ.pop("VOYAGE_API_KEY", None)\n',
            '    Path(__file__).unlink()\n    saved = os.environ.pop("VOYAGE_API_KEY", None)\n',
            1,
        ),
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "candidate snapshot mutation")

    result = eval_pilot.run_pinned_pilot(
        repo,
        pin=pin,
        cases_path=repo / eval_pilot.CANONICAL_EVALUATOR_CASES_PATH,
        lineage=eval_pilot.CandidateLineage(
            candidate_id="mutation", repo_commit=None, workflow="test", tool="pytest"
        ),
    )

    assert result.counts["errored"] == 1
    assert result.grades[0].verdict == "error"


def test_evaluator_process_cannot_write_host_files_or_use_network(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    repo = _repo(repo_root)
    marker = tmp_path / "evaluator-host-write"
    received = threading.Event()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    server.settimeout(30)
    port = server.getsockname()[1]

    def receive_probe():
        try:
            connection, _ = server.accept()
            with connection:
                if connection.recv(32) == b"evaluator-network-probe":
                    received.set()
        except OSError:
            pass

    receiver = threading.Thread(target=receive_probe, daemon=True)
    receiver.start()
    evaluator = repo / "src/codesight/eval_pilot.py"
    probe = (
        "\nfrom pathlib import Path as _ProbePath\n"
        "try:\n"
        f"    _ProbePath({str(marker)!r}).write_text('escaped', encoding='utf-8')\n"
        "except OSError:\n"
        "    pass\n"
        "import socket as _probe_socket\n"
        "try:\n"
        f"    with _probe_socket.create_connection(('127.0.0.1', {port}), timeout=2) as _probe:\n"
        "        _probe.sendall(b'evaluator-network-probe')\n"
        "except OSError:\n"
        "    pass\n"
    )
    evaluator.write_text(
        evaluator.read_text(encoding="utf-8").replace(
            "from __future__ import annotations\n",
            "from __future__ import annotations\n" + probe,
            1,
        ),
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "approved evaluator isolation probe")
    pin = eval_pilot.build_evaluator_pin(repo)
    (repo / "src/codesight/production.py").write_text("production-v2\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "production candidate")

    try:
        result = eval_pilot.run_pinned_pilot(
            repo,
            pin=pin,
            cases_path=repo / eval_pilot.CANONICAL_EVALUATOR_CASES_PATH,
            lineage=eval_pilot.CandidateLineage(
                candidate_id="evaluator-isolation",
                repo_commit=None,
                workflow="test",
                tool="pytest",
            ),
        )
    finally:
        server.close()
        receiver.join(timeout=1)

    assert result.counts.passed == 1
    assert not marker.exists()
    assert not received.is_set()


def test_pinned_evaluation_runs_in_a_fresh_process(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    pin = eval_pilot.build_evaluator_pin(repo)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("in-process evaluator executed")

    monkeypatch.setattr(eval_pilot, "run_pilot", fail_if_called)
    result = eval_pilot.run_pinned_pilot(
        repo,
        pin=pin,
        cases_path=repo / eval_pilot.CANONICAL_EVALUATOR_CASES_PATH,
        lineage=eval_pilot.CandidateLineage(
            candidate_id="fresh", repo_commit=None, workflow="test", tool="pytest"
        ),
    )

    assert result.counts["passed"] == 1
    assert result.subject.commit == pin.subject.commit


def test_trusted_entrypoint_remains_authoritative_when_candidate_cli_is_broken(tmp_path):
    repo = _repo(tmp_path)
    pin = eval_pilot.build_evaluator_pin(repo)
    pin_path = repo / "specs/approved.evaluator-pin.json"
    pin_path.parent.mkdir()
    pin_path.write_text(json.dumps(pin.model_dump(mode="json")) + "\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "approve evaluator")
    (repo / "src/codesight/cli_axi.py").write_text(
        "raise RuntimeError('candidate-owned CLI must not orchestrate trust')\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "break candidate CLI")

    completed = _trusted_launcher(repo, pin_path)

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    receipt_path = repo / payload["receipt_path"]
    assert receipt_path.is_file()
    assert payload["receipt"]["promotion_allowed"] is False
    assert payload["promotion"]["allowed"] is False


def test_candidate_internal_evaluation_cannot_persist_trusted_receipt(tmp_path):
    repo = _repo(tmp_path)
    pin = eval_pilot.build_evaluator_pin(repo)
    pin_path = repo / "specs/approved.evaluator-pin.json"
    pin_path.parent.mkdir()
    pin_path.write_text(json.dumps(pin.model_dump(mode="json")) + "\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "approve evaluator")
    authority_pin_blob = subprocess.run(
        ["git", "rev-parse", "HEAD:specs/approved.evaluator-pin.json"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    (repo / "src/codesight/production.py").write_text("candidate-v2\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "candidate")
    bootstrap = (
        "import importlib,sys,types;"
        "package=types.ModuleType('codesight');"
        "package.__path__=[sys.argv.pop(1)];"
        "package.__package__='codesight';"
        "sys.modules['codesight']=package;"
        "module=importlib.import_module('codesight.eval_pilot');"
        "raise SystemExit(module.main())"
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            bootstrap,
            str(repo / "src/codesight"),
            "trusted-evaluate-internal",
            "--repo-root",
            str(repo),
            "--cases",
            str(repo / eval_pilot.CANONICAL_EVALUATOR_CASES_PATH),
            "--evaluator-pin",
            str(pin_path),
            "--approved-pin-blob",
            authority_pin_blob,
        ],
        cwd=repo,
        env={
            "PATH": os.defpath,
            "PYTHONDONTWRITEBYTECODE": "1",
            "HOLUS_TRUSTED_LAUNCHER_SUBJECT": pin.subject.commit,
        },
        text=True,
        capture_output=True,
        check=False,
        timeout=210,
    )

    assert completed.returncode == 2
    assert "acceptance-record-sha256" in completed.stderr
    assert not (repo / ".holusight/improvement-results/receipts").exists()


def test_approved_launcher_never_imports_candidate_evaluator_before_preflight(tmp_path):
    repo = _repo(tmp_path)
    pin = eval_pilot.build_evaluator_pin(repo)
    pin_path = repo / "specs/approved.evaluator-pin.json"
    pin_path.parent.mkdir()
    pin_path.write_text(json.dumps(pin.model_dump(mode="json")) + "\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "approve evaluator")
    marker = repo / ".holusight/candidate-imported"
    evaluator = repo / "src/codesight/eval_pilot.py"
    evaluator.write_text(
        f"from pathlib import Path\n"
        f"Path({str(marker)!r}).parent.mkdir(parents=True, exist_ok=True)\n"
        f"Path({str(marker)!r}).write_text('candidate import')\n"
        + evaluator.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "candidate import side effect")

    completed = _trusted_launcher(repo, pin_path)

    assert completed.returncode == 2
    assert "substituted pinned bytes" in completed.stderr
    assert not marker.exists()


def test_git_replacements_cannot_substitute_approved_authority(tmp_path):
    repo = _repo(tmp_path)
    pin = eval_pilot.build_evaluator_pin(repo)
    pin_path = repo / "specs/approved.evaluator-pin.json"
    pin_path.parent.mkdir()
    pin_path.write_text(json.dumps(pin.model_dump(mode="json")) + "\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "approve evaluator")
    authority_subject = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    authority_pin_blob = subprocess.run(
        ["git", "rev-parse", f"{authority_subject}:specs/approved.evaluator-pin.json"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    authority_launcher_blob = subprocess.run(
        [
            "git",
            "rev-parse",
            f"{authority_subject}:src/codesight/trusted_eval_launcher.py",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    (repo / "src/codesight/production.py").write_text("production-v2\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "candidate")

    replacement_pin = pin.model_copy(update={"protocol_revision": "attacker/v2"})
    replacement_pin_blob = subprocess.run(
        ["git", "hash-object", "-w", "--stdin"],
        cwd=repo,
        input=json.dumps(replacement_pin.model_dump(mode="json")).encode("utf-8"),
        capture_output=True,
        check=True,
    ).stdout.decode("ascii").strip()
    marker = repo / ".holusight/replacement-launcher-executed"
    replacement_launcher_blob = subprocess.run(
        ["git", "hash-object", "-w", "--stdin"],
        cwd=repo,
        input=(
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).parent.mkdir(parents=True, exist_ok=True)\n"
            f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n"
        ).encode("utf-8"),
        capture_output=True,
        check=True,
    ).stdout.decode("ascii").strip()
    _git(repo, "replace", authority_pin_blob, replacement_pin_blob)
    _git(repo, "replace", authority_launcher_blob, replacement_launcher_blob)

    completed = _trusted_launcher(repo, pin_path)

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["receipt"]["evaluator_pin"]["protocol_revision"] == pin.protocol_revision
    assert not marker.exists()


def test_candidate_cannot_replace_approved_pin_configuration(tmp_path):
    repo = _repo(tmp_path)
    pin = eval_pilot.build_evaluator_pin(repo)
    pin_path = repo / "specs/approved.evaluator-pin.json"
    pin_path.parent.mkdir()
    pin_path.write_text(json.dumps(pin.model_dump(mode="json")) + "\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "approve evaluator")

    replacement = pin.model_copy(update={"protocol_revision": "attacker/v2"})
    pin_path.write_text(
        json.dumps(replacement.model_dump(mode="json")) + "\n", encoding="utf-8"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "replace approved configuration")

    completed = _trusted_launcher(repo, pin_path)

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["receipt"]["evaluator_pin"]["protocol_revision"] == pin.protocol_revision
    assert payload["promotion"]["allowed"] is False


def _external_acceptance_candidate(tmp_path: Path) -> tuple[Path, Path]:
    repo = _repo(tmp_path)
    pin = eval_pilot.build_evaluator_pin(repo)
    pin_path = repo / "specs/advisory.evaluator-pin.json"
    pin_path.parent.mkdir()
    pin_path.write_text(json.dumps(pin.model_dump(mode="json")) + "\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "record advisory evaluator pin")
    (repo / "src/codesight/production.py").write_text("production-v2\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "candidate")
    return repo, pin_path


def _mutate_nested(path: str, value):
    def mutate(payload: dict) -> None:
        target = payload
        parts = path.split(".")
        for part in parts[:-1]:
            target = target[part]
        target[parts[-1]] = value(payload) if callable(value) else value

    return mutate


def test_candidate_created_pin_only_lineage_cannot_establish_acceptance(tmp_path):
    repo = _repo(tmp_path)
    pin = eval_pilot.build_evaluator_pin(repo)
    pin_path = repo / "specs/candidate.evaluator-pin.json"
    pin_path.parent.mkdir()
    pin_path.write_text(json.dumps(pin.model_dump(mode="json")) + "\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "candidate-created pin-only authority")
    (repo / "src/codesight/production.py").write_text("production-v2\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "candidate")

    launcher = repo / "src/codesight/trusted_eval_launcher.py"
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            str(launcher),
            "--repo-root",
            str(repo),
            "--authority-subject",
            _git_output(repo, "rev-parse", "HEAD^").decode().strip(),
            "--evaluator-pin",
            str(pin_path),
            "--cases",
            str(repo / eval_pilot.CANONICAL_EVALUATOR_CASES_PATH),
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "--acceptance-record" in completed.stderr
    assert "--attestation-capability-fd" in completed.stderr
    assert not (repo / ".holusight/improvement-results/receipts").exists()


@pytest.mark.parametrize(
    ("path", "value", "error"),
    [
        ("candidate.commit", "0" * 40, "stale"),
        ("candidate.tree", "0" * 40, "stale"),
        ("evaluator.pin_blob", "0" * 40, "pin blob bytes"),
        ("evaluator.pin_sha256", "sha256:" + "0" * 64, "pin bytes"),
        ("evaluator.identity_sha256", "sha256:" + "0" * 64, "evaluator identity"),
        ("launcher.blob", "0" * 40, "launcher blob bytes"),
        ("launcher.sha256", "sha256:" + "0" * 64, "launcher"),
        ("manifest.blob", "0" * 40, "manifest blob bytes"),
        ("manifest.sha256", "sha256:" + "0" * 64, "manifest bytes"),
        ("corpus.blob", "0" * 40, "corpus identity"),
        ("corpus.sha256", "sha256:" + "0" * 64, "corpus bytes"),
        ("configuration.identity_sha256", "sha256:" + "0" * 64, "configuration"),
        ("configuration.candidate_id", "substituted", "runtime configuration"),
        ("configuration.egress_allowed", 0, "runtime configuration"),
        ("record_version", True, "version is unsupported"),
        ("decision", "rejected", "decision"),
        ("replay.replay_version", True, "rolled back"),
        ("replay.sequence", 2, "rolled back"),
        (
            "replay.expires_at",
            lambda _payload: int(time.time()) - 1,
            "stale",
        ),
    ],
)
def test_external_acceptance_byte_verifies_every_binding(tmp_path, path, value, error):
    repo, pin_path = _external_acceptance_candidate(tmp_path)

    completed = _trusted_launcher(
        repo,
        pin_path,
        mutate_record=_mutate_nested(path, value),
    )

    assert completed.returncode == 2
    assert error in completed.stderr
    assert not (repo / ".holusight/improvement-results/receipts").exists()


@pytest.mark.parametrize(
    ("path", "value", "error"),
    [
        ("acceptance_record_sha256", "sha256:" + "0" * 64, "substituted or rolled back"),
        ("replay_sequence", 2, "rolled back or substituted"),
        ("key_hex", "00" * 32, "attestation"),
    ],
)
def test_external_capability_rejects_substitution_and_rollback(
    tmp_path, path, value, error
):
    repo, pin_path = _external_acceptance_candidate(tmp_path)

    completed = _trusted_launcher(
        repo,
        pin_path,
        mutate_capability=lambda capability: capability.__setitem__(path, value),
    )

    assert completed.returncode == 2
    assert error in completed.stderr


def test_attestation_capability_must_be_launcher_held_and_one_shot(tmp_path):
    repo, pin_path = _external_acceptance_candidate(tmp_path)

    completed = _trusted_launcher(
        repo,
        pin_path,
        capability_as_regular_file=True,
    )

    assert completed.returncode == 2
    assert "launcher-held one-shot descriptor" in completed.stderr


def test_external_acceptance_rejects_ambiguous_or_absent_fields(tmp_path):
    repo, pin_path = _external_acceptance_candidate(tmp_path)
    ambiguous = _trusted_launcher(
        repo,
        pin_path,
        transform_record_bytes=lambda raw: b'{"decision":"accepted",' + raw[1:],
    )
    absent = _trusted_launcher(
        repo,
        pin_path,
        mutate_record=lambda record: record.pop("manifest"),
    )

    assert ambiguous.returncode == 2
    assert "unambiguous JSON" in ambiguous.stderr
    assert absent.returncode == 2
    assert "fields are not closed" in absent.stderr


@pytest.mark.parametrize(
    ("mode", "inside"),
    [(0o600, False), (0o400, True)],
)
def test_external_acceptance_rejects_candidate_writable_records(tmp_path, mode, inside):
    repo, pin_path = _external_acceptance_candidate(tmp_path)

    completed = _trusted_launcher(
        repo,
        pin_path,
        record_mode=mode,
        record_inside_candidate=inside,
    )

    assert completed.returncode == 2
    assert "candidate-writable" in completed.stderr


def test_external_acceptance_rejects_self_reference_and_stale_candidate(tmp_path):
    repo, pin_path = _external_acceptance_candidate(tmp_path)
    pin = json.loads(pin_path.read_text(encoding="utf-8"))
    self_reference = _trusted_launcher(
        repo,
        pin_path,
        mutate_record=lambda record: record["candidate"].update(
            {"commit": pin["subject"]["commit"], "tree": pin["subject"]["tree"]}
        ),
    )

    def advance_candidate(candidate_repo: Path) -> None:
        (candidate_repo / "src/codesight/production.py").write_text(
            "production-v3\n", encoding="utf-8"
        )
        _git(candidate_repo, "add", ".")
        _git(candidate_repo, "commit", "-q", "-m", "advance after acceptance")

    stale = _trusted_launcher(repo, pin_path, before_launch=advance_candidate)

    assert self_reference.returncode == 2
    assert "self-referential" in self_reference.stderr
    assert stale.returncode == 2
    assert "stale" in stale.stderr


def test_running_launcher_substitution_is_rejected(tmp_path):
    repo, pin_path = _external_acceptance_candidate(tmp_path)

    completed = _trusted_launcher(
        repo,
        pin_path,
        transform_launcher_bytes=lambda raw: raw + b"\n# substituted\n",
    )

    assert completed.returncode == 2
    assert "running launcher bytes were substituted" in completed.stderr


def test_external_launcher_sandboxes_evaluator_import_and_finalization(tmp_path):
    repo = _repo(tmp_path)
    marker = tmp_path.parent / f"{tmp_path.name}-host-write"
    received = threading.Event()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(2)
    server.settimeout(30)
    port = server.getsockname()[1]

    def receive_probes() -> None:
        try:
            while True:
                connection, _ = server.accept()
                with connection:
                    if connection.recv(32) == b"outer-evaluator-probe":
                        received.set()
        except OSError:
            pass

    receiver = threading.Thread(target=receive_probes, daemon=True)
    receiver.start()
    evaluator = repo / "src/codesight/eval_pilot.py"
    probe = (
        "\ndef _outer_sandbox_probe():\n"
        "    try:\n"
        f"        ProbePath({str(marker)!r}).write_text('escaped', encoding='utf-8')\n"
        "    except OSError:\n"
        "        pass\n"
        "    try:\n"
        f"        with socket.create_connection(('127.0.0.1', {port}), timeout=1) as probe:\n"
        "            probe.sendall(b'outer-evaluator-probe')\n"
        "    except OSError:\n"
        "        pass\n"
        "\n_outer_sandbox_probe()\n"
    )
    source = evaluator.read_text(encoding="utf-8").replace(
        "import argparse\n",
        "import argparse\nimport socket\nfrom pathlib import Path as ProbePath\n" + probe,
        1,
    )
    source = source.replace(
        "        receipt = build_trusted_receipt(\n",
        "        _outer_sandbox_probe()\n        receipt = build_trusted_receipt(\n",
        1,
    )
    evaluator.write_text(source, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "approved evaluator sandbox probes")
    pin = eval_pilot.build_evaluator_pin(repo)
    pin_path = repo / "specs/advisory.evaluator-pin.json"
    pin_path.parent.mkdir()
    pin_path.write_text(json.dumps(pin.model_dump(mode="json")) + "\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "record advisory pin")
    (repo / "src/codesight/production.py").write_text("production-v2\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "candidate")

    try:
        completed = _trusted_launcher(repo, pin_path)
    finally:
        server.close()
        receiver.join(timeout=1)

    assert completed.returncode == 0, completed.stderr
    assert not marker.exists()
    assert not received.is_set()


def test_candidate_tracked_pin_is_advisory_only(tmp_path):
    repo, pin_path = _external_acceptance_candidate(tmp_path)
    pin_path.write_text('{"candidate":"claims authority"}\n', encoding="utf-8")
    _git(repo, "add", pin_path.relative_to(repo).as_posix())
    _git(repo, "commit", "-q", "-m", "candidate replaces advisory pin")

    completed = _trusted_launcher(repo, pin_path)

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["promotion"]["allowed"] is False
    assert payload["acceptance"]["replay_sequence"] == 1
    assert payload["receipt"]["acceptance"] == {
        "record_sha256": payload["acceptance"]["record_sha256"],
        "replay_version": 1,
        "replay_epoch": payload["acceptance"]["replay_epoch"],
        "replay_sequence": payload["acceptance"]["replay_sequence"],
        "configuration_sha256": payload["acceptance"]["configuration_sha256"],
        "decision": "accepted",
    }


def test_candidate_manifest_cannot_refer_to_acceptance_authority(tmp_path):
    repo, pin_path = _external_acceptance_candidate(tmp_path)
    manifest = repo / "specs/candidate.change.json"
    manifest.write_text(
        '{"schema_version":"holus-external-evaluator-acceptance/v1"}\n',
        encoding="utf-8",
    )
    _git(repo, "add", manifest.relative_to(repo).as_posix())
    _git(repo, "commit", "-q", "-m", "self-referential manifest")

    completed = _trusted_launcher(repo, pin_path)

    assert completed.returncode == 2
    assert "self-referential" in completed.stderr


def test_candidate_owned_authority_at_head_is_rejected(tmp_path):
    repo = _repo(tmp_path)
    pin = eval_pilot.build_evaluator_pin(repo)
    pin_path = repo / "specs/self-approved.evaluator-pin.json"
    pin_path.parent.mkdir()
    pin_path.write_text(json.dumps(pin.model_dump(mode="json")) + "\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "self-approved candidate authority")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    pin_blob = subprocess.run(
        ["git", "rev-parse", "HEAD:specs/self-approved.evaluator-pin.json"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    launcher_blob = subprocess.run(
        ["git", "rev-parse", "HEAD:src/codesight/trusted_eval_launcher.py"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    launcher = subprocess.run(
        ["git", "show", "HEAD:src/codesight/trusted_eval_launcher.py"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            launcher,
            "--repo-root",
            str(repo),
            "--authority-subject",
            head,
            "--authority-pin-blob",
            pin_blob,
            "--authority-launcher-blob",
            launcher_blob,
            "--cases",
            str(repo / eval_pilot.CANONICAL_EVALUATOR_CASES_PATH),
            "--evaluator-pin",
            str(pin_path),
        ],
        cwd=repo,
        env={"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "--acceptance-record" in completed.stderr
    assert "--attestation-capability-fd" in completed.stderr


def test_candidate_adapter_cannot_spawn_processes_under_trusted_profile(tmp_path):
    repo = _repo(tmp_path)
    pin = eval_pilot.build_evaluator_pin(repo)
    provider = repo / "src/codesight/axi_providers.py"
    provider.write_text(
        provider.read_text(encoding="utf-8").replace(
            '    saved = os.environ.pop("VOYAGE_API_KEY", None)\n',
            "    import subprocess, sys\n"
            "    subprocess.run([sys.executable, '-c', 'pass'], check=True)\n"
            '    saved = os.environ.pop("VOYAGE_API_KEY", None)\n',
            1,
        ),
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "candidate process spawn")

    result = eval_pilot.run_pinned_pilot(
        repo,
        pin=pin,
        cases_path=repo / eval_pilot.CANONICAL_EVALUATOR_CASES_PATH,
        lineage=eval_pilot.CandidateLineage(
            candidate_id="process-spawn", repo_commit=None, workflow="test", tool="pytest"
        ),
    )

    assert result.counts.errored == 1
    assert result.grades[0].verdict == "error"


@pytest.mark.skipif(
    not sys.platform.startswith("linux")
    or platform.machine().lower() not in {"x86_64", "amd64"}
    or shutil.which("bwrap") is None,
    reason="requires Linux x86_64 bubblewrap seccomp",
)
def test_candidate_adapter_denies_compatibility_abi_fork(tmp_path):
    repo = _repo(tmp_path)
    pin = eval_pilot.build_evaluator_pin(repo)
    provider = repo / "src/codesight/axi_providers.py"
    provider.write_text(
        provider.read_text(encoding="utf-8").replace(
            '    saved = os.environ.pop("VOYAGE_API_KEY", None)\n',
            "    import ctypes, mmap\n"
            "    code = mmap.mmap(-1, mmap.PAGESIZE, prot=(mmap.PROT_READ | "
            "mmap.PROT_WRITE | mmap.PROT_EXEC))\n"
            "    code.write(b'\\xb8\\x02\\x00\\x00\\x00\\xcd\\x80\\xc3')\n"
            "    address = ctypes.addressof(ctypes.c_char.from_buffer(code))\n"
            "    compat_fork = ctypes.CFUNCTYPE(ctypes.c_long)(address)\n"
            "    pid = compat_fork()\n"
            "    if pid == 0: os._exit(0)\n"
            "    if pid > 0: os.waitpid(pid, 0)\n"
            '    saved = os.environ.pop("VOYAGE_API_KEY", None)\n',
            1,
        ),
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "candidate compatibility fork")

    result = eval_pilot.run_pinned_pilot(
        repo,
        pin=pin,
        cases_path=repo / eval_pilot.CANONICAL_EVALUATOR_CASES_PATH,
        lineage=eval_pilot.CandidateLineage(
            candidate_id="compatibility-fork", repo_commit=None, workflow="test", tool="pytest"
        ),
    )

    assert result.counts.errored == 1
    assert result.grades[0].verdict == "error"


def test_bounded_process_terminates_descendant_tree(tmp_path):
    marker = tmp_path / "escaped-child"
    child = (
        f"import pathlib,time; time.sleep(2); pathlib.Path({str(marker)!r}).write_text('escaped')"
    )
    parent = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable, '-c', {child!r}]); time.sleep(30)"
    )

    result = eval_pilot._run_bounded_process(
        [sys.executable, "-c", parent],
        cwd=tmp_path,
        env=dict(os.environ),
        input_text=None,
        timeout=1,
        output_dir=tmp_path,
        cpu_seconds=10,
        memory_bytes=536_870_912,
        process_count=1024,
        max_output_bytes=65_536,
    )

    time.sleep(2.5)
    assert result.timed_out is True
    assert not marker.exists()


def test_trusted_evaluator_denies_host_reads_and_optional_egress(tmp_path):
    repo = _repo(tmp_path)
    pin = eval_pilot.build_evaluator_pin(repo)
    secret_path = tmp_path.parent / f"{tmp_path.name}-host-secret"
    secret_path.write_text("private-host-value\n", encoding="utf-8")
    provider_path = repo / "src/codesight/axi_providers.py"
    provider_path.write_text(
        provider_path.read_text(encoding="utf-8").replace(
            '    saved = os.environ.pop("VOYAGE_API_KEY", None)\n',
            f"    Path({str(secret_path)!r}).read_text(encoding='utf-8')\n"
            '    saved = os.environ.pop("VOYAGE_API_KEY", None)\n',
            1,
        ),
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "candidate host read")

    result = eval_pilot.run_pinned_pilot(
        repo,
        pin=pin,
        cases_path=repo / eval_pilot.CANONICAL_EVALUATOR_CASES_PATH,
        lineage=eval_pilot.CandidateLineage(
            candidate_id="host-read", repo_commit=None, workflow="test", tool="pytest"
        ),
    )
    assert result.counts.errored == 1
    with pytest.raises(ValueError, match="only local non-semantic"):
        eval_pilot.run_pinned_pilot(
            repo,
            pin=pin,
            cases_path=repo / eval_pilot.CANONICAL_EVALUATOR_CASES_PATH,
            lineage=eval_pilot.CandidateLineage(
                candidate_id="egress", repo_commit=None, workflow="test", tool="pytest"
            ),
            allow_egress=True,
        )


def test_unpinned_public_run_stays_outside_trusted_receipt_boundary(tmp_path):
    repo = _repo(tmp_path)
    command = Path(sys.executable).with_name("holus")
    completed = subprocess.run(
        [
            str(command),
            "improve-run",
            "--cases",
            eval_pilot.CANONICAL_EVALUATOR_CASES_PATH,
            "--candidate-id",
            "advisory",
            "--format",
            "json",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout
    payload = json.loads(completed.stdout)
    assert payload["lifecycle"].get("receipt") is None
    assert payload["lifecycle"].get("evaluation_trust", "advisory_unpinned") == (
        "advisory_unpinned"
    )
    assert not (repo / ".holusight/improvement-results/receipts").exists()


def test_unanchored_prior_cannot_derive_a_trusted_evaluator(tmp_path):
    repo = _repo(tmp_path)
    prior = _run(repo, candidate="advisory")
    prior_path = repo / ".holusight/improvement-results/prior.json"
    prior_path.parent.mkdir(parents=True)
    prior_path.write_text(json.dumps(prior.model_dump(mode="json")) + "\n", encoding="utf-8")
    command = Path(sys.executable).with_name("holus")
    completed = subprocess.run(
        [
            str(command),
            "improve-run",
            "--cases",
            eval_pilot.CANONICAL_EVALUATOR_CASES_PATH,
            "--candidate-id",
            "advisory",
            "--compare-result",
            ".holusight/improvement-results/prior.json",
            "--format",
            "json",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout
    payload = json.loads(completed.stdout)
    assert payload["lifecycle"].get("receipt") is None
    assert payload["lifecycle"].get("evaluation_trust", "advisory_unpinned") == (
        "advisory_unpinned"
    )
    assert payload["lifecycle"].get("evaluator_pin", {}).get("reference") is None
    assert payload["progress"]["comparison"]["promotion_relevant"] is False


def test_trusted_execution_rejects_baseline_derived_evaluator_authority(
    tmp_path, monkeypatch
):
    repo = _repo(tmp_path)
    baseline = _run(repo)
    pin = eval_pilot.build_evaluator_pin(repo)
    compare_path = repo / ".holusight/improvement-results/prior.json"
    compare_path.parent.mkdir(parents=True)
    compare_path.write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(
        eval_pilot,
        "load_anchored_baseline",
        lambda *_args: (baseline, _anchor(repo, baseline)),
    )

    def derived_pin_must_not_run(*_args, **_kwargs):
        raise AssertionError("baseline-derived evaluator authority was used")

    monkeypatch.setattr(eval_pilot, "evaluator_pin_for_result", derived_pin_must_not_run)

    with pytest.raises(ValueError, match="external acceptance record pin"):
        eval_pilot.execute_trusted_evaluation(
            repo,
            evaluator_pin_path=None,
            cases_path=repo / eval_pilot.CANONICAL_EVALUATOR_CASES_PATH,
            compare_path=compare_path,
            candidate_id="candidate",
            workflow="test",
            tool="pytest",
            launcher_subject=pin.subject.commit,
            approved_pin_blob="0" * 40,
        )


def test_load_pin_rejects_worktree_swap_after_git_subject_capture(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    approved = eval_pilot.build_evaluator_pin(repo)
    pin_path = repo / "specs/approved.evaluator-pin.json"
    pin_path.parent.mkdir()
    pin_path.write_text(json.dumps(approved.model_dump(mode="json")) + "\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "approve evaluator")
    replacement = approved.model_copy(update={"protocol_revision": "attacker/v2"})
    original_git_run = eval_pilot._git_run

    def swapping_git_run(root, *args, **kwargs):
        completed = original_git_run(root, *args, **kwargs)
        if args[:1] == ("show",) and args[1].endswith(":specs/approved.evaluator-pin.json"):
            pin_path.write_text(
                json.dumps(replacement.model_dump(mode="json")) + "\n", encoding="utf-8"
            )
        return completed

    monkeypatch.setattr(eval_pilot, "_git_run", swapping_git_run)
    with pytest.raises(ValueError, match="changed while its Git identity was captured"):
        eval_pilot.load_evaluator_pin(repo, pin_path)


def test_load_pin_rejects_reused_protocol_revision(tmp_path):
    repo = _repo(tmp_path)
    approved = eval_pilot.build_evaluator_pin(repo)
    specs = repo / "specs"
    specs.mkdir()
    approved_path = specs / "approved.evaluator-pin.json"
    approved_path.write_text(json.dumps(approved.model_dump(mode="json")) + "\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "approve evaluator")

    evaluator_path = repo / "src/codesight/eval_pilot.py"
    evaluator_path.write_text(evaluator_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "revise evaluator")
    revised = eval_pilot.build_evaluator_pin(
        repo, protocol_revision="holus-eval-pilot/v2"
    ).model_copy(update={"protocol_revision": approved.protocol_revision})
    reused_path = specs / "reused.evaluator-pin.json"
    reused_path.write_text(json.dumps(revised.model_dump(mode="json")) + "\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "reuse evaluator revision")

    with pytest.raises(ValueError, match="new separately reviewed protocol revision"):
        eval_pilot.load_evaluator_pin(repo, reused_path)


def test_receipt_requires_baseline_result_and_anchor_together(tmp_path):
    repo = _repo(tmp_path)
    baseline = _run(repo)

    with pytest.raises(ValueError, match="present or absent together"):
        eval_pilot.build_trusted_receipt(
            baseline,
            evaluator_pin=eval_pilot.build_evaluator_pin(repo),
            evaluator_pin_source="explicit",
            baseline_result=baseline,
            baseline_anchor=None,
        )


def test_receipt_rejects_anchor_for_different_embedded_baseline(tmp_path):
    repo = _repo(tmp_path)
    baseline = _run(repo)
    anchor = _anchor(repo, baseline).model_copy(
        update={"result_payload_hash": "sha256:" + "0" * 64}
    )

    with pytest.raises(ValueError, match="embedded result payload"):
        eval_pilot.build_trusted_receipt(
            baseline,
            evaluator_pin=eval_pilot.build_evaluator_pin(repo),
            evaluator_pin_source="explicit",
            baseline_result=baseline,
            baseline_anchor=anchor,
        )


def test_receipt_reload_uses_bytes_from_held_directory(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    result = _run(repo)
    receipt = eval_pilot.build_trusted_receipt(
        result,
        evaluator_pin=eval_pilot.build_evaluator_pin(repo),
        evaluator_pin_source="explicit",
        baseline_result=None,
        baseline_anchor=None,
    )
    original_create = eval_pilot.safe_atomic_create_or_read_identical

    def replace_receipt_directory(*args, **kwargs):
        destination, persisted = original_create(*args, **kwargs)
        receipts = destination.parent
        displaced = receipts.with_name("receipts-created")
        receipts.rename(displaced)
        receipts.mkdir()
        destination.write_text("{}\n", encoding="utf-8")
        return destination, persisted

    monkeypatch.setattr(
        eval_pilot,
        "safe_atomic_create_or_read_identical",
        replace_receipt_directory,
    )

    _, loaded = eval_pilot.persist_trusted_receipt(repo, receipt)

    created = (
        repo
        / ".holusight/improvement-results/receipts-created"
        / (receipt.receipt_id.removeprefix("sha256:") + ".json")
    )
    assert loaded == receipt
    assert json.loads(created.read_text(encoding="utf-8"))["receipt_id"] == receipt.receipt_id


def test_candidate_receipt_apis_cannot_claim_promotion_relevance(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    baseline = _run(repo)
    current = _run(repo)
    receipt = eval_pilot.build_trusted_receipt(
        current,
        evaluator_pin=eval_pilot.build_evaluator_pin(repo),
        evaluator_pin_source="explicit",
        baseline_result=baseline,
        baseline_anchor=_anchor(repo, baseline),
    )
    monkeypatch.setattr(eval_pilot, "_baseline_anchor_blockers", lambda *_args: [])

    _, persisted = eval_pilot.persist_trusted_receipt(repo, receipt)
    progress = eval_pilot.evaluate_receipt_progress(persisted, repo_root=repo)

    assert progress["comparison"]["review_eligible"] is True
    assert progress["comparison"]["classification"] == "advisory"
    assert progress["comparison"]["promotion_relevant"] is False


def test_receipt_is_content_addressed_create_only_and_drives_progress(tmp_path):
    repo = _repo(tmp_path)
    result = _run(repo)
    receipt = eval_pilot.build_trusted_receipt(
        result,
        evaluator_pin=eval_pilot.build_evaluator_pin(repo),
        evaluator_pin_source="explicit",
        baseline_result=None,
        baseline_anchor=None,
    )

    path, loaded = eval_pilot.persist_trusted_receipt(repo, receipt)
    repeated_path, repeated = eval_pilot.persist_trusted_receipt(repo, receipt)

    assert path == repeated_path
    assert loaded == repeated
    assert path.name == receipt.receipt_id.removeprefix("sha256:") + ".json"
    assert eval_pilot.evaluate_receipt_progress(loaded, repo_root=repo)["outcome"] == (
        "research_needed"
    )
