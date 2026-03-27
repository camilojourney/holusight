"""Configuration for the CodeSight search engine."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DATA_DIR = Path(
    os.environ.get("CODESIGHT_DATA_DIR", Path.home() / ".codesight" / "data")
)


def repo_data_dir(repo_path: str | Path) -> Path:
    """Return the data directory for a given folder, creating parent dirs if needed.

    Each folder gets its own subdirectory containing:
      - LanceDB table files (vectors)
      - metadata.db (SQLite FTS5 sidecar for BM25)
    """
    canonical = os.path.realpath(str(repo_path))
    short_hash = hashlib.sha256(canonical.encode()).hexdigest()[:12]
    data_dir = DATA_DIR / short_hash
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def repo_fts_db_path(repo_path: str | Path) -> Path:
    """Return the SQLite FTS5 sidecar DB path for a given folder."""
    return repo_data_dir(repo_path) / "metadata.db"


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_EMBEDDING_MODEL = os.environ.get(
    "CODESIGHT_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
DEFAULT_EMBEDDING_BACKEND = os.environ.get("CODESIGHT_EMBEDDING_BACKEND", "local")

# Allowlist of tested embedding models with their dimensions.
EMBEDDING_MODEL_REGISTRY: dict[str, int] = {
    "sentence-transformers/all-MiniLM-L6-v2": 384,
    "nomic-ai/nomic-embed-text-v1.5": 768,
    "mixedbread-ai/mxbai-embed-large-v1": 1024,
    "jinaai/jina-embeddings-v2-base-code": 768,
    "text-embedding-3-large": 3072,  # OpenAI API model
    "text-embedding-3-small": 1536,  # OpenAI API model
}


def resolve_embedding_dim(model_name: str) -> int:
    """Return expected embedding dimension for a model. Falls back to 384."""
    return EMBEDDING_MODEL_REGISTRY.get(model_name, 384)


DEFAULT_EMBEDDING_DIM = resolve_embedding_dim(DEFAULT_EMBEDDING_MODEL)
DEFAULT_TOP_K = 8
DEFAULT_CHUNK_MAX_LINES = 200
DEFAULT_CHUNK_OVERLAP_LINES = 50
DEFAULT_DOC_CHUNK_MAX_CHARS = 1500
DEFAULT_DOC_CHUNK_OVERLAP_CHARS = 200
STALE_THRESHOLD_SECONDS = int(os.environ.get("CODESIGHT_STALE_SECONDS", "300"))  # 5 minutes
BM25_CANDIDATE_MULTIPLIER = 3  # fetch 3x top_k from each retriever before RRF

DEFAULT_LLM_MODEL = "claude-sonnet-4-20250514"

# Reranker
DEFAULT_RERANKER_ENABLED = os.environ.get("CODESIGHT_RERANKER", "false").lower() == "true"
DEFAULT_RERANKER_MODEL = os.environ.get(
    "CODESIGHT_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"
)
DEFAULT_RERANKER_TOP_N = int(os.environ.get("CODESIGHT_RERANKER_TOP_N", "20"))
DEFAULT_LLM_BACKEND = os.environ.get("CODESIGHT_LLM_BACKEND", "claude")


# ---------------------------------------------------------------------------
# File walking
# ---------------------------------------------------------------------------

# Code files (read as UTF-8 text, chunked by scope boundaries)
CODE_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".go", ".rs", ".java", ".kt", ".scala",
    ".c", ".cpp", ".h", ".hpp", ".cs",
    ".rb", ".php", ".swift", ".m",
    ".sql", ".sh", ".bash", ".zsh",
    ".yaml", ".yml", ".toml", ".json",
    ".html", ".css", ".scss",
    ".tf", ".hcl",
    ".proto", ".graphql",
    ".lua", ".r", ".jl",
    ".ex", ".exs", ".erl",
    ".zig", ".nim", ".v",
    ".dockerfile",
}

# Plain text files (read as UTF-8, chunked by windows)
TEXT_EXTENSIONS: set[str] = {
    ".md", ".txt", ".rst", ".csv", ".log",
}

# Binary document files (parsed by parsers.py, chunked by pages/sections)
DOCUMENT_EXTENSIONS: set[str] = {
    ".pdf", ".docx", ".pptx",
}

# All indexable extensions
INDEXABLE_EXTENSIONS: set[str] = CODE_EXTENSIONS | TEXT_EXTENSIONS | DOCUMENT_EXTENSIONS

ALWAYS_SKIP_DIRS: set[str] = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build", ".eggs", ".next", ".nuxt",
    "vendor", "target", "Pods",
}

ALWAYS_SKIP_FILES: set[str] = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "Cargo.lock", "Gemfile.lock",
    "go.sum", "composer.lock",
}

MAX_FILE_SIZE_BYTES = 10_000_000  # 10 MB (documents can be large)


class ServerConfig(BaseModel):
    """Runtime configuration."""

    embedding_model: str = Field(default=DEFAULT_EMBEDDING_MODEL)
    embedding_backend: str = Field(default=DEFAULT_EMBEDDING_BACKEND)
    embedding_dim: int = Field(default=DEFAULT_EMBEDDING_DIM)
    top_k: int = Field(default=DEFAULT_TOP_K)
    chunk_max_lines: int = Field(default=DEFAULT_CHUNK_MAX_LINES)
    chunk_overlap_lines: int = Field(default=DEFAULT_CHUNK_OVERLAP_LINES)
    doc_chunk_max_chars: int = Field(default=DEFAULT_DOC_CHUNK_MAX_CHARS)
    doc_chunk_overlap_chars: int = Field(default=DEFAULT_DOC_CHUNK_OVERLAP_CHARS)
    stale_threshold_seconds: int = Field(default=STALE_THRESHOLD_SECONDS)
    llm_backend: str = Field(default=DEFAULT_LLM_BACKEND)
    llm_model: str = Field(default=DEFAULT_LLM_MODEL)
    reranker: bool = Field(default=DEFAULT_RERANKER_ENABLED)
    reranker_model: str = Field(default=DEFAULT_RERANKER_MODEL)
    reranker_top_n: int = Field(default=DEFAULT_RERANKER_TOP_N)
