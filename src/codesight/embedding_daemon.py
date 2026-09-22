"""Persistent local embedding daemon.

`holus` is a stateless CLI: every invocation is a fresh process. Loading a
large local embedding model on every single query is a real, measured
latency cost -- on this machine, Qwen3-Embedding-8B takes ~12s to load
from disk plus ~3s to embed one query, every time, with no in-process
caching able to help because the process exits after each command.

This module keeps the model warm in a small background process instead,
so a CLI invocation only pays the load cost once, not per query. Only
backend="local" needs this: API/Voyage backends are already a stateless
HTTP call with no local model to keep warm.

Architecture: a single background process listens on a Unix domain
socket, holds one or more loaded LocalEmbedder instances (keyed the same
way get_embedder() already caches them), and serves embed/embed_query
requests as newline-delimited JSON. It exits itself after an idle
timeout so it never runs forever unattended. get_embedder() (in
embeddings.py) tries the daemon first with a short connect timeout; if
it's not reachable, it spawns the daemon in the background for next
time and falls back to an in-process LocalEmbedder for the current call
-- a query is never blocked waiting for the daemon to start, and any
daemon failure degrades transparently to the same behavior as if this
module didn't exist.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path

from .config import DATA_DIR

logger = logging.getLogger(__name__)

DAEMON_DIR = Path(os.environ.get("CODESIGHT_DAEMON_DIR", DATA_DIR.parent / "daemon"))
SOCKET_PATH = DAEMON_DIR / "embed.sock"
PID_PATH = DAEMON_DIR / "embed.pid"
LOG_PATH = DAEMON_DIR / "embed.log"

IDLE_TIMEOUT_SECONDS = int(os.environ.get("CODESIGHT_DAEMON_IDLE_TIMEOUT", "1800"))
CONNECT_TIMEOUT_SECONDS = 0.5
REQUEST_TIMEOUT_SECONDS = 120  # a single embed call, not the whole connection

# Unix domain socket paths have a short OS-enforced length limit (~104
# bytes on macOS); DAEMON_DIR defaults under DATA_DIR, which is itself
# user-configurable, so this is a real possible failure, not paranoia.
_MAX_SOCKET_PATH_LEN = 100


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------


class _IdleWatchdog:
    """Exits the process after IDLE_TIMEOUT_SECONDS with no request."""

    def __init__(self, timeout_seconds: int) -> None:
        self._timeout = timeout_seconds
        self._last_activity = time.monotonic()
        self._lock = threading.Lock()

    def touch(self) -> None:
        with self._lock:
            self._last_activity = time.monotonic()

    def run(self) -> None:
        while True:
            time.sleep(5)
            with self._lock:
                idle_for = time.monotonic() - self._last_activity
            if idle_for >= self._timeout:
                logger.info("Idle for %.0fs, shutting down", idle_for)
                _cleanup_pid_and_socket()
                os._exit(0)  # noqa: SLF001 - deliberate hard exit, no cleanup handlers to run


class _RequestHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        self.server.watchdog.touch()  # type: ignore[attr-defined]
        buf = b""
        self.request.settimeout(REQUEST_TIMEOUT_SECONDS)
        try:
            while b"\n" not in buf:
                chunk = self.request.recv(65536)
                if not chunk:
                    return
                buf += chunk
            line, _, _ = buf.partition(b"\n")
            request = json.loads(line.decode("utf-8"))
            response = self._dispatch(request)
        except Exception as exc:  # noqa: BLE001 - always reply, never crash the server
            logger.warning("Request failed: %s", exc, exc_info=True)
            response = {"error": f"{type(exc).__name__}: {exc}"}
        try:
            self.request.sendall(json.dumps(response).encode("utf-8") + b"\n")
        except OSError:
            pass  # client already disconnected

    def _dispatch(self, request: dict) -> dict:
        from .embeddings import LocalEmbedder  # local import: avoid a cycle at module load

        model_name = request["model_name"]
        expected_dim = request["expected_dim"]
        cmd = request["cmd"]
        texts = request["texts"]

        key = (model_name, expected_dim)
        embedders: dict = self.server.embedders  # type: ignore[attr-defined]
        lock: threading.Lock = self.server.model_lock  # type: ignore[attr-defined]
        with lock:
            embedder = embedders.get(key)
            if embedder is None:
                embedder = LocalEmbedder(model_name=model_name, expected_dim=expected_dim)
                embedder.model  # noqa: B018 - force the lazy load now, inside the lock
                embedders[key] = embedder

            if cmd == "embed_query":
                vector = embedder.embed_query(texts[0])
                vectors = [vector.tolist()]
            elif cmd == "embed":
                vectors = embedder.embed(texts).tolist()
            else:
                raise ValueError(f"unknown cmd: {cmd!r}")
        return {"vectors": vectors}


class _DaemonServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, socket_path: Path, watchdog: _IdleWatchdog) -> None:
        super().__init__(str(socket_path), _RequestHandler)
        self.embedders: dict = {}
        self.model_lock = threading.Lock()
        self.watchdog = watchdog


def _cleanup_pid_and_socket() -> None:
    for path in (SOCKET_PATH, PID_PATH):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def serve() -> None:
    """Run the daemon in the foreground. Called via the CLI entrypoint,
    normally as a detached background process spawned by ensure_daemon_spawned()."""
    DAEMON_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(LOG_PATH), level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    _cleanup_pid_and_socket()
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")

    watchdog = _IdleWatchdog(IDLE_TIMEOUT_SECONDS)
    threading.Thread(target=watchdog.run, daemon=True).start()

    server = _DaemonServer(SOCKET_PATH, watchdog)
    logger.info("Listening on %s (idle timeout %ds)", SOCKET_PATH, IDLE_TIMEOUT_SECONDS)
    try:
        server.serve_forever()
    finally:
        _cleanup_pid_and_socket()


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def is_daemon_running() -> bool:
    if not PID_PATH.exists() or not SOCKET_PATH.exists():
        return False
    try:
        pid = int(PID_PATH.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return False
    return _pid_is_alive(pid)


def ensure_daemon_spawned() -> None:
    """Fire-and-forget: start the daemon in the background if it isn't
    already running. Never raises -- a failed spawn just means every call
    keeps falling back to in-process loading, same as if this module
    didn't exist."""
    if is_daemon_running():
        return
    try:
        DAEMON_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "ab") as log_file:
            subprocess.Popen(  # noqa: S603 - fixed argv, no shell, no user input
                [sys.executable, "-m", "codesight.embedding_daemon", "serve"],
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=log_file,
                start_new_session=True,
            )
    except OSError as exc:
        logger.debug("Could not spawn embedding daemon: %s", exc)


