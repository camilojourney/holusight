# Spec 002: Embedding Model Configuration

**Status:** implemented
**Phase:** v0.3
**Author:** Juan Martinez
**Created:** 2026-02-24
**Updated:** 2026-02-28

## Problem

The current default embedding model (`all-MiniLM-L6-v2`, 384 dims, 256 token context) limits search quality. Its short context window truncates longer document chunks, and 384 dimensions restrict semantic precision. Clients asking "What are the payment terms?" may miss relevant chunks because the embedding doesn't capture enough meaning.

Better local models exist (768+ dims, 8K context) that are still free, still run on a laptop, and significantly improve retrieval — especially for document search where chunks contain longer paragraphs.

Additionally, some clients may want the absolute best embedding quality and are willing to use a cloud API (OpenAI, Voyage) for it. We should support both local and API embeddings as a configuration choice.

## Goals

- Upgrade default embedding model to `nomic-embed-text-v1.5` (768 dims, 8K context)
- Allow model selection via `CODESIGHT_EMBEDDING_MODEL` env var with allowlist validation
- Support optional API embedding backend for clients who want maximum quality
- Safe model switching: detect dimension mismatch, force index rebuild automatically
- Measurable: Precision@5 improvement of at least 10% on a test query set vs current default

## Non-Goals

- Multiple models simultaneously — one model per index, switching requires rebuild
- Fine-tuning embedding models — use pre-trained models only
- Custom model hosting (vLLM-style) — local sentence-transformers or API, nothing in between

## Solution

Two layers of configuration:

1. **Embedding model** (`CODESIGHT_EMBEDDING_MODEL`): which model to use
2. **Embedding backend** (`CODESIGHT_EMBEDDING_BACKEND`): local (sentence-transformers) or API (OpenAI)

```
CODESIGHT_EMBEDDING_BACKEND=local (default)
├── Model runs on CPU/GPU via sentence-transformers
├── Downloaded once (~80-670MB depending on model)
├── No API key, no internet, no cost, no data leaves
└── CODESIGHT_EMBEDDING_MODEL selects which model

CODESIGHT_EMBEDDING_BACKEND=api
├── Calls OpenAI text-embedding-3-large API
├── Requires OPENAI_API_KEY
├── Best quality (3072 dims), but data goes to OpenAI
└── Cost: ~$0.13 per million tokens (~$5 per 500 docs)
```

## Implementation Notes

### Key Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Default model | `nomic-embed-text-v1.5` | 768 dims, 8K context, strong code+NL, free |
| Fallback model | `all-MiniLM-L6-v2` | Backward compat, fast, known-good |
| API model | `text-embedding-3-large` | Best available, 3072 dims |
| Model allowlist | 4 local + 1 API | Prevent typos, ensure tested models only |

### Model Comparison

| Model | Dims | Context | Size | Speed | Quality |
|-------|------|---------|------|-------|---------|
| all-MiniLM-L6-v2 | 384 | 256 | 80MB | Fastest | Good |
| nomic-embed-text-v1.5 | 768 | 8192 | 270MB | Fast | Better |
| mxbai-embed-large | 1024 | 512 | 670MB | Moderate | Best local |
| jina-embeddings-v2-base-code | 768 | 8192 | 270MB | Fast | Best for code |
| text-embedding-3-large (API) | 3072 | 8191 | — | Network-bound | Best overall |

### Dependencies

- `sentence-transformers` (already have) — local embedding
- `openai>=1.0` (new, optional) — API embedding only
- Depends on: Spec 001 (core search engine must be working)
- Depended on by: Spec 007 (reranking quality depends on embedding quality)

### Implementation Steps

1. Add model allowlist to `config.py` with validation
2. Update `embeddings.py` to accept model name from config
3. Store model name + dims in index metadata (`repo_meta` table)
4. On load, compare stored model vs configured model → force rebuild on mismatch
5. Add `EmbeddingBackend` protocol with `LocalBackend` and `APIBackend` implementations
6. Add `openai` to optional dependencies: `pip install codesight[openai]`

## Alternatives Considered

### Alternative A: Always use API embeddings

Trade-off: Best quality, but requires API key, costs money, and sends document data to OpenAI.
Rejected because: Contradicts our "search is 100% local" privacy story. Must remain optional.

### Alternative B: Use Ollama for embeddings too

Trade-off: Unified with LLM backend, but Ollama's embedding API is less mature than sentence-transformers.
Rejected because: sentence-transformers is battle-tested, has better model selection, and MPS acceleration built in.

## Edge Cases & Failure Modes

- User changes model after indexing → detect dimension mismatch in metadata, log warning, force full rebuild
- Model not installed → clear error: "Model 'X' not found. Run: pip install sentence-transformers && python -c 'from sentence_transformers import SentenceTransformer; SentenceTransformer(\"X\")'"
- Invalid model name → fail fast with list of valid options
- API embedding with no internet → clear error suggesting local model as fallback
- API rate limit → exponential backoff (1s, 2s, 4s), max 3 retries, then fail with message
- Very large batch (100K chunks) → batch embedding in groups of 512, show progress

## Open Questions

- [ ] Should we auto-detect Apple Silicon and recommend `mxbai-embed-large` for M-series chips? — @juan
- [ ] Should model download happen at `pip install` time or first use? — @juan
- [ ] Is 10% Precision@5 improvement a realistic target for nomic vs MiniLM? Need benchmarking. — @juan

## Status Note (2026-08-23)

**Documented drift, not silently changed** — recorded per the
`spec002-default-drift` boundary in
`specs/017-holusight-safe-continuous-evaluation-pilot.md` §10. The "Key
Parameters" table above states the default model is
`nomic-embed-text-v1.5`. The actually shipped default
(`src/codesight/config.py::DEFAULT_EMBEDDING_MODEL`, unchanged by this
note) is:

```python
DEFAULT_EMBEDDING_MODEL = os.environ.get(
    "CODESIGHT_EMBEDDING_MODEL",
    "voyage-code-3" if VOYAGE_API_KEY else "sentence-transformers/all-MiniLM-L6-v2",
)
```

i.e. `all-MiniLM-L6-v2` with no `VOYAGE_API_KEY` set (the common case),
or `voyage-code-3` when one is present — **never** `nomic-embed-text-v1.5`
in current shipped behavior. `nomic-embed-text-v1.5` remains a supported,
allowlisted model (`EMBEDDING_MODEL_REGISTRY`) selectable via
`CODESIGHT_EMBEDDING_MODEL=nomic-ai/nomic-embed-text-v1.5`; it is simply
not the default. This note documents the drift rather than changing the
production default, per the delegated pilot's explicit boundary — a
default change is a separate product decision this note does not make.

## Acceptance Criteria

- [ ] `CODESIGHT_EMBEDDING_MODEL=nomic-embed-text-v1.5` produces 768-dim vectors
- [ ] `CODESIGHT_EMBEDDING_MODEL=all-MiniLM-L6-v2` still works (backward compat)
- [ ] Invalid model name raises `ValueError` listing valid options
- [ ] Index metadata stores model name; changing model triggers auto-rebuild with warning
- [ ] `CODESIGHT_EMBEDDING_BACKEND=api` uses OpenAI API, requires `OPENAI_API_KEY`
- [ ] API embedding missing key → clear error naming the required env var
- [ ] File preamble (first 3 lines of imports/docstring) prepended to chunk context before embedding
- [ ] `uv run --extra dev pytest tests/ -x -v` passes with both local and API backends (API tests mocked)
