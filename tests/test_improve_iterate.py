from __future__ import annotations

from holusight.improve_iterate import compare_iterations


def _result(verdict: str, passed: int, total: int) -> dict:
    return {
        "verdict": verdict,
        "surfaces": [{"name": "eval-pilot", "counts": {"passed": passed, "total": total}}],
    }


def test_baseline_without_prior():
    cur = _result("pass", 4, 4)
    out = compare_iterations(cur, None)
    assert out["progress"] == "baseline"
    assert out["next_action"]


def test_improved_on_rate():
    prev = _result("pass", 2, 4)
    cur = _result("pass", 4, 4)
    out = compare_iterations(cur, prev)
    assert out["progress"] == "improved"


def test_regressed_on_rate():
    prev = _result("pass", 4, 4)
    cur = _result("pass", 2, 4)
    out = compare_iterations(cur, prev)
    assert out["progress"] == "regressed"


def test_stagnated_when_unchanged_pass():
    prev = _result("pass", 4, 4)
    cur = _result("pass", 4, 4)
    out = compare_iterations(cur, prev)
    assert out["progress"] == "stagnated"
    assert out["research_needed"] is True


def test_blocked():
    cur = {"verdict": "block", "reason": "x", "surfaces": []}
    prev = {"verdict": "pass", "surfaces": []}
    out = compare_iterations(cur, prev)
    assert out["progress"] == "blocked"