def call_daemon(
    model_name: str, expected_dim: int, cmd: str, texts: list[str],
) -> list[list[float]] | None:
    """Returns embedded vectors, or None if the daemon is unreachable or
    errored -- callers must fall back to in-process embedding on None,
    never raise the caller's request on a daemon failure."""
    if len(str(SOCKET_PATH)) > _MAX_SOCKET_PATH_LEN:
        return None
    if not SOCKET_PATH.exists():
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(CONNECT_TIMEOUT_SECONDS)
            sock.connect(str(SOCKET_PATH))
            request = {
                "model_name": model_name, "expected_dim": expected_dim,
                "cmd": cmd, "texts": texts,
            }
            sock.sendall(json.dumps(request).encode("utf-8") + b"\n")
            sock.settimeout(REQUEST_TIMEOUT_SECONDS)
            buf = b""
            while b"\n" not in buf:
                chunk = sock.recv(65536)
                if not chunk:
                    return None
                buf += chunk
        line, _, _ = buf.partition(b"\n")
        response = json.loads(line.decode("utf-8"))
    except (OSError, json.JSONDecodeError, KeyError):
        return None
    if "error" in response:
        logger.debug("Daemon returned an error: %s", response["error"])
        return None
    return response.get("vectors")


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def stop() -> None:
    if not PID_PATH.exists():
        print("daemon is not running")
        return
    try:
        pid = int(PID_PATH.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        print("daemon is not running")
        return
    if not _pid_is_alive(pid):
        print("daemon is not running")
        _cleanup_pid_and_socket()
        return
    os.kill(pid, 15)  # SIGTERM
    print(f"stopped daemon (pid {pid})")


def status() -> None:
    if is_daemon_running():
        pid = PID_PATH.read_text(encoding="utf-8").strip()
        print(f"running (pid {pid}, socket {SOCKET_PATH})")
    else:
        print("not running")


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    cmd = args[0] if args else "serve"
    if cmd == "serve":
        serve()
    elif cmd == "stop":
        stop()
    elif cmd == "status":
        status()
    else:
        print(f"unknown command: {cmd!r} (expected serve/stop/status)", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
