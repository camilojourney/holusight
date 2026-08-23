#!/usr/bin/env python3
"""Opt-in embedding-model variant runner for the retrieval eval harness.

This module NEVER changes `codesight.config.DEFAULT_EMBEDDING_MODEL` and is
NEVER invoked by `eval_holusight.py`'s default flow (`just eval`). It only
runs when a caller explicitly supplies a model/backend, either via
`run_variant_eval(...)` or `--variant-model`/`--variant-backend` on this
script's own CLI.

Because a different embedding model produces vectors in a different space
than whatever is already indexed at `~/.codesight/data/<hash>/`, a variant
run cannot reuse the default store — it builds a small, disposable, LOCAL-ONLY
index in a temp directory (via `CODESIGHT_DATA_DIR`, set before `codesight` is
imported) and deletes it when done. The default store is never opened, read,
or written by this module.

If the requested backend needs an API key (`voyage`, `api`) and the key is
absent, `codesight.embeddings.get_embedder` raises immediately — this module
adds no fallback, so there is no silent network call and no silent
downgrade to a different model.

Every run reports, per spec 014's model-pluggability guardrail:
  provider   — backend ("local" | "voyage" | "api")
  model      — exact model name requested
  dimensions — resolved embedding dimension
  timing     — index build wall time, average query latency
  usage      — embedding call count and an ESTIMATED token count
               (len(text)//4 per embedded string — the same fallback
               tokenizer eval_harness.py uses for snippets; not a
               provider-billed token count)
  cost       — only computed when the caller supplies --price-per-1k-input /
               --price-per-1k-output; otherwise reported as null with an
               explicit "unknown" note. Never guessed from a hardcoded price
               table, because provider prices change.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUERIES = Path(__file__).resolve().parent / "fixtures" / "holusight_eval_taxonomy.json"


@dataclass
class EmbeddingVariantSpec:
    """An explicit, caller-supplied embedding model to benchmark.

    Never constructed with a default model — every field must come from the
    caller (CLI flags or direct instantiation), so a variant run can never
    silently exercise the process default.
    """

    model_name: str
    backend: str  # "local" | "voyage" | "api"
    dim: int | None = None  # resolved via codesight's own registry if None
    price_per_1k_input: float | None = None
    price_per_1k_output: float | None = None  # reserved; embeddings are input-only today


@dataclass
class _EmbedUsage:
    query_calls: int = 0
    document_calls: int = 0
    texts_embedded: int = 0
    estimated_tokens: int = 0
    embed_wall_ms: float = 0.0


class _InstrumentedEmbedder:
    """Wraps a real Embedder to record call/token/timing usage without
    changing its behavior. Delegates every call to the wrapped embedder."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.usage = _EmbedUsage()

    def _tokens_for(self, texts: list[str]) -> int:
        return sum(max(1, len(t) // 4) for t in texts)

    def embed(self, texts: list[str]):
        t0 = time.perf_counter()
        result = self._inner.embed(texts)
        self.usage.embed_wall_ms += (time.perf_counter() - t0) * 1000.0
        self.usage.document_calls += 1
        self.usage.texts_embedded += len(texts)
        self.usage.estimated_tokens += self._tokens_for(texts)
        return result

    def embed_query(self, query: str):
        t0 = time.perf_counter()
        result = self._inner.embed_query(query)
        self.usage.embed_wall_ms += (time.perf_counter() - t0) * 1000.0
        self.usage.query_calls += 1
        self.usage.texts_embedded += 1
        self.usage.estimated_tokens += self._tokens_for([query])
        return result


def run_variant_eval(
    queries,
    repo_path: str | Path,
    variant: EmbeddingVariantSpec,
    top_k: int = 10,
    reranker: bool = False,
) -> dict:
    """Run the eval harness against an isolated, disposable index built with
    `variant`'s embedding model. Returns a JSON-serializable report.

    Must be called with `codesight` NOT YET IMPORTED in this process if you
    need `CODESIGHT_DATA_DIR` isolation to take effect (it's read once at
    import time). The CLI in this module handles that ordering; callers
    importing this function directly are responsible for the same ordering
    if they want the isolation guarantee.
    """
    from codesight.config import DEFAULT_EMBEDDING_MODEL, ServerConfig, resolve_embedding_dim
    from tests.eval_harness import run_eval

    dim = variant.dim if variant.dim is not None else resolve_embedding_dim(variant.model_name)

    config = ServerConfig(
        embedding_model=variant.model_name,
        embedding_backend=variant.backend,
        embedding_dim=dim,
        reranker=reranker,  # off by default: isolates the embedding, not the reranker
        query_enhancement=False,
    )

    import codesight.indexer as _indexer_module
    from codesight.api import CodeSight

    engine = CodeSight(repo_path, config=config)
    # get_embedder(...) raises immediately if a required API key is missing.
    raw_embedder = engine.embedder
    instrumented = _InstrumentedEmbedder(raw_embedder)
    # noqa: SLF001 — intentional: swap in the instrumented wrapper post-construction
    engine._embedder = instrumented

    # index_repo() resolves its own embedder via codesight.indexer.get_embedder(...)
    # rather than engine.embedder, so document-embedding calls made during
    # indexing would otherwise bypass the instrumentation above. Temporarily
    # redirect indexer.py's bound name to return the same instrumented
    # wrapper so index-time usage is captured too, then restore it — this
    # never touches the shared get_embedder() cache or any other caller.
    _original_get_embedder = _indexer_module.get_embedder

    def _instrumented_get_embedder(model_name, dim_, backend="local"):
        if model_name == variant.model_name and backend == variant.backend:
            return instrumented
        return _original_get_embedder(model_name, dim_, backend=backend)

    _indexer_module.get_embedder = _instrumented_get_embedder
    try:
        t0 = time.perf_counter()
        index_stats = engine.index(force_rebuild=True)
        index_build_ms = (time.perf_counter() - t0) * 1000.0
    finally:
        _indexer_module.get_embedder = _original_get_embedder

    result = run_eval(
        queries,
        engine.store,
        instrumented,
        top_k=top_k,
        config=config,
    )

    cost = None
    cost_note = (
        "no --price-per-1k-input supplied; cost intentionally left unknown, not assumed zero"
    )
    if variant.price_per_1k_input is not None:
        cost = round(
            (instrumented.usage.estimated_tokens / 1000.0) * variant.price_per_1k_input, 6
        )
        cost_note = (
            "estimated: (estimated_tokens / 1000) * price_per_1k_input; "
            "tokens are len//4, not provider-billed counts"
        )

    return {
        "schema_version": "holus-eval-variant-report/v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "guardrail": {
            "process_default_embedding_model": DEFAULT_EMBEDDING_MODEL,
            "variant_changed_process_default": False,
            "note": "This run built an isolated, disposable local index and never touched "
            "the default ~/.codesight/data store or codesight.config.DEFAULT_EMBEDDING_MODEL.",
        },
        "provider": {
            "backend": variant.backend,
            "model": variant.model_name,
            "dimensions": dim,
        },
        "index": {
            "files_indexed": index_stats.files_indexed,
            "chunks_created": index_stats.chunks_created,
            "build_ms": round(index_build_ms, 1),
        },
        "usage": {
            "query_embed_calls": instrumented.usage.query_calls,
            "document_embed_calls": instrumented.usage.document_calls,
            "texts_embedded": instrumented.usage.texts_embedded,
            "estimated_tokens": instrumented.usage.estimated_tokens,
            "embed_wall_ms": round(instrumented.usage.embed_wall_ms, 1),
        },
        "cost": {
            "currency": "USD",
            "estimated": cost,
            "note": cost_note,
        },
        "timing": {
            "avg_query_latency_ms": round(result.avg_latency_ms, 2),
        },
        "metrics": {
            "hit_rate": round(result.hit_rate, 4),
            "recall_at_k": {str(k): round(v, 4) for k, v in result.recall_at_k.items()},
            "mrr_at_10": round(result.mrr_at_10, 4),
            "ndcg_at_10": round(result.ndcg_at_10, 4),
            "evidence_completeness": round(result.evidence_completeness, 4),
            "num_graded": result.num_graded,
            "num_diagnostic_probes": result.num_diagnostic_probes,
        },
        "per_query": result.per_query,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run an opt-in embedding-model variant against an isolated local index. "
        "Never changes the process default embedding model."
    )
    parser.add_argument("--repo-path", type=Path, default=REPO_ROOT)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--variant-model", required=True, help="Embedding model name to benchmark")
    parser.add_argument(
        "--variant-backend", required=True, choices=["local", "voyage", "api"],
        help="Embedding backend for --variant-model",
    )
    parser.add_argument("--variant-dim", type=int, default=None)
    parser.add_argument("--price-per-1k-input", type=float, default=None)
    parser.add_argument(
        "--reranker", action="store_true", help="Enable reranker for this variant run",
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    # Isolation MUST happen before `codesight` (and therefore
    # `codesight.config`) is imported anywhere in this process — DATA_DIR is
    # resolved from the environment once, at import time.
    if "codesight" in sys.modules or "codesight.config" in sys.modules:
        print(
            "error: codesight was already imported before isolation could be set up; "
            "run this file as a fresh process (python tests/eval_variants.py ...), "
            "don't import eval_variants after importing codesight.",
            file=sys.stderr,
        )
        return 1

    repo_path = args.repo_path.resolve()
    sys.path.insert(0, str(repo_path / "src"))
    sys.path.insert(0, str(repo_path))

    tmp_data_dir = tempfile.mkdtemp(prefix="codesight-eval-variant-")
    os.environ["CODESIGHT_DATA_DIR"] = tmp_data_dir

    try:
        from tests.eval_holusight import _load_queries

        queries = _load_queries(args.queries)
        variant = EmbeddingVariantSpec(
            model_name=args.variant_model,
            backend=args.variant_backend,
            dim=args.variant_dim,
            price_per_1k_input=args.price_per_1k_input,
        )
        payload = run_variant_eval(
            queries,
            repo_path,
            variant,
            top_k=args.top_k,
            reranker=args.reranker,
        )
    finally:
        shutil.rmtree(tmp_data_dir, ignore_errors=True)

    text = json.dumps(payload, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n")
        print(f"Wrote {args.output}")
    else:
        print(text)

    m = payload["metrics"]
    print(
        f"variant={variant.model_name} hit_rate={m['hit_rate']:.1%} "
        f"mrr@10={m['mrr_at_10']:.3f} ndcg@10={m['ndcg_at_10']:.3f} "
        f"est_tokens={payload['usage']['estimated_tokens']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
