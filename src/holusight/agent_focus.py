"""Deterministic agent-focus harness for Holusight (ADR-0019).

Holusight is a tool for agents: this module packs project context and runs a
fixed set of alignment lenses so an agent can focus before changing anything.

This is the captain's "100 copies discussing" intent without spawning chat
agents: each lens is a deterministic viewpoint (structure, eval loop,
promotion boundary, CI, docs, …). No LLM calls. Promotion stays denied.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "holusight-agent-focus-result/v1"
Verdict = Literal["pass", "block", "indeterminate"]

LensFn = Callable[[Path], "LensResult"]


@dataclass(frozen=True)
class LensResult:
    lens_id: str
    role: str
    verdict: Verdict
    finding: str
    evidence: list[str]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _git_subject(repo_root: Path) -> dict[str, Any]:
    import subprocess

    def run(*args: str) -> str | None:
        r = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            check=False,
        )
        out = r.stdout.strip()
        return out if r.returncode == 0 and out else None

    commit = run("rev-parse", "HEAD")
    tree = run("rev-parse", "HEAD^{tree}")
    branch = run("symbolic-ref", "--quiet", "--short", "HEAD")
    dirty = bool(run("status", "--porcelain"))
    return {
        "commit": commit,
        "tree": tree,
        "branch": branch,
        "clean": bool(commit and tree and not dirty),
    }



def _denies_promotion(source: str) -> bool:
    """True if source hard-codes promotion allowed=False (Python or JSON-ish)."""
    markers = (
        '"allowed": False',
        "'allowed': False",
        '"allowed": false',
        "'allowed': false",
    )
    return any(m in source for m in markers)

def _lens_structure(repo_root: Path) -> LensResult:
    required = [
        "AGENTS.md",
        "ARCHITECTURE.md",
        ".claude/rules/structure.md",
        "justfile",
        "agentic/manifest.yaml",
    ]
    missing = [p for p in required if not (repo_root / p).is_file()]
    if missing:
        return LensResult(
            "structure_authority",
            "structure steward",
            "block",
            "required agent authority files missing",
            missing,
        )
    return LensResult(
        "structure_authority",
        "structure steward",
        "pass",
        "AGENTS.md, structure rules, and agentic manifest present",
        required,
    )


def _lens_promotion(repo_root: Path) -> LensResult:
    adr = _read(repo_root / "docs/decisions/0019-local-advisory-evaluator-promotion-denied.md")
    pe = _read(repo_root / "src/holusight/proper_eval.py") or ""
    ii = _read(repo_root / "src/holusight/improve_iterate.py") or ""
    evidence: list[str] = []
    if not adr:
        return LensResult(
            "promotion_boundary",
            "safety officer",
            "block",
            "ADR-0019 missing",
            ["docs/decisions/0019-local-advisory-evaluator-promotion-denied.md"],
        )
    evidence.append("ADR-0019 present")
    if not _denies_promotion(pe):
        return LensResult(
            "promotion_boundary",
            "safety officer",
            "block",
            "proper_eval does not hard-deny promotion",
            evidence,
        )
    evidence.append("proper_eval denies promotion")
    if not _denies_promotion(ii):
        return LensResult(
            "promotion_boundary",
            "safety officer",
            "block",
            "improve_iterate does not hard-deny promotion",
            evidence,
        )
    evidence.append("improve_iterate denies promotion")
    manifest = _read(repo_root / "agentic/manifest.yaml") or ""
    if "default_training_eligibility: false" not in manifest:
        return LensResult(
            "promotion_boundary",
            "safety officer",
            "block",
            "agentic manifest missing default_training_eligibility: false",
            evidence,
        )
    evidence.append("manifest training eligibility false")
    return LensResult(
        "promotion_boundary",
        "safety officer",
        "pass",
        "promotion denied across ADR, runners, and Fleet manifest",
        evidence,
    )


def _lens_eval_loop(repo_root: Path) -> LensResult:
    just = _read(repo_root / "justfile") or ""
    needed = ("proper-eval:", "improve-iterate:", "eval-pilot:", "fleet-smoke:")
    missing = [n for n in needed if n not in just]
    mods = [
        "src/holusight/proper_eval.py",
        "src/holusight/improve_iterate.py",
        "src/holusight/eval_pilot.py",
        "src/holusight/eval_suite.py",
    ]
    missing_mods = [m for m in mods if not (repo_root / m).is_file()]
    if missing or missing_mods:
        return LensResult(
            "eval_loop_wired",
            "evaluation lead",
            "block",
            "self-improve measurement surface incomplete",
            missing + missing_mods,
        )
    return LensResult(
        "eval_loop_wired",
        "evaluation lead",
        "pass",
        "fleet-smoke, eval-pilot, proper-eval, improve-iterate wired",
        list(needed) + mods,
    )


def _lens_ci(repo_root: Path) -> LensResult:
    path = repo_root / ".github/workflows/improve-iterate.yml"
    text = _read(path)
    if not text:
        return LensResult(
            "ci_self_check",
            "ci steward",
            "block",
            "improve-iterate workflow missing",
            [str(path)],
        )
    if "improve_iterate" not in text and "improve-iterate" not in text:
        return LensResult(
            "ci_self_check",
            "ci steward",
            "block",
            "workflow does not invoke improve-iterate",
            [str(path)],
        )
    return LensResult(
        "ci_self_check",
        "ci steward",
        "pass",
        "daily/advisory improve-iterate workflow present",
        [str(path.relative_to(repo_root))],
    )


def _lens_workers_honesty(repo_root: Path) -> LensResult:
    path = repo_root / ".self-improvement/workers.yaml"
    text = _read(path) or ""
    if "proposal, not a running system" not in text and "not a running system" not in text:
        return LensResult(
            "workers_honesty",
            "ops realist",
            "indeterminate",
            "workers.yaml does not clearly mark cron schedule as proposal-only",
            [str(path)],
        )
    if "just improve-iterate" not in text:
        return LensResult(
            "workers_honesty",
            "ops realist",
            "indeterminate",
            "workers.yaml should point agents at the live improve-iterate loop",
            [str(path)],
        )
    return LensResult(
        "workers_honesty",
        "ops realist",
        "pass",
        "cron workers documented as proposal; live loop is improve-iterate",
        [str(path)],
    )


def _lens_next_priorities(repo_root: Path) -> LensResult:
    path = repo_root / ".self-improvement/NEXT.md"
    text = _read(path)
    if not text:
        return LensResult(
            "next_priorities",
            "product owner",
            "block",
            "NEXT.md missing — agents lack priority alignment",
            [str(path)],
        )
    if "## P0" not in text:
        return LensResult(
            "next_priorities",
            "product owner",
            "indeterminate",
            "NEXT.md has no P0 section",
            [str(path)],
        )
    return LensResult(
        "next_priorities",
        "product owner",
        "pass",
        "NEXT.md publishes P0 gaps for agent alignment",
        [str(path)],
    )


def _lens_agent_docs(repo_root: Path) -> LensResult:
    agents = _read(repo_root / "AGENTS.md") or ""
    need = ("proper_eval.py", "improve_iterate.py")
    missing = [n for n in need if n not in agents]
    playbooks = [
        "docs/playbooks/run-proper-eval.md",
        "docs/playbooks/run-improve-iterate.md",
    ]
    missing_pb = [p for p in playbooks if not (repo_root / p).is_file()]
    if missing or missing_pb:
        return LensResult(
            "agent_docs",
            "docs steward",
            "block",
            "agents lack documented focus/eval entrypoints",
            missing + missing_pb,
        )
    return LensResult(
        "agent_docs",
        "docs steward",
        "pass",
        "AGENTS.md and playbooks document the eval/improve loop",
        list(need) + playbooks,
    )


def _lens_security_suite(repo_root: Path) -> LensResult:
    path = repo_root / "tests/test_security.py"
    if not path.is_file():
        return LensResult(
            "security_suite",
            "security sentinel",
            "block",
            "tests/test_security.py missing",
            [str(path)],
        )
    return LensResult(
        "security_suite",
        "security sentinel",
        "pass",
        "security regression suite present",
        [str(path.relative_to(repo_root))],
    )


def _lens_fleet_entrypoint(repo_root: Path) -> LensResult:
    text = _read(repo_root / "agentic/manifest.yaml") or ""
    if "command: just fleet-smoke" not in text:
        return LensResult(
            "fleet_entrypoint",
            "fleet adapter",
            "block",
            "Fleet eval_entrypoint must remain just fleet-smoke",
            ["agentic/manifest.yaml"],
        )
    return LensResult(
        "fleet_entrypoint",
        "fleet adapter",
        "pass",
        "Fleet eval_entrypoint is just fleet-smoke (unchanged)",
        ["agentic/manifest.yaml"],
    )


def _lens_rigid_tests(repo_root: Path) -> LensResult:
    tests = [
        "tests/test_proper_eval.py",
        "tests/test_improve_iterate.py",
        "tests/test_eval_pilot.py",
    ]
    missing = [t for t in tests if not (repo_root / t).is_file()]
    if missing:
        return LensResult(
            "rigid_tests",
            "qa lead",
            "block",
            "rigid eval/improve tests missing",
            missing,
        )
    return LensResult(
        "rigid_tests",
        "qa lead",
        "pass",
        "rigid unit tests cover proper-eval and improve-iterate",
        tests,
    )


LENSES: tuple[LensFn, ...] = (
    _lens_structure,
    _lens_promotion,
    _lens_eval_loop,
    _lens_ci,
    _lens_workers_honesty,
    _lens_next_priorities,
    _lens_agent_docs,
    _lens_security_suite,
    _lens_fleet_entrypoint,
    _lens_rigid_tests,
)


def build_context_pack(repo_root: Path) -> dict[str, Any]:
    """Compact, deterministic orientation packet for an agent."""
    next_md = _read(repo_root / ".self-improvement/NEXT.md") or ""
    p0_lines = [
        line.strip()
        for line in next_md.splitlines()
        if line.strip().startswith("- [") and "P0" not in line
    ]
    # Prefer bullets under P0 section
    p0_section: list[str] = []
    in_p0 = False
    for line in next_md.splitlines():
        if line.startswith("## P0"):
            in_p0 = True
            continue
        if in_p0 and line.startswith("## "):
            break
        if in_p0 and line.strip().startswith("- ["):
            p0_section.append(line.strip())
    return {
        "purpose": (
            "Holusight helps agents do better work: project context, alignment, "
            "and deterministic focus before retrieval/answer changes."
        ),
        "subject": _git_subject(repo_root),
        "read_first": [
            "AGENTS.md",
            "docs/decisions/0019-local-advisory-evaluator-promotion-denied.md",
            ".self-improvement/NEXT.md",
            "docs/playbooks/run-improve-iterate.md",
            "docs/playbooks/run-proper-eval.md",
        ],
        "commands": {
            "orient": "just agent-focus",
            "measure": "just improve-iterate",
            "gate": "just proper-eval",
            "fleet": "just fleet-smoke",
            "pilot": "just eval-pilot",
        },
        "hard_rules": [
            "Promotion denied — no autonomous promote/merge/deploy from eval gates",
            "Do not invent Graphify superiority metrics",
            "Prefer offline/no-spend surfaces unless explicitly authorized",
            "Write derived state only under .holusight/, never as canonical truth",
        ],
        "p0_gaps": p0_section or p0_lines[:8],
    }


def run_agent_focus(repo_root: Path) -> dict[str, Any]:
    results = [lens(repo_root) for lens in LENSES]
    blocks = [r for r in results if r.verdict == "block"]
    inds = [r for r in results if r.verdict == "indeterminate"]
    if blocks:
        verdict: Verdict = "block"
        focus = (
            "Stop and repair blocked alignment lenses before product changes: "
            + ", ".join(r.lens_id for r in blocks)
        )
    elif inds:
        verdict = "indeterminate"
        focus = (
            "Proceed carefully; resolve indeterminate lenses: "
            + ", ".join(r.lens_id for r in inds)
        )
    else:
        verdict = "pass"
        focus = (
            "Aligned. Prefer P0 in NEXT.md; measure with just improve-iterate; "
            "promotion remains denied."
        )

    return {
        "schema_version": SCHEMA,
        "recorded_at": _now(),
        "verdict": verdict,
        "focus": focus,
        "promotion": {
            "allowed": False,
            "status": "denied",
            "reason": "ADR-0019 — focus harness is advisory orientation only",
        },
        "council_size": len(results),
        "council": [
            {
                "lens_id": r.lens_id,
                "role": r.role,
                "verdict": r.verdict,
                "finding": r.finding,
                "evidence": r.evidence,
            }
            for r in results
        ],
        "context_pack": build_context_pack(repo_root),
        "loop": {
            "deterministic": True,
            "llm_calls": 0,
            "spawns_chat_agents": False,
            "next_measure": "just improve-iterate",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Holusight deterministic agent-focus harness")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    payload = run_agent_focus(args.repo_root.resolve())
    print(json.dumps(payload, sort_keys=True, indent=2))
    if payload["verdict"] == "pass":
        return 0
    if payload["verdict"] == "indeterminate":
        return 3
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
