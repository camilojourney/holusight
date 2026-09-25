"""Configuration for the Holusight search engine."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

# Auto-load .env from CWD or repo root if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DATA_DIR = Path(
    os.environ.get("HOLUSIGHT_DATA_DIR", Path.home() / ".holusight" / "data")
)


def repo_data_dir(repo_path: str | Path) -> Path:
    """Return the data directory for a given folder, creating parent dirs if needed.

    Each folder gets its own subdirectory containing:
      - LanceDB table files (vectors)
      - metadata.db (SQLite FTS5 sidecar for BM25)

    SEC-002: refuses to open a data directory that resolves inside, equal
    to, or (via a symlink on either side) redirected into the indexed
    folder itself -- the engine must never write where it reads.

    Re-reads the HOLUSIGHT_DATA_DIR env var on every call rather than
    trusting only the module-level DATA_DIR constant, which is computed
    once at import time: a later `os.environ["HOLUSIGHT_DATA_DIR"] = ...`
    (or test monkeypatch.setenv) in the same process would otherwise be
    silently ignored, and every caller would keep writing to whatever
    directory was current at first import. Code that instead monkeypatches
    the module attribute directly (`monkeypatch.setattr(config, "DATA_DIR",
    ...)`) still works when no env var is set.
    """
    env_override = os.environ.get("HOLUSIGHT_DATA_DIR")
    data_root = Path(env_override) if env_override else DATA_DIR
    canonical = os.path.realpath(str(repo_path))
    resolved_data_root = os.path.realpath(str(data_root))
    if resolved_data_root == canonical or resolved_data_root.startswith(
        canonical + os.sep
    ):
        raise ValueError(
            f"HOLUSIGHT_DATA_DIR ({data_root}) resolves inside the indexed "
            f"folder ({repo_path}); the engine must never write inside a "
            "folder it indexes. Point HOLUSIGHT_DATA_DIR somewhere outside "
            "every folder you index."
        )
    short_hash = hashlib.sha256(canonical.encode()).hexdigest()[:12]
    data_dir = data_root / short_hash
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def repo_fts_db_path(repo_path: str | Path) -> Path:
    """Return the SQLite FTS5 sidecar DB path for a given folder."""
    return repo_data_dir(repo_path) / "metadata.db"


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY")

# Allowlist of tested embedding models with their dimensions.
EMBEDDING_MODEL_REGISTRY: dict[str, int] = {
    "sentence-transformers/all-MiniLM-L6-v2": 384,
    "nomic-ai/nomic-embed-text-v1.5": 768,
    "mixedbread-ai/mxbai-embed-large-v1": 1024,
    "jinaai/jina-embeddings-v2-base-code": 768,
    "Qwen/Qwen3-Embedding-0.6B": 1024,
    "Qwen/Qwen3-Embedding-4B": 2560,
    "Qwen/Qwen3-Embedding-8B": 4096,
    "voyage-code-3": 1024,
    "text-embedding-3-large": 3072,  # OpenAI API model
    "text-embedding-3-small": 1536,  # OpenAI API model
}


def resolve_embedding_dim(model_name: str) -> int:
    """Return expected embedding dimension for a model. Falls back to 384."""
    return EMBEDDING_MODEL_REGISTRY.get(model_name, 384)


# When VOYAGE_API_KEY is set, default to voyage-code-3 for everything (single model, no dual-index).
# Override via HOLUSIGHT_EMBEDDING_MODEL / HOLUSIGHT_EMBEDDING_BACKEND env vars.
#
# Local cold-index default is Qwen3-Embedding-0.6B. The 8B model is still
# available and remains an explicit opt-in via HOLUSIGHT_EMBEDDING_MODEL.
# This keeps the local-first default usable on laptops where loading 8B into
# MPS can exhaust memory before the frozen retrieval evaluation completes.
# LocalEmbedder applies Qwen's query/document asymmetric prompting
# automatically. Operators with sufficient memory can opt into 4B or 8B via
# HOLUSIGHT_EMBEDDING_MODEL; explicit model configuration is authoritative.
def _resolve_default_embedding_model() -> str:
    """Fresh per-call resolution, unlike the DEFAULT_EMBEDDING_MODEL
    constant below (frozen at import time, kept only for other modules'
    direct imports). ServerConfig.embedding_model uses this via
    default_factory so a later os.environ mutation -- a test's
    monkeypatch.setenv, or any code setting the var after config.py was
    first imported -- actually takes effect, the same class of bug
    repo_data_dir() had for HOLUSIGHT_DATA_DIR."""
    return os.environ.get(
        "HOLUSIGHT_EMBEDDING_MODEL",
        "voyage-code-3" if os.environ.get("VOYAGE_API_KEY") else "Qwen/Qwen3-Embedding-0.6B",
    )


def _resolve_default_embedding_backend() -> str:
    """See _resolve_default_embedding_model -- same fresh-read rationale."""
    return os.environ.get(
        "HOLUSIGHT_EMBEDDING_BACKEND",
        "voyage" if os.environ.get("VOYAGE_API_KEY") else "local",
    )


def _resolve_default_embedding_dim() -> int:
    return resolve_embedding_dim(_resolve_default_embedding_model())


DEFAULT_EMBEDDING_MODEL = _resolve_default_embedding_model()
DEFAULT_EMBEDDING_BACKEND = _resolve_default_embedding_backend()
DEFAULT_EMBEDDING_DIM = resolve_embedding_dim(DEFAULT_EMBEDDING_MODEL)
DEFAULT_TOP_K = 8
DEFAULT_CHUNK_MAX_LINES = 200
DEFAULT_CHUNK_OVERLAP_LINES = 50
DEFAULT_DOC_CHUNK_MAX_CHARS = 1500
DEFAULT_DOC_CHUNK_OVERLAP_CHARS = 200
STALE_THRESHOLD_SECONDS = int(os.environ.get("HOLUSIGHT_STALE_SECONDS", "300"))  # 5 minutes
BM25_CANDIDATE_MULTIPLIER = 3  # fetch 3x top_k from each retriever before RRF

DEFAULT_LLM_MODEL = "claude-sonnet-4-20250514"

# Reranker
# Default to enabled only when Voyage API key is set (voyage rerank-2 helps code retrieval;
# local ms-marco cross-encoder is trained on MS-MARCO QA and can hurt code search ranking).
# Users with VOYAGE_API_KEY get always-on reranking. Local users can opt in
# via HOLUSIGHT_RERANKER=true.
_default_reranker_on = "true" if os.environ.get("VOYAGE_API_KEY") else "false"
DEFAULT_RERANKER_ENABLED = (
    os.environ.get("HOLUSIGHT_RERANKER", _default_reranker_on).lower() == "true"
)
# Auto-select backend: voyage when VOYAGE_API_KEY is set, local cross-encoder otherwise
DEFAULT_RERANKER_BACKEND = os.environ.get(
    "HOLUSIGHT_RERANKER_BACKEND",
    "voyage" if os.environ.get("VOYAGE_API_KEY") else "local"
)
DEFAULT_RERANKER_MODEL = os.environ.get(
    "HOLUSIGHT_RERANKER_MODEL",
    "rerank-2" if os.environ.get("VOYAGE_API_KEY") else "cross-encoder/ms-marco-MiniLM-L-6-v2",
)
DEFAULT_RERANKER_TOP_N = int(os.environ.get("HOLUSIGHT_RERANKER_TOP_N", "20"))
DEFAULT_QUERY_ENHANCEMENT = os.environ.get("HOLUSIGHT_QUERY_ENHANCEMENT", "false").lower() == "true"
DEFAULT_LLM_BACKEND = os.environ.get("HOLUSIGHT_LLM_BACKEND", "claude")
DEFAULT_CNFB_ALPHA = float(os.environ.get("HOLUSIGHT_CNFB_ALPHA", "0.0"))


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

CODE_EMBEDDING_EXTENSIONS: set[str] = {
    ".py", ".ts", ".js", ".tsx", ".jsx",
    ".go", ".rs", ".java", ".kt", ".scala",
    ".c", ".cpp", ".h", ".swift",
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

# SEC-007: the per-file limit above bounds one file; without an aggregate
# budget, a folder with an unbounded number of allowed files (or an
# unbounded total size) can consume excessive CPU, RAM, provider quota, or
# indexing time with no ceiling at all.
MAX_INDEXED_FILES = 50_000
MAX_TOTAL_INDEXED_BYTES = 2_000_000_000  # 2 GB aggregate across one index run


class IndexBudgetExceeded(ValueError):
    """Raised when a folder exceeds the aggregate indexing budget.

    Deliberately raised, not silently truncated: walk_repo_files()'s
    incremental-refresh caller treats any file absent from a returned
    listing as a candidate removal from the index. A silently truncated
    listing would make every file past the cutoff look deleted."""


class ServerConfig(BaseModel):
    """Runtime configuration."""

    # default_factory, not default=DEFAULT_EMBEDDING_MODEL: a bare default
    # value is bound once at class-definition time, so ServerConfig()
    # would keep resolving to whatever HOLUSIGHT_EMBEDDING_MODEL was set
    # to (or absent) the first time this module was imported, ignoring any
    # later os.environ change in the same process.
    embedding_model: str = Field(default_factory=_resolve_default_embedding_model)
    embedding_backend: str = Field(default_factory=_resolve_default_embedding_backend)
    embedding_dim: int = Field(default_factory=_resolve_default_embedding_dim)
    top_k: int = Field(default=DEFAULT_TOP_K)
    chunk_max_lines: int = Field(default=DEFAULT_CHUNK_MAX_LINES)
    chunk_overlap_lines: int = Field(default=DEFAULT_CHUNK_OVERLAP_LINES)
    doc_chunk_max_chars: int = Field(default=DEFAULT_DOC_CHUNK_MAX_CHARS)
    doc_chunk_overlap_chars: int = Field(default=DEFAULT_DOC_CHUNK_OVERLAP_CHARS)
    stale_threshold_seconds: int = Field(default=STALE_THRESHOLD_SECONDS)
    llm_backend: str = Field(default=DEFAULT_LLM_BACKEND)
    llm_model: str = Field(default=DEFAULT_LLM_MODEL)
    reranker: bool = Field(default=DEFAULT_RERANKER_ENABLED)
    reranker_backend: str = Field(default=DEFAULT_RERANKER_BACKEND)
    reranker_model: str = Field(default=DEFAULT_RERANKER_MODEL)
    reranker_top_n: int = Field(default=DEFAULT_RERANKER_TOP_N)
    query_enhancement: bool = Field(default=DEFAULT_QUERY_ENHANCEMENT)
    metadata_boost: bool = Field(default=True)
    cnfb_alpha: float = Field(default=DEFAULT_CNFB_ALPHA)

    @field_validator("chunk_max_lines")
    @classmethod
    def validate_chunk_max_lines(cls, value: int) -> int:
        """Require a positive window so line chunking can advance."""
        if value <= 0:
            raise ValueError("chunk_max_lines must be greater than 0")
        return value

    @field_validator("chunk_overlap_lines")
    @classmethod
    def validate_chunk_overlap_lines(cls, value: int) -> int:
        """Reject negative overlap before indexing begins."""
        if value < 0:
            raise ValueError("chunk_overlap_lines must be greater than or equal to 0")
        return value

    @model_validator(mode="after")
    def validate_progressing_line_window(self) -> ServerConfig:
        """Ensure each line window advances instead of repeating or moving backward."""
        if self.chunk_overlap_lines >= self.chunk_max_lines:
            raise ValueError(
                "chunk_overlap_lines must be less than chunk_max_lines "
                f"(got {self.chunk_overlap_lines} >= {self.chunk_max_lines})"
            )
        return self

    @field_validator("cnfb_alpha")
    @classmethod
    def clamp_cnfb_alpha(cls, v: float) -> float:
        """Clamp CNFB alpha to [0.0, 2.0]. Logs a warning if clamping occurred."""
        import logging  # noqa: PLC0415 — local import to avoid circular at module load
        clamped = max(0.0, min(2.0, v))
        if clamped != v:
            logging.getLogger(__name__).warning(
                "HOLUSIGHT_CNFB_ALPHA=%s is outside [0.0, 2.0]; clamped to %s", v, clamped
            )
        return clamped
