from __future__ import annotations

from codesight.improve_iterate import compare_iterations


def test_baseline_without_prior():
    cur = {"verdict": "pass", "surfaces": [{"name": "eval-pilot", "counts": {"passed": 4, "total": 4}}]}
    out = compare_iterations(cur, None)
    assert out["progress"] == "baseline"
    assert out["next_action"]


def test_improved_on_rate():
    prev = {"verdict": "pass", "surfaces": [{"name": "eval-pilot", "counts": {"passed": 2, "total": 4}}]}
    cur = {"verdict": "pass", "surfaces": [{"name": "eval-pilot", "counts": {"passed": 4, "total": 4}}]}
    out = compare_iterations(cur, prev)
    assert out["progress"] == "improved"


def test_regressed_on_rate():
    prev = {"verdict": "pass", "surfaces": [{"name": "eval-pilot", "counts": {"passed": 4, "total": 4}}]}
    cur = {"verdict": "pass", "surfaces": [{"name": "eval-pilot", "counts": {"passed": 2, "total": 4}}]}
    out = compare_iterations(cur, prev)
    assert out["progress"] == "regressed"


def test_stagnated_when_unchanged_pass():
    prev = {"verdict": "pass", "surfaces": [{"name": "eval-pilot", "counts": {"passed": 4, "total": 4}}]}
    cur = {"verdict": "pass", "surfaces": [{"name": "eval-pilot", "counts": {"passed": 4, "total": 4}}]}
    out = compare_iterations(cur, prev)
    assert out["progress"] == "stagnated"
    assert out["research_needed"] is True


def test_blocked():
    out = compare_iterations({"verdict": "block", "reason": "x", "surfaces": []}, {"verdict": "pass", "surfaces": []})
    assert out["progress"] == "blocked"
