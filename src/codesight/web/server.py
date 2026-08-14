"""FastAPI production server for single-team CodeSight deployments.

Serves a minimal browser UI plus JSON API for search, ask, index, and status.
Authentication is required in production-shaped runs (Docker / ``codesight serve``).
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from codesight.api import CodeSight
from codesight.config import ServerConfig
from codesight.types import Answer, IndexStats, RepoStatus, SearchResult

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def documents_dir() -> Path:
    """Folder mounted read-only for indexing (default /data in Docker)."""
    raw = os.environ.get("CODESIGHT_DOCUMENTS_DIR", "/data")
    return Path(raw).expanduser().resolve()


def api_key() -> str | None:
    return os.environ.get("CODESIGHT_API_KEY")


def require_auth() -> bool:
    """Production-shaped deployments must authenticate API calls."""
    # Explicit dev escape hatch only — never the default in Docker.
    if _env_bool("CODESIGHT_ALLOW_UNAUTHENTICATED", False):
        return False
    # Server / Docker entrypoints set CODESIGHT_PRODUCTION=1
    if _env_bool("CODESIGHT_PRODUCTION", False):
        return True
    # If an API key is configured, enforce it even outside production flag.
    return bool(api_key())


def validate_startup() -> None:
    docs = documents_dir()
    if not docs.is_dir():
        raise RuntimeError(
            f"Documents directory not found: {docs}. "
            "Mount your documents read-only, e.g. -v /path/to/docs:/data:ro "
            "and set CODESIGHT_DOCUMENTS_DIR=/data"
        )
    if require_auth() and not api_key():
        raise RuntimeError(
            "CODESIGHT_API_KEY is required for production deployments. "
            "Set CODESIGHT_API_KEY to a secret value, or for local dev only "
            "set CODESIGHT_ALLOW_UNAUTHENTICATED=true"
        )


# ---------------------------------------------------------------------------
# Engine + indexing lock (single-flight index)
# ---------------------------------------------------------------------------

_engine: CodeSight | None = None
_index_lock = threading.Lock()
_index_operation_lock = threading.Lock()
_index_in_progress = False


def get_engine() -> CodeSight:
    global _engine
    if _engine is None:
        _engine = CodeSight(documents_dir(), config=ServerConfig())
    return _engine


def _run_index(force_rebuild: bool = False) -> IndexStats:
    global _index_in_progress
    if not _index_operation_lock.acquire(blocking=False):
        raise IndexInProgressError()
    with _index_lock:
        if _index_in_progress:
            _index_operation_lock.release()
            raise IndexInProgressError()
        _index_in_progress = True
    try:
        return get_engine().index(force_rebuild=force_rebuild)
    finally:
        with _index_lock:
            _index_in_progress = False
        _index_operation_lock.release()


class IndexInProgressError(Exception):
    """Raised when a second index request arrives while indexing runs."""


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def _extract_key(request: Request) -> str | None:
    header = request.headers.get("X-API-Key")
    if header:
        return header.strip()
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


async def verify_api_key(request: Request) -> None:
    if not require_auth():
        logger.warning(
            "API authentication disabled — set CODESIGHT_API_KEY for production"
        )
        return
    expected = api_key()
    if not expected:
        raise HTTPException(status_code=503, detail="Server auth not configured")
    provided = _extract_key(request)
    if provided != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=8, ge=1, le=50)
    file_glob: str | None = None


class AskRequest(BaseModel):
    question: str
    top_k: int = Field(default=5, ge=1, le=20)
    file_glob: str | None = None


class IndexRequest(BaseModel):
    force_rebuild: bool = False


class HealthResponse(BaseModel):
    status: str
    documents_dir: str
    auth_required: bool
    indexed: bool
    llm_backend: str


class PublicConfigResponse(BaseModel):
    auth_required: bool
    llm_backend: str
    search_local: bool = True
    ask_requires_llm: bool = True


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_startup()
    docs = documents_dir()
    logger.info("CodeSight server starting — documents=%s auth=%s", docs, require_auth())
    yield
    logger.info("CodeSight server shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="CodeSight",
        description="Hybrid BM25 + vector document search with source citations",
        version="0.3.0",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        import time

        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        if request.url.path.startswith("/api/"):
            logger.info(
                "%s %s -> %s (%.1fms)",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
        return response

    # ----- Public config (no auth — UI needs to know if login is required) -----

    @app.get("/api/config", response_model=PublicConfigResponse)
    async def public_config() -> PublicConfigResponse:
        cfg = ServerConfig()
        return PublicConfigResponse(
            auth_required=require_auth(),
            llm_backend=cfg.llm_backend,
        )

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        engine = get_engine()
        st = engine.status()
        cfg = ServerConfig()
        return HealthResponse(
            status="ok",
            documents_dir=str(documents_dir()),
            auth_required=require_auth(),
            indexed=st.indexed,
            llm_backend=cfg.llm_backend,
        )

    # ----- Protected API -----

    @app.get("/api/status", response_model=RepoStatus, dependencies=[Depends(verify_api_key)])
    async def status() -> RepoStatus:
        return get_engine().status()

    @app.post("/api/search", dependencies=[Depends(verify_api_key)])
    async def search(body: SearchRequest) -> dict[str, Any]:
        if not body.query.strip():
            raise HTTPException(status_code=400, detail="Query cannot be empty")
        with _index_operation_lock:
            results: list[SearchResult] = get_engine().search(
                body.query.strip(),
                top_k=body.top_k,
                file_glob=body.file_glob,
            )
        return {"results": [r.model_dump() for r in results]}

    @app.post("/api/ask", dependencies=[Depends(verify_api_key)])
    async def ask(body: AskRequest) -> dict[str, Any]:
        if not body.question.strip():
            raise HTTPException(status_code=400, detail="Question cannot be empty")
        try:
            answer: Answer = get_engine().ask(
                body.question.strip(),
                top_k=body.top_k,
                file_glob=body.file_glob,
            )
        except ValueError as exc:
            if "API_KEY" in str(exc) or "environment variable is required" in str(exc):
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "LLM backend unavailable",
                        "message": str(exc),
                        "hint": (
                            "Search works without an LLM. Configure CODESIGHT_LLM_BACKEND "
                            "and the provider API key for ask(), or use Ollama locally."
                        ),
                    },
                ) from exc
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("ask() failed")
            raise HTTPException(status_code=503, detail=f"LLM request failed: {exc}") from exc

        return {
            "text": answer.text,
            "sources": [s.model_dump() for s in answer.sources],
            "model": answer.model,
            "synthesis": "llm",
        }

    @app.post("/api/index", dependencies=[Depends(verify_api_key)])
    async def index_documents(body: IndexRequest) -> dict[str, Any]:
        try:
            stats = await asyncio.to_thread(_run_index, body.force_rebuild)
        except IndexInProgressError:
            raise HTTPException(status_code=409, detail="Indexing already in progress")
        return {
            "total_files": stats.files_indexed,
            "total_chunks": stats.total_chunks,
            "duration_seconds": stats.elapsed_seconds,
            "chunks_created": stats.chunks_created,
        }

    # ----- Static UI -----

    @app.get("/")
    async def index_page():
        index_html = STATIC_DIR / "index.html"
        if not index_html.is_file():
            raise HTTPException(status_code=500, detail="UI assets missing")
        return FileResponse(index_html)

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app


app = create_app()
