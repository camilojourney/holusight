from __future__ import annotations

from pathlib import Path

from codesight.agent_focus import LENSES, build_context_pack, run_agent_focus

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_council_is_fixed_and_nontrivial():
    assert len(LENSES) >= 8
    assert len(LENSES) <= 20  # deliberate council, not chat fan-out


def test_run_agent_focus_on_repo():
    payload = run_agent_focus(REPO_ROOT)
    assert payload["schema_version"].startswith("holusight-agent-focus")
    assert payload["promotion"]["allowed"] is False
    assert payload["loop"]["llm_calls"] == 0
    assert payload["loop"]["spawns_chat_agents"] is False
    assert payload["council_size"] == len(LENSES)
    assert payload["verdict"] in {"pass", "block", "indeterminate"}
    assert "context_pack" in payload
    assert payload["context_pack"]["commands"]["orient"] == "just agent-focus"


def test_context_pack_lists_hard_rules():
    pack = build_context_pack(REPO_ROOT)
    assert any("Promotion denied" in r for r in pack["hard_rules"])
    assert "AGENTS.md" in pack["read_first"]


def test_promotion_lens_passes_on_master_shape():
    from codesight.agent_focus import _lens_promotion

    result = _lens_promotion(REPO_ROOT)
    assert result.verdict == "pass", result
