from __future__ import annotations

import json
import subprocess
from pathlib import Path

from holusight.council import list_prior_runs, main, persist_council, render_board_html, run_council

COUNCIL_LATEST = Path(".holusight/improvement-runs/council-runs/latest.json")
TMP_BOARD = Path("/tmp/holusight-council-board.html")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "council@example.com")
    _git(tmp_path, "config", "user.name", "council-test")
    (tmp_path / ".gitignore").write_text(".holusight/\n", encoding="utf-8")
    (tmp_path / "README").write_text("council fixture\n", encoding="utf-8")
    _git(tmp_path, "add", ".gitignore", "README")
    _git(tmp_path, "commit", "-m", "init")
    return tmp_path


def test_council_denies_promotion_and_emits_three_seed_takes(tmp_path: Path):
    repo = _repo(tmp_path)
    readme = (repo / "README").read_bytes()
    payload = run_council(repo, trigger="manual")
    assert payload["promotion"]["allowed"] is False
    assert payload["promotion"]["status"] == "denied"
    assert payload["loop"]["accumulates_history"] is True
    assert payload["loop"]["runs_evaluator"] is False
    assert payload["loop"]["edits_source"] is False
    assert payload["loop"]["llm_calls"] == 0
    assert payload["loop"]["controls_absent"] == [
        "retry",
        "cancel",
        "budget",
        "stop",
        "recovery",
    ]
    assert len(payload["seed_takes"]) == 3
    assert {take["role_id"] for take in payload["seed_takes"]} == {"eval", "fix", "chair"}
    assert payload["subject"]["commit"]
    assert payload["subject"]["tree"]
    assert payload["subject"]["clean"] is True
    assert (repo / "README").read_bytes() == readme
    assert not (repo / ".holusight").exists()


def test_persist_and_list_history_stay_under_derived_root(tmp_path: Path):
    repo = _repo(tmp_path)
    first = run_council(repo, trigger="manual")
    first_paths = persist_council(repo, first)
    second = run_council(repo, trigger="manual")
    second_paths = persist_council(repo, second)

    latest = repo / second_paths["latest"]
    assert latest == repo / COUNCIL_LATEST
    assert latest.is_file()
    assert (repo / first_paths["iteration"]).is_file()
    assert (repo / second_paths["iteration"]).is_file()
    stored = json.loads(latest.read_text(encoding="utf-8"))
    assert stored["promotion"]["allowed"] is False
    assert stored["digest"] == second_paths["digest"]

    priors = list_prior_runs(repo, limit=5)
    assert len(priors) == 2
    assert priors[0]["recorded_at"] >= priors[1]["recorded_at"]
    limited = list_prior_runs(repo, limit=1)
    assert len(limited) == 1
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert status.stdout == ""


def test_main_board_stays_in_derived_state_and_not_tmp(tmp_path: Path):
    repo = _repo(tmp_path)
    before = TMP_BOARD.read_bytes() if TMP_BOARD.exists() else None
    assert main(["--repo-root", str(repo), "--trigger", "manual", "--board"]) == 0
    board = repo / ".holusight/improvement-runs/council-runs/board.html"
    assert board.is_file()
    text = board.read_text(encoding="utf-8")
    assert "Promotion denied" in text
    assert "<script" not in text.lower()
    after = TMP_BOARD.read_bytes() if TMP_BOARD.exists() else None
    assert after == before


def test_hostile_improve_receipt_is_not_copied_into_the_board(tmp_path: Path):
    repo = _repo(tmp_path)
    receipt = repo / ".holusight/improvement-runs/proper-eval-iterations"
    receipt.mkdir(parents=True)
    (receipt / "latest.json").write_text(
        json.dumps(
            {
                "progress": "<script>alert(1)</script>",
                "next_action": "rm -rf /",
                "iteration_id": "iter-<b>",
            }
        ),
        encoding="utf-8",
    )
    payload = run_council(repo, trigger="manual")
    assert payload["snapshot"]["improve"]["progress"] is None
    assert payload["snapshot"]["improve"]["next_action"] is None
    page = render_board_html(payload, [])
    assert "<script>" not in page
    assert "rm -rf" not in page
