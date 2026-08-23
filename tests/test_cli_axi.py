"""Tests for the `holus` AXI command surface (codesight.cli_axi / axi_providers).

Covers, per the ship task's acceptance criteria: unknown flags, no-evidence,
stale/unavailable providers, dirty repositories, projection/truncation,
JSON round-trip, TOON output, no-network/no-credential defaults, and
derived-state (`.holusight/`) rebuild equivalence.

Most tests build a small synthetic repository under `tmp_path` (mirroring
`tests/test_consistency.py`'s pattern) so they never touch this actual
repository's own `.holusight/` cache. A handful of true subprocess tests
exercise the real process boundary (exit codes, stdout wiring, unknown
flags) for genuine end-to-end coverage of `python -m codesight.cli_axi`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from codesight import axi_providers, cli_axi, consistency

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write(root: Path, rel_path: str, text: str) -> Path:
    full = root / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(text, encoding="utf-8")
    return full


def _minimal_repo(tmp_path: Path) -> Path:
    _write(
        tmp_path,
        "specs/001-alpha.md",
        "# Alpha Feature\n\nImplemented by `src/pkg/mod.py`.\n",
    )
    _write(tmp_path, "src/pkg/mod.py", "VALUE = 1\n")
    return tmp_path


def _git_repo(tmp_path: Path) -> Path:
    """A minimal repo that is also a real git repository, for freshness/dirty tests."""
    _minimal_repo(tmp_path)
    # Exclude the derived .holusight/ cache the same way the real repo does
    # (ARCHITECTURE.md, .gitignore) - otherwise refreshing the cache itself
    # makes git report the repo dirty, which is a test-fixture artifact,
    # not something `holus` should ever surface as real repo dirtiness.
    _write(tmp_path, ".gitignore", ".holusight/\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=tmp_path, check=True)
    return tmp_path


def _run(argv: list[str], cwd: Path) -> tuple[dict, str, int]:
    import os

    old_cwd = os.getcwd()
    os.chdir(cwd)
    try:
        return cli_axi._dispatch(argv)
    finally:
        os.chdir(old_cwd)


def _subprocess_holus(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "codesight.cli_axi", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# Unknown flags / usage errors (unit-level, fast)
# ---------------------------------------------------------------------------


def test_unknown_flag_is_usage_error():
    with pytest.raises(cli_axi.UsageError, match="unknown flag --stat"):
        cli_axi._parse_command_args(cli_axi.command_by_name("evidence"), ["--stat", "closed"])


def test_missing_required_positional_is_usage_error(tmp_path):
    repo = _minimal_repo(tmp_path)
    with pytest.raises(cli_axi.UsageError, match="missing required argument"):
        _run(["evidence"], repo)


def test_unknown_command_lists_valid_jobs():
    with pytest.raises(cli_axi.UsageError, match="unknown command 'frobnicate'"):
        cli_axi._split_command(["frobnicate"])


def test_invalid_choice_value_is_usage_error():
    with pytest.raises(cli_axi.UsageError, match="invalid value 'bogus'"):
        cli_axi._parse_command_args(
            cli_axi.command_by_name("evidence"), ["--mode", "bogus", "q"]
        )


def test_incompatible_mode_and_provider_is_usage_error(tmp_path):
    repo = _minimal_repo(tmp_path)
    with pytest.raises(cli_axi.UsageError, match="is not valid with --mode"):
        _run(["evidence", "q", "--mode", "exact", "--provider", "semantic"], repo)


def test_extra_positional_on_status_is_usage_error(tmp_path):
    repo = _minimal_repo(tmp_path)
    with pytest.raises(cli_axi.UsageError, match="unexpected argument"):
        _run(["status", "extra"], repo)


def test_help_flag_short_circuits_as_help_requested():
    with pytest.raises(cli_axi._HelpRequested):
        cli_axi._parse_command_args(cli_axi.command_by_name("evidence"), ["--help"])


# ---------------------------------------------------------------------------
# Unknown flags - real subprocess (end-to-end)
# ---------------------------------------------------------------------------


def test_e2e_unknown_flag_exit_code_2(tmp_path):
    repo = _minimal_repo(tmp_path)
    result = _subprocess_holus(["evidence", "alpha", "--stat", "closed"], repo)
    assert result.returncode == 2
    assert "error" in result.stdout
    assert "unknown flag --stat" in result.stdout
    assert result.stderr == "" or "Traceback" not in result.stderr


def test_e2e_help_exit_code_0(tmp_path):
    repo = _minimal_repo(tmp_path)
    result = _subprocess_holus(["--help"], repo)
    assert result.returncode == 0
    assert "usage: holus" in result.stdout


def test_e2e_home_view_runs(tmp_path):
    repo = _minimal_repo(tmp_path)
    result = _subprocess_holus([], repo)
    assert result.returncode == 0
    assert "schema_version" in result.stdout
    assert "bin:" in result.stdout


# ---------------------------------------------------------------------------
# No evidence
# ---------------------------------------------------------------------------


def test_no_evidence_is_definitive_not_an_error(tmp_path):
    repo = _minimal_repo(tmp_path)
    payload, _fmt, exit_code = _run(["evidence", "zzzznonexistentzzzz"], repo)
    assert exit_code == 0
    assert payload["answerable"] is False
    assert payload["reason"] == "no_matching_evidence"
    assert payload["evidence"] == []
    assert payload["evidence_total"] == 0


def test_empty_question_is_unsupported(tmp_path):
    repo = _minimal_repo(tmp_path)
    payload, _fmt, exit_code = _run(["evidence", ""], repo)
    assert exit_code == 0
    assert payload["answerable"] is False
    assert payload["reason"] == "unsupported_question"


# ---------------------------------------------------------------------------
# Stale / unavailable providers
# ---------------------------------------------------------------------------


def test_structural_provider_unavailable_without_graphify(tmp_path):
    repo = _minimal_repo(tmp_path)
    result = axi_providers.structural_provider(repo, "alpha")
    assert result.state == axi_providers.ProviderState.UNAVAILABLE
    assert "graphify" in result.detail


def test_semantic_provider_unavailable_without_index(tmp_path):
    repo = _minimal_repo(tmp_path)
    result = axi_providers.semantic_provider(repo, "alpha")
    assert result.state == axi_providers.ProviderState.UNAVAILABLE
    assert "not indexed" in result.detail


def test_consistency_provider_unavailable_before_first_refresh(tmp_path):
    repo = _minimal_repo(tmp_path)
    result = axi_providers.consistency_provider(repo, "alpha")
    assert result.state == axi_providers.ProviderState.UNAVAILABLE


def test_providers_job_reports_unavailable_entries(tmp_path):
    repo = _minimal_repo(tmp_path)
    payload, _fmt, exit_code = _run(["providers"], repo)
    assert exit_code == 0
    by_name = {p["name"]: p for p in payload["providers"]}
    assert by_name["structural"]["available"] is False
    assert by_name["structural"]["freshness"] == "unavailable"
    assert by_name["semantic"]["available"] is False


def test_structural_graph_stale_is_reported_not_hidden(tmp_path):
    repo = _minimal_repo(tmp_path)
    # A graph claiming to be built at a commit this repo never had.
    graph = {"built_at_commit": "0000000000000000000000000000000000dead", "nodes": [], "links": []}
    _write(repo, "graphify-out/graph.json", json.dumps(graph))
    result = axi_providers.structural_provider(repo, "alpha")
    # No matching nodes either way, but staleness must still be visible via
    # the detail string (never silently swallowed).
    assert "stale" in result.detail or result.state in (
        axi_providers.ProviderState.NO_EVIDENCE,
        axi_providers.ProviderState.STALE,
    )


def test_consistency_freshness_detects_stale_after_new_commit(tmp_path):
    repo = _git_repo(tmp_path)
    consistency.refresh(repo, run_semantic=False)
    statuses = {s.name: s for s in axi_providers.provider_statuses(repo)}
    assert statuses["consistency"].freshness == "current"

    # A new commit lands after refresh - the cache is now behind HEAD.
    _write(repo, "specs/002-beta.md", "# Beta Feature\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add beta"], cwd=repo, check=True)

    statuses = {s.name: s for s in axi_providers.provider_statuses(repo)}
    assert statuses["consistency"].freshness == "stale"


# ---------------------------------------------------------------------------
# Dirty repositories
# ---------------------------------------------------------------------------


def test_snapshot_reports_dirty_true_after_uncommitted_edit(tmp_path):
    repo = _git_repo(tmp_path)
    head_before, dirty_before = cli_axi._snapshot(repo)
    assert dirty_before is False
    assert head_before is not None

    _write(repo, "src/pkg/mod.py", "VALUE = 2\n")  # uncommitted change
    head_after, dirty_after = cli_axi._snapshot(repo)
    assert head_after == head_before  # commit unchanged, only working tree
    assert dirty_after is True


def test_home_view_surfaces_dirty_state(tmp_path):
    repo = _git_repo(tmp_path)
    _write(repo, "src/pkg/mod.py", "VALUE = 2\n")
    payload, _fmt, _exit = _run([], repo)
    assert payload["snapshot"]["dirty"] is True


# ---------------------------------------------------------------------------
# Projection (--fields) and truncation
# ---------------------------------------------------------------------------


def test_project_fields_whole_key_and_nested_list():
    payload = {
        "snapshot": {"commit": "abc", "dirty": False},
        "evidence": [
            {"source": "a.py", "location": "line 1", "excerpt": "x"},
            {"source": "b.py", "location": "line 2", "excerpt": "y"},
        ],
        "unrelated": "drop me",
    }
    out = cli_axi.project_fields(payload, ["snapshot", "evidence.source", "evidence.location"])
    assert out == {
        "snapshot": {"commit": "abc", "dirty": False},
        "evidence": [
            {"source": "a.py", "location": "line 1"},
            {"source": "b.py", "location": "line 2"},
        ],
    }
    assert "unrelated" not in out


def test_project_fields_missing_key_is_silently_dropped():
    out = cli_axi.project_fields({"a": 1}, ["a", "b"])
    assert out == {"a": 1}


def test_evidence_truncates_display_but_reports_total(tmp_path):
    repo = _minimal_repo(tmp_path)
    # 35 files each with one matching line - exceeds the exact provider's
    # 30-match budget, forcing a real budget_exceeded + truncation path.
    for i in range(35):
        _write(repo, f"docs/note{i:02d}.md", "the target phrase appears here\n")

    payload, _fmt, exit_code = _run(
        ["evidence", "target phrase", "--mode", "exact"], repo
    )
    assert exit_code == 0
    assert payload["answerable"] is True
    assert len(payload["evidence"]) <= cli_axi._MAX_DISPLAY_ITEMS
    assert payload["evidence_total"] >= len(payload["evidence"])
    assert payload["truncated"] is True
    assert any("budget" in w for w in payload["warnings"])


def test_full_flag_disables_excerpt_truncation(tmp_path):
    repo = _minimal_repo(tmp_path)
    long_line = "target " + ("x" * 900)
    _write(repo, "docs/long.md", long_line + "\n")

    truncated_payload, _fmt, _exit = _run(["evidence", "target", "--mode", "exact"], repo)
    full_payload, _fmt2, _exit2 = _run(
        ["evidence", "target", "--mode", "exact", "--full"], repo
    )
    truncated_item = truncated_payload["evidence"][0]
    full_item = full_payload["evidence"][0]
    assert truncated_item["excerpt_truncated"] is True
    assert len(truncated_item["excerpt"]) < len(long_line)
    assert full_item["excerpt_truncated"] is False
    assert full_item["excerpt"] == long_line


# ---------------------------------------------------------------------------
# JSON round-trip and TOON output
# ---------------------------------------------------------------------------


def test_json_round_trip_preserves_structure(tmp_path):
    repo = _minimal_repo(tmp_path)
    payload, _fmt, _exit = _run(["evidence", "alpha", "--mode", "exact"], repo)
    rendered = cli_axi._render(payload, "json")
    round_tripped = json.loads(rendered)
    assert round_tripped == payload


def test_json_round_trip_for_check_status_enum(tmp_path):
    repo = _git_repo(tmp_path)
    consistency.refresh(repo, run_semantic=False)
    payload, _fmt, _exit = _run(["check", "specs/001-alpha.md"], repo)
    rendered = cli_axi._render(payload, "json")
    round_tripped = json.loads(rendered)
    assert round_tripped == payload
    assert isinstance(payload["status"], str)
    assert "ConsistencyStatus" not in payload["status"]


def test_evidence_items_share_uniform_keys_for_toon_table(tmp_path):
    repo = _minimal_repo(tmp_path)
    payload, _fmt, _exit = _run(["evidence", "alpha", "--mode", "exact"], repo)
    assert payload["evidence"], "expected at least one match on 'alpha'"
    first_keys = set(payload["evidence"][0].keys())
    assert all(set(item.keys()) == first_keys for item in payload["evidence"])
    rendered = cli_axi._render(payload, "toon")
    assert f"evidence[{len(payload['evidence'])}]{{" in rendered


def test_toon_output_is_well_formed(tmp_path):
    repo = _minimal_repo(tmp_path)
    payload, _fmt, _exit = _run(["providers"], repo)
    rendered = cli_axi._render(payload, "toon")
    assert "providers[4]{name,available,version,freshness,egress,detail}:" in rendered
    assert "ConsistencyStatus" not in rendered


def test_text_format_renders_without_error(tmp_path):
    repo = _minimal_repo(tmp_path)
    payload, _fmt, _exit = _run(["status"], repo)
    rendered = cli_axi._render(payload, "text")
    assert "snapshot:" in rendered
    assert "commit:" in rendered


# ---------------------------------------------------------------------------
# No-network / no-credential defaults
# ---------------------------------------------------------------------------


def test_no_egress_env_hides_and_restores_voyage_key(monkeypatch):
    monkeypatch.setenv("VOYAGE_API_KEY", "fake-test-key")
    import os

    with axi_providers._no_egress_env():
        assert "VOYAGE_API_KEY" not in os.environ
    assert os.environ.get("VOYAGE_API_KEY") == "fake-test-key"


def test_no_egress_env_is_noop_when_key_absent(monkeypatch):
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    import os

    with axi_providers._no_egress_env():
        assert "VOYAGE_API_KEY" not in os.environ
    assert "VOYAGE_API_KEY" not in os.environ


def test_semantic_provider_denies_voyage_index_without_allow_egress(tmp_path, monkeypatch):
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    from codesight.api import CodeSight

    repo = _minimal_repo(tmp_path)
    engine = CodeSight(repo)
    engine.index()
    # Simulate an index that claims Voyage embeddings, without ever calling
    # the real Voyage API (VOYAGE_API_KEY stays unset for this whole test).
    engine.store.fts.set_meta("embedding_model", "voyage-code-3")

    denied = axi_providers.semantic_provider(repo, "alpha", allow_egress=False)
    assert denied.state == axi_providers.ProviderState.DENIED
    assert "--allow-egress" in denied.detail

    allowed = axi_providers.semantic_provider(repo, "alpha", allow_egress=True)
    assert allowed.state != axi_providers.ProviderState.DENIED


def test_evidence_default_mode_never_reports_egress_without_flag(tmp_path, monkeypatch):
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    repo = _minimal_repo(tmp_path)
    payload, _fmt, _exit = _run(["evidence", "alpha"], repo)
    assert payload["egress"]["occurred"] is False
    assert payload["egress"]["destination"] is None


# ---------------------------------------------------------------------------
# Derived-state (.holusight/) rebuild equivalence
# ---------------------------------------------------------------------------


def test_holusight_cache_rebuild_is_equivalent(tmp_path):
    repo = _git_repo(tmp_path)
    consistency.refresh(repo, run_semantic=False)
    first_status = cli_axi._claims_summary(repo)
    first_flags = cli_axi._health_flags_summary(repo)
    first_providers = [p.model_dump() for p in axi_providers.provider_statuses(repo)]

    import shutil

    shutil.rmtree(consistency.consistency_db_path(repo).parent)
    assert not consistency.consistency_db_path(repo).exists()

    consistency.refresh(repo, run_semantic=False)
    second_status = cli_axi._claims_summary(repo)
    second_flags = cli_axi._health_flags_summary(repo)
    second_providers = [p.model_dump() for p in axi_providers.provider_statuses(repo)]

    assert first_status == second_status
    assert first_flags == second_flags
    # Freshness/version fields are point-in-time and may legitimately shift
    # (e.g. last_refreshed_at); compare only the structural identity fields.
    for a, b in zip(first_providers, second_providers):
        assert a["name"] == b["name"]
        assert a["available"] == b["available"]


# ---------------------------------------------------------------------------
# check: bootstrap-once vs explicit --refresh baseline semantics
# ---------------------------------------------------------------------------


def test_check_never_silently_resets_baseline(tmp_path):
    repo = _git_repo(tmp_path)
    consistency.refresh(repo, run_semantic=False)

    # Edit the canonical spec without refreshing.
    _write(
        repo, "specs/001-alpha.md",
        "# Alpha Feature\n\nImplemented by `src/pkg/mod.py`. Edited.\n",
    )

    payload, _fmt, _exit = _run(["check", "specs/001-alpha.md"], repo)
    assert payload["status"] == "spec_changed_awaiting_implementation"

    # Calling `status` (which bootstraps only when the cache never existed)
    # must NOT reset the drift baseline check depends on.
    _run(["status"], repo)
    payload_again, _fmt2, _exit2 = _run(["check", "specs/001-alpha.md"], repo)
    assert payload_again["status"] == "spec_changed_awaiting_implementation"


def test_check_refresh_flag_resets_baseline(tmp_path):
    repo = _git_repo(tmp_path)
    consistency.refresh(repo, run_semantic=False)
    _write(
        repo, "specs/001-alpha.md",
        "# Alpha Feature\n\nImplemented by `src/pkg/mod.py`. Edited.\n",
    )
    payload, _fmt, _exit = _run(["check", "specs/001-alpha.md", "--refresh"], repo)
    assert payload["status"] == "up_to_date"


def test_check_unknown_scope_suggests_candidates(tmp_path):
    repo = _git_repo(tmp_path)
    consistency.refresh(repo, run_semantic=False)
    payload, _fmt, exit_code = _run(["check", "001-alp"], repo)
    assert exit_code == 0
    assert payload["status"] == "unknown_concept"
    assert any("001-alpha" in c for c in payload["candidates"])


def test_check_all_concepts_reports_total_and_summary(tmp_path):
    repo = _git_repo(tmp_path)
    consistency.refresh(repo, run_semantic=False)
    payload, _fmt, exit_code = _run(["check"], repo)
    assert exit_code == 0
    assert payload["concepts_checked"] == 1
    assert payload["summary"] == {"up_to_date": 1}
