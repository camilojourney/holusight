"""Benchmark configuration profiles (A-H) for reproducible comparisons."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import chunker


@dataclass(frozen=True)
class BenchmarkProfile:
    name: str
    retrieval: str
    reranker: str | None
    chunking: str
    requires_ast: bool = False
    requires_jit: bool = False
    requires_cag: bool = False


# SPEC-009-004: Predefined benchmark configuration matrix A-H.
BENCHMARK_PROFILES: dict[str, BenchmarkProfile] = {
    "A": BenchmarkProfile(
        name="A",
        retrieval="vector_only",
        reranker=None,
        chunking="512",
    ),
    "B": BenchmarkProfile(
        name="B",
        retrieval="hybrid",
        reranker=None,
        chunking="512",
    ),
    "C": BenchmarkProfile(
        name="C",
        retrieval="hybrid",
        reranker="minilm",
        chunking="512",
    ),
    "D": BenchmarkProfile(
        name="D",
        retrieval="hybrid",
        reranker="qwen3",
        chunking="512",
    ),
    "E": BenchmarkProfile(
        name="E",
        retrieval="hybrid",
        reranker="qwen3",
        chunking="1024_overlap_15",
    ),
    "F": BenchmarkProfile(
        name="F",
        retrieval="hybrid",
        reranker="qwen3",
        chunking="ast_code_512_text",
        requires_ast=True,
    ),
    "G": BenchmarkProfile(
        name="G",
        retrieval="hybrid_jit",
        reranker="qwen3",
        chunking="ast_512_jit",
        requires_ast=True,
        requires_jit=True,
    ),
    "H": BenchmarkProfile(
        name="H",
        retrieval="cag",
        reranker=None,
        chunking="cag",
        requires_cag=True,
    ),
}


def get_profile(name: str) -> BenchmarkProfile:
    key = name.strip().upper()
    if key not in BENCHMARK_PROFILES:
        valid = ", ".join(sorted(BENCHMARK_PROFILES))
        raise ValueError(f"Unknown benchmark config '{name}'. Valid options: {valid}")
    profile = BENCHMARK_PROFILES[key]
    _validate_profile_dependencies(profile)
    return profile


def load_profile_from_file(path: str | Path) -> BenchmarkProfile:
    payload: dict[str, Any] = json.loads(Path(path).read_text(encoding="utf-8"))
    name = str(payload.get("name", "custom"))
    return BenchmarkProfile(
        name=name,
        retrieval=str(payload.get("retrieval", "hybrid")),
        reranker=payload.get("reranker"),
        chunking=str(payload.get("chunking", "custom")),
    )


def _validate_profile_dependencies(profile: BenchmarkProfile) -> None:
    if profile.requires_ast and not hasattr(chunker, "_chunk_file_ast"):
        # EDGE-009-005: Config requires feature not yet implemented.
        raise ValueError(
            "Config F requires AST chunking (Spec 004). "
            "Implement Spec 004 first or use Config A-E."
        )
    if profile.requires_jit:
        raise ValueError(
            f"Config {profile.name} requires JIT retrieval (v0.6). "
            "Use Config A-F until JIT is implemented."
        )
    if profile.requires_cag:
        raise ValueError(
            f"Config {profile.name} requires CAG mode (v0.5). "
            "Use Config A-F until CAG is implemented."
        )
