"""Tests for the persistent local embedding daemon (embedding_daemon.py).

Uses a real Unix domain socket and a real background server thread, but a
fake stand-in for LocalEmbedder -- no real ML model needed to test the
daemon's own protocol, lifecycle, and fallback behavior.

AF_UNIX socket paths have a short OS-enforced length limit (~104 bytes on
macOS); pytest's default tmp_path is nested deep enough to risk exceeding
it, so these tests use a short-rooted tempfile.mkdtemp() directory instead.
"""

from __future__ import annotations

import json
import shutil
import socket
import tempfile
import threading
import time
from pathlib import Path

import numpy as np
import pytest

from holusight import embedding_daemon
from holusight.embeddings import DaemonEmbedder


class _FakeLocalEmbedder:
    """Stand-in for embeddings.LocalEmbedder -- no real model load."""

    def __init__(self, model_name: str, expected_dim: int) -> None:
        self.model_name = model_name
        self.expected_dim = expected_dim
        self.model = "loaded"  # _dispatch touches .model to force a "load"

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.tile(np.arange(self.expected_dim, dtype=np.float32), (len(texts), 1))

    def embed_query(self, query: str) -> np.ndarray:
        return self.embed([query])[0]


@pytest.fixture
def daemon_dir(monkeypatch):
    """A short-rooted temp dir, and every daemon module path pointed at it."""
    d = Path(tempfile.mkdtemp(dir="/tmp"))
    monkeypatch.setattr(embedding_daemon, "DAEMON_DIR", d)
    monkeypatch.setattr(embedding_daemon, "SOCKET_PATH", d / "embed.sock")
    monkeypatch.setattr(embedding_daemon, "PID_PATH", d / "embed.pid")
    monkeypatch.setattr(embedding_daemon, "LOG_PATH", d / "embed.log")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def running_server(daemon_dir, monkeypatch):
    """A real daemon server, running in a background thread, using the fake
    embedder so no real model load happens."""
    monkeypatch.setattr("holusight.embeddings.LocalEmbedder", _FakeLocalEmbedder)

    watchdog = embedding_daemon._IdleWatchdog(timeout_seconds=999)
    server = embedding_daemon._DaemonServer(embedding_daemon.SOCKET_PATH, watchdog)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


def _raw_request(sock_path: Path, request: dict, timeout: float = 2.0) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(str(sock_path))
        sock.sendall(json.dumps(request).encode("utf-8") + b"\n")
        buf = b""
        while b"\n" not in buf:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf += chunk
    line, _, _ = buf.partition(b"\n")
    return json.loads(line.decode("utf-8"))


class TestServerProtocol:
    def test_embed_query_returns_a_vector(self, running_server):
        response = _raw_request(embedding_daemon.SOCKET_PATH, {
            "model_name": "fake-model", "expected_dim": 4,
            "cmd": "embed_query", "texts": ["hello"],
        })
        assert response["vectors"] == [[0.0, 1.0, 2.0, 3.0]]

    def test_embed_returns_one_vector_per_text(self, running_server):
        response = _raw_request(embedding_daemon.SOCKET_PATH, {
            "model_name": "fake-model", "expected_dim": 3,
            "cmd": "embed", "texts": ["a", "b"],
        })
        assert response["vectors"] == [[0.0, 1.0, 2.0], [0.0, 1.0, 2.0]]

    def test_unknown_cmd_returns_an_error_not_a_crash(self, running_server):
        response = _raw_request(embedding_daemon.SOCKET_PATH, {
            "model_name": "fake-model", "expected_dim": 3,
            "cmd": "not_a_real_command", "texts": ["a"],
        })
        assert "error" in response
        # The server must still be alive after a bad request.
        again = _raw_request(embedding_daemon.SOCKET_PATH, {
            "model_name": "fake-model", "expected_dim": 3,
            "cmd": "embed", "texts": ["a"],
        })
        assert "vectors" in again

    def test_malformed_json_returns_an_error_not_a_crash(self, running_server):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(2.0)
            sock.connect(str(embedding_daemon.SOCKET_PATH))
            sock.sendall(b"not valid json at all\n")
            buf = sock.recv(65536)
        response = json.loads(buf.decode("utf-8"))
        assert "error" in response

    def test_reuses_the_same_embedder_across_requests(self, running_server):
        _raw_request(embedding_daemon.SOCKET_PATH, {
            "model_name": "fake-model", "expected_dim": 2,
            "cmd": "embed_query", "texts": ["first"],
        })
        _raw_request(embedding_daemon.SOCKET_PATH, {
            "model_name": "fake-model", "expected_dim": 2,
            "cmd": "embed_query", "texts": ["second"],
        })
        assert len(running_server.embedders) == 1

    def test_different_model_configs_get_separate_embedders(self, running_server):
        _raw_request(embedding_daemon.SOCKET_PATH, {
            "model_name": "model-a", "expected_dim": 2,
            "cmd": "embed_query", "texts": ["x"],
        })
        _raw_request(embedding_daemon.SOCKET_PATH, {
            "model_name": "model-b", "expected_dim": 4,
            "cmd": "embed_query", "texts": ["x"],
        })
        assert len(running_server.embedders) == 2


