"""Deployment regression tests for holusight.com static site."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from markdown_it import MarkdownIt

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"
VERCEL_CONFIG = REPO_ROOT / "vercel.json"
CANONICAL_PUBLIC_SITE = "https://holusight.com/"


def _load_vercel_config() -> dict:
    return json.loads(VERCEL_CONFIG.read_text(encoding="utf-8"))


def test_vercel_output_directory_contains_index_html():
    """Vercel must serve a static entry point or holusight.com returns 404."""
    config = _load_vercel_config()
    output_dir = REPO_ROOT / config["outputDirectory"]

    assert output_dir.is_dir(), f"outputDirectory {output_dir} is missing"
    index_html = output_dir / "index.html"
    assert index_html.is_file(), (
        f"{index_html} is missing - Vercel static deploy will 404 at holusight.com"
    )


def test_landing_pages_exist():
    """Key marketing/docs pages must exist for holusight.com navigation."""
    config = _load_vercel_config()
    output_dir = REPO_ROOT / config["outputDirectory"]
    for page in ("index.html", "docs.html", "pricing.html"):
        assert (output_dir / page).is_file(), f"missing landing/{page}"
    assert (output_dir / "css" / "site.css").is_file()


def test_vercel_config_is_static_site_not_python_build():
    """Keep Vercel deploy as a static landing page, not a Streamlit/FastAPI build."""
    config = _load_vercel_config()

    assert config.get("framework") is None
    assert not config.get("buildCommand")
    assert config["outputDirectory"] == "landing"


def test_readme_renders_canonical_public_site_link():
    """Human-facing README must render the canonical public-site link."""
    tokens = MarkdownIt("commonmark").parse(README.read_text(encoding="utf-8"))
    destinations = {
        child.attrGet("href")
        for token in tokens
        for child in token.children or []
        if child.type == "link_open"
    }

    assert CANONICAL_PUBLIC_SITE in destinations


FORBIDDEN_AFFIRMATIVE_CLAIMS = (
    "50 concurrent users",
    "supports 50 users",
    "SOC 2 certified",
    "SOC2 certified",
    "HIPAA compliant",
    "SAML included",
    "Graphify-powered",
    "live Microsoft 365 integration",
    "live M365 integration",
)


def test_public_site_does_not_claim_unshipped_capabilities():
    """Marketing copy must not claim planned or unverified capabilities."""
    landing = REPO_ROOT / "landing"
    pages = list(landing.glob("*.html"))
    assert pages
    for page in pages:
        text = page.read_text(encoding="utf-8")
        for claim in FORBIDDEN_AFFIRMATIVE_CLAIMS:
            assert claim.lower() not in text.lower(), f"{page.name} claims {claim!r}"


def test_public_site_states_static_boundary_and_pilot_range():
    home = (REPO_ROOT / "landing" / "index.html").read_text(encoding="utf-8")
    pricing = (REPO_ROOT / "landing" / "pricing.html").read_text(encoding="utf-8")
    assert "does not index" in home.lower() or "static" in home.lower()
    assert "$1,000" in pricing and "$2,000" in pricing


def test_compose_resolves_customer_mount_and_production_environment(tmp_path):
    """Docker Compose's normalized model must protect the customer boundary."""
    if shutil.which("docker") is None:
        pytest.skip("Docker is not installed")

    env = {
        **os.environ,
        "CODESIGHT_API_KEY": "test-key",
        "CODESIGHT_DOCUMENTS_HOST_DIR": str(tmp_path),
    }
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(REPO_ROOT / "docker-compose.yml"),
            "config",
            "--format",
            "json",
        ],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    model = json.loads(result.stdout)
    service = model["services"]["holusight"]
    assert service["environment"]["CODESIGHT_PRODUCTION"] == "1"
    assert service["environment"]["CODESIGHT_DOCUMENTS_DIR"] == "/data"
    mount = next(volume for volume in service["volumes"] if volume["target"] == "/data")
    assert mount["source"] == str(tmp_path)
    assert mount["read_only"] is True
