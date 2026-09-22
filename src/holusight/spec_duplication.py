"""Advisory nearest-neighbor spec similarity check.

Surfaces, for a changed spec, which other `specs/NNN-*.md` files it reads
most similarly to -- so a human or reviewing agent can ask "should this have
updated one of these instead of becoming a new spec?" -- and whether that
relationship is already declared in prose, using this repo's existing
convention ("spec 014", "specs 017-020", "Depends on: Spec 014 ..."; see
specs 018-022 for real examples already in this repository).

This is deliberately a ranked nearest-neighbor report, not a pass/fail
duplicate classifier. Empirical testing against this repository's own 22
specs showed why: general-purpose embeddings over whole spec documents do
not cleanly separate "same feature, different spec" from "different
feature, same project vocabulary" at any single similarity threshold --
e.g. specs 011/012 (genuinely related research docs) score 0.80, but spec
010 (an unrelated capability-status table) scores 0.55-0.60 against half
the eval-control-plane family purely from shared Holusight/ADR/advisory
jargon. A threshold-based classifier at this corpus's scale would file
more false positives than true ones. Ranking is honest about what the
signal actually supports; a human still makes the call.

Advisory only, same posture as the rest of the improvement control plane
(ADR-0019): this module never edits, blocks, or merges anything. It reuses
the existing local-embedding similarity machinery in ``consistency.py``
rather than introducing a second embedding path.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from .consistency import EmbedFn, _cosine, _default_local_embed_fn

REPO_ROOT = Path(__file__).resolve().parents[2]

_SPEC_FILENAME_RE = re.compile(r"^(\d{3})-")
_SPEC_KEYWORD_RE = re.compile(r"\bspecs?\b", re.IGNORECASE)
_RANGE_RE = re.compile(r"(\d{3})\s*-\s*(\d{3})")
_NUMBER_RE = re.compile(r"\d{3}")
_MENTION_WINDOW = 60
_MAX_DECLARED_RANGE = 50


def declared_spec_numbers(text: str) -> set[str]:
    """Every spec number this text declares a relationship to, by scanning a
    short window after each "spec"/"specs" mention for 3-digit numbers and
    NNN-MMM ranges. A heuristic over existing prose, not a parser -- matches
    real phrasing already in this repo ("specs 017-020", "spec 014
    (85-case visible taxonomy)", "Depends on: Spec 014 ...")."""
    declared: set[str] = set()
    for m in _SPEC_KEYWORD_RE.finditer(text):
        window = text[m.end() : m.end() + _MENTION_WINDOW]
        for r in _RANGE_RE.finditer(window):
            lo, hi = int(r.group(1)), int(r.group(2))
            if lo <= hi and hi - lo <= _MAX_DECLARED_RANGE:
                declared.update(f"{n:03d}" for n in range(lo, hi + 1))
        declared.update(n.group() for n in _NUMBER_RE.finditer(window))
    return declared


def _spec_paths(repo_root: Path) -> list[Path]:
    specs_dir = repo_root / "specs"
    if not specs_dir.is_dir():
        return []
    return sorted(
        p
        for p in specs_dir.glob("*.md")
        if _SPEC_FILENAME_RE.match(p.name) and p.name != "000-template.md"
    )


def _pairwise_similarity(
    paths: list[Path], embed_fn: EmbedFn | None
) -> dict[tuple[Path, Path], float]:
    texts = {p: p.read_text(encoding="utf-8", errors="replace") for p in paths}
    embed = embed_fn or _default_local_embed_fn()
    ordered = sorted(texts)
    vectors = embed([texts[p] for p in ordered])
    vector_by_path = dict(zip(ordered, vectors))
    scores: dict[tuple[Path, Path], float] = {}
    for i, a in enumerate(ordered):
        for b in ordered[i + 1 :]:
            scores[(a, b)] = _cosine(vector_by_path[a], vector_by_path[b])
    return scores


def nearest_neighbor_specs(
    repo_root: Path,
    embed_fn: EmbedFn | None = None,
    top_k: int = 3,
    target_specs: set[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """For each spec (or only ``target_specs`` filenames when given), the
    ``top_k`` other specs it reads most similarly to, each carrying whether
    that relationship is already declared in prose. Always returns
    something for every requested spec -- there is no cutoff to silently
    drop a spec's nearest neighbors, only a rank."""
    paths = _spec_paths(repo_root)
    if len(paths) < 2:
        return {}

    texts = {p: p.read_text(encoding="utf-8", errors="replace") for p in paths}
    numbers = {p: p.name[:3] for p in paths}
    declared = {p: declared_spec_numbers(texts[p]) for p in paths}
    scores = _pairwise_similarity(paths, embed_fn)

    def score_of(a: Path, b: Path) -> float:
        return scores.get((a, b), scores.get((b, a), 0.0))

    result: dict[str, list[dict[str, Any]]] = {}
    for spec in paths:
        if target_specs is not None and spec.name not in target_specs:
            continue
        others = [p for p in paths if p != spec]
        others.sort(key=lambda o: -score_of(spec, o))
        neighbors = []
        for other in others[:top_k]:
            declared_relationship = (
                numbers[other] in declared[spec] or numbers[spec] in declared[other]
            )
            neighbors.append(
                {
                    "spec": other.name,
                    "similarity": round(score_of(spec, other), 4),
                    "declared_relationship": declared_relationship,
                }
            )
        result[spec.name] = neighbors
    return result


def run(
    repo_root: Path | None = None,
    top_k: int = 3,
    changed_specs: list[str] | None = None,
    embed_fn: EmbedFn | None = None,
) -> dict[str, Any]:
    """``changed_specs`` (filenames) scopes the report to just those specs --
    the intended CI usage, reporting nearest neighbors only for specs that
    changed in the current diff. Omit it to report on every spec."""
    root = repo_root or REPO_ROOT
    target = set(changed_specs) if changed_specs else None
    neighbors = nearest_neighbor_specs(root, embed_fn=embed_fn, top_k=top_k, target_specs=target)
    worth_a_look = {
        spec: [n for n in nbrs if not n["declared_relationship"] and n["similarity"] >= 0.5]
        for spec, nbrs in neighbors.items()
    }
    worth_a_look = {spec: nbrs for spec, nbrs in worth_a_look.items() if nbrs}
    return {
        "schema_version": "holusight-spec-neighbors/v1",
        "specs_checked": len(_spec_paths(root)),
        "nearest_neighbors": neighbors,
        "undeclared_and_worth_a_look": worth_a_look,
        "advisory_only": True,
        "promotion": {
            "allowed": False,
            "reason": "ADR-0019 local/advisory evaluator; no autonomous promote/merge/deploy",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Advisory spec nearest-neighbor check")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument(
        "--changed",
        nargs="*",
        default=None,
        help="Filenames (e.g. 023-foo.md) to scope the report to; omit for every spec",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    payload = run(args.repo_root.resolve(), top_k=args.top_k, changed_specs=args.changed)
    print(json.dumps(payload, indent=2, sort_keys=True))
    # Advisory: findings are reported, never fail CI on their own.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
