"""Deployment regression tests for holusight.com static site."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VERCEL_CONFIG = REPO_ROOT / "vercel.json"


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


def test_vercel_config_is_static_site_not_python_build():
    """Keep Vercel deploy as a static landing page, not a Streamlit/FastAPI build."""
    config = _load_vercel_config()

    assert config.get("framework") is None
    assert not config.get("buildCommand")
    assert config["outputDirectory"] == "landing"
