"""Offline public-research tests, including the actual CLI process boundary."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from holusight import public_research

URLS = ["https://example.org/one", "https://example.net/two"]


def _fetch(url):
    return (
        "The solar policy requires a permit before installation."
        if url == URLS[0]
        else "The solar policy provides an annual inspection."
    ), "2026-09-28T12:00:00+00:00"


def test_success_writes_dated_report_and_receipt_outside_private_index(tmp_path):
    result, code = public_research.run(
        "What does solar policy require?",
        URLS,
        allow_egress=True,
        repo_root=tmp_path,
        fetcher=_fetch,
    )
    assert code == 0
    assert result["status"] == "verified_excerpts"
    report = Path(result["report"])
    receipt = json.loads(Path(result["receipt"]).read_text())
    assert report.parent == tmp_path / ".holusight/public-research"
    assert report.name.startswith("202")
    assert "fetched 2026-09-28" in report.read_text()
    assert receipt["sources"][0]["fetched_at"] == "2026-09-28T12:00:00+00:00"
    assert receipt["claims"] and all(c["verified"] for c in receipt["claims"])
    for claim in receipt["claims"]:
        source = next(s for s in receipt["sources"] if s["id"] == claim["source_id"])
        assert {"id": claim["excerpt_id"], "text": claim["quote"]} in source["excerpts"]
    assert all("text" not in source for source in receipt["sources"])
    assert not (tmp_path / ".holusight/index").exists()


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org/",
        "https://127.0.0.1/",
        "https://localhost/",
        "https://example.org:8443/",
        "https://user@example.org/",
        "https://example.org/#fragment",
        "https://example.org\\@example.net/",
    ],
)
def test_blocked_url_never_invokes_fetch(tmp_path, url):
    def forbidden(_):
        pytest.fail("network attempted for blocked URL")

    with pytest.raises(public_research.ResearchError):
        public_research.run(
            "solar policy?",
            [url, URLS[1]],
            allow_egress=True,
            repo_root=tmp_path,
            fetcher=forbidden,
        )
    assert not (tmp_path / ".holusight").exists()


def test_private_dns_resolution_blocked_before_connection(monkeypatch):
    monkeypatch.setattr(
        public_research.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(public_research.ResearchError, match="non-public"):
        public_research._public_address("example.org")


def test_empty_evidence_explicitly_unanswered(tmp_path):
    result, code = public_research.run(
        "quantum orbital?", URLS, allow_egress=True, repo_root=tmp_path, fetcher=_fetch
    )
    assert code == 0
    assert result["status"] == "no_evidence"
    assert "unanswered" in Path(result["report"]).read_text()
    assert json.loads(Path(result["receipt"]).read_text())["claims"] == []


def test_mismatched_citation_fails_visible_in_report_and_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(public_research, "_excerpts", lambda *_: ["Invented solar claim."])
    result, code = public_research.run(
        "solar policy?", URLS, allow_egress=True, repo_root=tmp_path, fetcher=_fetch
    )
    assert code == 1
    assert result["status"] == "verification_failed"
    assert "citation does not match" in Path(result["report"]).read_text()
    assert not any(c["verified"] for c in json.loads(Path(result["receipt"]).read_text())["claims"])
    assert "## Retrieved excerpts" not in Path(result["report"]).read_text()


def test_zero_network_without_opt_in_even_for_valid_urls(tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("DNS or network attempted without opt-in")

    monkeypatch.setattr(public_research.socket, "getaddrinfo", forbidden)
    with pytest.raises(public_research.ResearchError, match="egress denied"):
        public_research.run(
            "solar policy?", URLS, allow_egress=False, repo_root=tmp_path, fetcher=forbidden
        )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "holusight.cli_axi",
            "research-urls",
            "solar policy?",
            "--url",
            URLS[0],
            "--url",
            URLS[1],
            "--format",
            "json",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 1
    assert json.loads(completed.stdout)["error"]["code"] == "PUBLIC_RESEARCH_BLOCKED"
    assert not (tmp_path / ".holusight/public-research").exists()


def test_cli_dispatch_success_offline(tmp_path, monkeypatch):
    from holusight import cli_axi

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(public_research, "fetch", _fetch)
    payload, fmt, code = cli_axi._dispatch(
        [
            "research-urls",
            "solar policy?",
            "--url",
            URLS[0],
            "--url",
            URLS[1],
            "--allow-egress",
            "--format",
            "json",
        ]
    )
    assert fmt == "json" and code == 0
    assert payload["status"] == "verified_excerpts"
    assert json.loads(Path(payload["receipt"]).read_text())["egress"]["destinations"] == URLS


def test_fetch_rejects_redirect_and_never_follows(monkeypatch):
    class Response:
        status = 302

    class Connection:
        def __init__(self, host, address):
            assert host == "example.org" and address == "93.184.215.14"

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(public_research, "_public_address", lambda _: "93.184.215.14")
    monkeypatch.setattr(public_research, "_PinnedHTTPS", Connection)
    with pytest.raises(public_research.ResearchError, match="redirects are not followed"):
        public_research.fetch(URLS[0])


def test_research_cli_rejects_unknown_flag_and_wrong_url_count(tmp_path):
    from holusight import cli_axi

    with pytest.raises(cli_axi.UsageError, match="unknown flag"):
        cli_axi._dispatch(["research-urls", "question", "--sources", "x"])
    payload, _, code = cli_axi._dispatch(
        ["research-urls", "question", "--url", URLS[0], "--allow-egress", "--format", "json"]
    )
    assert code == 1 and payload["error"]["code"] == "PUBLIC_RESEARCH_BLOCKED"