class TestIdleWatchdog:
    def test_touch_resets_the_idle_clock(self):
        watchdog = embedding_daemon._IdleWatchdog(timeout_seconds=999)
        first = watchdog._last_activity
        time.sleep(0.05)
        watchdog.touch()
        assert watchdog._last_activity > first


class TestClient:
    def test_call_daemon_returns_none_when_socket_does_not_exist(self, daemon_dir):
        result = embedding_daemon.call_daemon("m", 4, "embed_query", ["x"])
        assert result is None

    def test_call_daemon_returns_vectors_from_a_real_server(self, running_server):
        result = embedding_daemon.call_daemon("fake-model", 3, "embed", ["a", "b"])
        assert result == [[0.0, 1.0, 2.0], [0.0, 1.0, 2.0]]

    def test_call_daemon_never_raises_on_connection_refused(self, daemon_dir):
        # Socket path exists but nothing is listening on it.
        embedding_daemon.SOCKET_PATH.touch()
        result = embedding_daemon.call_daemon("m", 4, "embed_query", ["x"])
        assert result is None

    def test_is_daemon_running_false_with_no_pid_file(self, daemon_dir):
        assert embedding_daemon.is_daemon_running() is False

    def test_is_daemon_running_false_for_a_dead_pid(self, daemon_dir):
        embedding_daemon.SOCKET_PATH.touch()
        # A PID number this high should never correspond to a live process.
        embedding_daemon.PID_PATH.write_text("999999", encoding="utf-8")
        assert embedding_daemon.is_daemon_running() is False


class TestEnsureDaemonSpawned:
    def test_does_not_spawn_when_already_running(self, daemon_dir, monkeypatch):
        monkeypatch.setattr(embedding_daemon, "is_daemon_running", lambda: True)
        spawned = []
        monkeypatch.setattr(
            "subprocess.Popen", lambda *a, **k: spawned.append((a, k)),
        )
        embedding_daemon.ensure_daemon_spawned()
        assert spawned == []

    def test_spawns_when_not_running(self, daemon_dir, monkeypatch):
        monkeypatch.setattr(embedding_daemon, "is_daemon_running", lambda: False)
        spawned = []
        monkeypatch.setattr(
            "subprocess.Popen", lambda *a, **k: spawned.append((a, k)),
        )
        embedding_daemon.ensure_daemon_spawned()
        assert len(spawned) == 1
        argv = spawned[0][0][0]
        assert argv[1:] == ["-m", "holusight.embedding_daemon", "serve"]

    def test_a_failed_spawn_never_raises(self, daemon_dir, monkeypatch):
        monkeypatch.setattr(embedding_daemon, "is_daemon_running", lambda: False)

        def _boom(*_a, **_k):
            raise OSError("no fork slots available")

        monkeypatch.setattr("subprocess.Popen", _boom)
        embedding_daemon.ensure_daemon_spawned()  # must not raise


class TestDaemonEmbedder:
    def test_uses_the_daemon_when_reachable(self, running_server):
        embedder = DaemonEmbedder(model_name="fake-model", expected_dim=3)
        vector = embedder.embed_query("hello")
        np.testing.assert_allclose(vector, [0.0, 1.0, 2.0])
        # The fallback embedder must never have been constructed.
        assert embedder._fallback is None

    def test_falls_back_when_daemon_unreachable(self, daemon_dir, monkeypatch):
        monkeypatch.setattr("holusight.embeddings.LocalEmbedder", _FakeLocalEmbedder)
        monkeypatch.setattr(embedding_daemon, "ensure_daemon_spawned", lambda: None)

        embedder = DaemonEmbedder(model_name="fake-model", expected_dim=3)
        vector = embedder.embed_query("hello")
        np.testing.assert_allclose(vector, [0.0, 1.0, 2.0])
        assert embedder._fallback is not None

    def test_falls_back_for_embed_too(self, daemon_dir, monkeypatch):
        monkeypatch.setattr("holusight.embeddings.LocalEmbedder", _FakeLocalEmbedder)
        monkeypatch.setattr(embedding_daemon, "ensure_daemon_spawned", lambda: None)

        embedder = DaemonEmbedder(model_name="fake-model", expected_dim=2)
        vectors = embedder.embed(["a", "b"])
        assert vectors.shape == (2, 2)

    def test_empty_embed_never_touches_the_daemon_or_fallback(self, daemon_dir):
        embedder = DaemonEmbedder(model_name="fake-model", expected_dim=3)
        vectors = embedder.embed([])
        assert vectors.shape == (0, 3)
        assert embedder._fallback is None
