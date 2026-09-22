"""Holusight.search()'s auto_index parameter.

Default (auto_index=True) preserves the casual Python-API/CLI "just
works" convenience: build the index if missing, refresh if stale, force
a full rebuild if the configured embedding model no longer matches what
the index was built with. auto_index=False exists specifically for a
caller (holus's AXI semantic provider) that must never have search()
silently trigger that rebuild as a side effect -- see
tests/test_cli_axi.py::test_semantic_provider_never_rebuilds_on_model_mismatch
for the real regression this was built to fix.
"""

from __future__ import annotations

from pathlib import Path

from holusight.api import Holusight


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "a.txt").write_text("hello world", encoding="utf-8")
    return tmp_path


class TestAutoIndex:
    def test_default_rebuilds_on_model_mismatch(self, tmp_path):
        repo = _repo(tmp_path)
        engine = Holusight(repo)
        engine.index()
        engine.store.fts.set_meta("embedding_model", "a-totally-different-model")

        engine.search("hello")  # must not raise; must rebuild silently (documented default)

        assert engine.store.fts.get_meta("embedding_model") == engine.config.embedding_model

    def test_auto_index_false_never_rebuilds_on_model_mismatch(self, tmp_path, monkeypatch):
        repo = _repo(tmp_path)
        engine = Holusight(repo)
        engine.index()
        engine.store.fts.set_meta("embedding_model", "a-totally-different-model")

        def _fail_if_called(*_a, **_k):
            raise AssertionError("index() must never be called when auto_index=False")

        monkeypatch.setattr(Holusight, "index", _fail_if_called)

        engine.search("hello", auto_index=False)  # must not raise, must not rebuild

        assert engine.store.fts.get_meta("embedding_model") == "a-totally-different-model"

    def test_auto_index_false_never_builds_a_missing_index(self, tmp_path):
        """auto_index=False skips the whole convenience, including the
        "no index yet -- build one" first-run case, not just the
        rebuild-on-mismatch case. hybrid_search degrades to an empty
        result on a missing table rather than raising -- it must stay
        empty, and no index may appear as a side effect of this call."""
        repo = _repo(tmp_path)
        engine = Holusight(repo)

        results = engine.search("hello", auto_index=False)

        assert results == []
        assert not engine.store.is_indexed
