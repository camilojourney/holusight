"""Session-wide test fixtures.

get_embedder(backend="local") now returns a DaemonEmbedder that, on a
cache miss, spawns a detached background daemon process
(embedding_daemon.ensure_daemon_spawned) that outlives the test run. A
test suite must never have that side effect -- HOLUSIGHT_DAEMON_DISABLED
routes get_embedder() back to a plain in-process LocalEmbedder for every
test, same behavior as before the daemon existed. tests/test_embedding_daemon.py
tests the daemon directly (DaemonEmbedder, embedding_daemon.*), which
does not go through get_embedder()'s dispatch, so this is unaffected by
that file's tests.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _disable_embedding_daemon_for_tests():
    os.environ["HOLUSIGHT_DAEMON_DISABLED"] = "1"
    yield
