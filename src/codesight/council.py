"""Advisory Holusight improve council.

On demand (``just council``):

1. Read prior council receipts, if any.
2. Snapshot focus and the latest improve-iterate receipt without running
   evaluators or editing source.
3. Emit three role seed takes (Eval, Fix, Chair).
4. Persist a new receipt when asked, under gitignored derived state.

Promotion is always denied. This module does not retry, cancel, budget,
stop, or recover a run, and it does not spawn agents.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent_focus import run_agent_focus
from .control_storage import HISTORY_ROOT, UnsafeStoragePath, safe_atomic_write
from .improve_iterate import ITERATE_DIR, LATEST_NAME

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "holusight-council-result/v1"
COUNCIL_DIR = HISTORY_ROOT / "council-runs"
_FOCUS_VERDICTS = frozenset({"pass", "block", "indeterminate"})
_IMPROVE_PROGRESS = frozenset(
    {"baseline", "improved", "stagnated", "regressed", "blocked", "indeterminate"}
)
_TOKEN = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
_ABSENT_CONTROLS = ("retry", "cancel", "budget", "stop", "recovery")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _token(value: object) -> str | None:
    if isinstance(value, str) and _TOKEN.fullmatch(value):
        return value
    return None


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _subject(repo_root: Path) -> dict[str, Any]:
    """Commit and tree only. Branch is an annotation, not an identity."""
    top = _git(repo_root, "rev-parse", "--show-toplevel")
    try:
        actual = Path(top.stdout.strip()).resolve()
        expected = repo_root.resolve()
    except OSError:
        actual = None
        expected = None
    if top.returncode != 0 or actual is None or actual != expected:
        return {"available": False, "commit": None, "tree": None, "clean": False, "branch": None}
    commit = _git(repo_root, "rev-parse", "--verify", "HEAD").stdout.strip()
    tree = _git(repo_root, "rev-parse", "--verify", "HEAD^{tree}").stdout.strip()
    oid = re.compile(r"^[0-9a-f]{40}$")
    if not oid.fullmatch(commit) or not oid.fullmatch(tree):
        return {"available": False, "commit": None, "tree": None, "clean": False, "branch": None}
    dirty = _git(repo_root, "status", "--porcelain")
    branch_raw = _git(repo_root, "symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip()
    branch = branch_raw if _TOKEN.fullmatch(branch_raw or "") else None
    return {
        "available": True,
        "commit": commit,
        "tree": tree,
        "clean": dirty.returncode == 0 and not dirty.stdout.strip(),
        "branch": branch,
    }


def _focus_snapshot(repo_root: Path) -> dict[str, Any]:
    try:
        payload = run_agent_focus(repo_root)
    except Exception:
        return {"available": False, "verdict": None}
    if not isinstance(payload, dict):
        return {"available": False, "verdict": None}
    verdict = payload.get("verdict")
    promotion = payload.get("promotion") if isinstance(payload.get("promotion"), dict) else {}
    return {
        "available": True,
        "verdict": verdict if verdict in _FOCUS_VERDICTS else None,
        "council_size": payload.get("council_size")
        if isinstance(payload.get("council_size"), int)
        else None,
        "promotion_allowed": promotion.get("allowed") is True,
    }


def _improve_snapshot(repo_root: Path) -> dict[str, Any]:
    """Read the latest receipt. Do not run improve-iterate."""
    path = repo_root / ITERATE_DIR / LATEST_NAME
    if not path.is_file() or path.is_symlink():
        return {"available": False, "progress": None, "next_action": None}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"available": False, "progress": None, "next_action": None}
    if not isinstance(payload, dict):
        return {"available": False, "progress": None, "next_action": None}
    progress = payload.get("progress")
    return {
        "available": True,
        "progress": progress if progress in _IMPROVE_PROGRESS else None,
        "next_action": _token(payload.get("next_action")),
        "iteration_id": _token(payload.get("iteration_id")),
    }


def _seed_takes(focus: dict[str, Any], improve: dict[str, Any]) -> list[dict[str, str]]:
    focus_verdict = focus.get("verdict") or "unavailable"
    progress = improve.get("progress") or "unavailable"
    return [
        {
            "role_id": "eval",
            "agent": "HS Eval",
            "stance": "measure",
            "finding": f"focus={focus_verdict}; improve={progress}",
            "ask": "Compare the next run to the stored receipt. Do not score a hidden holdout.",
        },
        {
            "role_id": "fix",
            "agent": "HS Fix",
            "stance": "propose-only",
            "finding": "This command does not edit source.",
            "ask": "Leave code changes to a later human review.",
        },
        {
            "role_id": "chair",
            "agent": "Chair",
            "stance": "deny-promotion",
            "finding": "Promotion stays denied.",
            "ask": "Record the receipt and stop. Do not merge or deploy.",
        },
    ]


def _decision(focus: dict[str, Any], improve: dict[str, Any]) -> dict[str, str]:
    needs_review = improve.get("progress") in {"stagnated", "blocked", "regressed"} or (
        focus.get("verdict") == "block"
    )
    if needs_review:
        return {
            "choice": "human_review",
            "reason": "advisory only; promotion denied",
        }
    return {
        "choice": "continue_measurement",
        "reason": "advisory only; promotion denied",
    }


def run_council(repo_root: Path, trigger: str = "manual") -> dict[str, Any]:
    """Build an advisory receipt. This function does not write."""
    root = repo_root.resolve()
    safe_trigger = _token(trigger) or "manual"
    focus = _focus_snapshot(root)
    improve = _improve_snapshot(root)
    takes = _seed_takes(focus, improve)
    return {
        "schema_version": SCHEMA,
        "recorded_at": _now(),
        "trigger": safe_trigger,
        "useful_now": _decision(focus, improve)["choice"] == "human_review",
        "promotion": {
            "allowed": False,
            "status": "denied",
            "reason": "ADR-0019 - council is advisory; humans own promotion",
        },
        "loop": {
            "accumulates_history": True,
            "deterministic": True,
            "llm_calls": 0,
            "spawns_chat_agents": False,
            "edits_source": False,
            "runs_evaluator": False,
            "controls_absent": list(_ABSENT_CONTROLS),
        },
        "subject": _subject(root),
        "snapshot": {"focus": focus, "improve": improve},
        "seed_takes": takes,
        "decision": _decision(focus, improve),
        "prior_runs": list_prior_runs(root, limit=5),
    }


def _canonical(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode("utf-8")


def persist_council(repo_root: Path, payload: dict[str, Any]) -> dict[str, str]:
    """Write the receipt under ``.holusight/improvement-runs/council-runs``."""
    root = repo_root.resolve()
    stored = dict(payload)
    stored.pop("digest", None)
    stored.pop("receipts", None)
    stored["promotion"] = {
        "allowed": False,
        "status": "denied",
        "reason": "ADR-0019 - council is advisory; humans own promotion",
    }
    digest = hashlib.sha256(_canonical(stored)).hexdigest()
    stored["digest"] = digest
    body = _canonical(stored)
    subject = stored.get("subject")
    commit = subject.get("commit") if isinstance(subject, dict) else None
    if isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit):
        prefix = commit[:12]
    else:
        prefix = "nogit"
    iteration_id = f"council-{prefix}-{_stamp()}"
    rel_iter = COUNCIL_DIR / f"{iteration_id}.json"
    rel_latest = COUNCIL_DIR / LATEST_NAME
    safe_atomic_write(root, rel_iter, body, allowed_repo_root=HISTORY_ROOT)
    safe_atomic_write(root, rel_latest, body, allowed_repo_root=HISTORY_ROOT)
    return {
        "iteration": rel_iter.as_posix(),
        "latest": rel_latest.as_posix(),
        "digest": digest,
    }


def list_prior_runs(repo_root: Path, limit: int = 5) -> list[dict[str, Any]]:
    """Summaries of prior iteration files, newest first. ``latest.json`` is a pointer."""
    root = repo_root.resolve()
    directory = root / COUNCIL_DIR
    if not directory.is_dir() or directory.is_symlink():
        return []
    rows: list[dict[str, Any]] = []
    for path in directory.glob("*.json"):
        if path.name == LATEST_NAME or path.is_symlink() or not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
        rows.append(
            {
                "recorded_at": _token(payload.get("recorded_at")) or "",
                "trigger": _token(payload.get("trigger")) or "",
                "decision": _token(decision.get("choice")) or "",
                "digest": _token(payload.get("digest")) or "",
                "path": path.name,
            }
        )
    rows.sort(key=lambda row: (row["recorded_at"], row["path"]), reverse=True)
    return rows[: max(0, limit)]


def render_board_html(payload: dict[str, Any], priors: list[dict[str, Any]]) -> str:
    snap = payload.get("snapshot") if isinstance(payload.get("snapshot"), dict) else {}
    focus = snap.get("focus") if isinstance(snap.get("focus"), dict) else {}
    improve = snap.get("improve") if isinstance(snap.get("improve"), dict) else {}
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    takes = payload.get("seed_takes") if isinstance(payload.get("seed_takes"), list) else []

    def cell(value: object) -> str:
        return html.escape("" if value is None else str(value), quote=True)

    take_rows = "".join(
        "<tr><td>{role}</td><td>{stance}</td><td>{finding}</td><td>{ask}</td></tr>".format(
            role=cell(item.get("role_id")) if isinstance(item, dict) else "",
            stance=cell(item.get("stance")) if isinstance(item, dict) else "",
            finding=cell(item.get("finding")) if isinstance(item, dict) else "",
            ask=cell(item.get("ask")) if isinstance(item, dict) else "",
        )
        for item in takes
    )
    prior_rows = "".join(
        "<tr><td>{when}</td><td>{trigger}</td><td>{decision}</td><td>{digest}</td></tr>".format(
            when=cell(item.get("recorded_at")) if isinstance(item, dict) else "",
            trigger=cell(item.get("trigger")) if isinstance(item, dict) else "",
            decision=cell(item.get("decision")) if isinstance(item, dict) else "",
            digest=cell((item.get("digest") or "")[:18]) if isinstance(item, dict) else "",
        )
        for item in priors
    ) or "<tr><td colspan=4>No prior runs yet.</td></tr>"
    subject = payload.get("subject") if isinstance(payload.get("subject"), dict) else {}
    commit = cell((subject.get("commit") or "")[:12])
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Holusight council board</title>
<style>
body{{margin:0;font:14px system-ui;background:#0b1020;color:#e8ecf7}}
header,section{{padding:18px 26px}}
table{{width:100%;border-collapse:collapse}}
td{{padding:8px 10px;border-bottom:1px solid #243049;vertical-align:top}}
</style></head><body>
<header>
  <h1>Holusight council board</h1>
  <p>Advisory only. Promotion denied. No evaluator run. No source edits.
  Controls not implemented: retry, cancel, budget, stop, recovery.
  {cell(payload.get("recorded_at"))}</p>
</header>
<section>
  <p>Choice: {cell(decision.get("choice"))}</p>
  <p>Focus: {cell(focus.get("verdict"))}. Improve: {cell(improve.get("progress"))}.</p>
  <p>Subject commit: {commit}</p>
</section>
<section><h2>Role seed takes</h2>
<table><tbody>{take_rows}</tbody></table></section>
<section><h2>Prior council runs</h2>
<table><tbody>{prior_rows}</tbody></table></section>
</body></html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Holusight advisory improve council")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--trigger", default="manual")
    parser.add_argument(
        "--board",
        action="store_true",
        help="Write board HTML under the gitignored council receipt directory",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    root = args.repo_root.resolve()
    payload = run_council(root, trigger=args.trigger)
    try:
        paths = persist_council(root, payload)
    except UnsafeStoragePath as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        return 1
    payload["receipts"] = paths
    if args.board:
        board_rel = COUNCIL_DIR / "board.html"
        page = render_board_html(payload, payload.get("prior_runs") or [])
        try:
            safe_atomic_write(
                root,
                board_rel,
                page.encode("utf-8"),
                allowed_repo_root=HISTORY_ROOT,
            )
        except UnsafeStoragePath as exc:
            print(json.dumps({"error": str(exc), "receipts": paths}, sort_keys=True))
            return 1
        payload["board"] = board_rel.as_posix()
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
