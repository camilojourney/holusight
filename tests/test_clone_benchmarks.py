"""Opt-in, bounded public-data CLI experiment, not part of pytest's dataset suite.

Run: python tests/test_clone_benchmarks.py PUBLIC_DATA NEW_RESULT_DIRECTORY
PUBLIC_DATA contains the three named pinned archives below. No downloads or corpus
execution occur. See specs/030-source-evaluation.md for labels and limitations.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
import time
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from tarfile import open as open_tar

ARCHIVES = {
    "GPTCloneBench_semantic_standalone_clones.zip": (
        "22fc617d8980f4c54df1d62fd2804f313c86f8fcefff84d8ff6a657c84cdf516"
    ),
    "SemanticCloneBench.zip": "d5601ad925dd26b942676cabef88a68b799668f0b6d2d01f0d63db46d2584643",
    "Project_CodeNet_Python800.tar.gz": (
        "39297d11df8030ce0b6619e678547a738d74c4715c5c9a5be0af83941a5587b0"
    ),
}


def _parts(raw: bytes) -> tuple[bytes, bytes] | None:
    headers = list(re.finditer(rb"(?m)^ {0,3}(?:async )?def [^\r\n]+", raw))
    if len(headers) != 2:
        return None
    cut = headers[1].start()
    return raw[:cut], raw[cut:]


def _counts(records: list[dict]) -> dict:
    counts = Counter(
        "TP"
        if r["label"] and r["predicted"]
        else "FN"
        if r["label"]
        else "FP"
        if r["predicted"]
        else "TN"
        for r in records
        if r["label"] is not None
    )
    tp, fp, fn = (counts.get(k, 0) for k in ("TP", "FP", "FN"))
    return {
        "counts": dict(counts),
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
    }


def _peak_child_rss() -> int | None:
    try:
        import resource
    except ImportError:  # Non-POSIX test environments can still test framing/scoring.
        return None
    return resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss


def _pairs(data: Path):
    for filename, expected in ARCHIVES.items():
        with (data / filename).open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected:
            raise ValueError(f"archive hash mismatch: {filename}")
    for dataset, filename, groups in (
        (
            "GPTCloneBench",
            "GPTCloneBench_semantic_standalone_clones.zip",
            [
                ("true-semantic", "standalone/true_semantic_clones/py/", True),
                ("high-syntactic-control", "standalone/false_semantic_clones/py/", None),
            ],
        ),
        (
            "SemanticCloneBench",
            "SemanticCloneBench.zip",
            [
                ("semantic", "Python/Stand alone clones/", True),
            ],
        ),
    ):
        with zipfile.ZipFile(data / filename) as archive:
            for category, prefix, label in groups:
                names = sorted(
                    n for n in archive.namelist() if n.startswith(prefix) and n.endswith(".py")
                )[:100]
                for i, name in enumerate(names):
                    raw = archive.read(name)
                    if len(raw) > 256_000:
                        raise ValueError("selected ZIP member exceeds adapter budget")
                    yield dataset, f"{category}-{i:03}", category, label, [name], _parts(raw)
    with open_tar(data / "Project_CodeNet_Python800.tar.gz") as archive:
        files = defaultdict(list)
        for member in archive.getmembers():
            if not member.isfile() or not member.name.endswith(".py"):
                continue
            parts = Path(member.name).parts
            if len(parts) != 3 or not re.fullmatch(r"p\d{5}", parts[1]):
                raise ValueError("unexpected Python800 member path")
            files[parts[1]].append(member)
        problems = sorted(files)[:101]
        for i, problem in enumerate(problems[:100]):
            left, right = sorted(files[problem], key=lambda m: m.name)[:2]
            other = sorted(files[problems[i + 1]], key=lambda m: m.name)[0]
            for category, label, partner in (
                ("same-problem-proxy", True, right),
                ("different-problem-proxy", False, other),
            ):
                pair = tuple(archive.extractfile(m).read() for m in (left, partner))
                yield (
                    "Python800",
                    f"{category}-{i:03}",
                    category,
                    label,
                    [
                        left.name,
                        partner.name,
                    ],
                    pair,
                )


def _run(data: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    records = []
    for dataset, key, category, label, sources, pair in _pairs(data):
        record = {
            "dataset": dataset,
            "id": key,
            "category": category,
            "label": label,
            "source": sources,
            "predicted": False,
            "adapter_unframed": pair is None,
            "eligible_files": 0,
            "parse_error_files": 0,
        }
        if pair is not None:
            root = output / "cases" / dataset / key
            root.mkdir(parents=True)
            # An independent Git root prevents ancestor-repository discovery.
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            record["sha256"] = {}
            for name, raw in zip(("left.py", "right.py"), pair, strict=True):
                (root / name).write_bytes(raw)
                record["sha256"][name] = hashlib.sha256(raw).hexdigest()
                try:
                    tree = ast.parse(raw.decode("utf-8"))
                    eligible = any(
                        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and len(n.body) >= 3
                        and len(list(ast.walk(n))) >= 20
                        for n in ast.walk(tree)
                    )
                    record["eligible_files"] += int(eligible)
                except (SyntaxError, UnicodeError):
                    record["parse_error_files"] += 1
            command = [sys.executable, "-m", "holusight", "align", str(root)]
            start = time.perf_counter()
            proc = subprocess.run(command, text=True, capture_output=True, timeout=15)
            report = json.loads(proc.stdout)
            (output / f"{dataset}-{key}.json").write_text(proc.stdout)
            (output / f"{dataset}-{key}.stderr").write_text(proc.stderr)
            record.update(
                command=command,
                exit=proc.returncode,
                status=report["status"],
                complete=report["complete"],
                elapsed_seconds=time.perf_counter() - start,
                peak_child_rss=_peak_child_rss(),
            )
            record["predicted"] = any(
                f["type"] == "code_duplicate"
                and {"left.py", "right.py"} <= {o["file"] for o in f["locations"]}
                for f in report["findings"]
            )
        records.append(record)
    summary = {}
    for dataset in sorted({r["dataset"] for r in records}):
        selected = [r for r in records if r["dataset"] == dataset]
        summary[dataset] = {
            **_counts(selected),
            "selected": len(selected),
            "unframed": sum(r["adapter_unframed"] for r in selected),
            "incomplete": sum(r.get("complete") is not True for r in selected),
            "parse_error_pairs": sum(r["parse_error_files"] > 0 for r in selected),
            "both_eligible_pairs": sum(r["eligible_files"] == 2 for r in selected),
            "elapsed_seconds": sum(r.get("elapsed_seconds", 0) for r in selected),
            "peak_child_rss": max(
                (r["peak_child_rss"] for r in selected if r.get("peak_child_rss") is not None),
                default=None,
            ),
            "candidate_yield_by_category": {
                category: sum(r["predicted"] for r in selected if r["category"] == category)
                for category in sorted({r["category"] for r in selected})
            },
        }
    (output / "metrics.json").write_text(
        json.dumps(
            {
                "archives": ARCHIVES,
                "summary": summary,
                "records": records,
                "platform": sys.platform,
                "rss_units": "bytes" if sys.platform == "darwin" else "platform ru_maxrss units",
                "rss_scope": "maximum child process RSS, not whole adapter memory",
            },
            indent=2,
        )
    )
    print(json.dumps(summary, indent=2))


def test_adapter_preserves_invalid_indentation_and_original_bytes():
    raw = b"def left():\n    pass\n\n def right():\n    pass\n"
    left, right = _parts(raw)
    assert left + right == raw
    assert right.startswith(b" def")
    assert _parts(b"print('no function pair')") is None


def test_high_syntactic_controls_are_not_invented_semantic_negatives():
    result = _counts(
        [
            {"label": True, "predicted": False},
            {"label": False, "predicted": False},
            {"label": None, "predicted": True},
        ]
    )
    assert result == {"counts": {"FN": 1, "TN": 1}, "precision": None, "recall": 0.0}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: test_clone_benchmarks.py PUBLIC_DATA NEW_RESULT_DIRECTORY")
    _run(Path(sys.argv[1]), Path(sys.argv[2]))
