"""Privacy and enabled/disabled contract tests for local usage events."""

from __future__ import annotations

import json

from holusight import cli_axi, local_usage_trace


def test_disabled_trace_writes_no_event(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLUSIGHT_LOCAL_TRACE", "0")
    monkeypatch.setenv("HOLUSIGHT_LOCAL_TRACE_DIR", str(tmp_path))
    assert local_usage_trace.record("evidence", {"question": "secret"}) is None
    assert not (tmp_path / "events.jsonl").exists()


def test_enabled_trace_is_content_minimized_and_unknown_tokens(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLUSIGHT_LOCAL_TRACE", "true")
    monkeypatch.setenv("HOLUSIGHT_LOCAL_TRACE_DIR", str(tmp_path))
    payload = {
        "question": "private prompt text",
        "snapshot": {"commit": "abc", "dirty": True},
        "providers_checked": [
            {"provider": "exact", "state": "no_evidence", "detail": "contains source"},
            {"provider": "semantic", "state": "budget_exceeded", "detail": "secret"},
        ],
        "evidence": [{"source": "/private/source.py", "excerpt": "password=secret"}],
        "coverage": "partial",
    }
    path = local_usage_trace.record("evidence", payload)
    assert path == tmp_path / "events.jsonl"
    event = json.loads(path.read_text())
    assert event["schema_version"] == "holusight.local_usage.v1"
    assert event["event_version"] == "1.1"
    assert event["invoked"] is True
    assert event["project_id"].startswith("sha256:")
    assert event["agent_id"] == "unknown"
    assert event["freshness"] == "partial"
    assert event["partial"] is True
    assert event["token_delta"] == {
        "status": "unknown",
        "input": None,
        "output": None,
        "total": None,
    }
    assert event["providers"] == [
        {"name": "exact", "invoked": True, "freshness": "current", "partial": False},
        {"name": "semantic", "invoked": True, "freshness": "partial", "partial": True},
    ]
    serialized = path.read_text()
    forbidden_values = (
        "private prompt text",
        "/private/source.py",
        "password=secret",
        "contains source",
    )
    for forbidden in forbidden_values:
        assert forbidden not in serialized


def test_cli_enabled_and_disabled_modes_are_observable(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("local trace test\n")
    trace_dir = tmp_path / "trace"
    monkeypatch.chdir(repo)
    monkeypatch.setenv("HOLUSIGHT_LOCAL_TRACE_DIR", str(trace_dir))

    monkeypatch.setenv("HOLUSIGHT_LOCAL_TRACE", "0")
    cli_axi._dispatch(["status"])
    assert not (trace_dir / "events.jsonl").exists()

    monkeypatch.setenv("HOLUSIGHT_LOCAL_TRACE", "1")
    cli_axi._dispatch(["status"])
    lines = (trace_dir / "events.jsonl").read_text().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["command"] == "status"
    assert event["invoked"] is True


def test_default_enabled_and_no_egress(tmp_path, monkeypatch):
    monkeypatch.delenv("HOLUSIGHT_LOCAL_TRACE", raising=False)
    monkeypatch.setenv("HOLUSIGHT_LOCAL_TRACE_DIR", str(tmp_path))

    def fail_network(*args, **kwargs):
        raise AssertionError("local usage trace attempted network egress")

    monkeypatch.setattr("socket.create_connection", fail_network)
    local_usage_trace.record("home", {"providers": []})
    assert (tmp_path / "events.jsonl").exists()


def test_summary_aggregates_multi_call_feedback_and_unknowns(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLUSIGHT_LOCAL_TRACE_DIR", str(tmp_path))
    local_usage_trace.record(
        "status", {"providers": [{"name": "semantic", "freshness": "unavailable"}]}
    )
    local_usage_trace.record(
        "improve-variation-feedback", {"review_queue": {"signal": "failure_case", "count": 2}}
    )
    summary = local_usage_trace.summarize()
    assert summary["events"] == 2
    assert summary["project_invocations"]["total"] == 2
    assert summary["agent_invocations"]["total"] == 2
    assert summary["providers"]["semantic"]["not_used"] == 1
    assert summary["providers"]["semantic"]["unavailable"] == 1
    assert summary["feedback_outcomes"] == {"failure_case": 2}
    assert summary["latency_ms"]["status"] == "unknown"
    assert summary["token_delta"]["status"] == "unknown"


def test_project_opt_out_writes_nothing(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / ".holusight").mkdir(parents=True)
    (repo / ".holusight" / "local-usage.disabled").touch()
    monkeypatch.chdir(repo)
    monkeypatch.setenv("HOLUSIGHT_LOCAL_TRACE_DIR", str(tmp_path / "trace"))
    assert local_usage_trace.record("status", {}) is None


def test_provider_not_used_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setenv("HOLUSIGHT_LOCAL_TRACE_DIR", str(tmp_path))
    local_usage_trace.record(
        "status",
        {"providers": [{"name": "semantic", "available": False, "freshness": "unavailable"}]},
    )
    event = json.loads((tmp_path / "events.jsonl").read_text())
    assert event["providers"] == [
        {"name": "semantic", "invoked": False, "freshness": "unavailable", "partial": False}
    ]
