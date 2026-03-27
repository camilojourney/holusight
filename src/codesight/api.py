"""Public Python API for CodeSight.

This is the single entry point for Streamlit, Slack, CLI, and any future interface.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from .config import ServerConfig
from .embeddings import get_embedder
from .indexer import index_repo
from .llm import SYSTEM_PROMPT, LLMBackend, get_backend
from .search import hybrid_search
from .store import ChunkStore
from .types import Answer, IndexStats, RepoStatus, SearchResult

logger = logging.getLogger(__name__)


class CodeSight:
    """AI-powered document search engine.

    Usage:
        engine = CodeSight("/path/to/documents")
        engine.index()
        results = engine.search("payment terms")
        answer = engine.ask("What are the payment terms in the contract?")
    """

    def __init__(
        self,
        folder_path: str | Path,
        config: ServerConfig | None = None,
    ) -> None:
        self.folder_path = Path(folder_path).expanduser().resolve()
        if not self.folder_path.is_dir():
            raise ValueError(f"Not a directory: {self.folder_path}")

        self.config = config or ServerConfig()
        self._store: ChunkStore | None = None
        self._embedder = None
        self._llm: LLMBackend | None = None

    @property
    def store(self) -> ChunkStore:
        if self._store is None:
            self._store = ChunkStore(self.folder_path, embedding_dim=self.config.embedding_dim)
        return self._store

    @property
    def embedder(self):
        if self._embedder is None:
            self._embedder = get_embedder(
                self.config.embedding_model,
                self.config.embedding_dim,
                backend=self.config.embedding_backend,
            )
        return self._embedder

    @property
    def llm(self) -> LLMBackend:
        """Lazy-loaded LLM backend. Only initialized when ask() is called."""
        if self._llm is None:
            self._llm = get_backend(self.config.llm_backend, model=self.config.llm_model)
        return self._llm

    def index(
        self, force_rebuild: bool = False, progress_callback: callable | None = None,
    ) -> IndexStats:
        """Index all documents in the folder.

        Handles code files, text files, PDFs, DOCX, and PPTX.
        Unchanged files are skipped (content hash dedup).

        Args:
            force_rebuild: If True, delete existing index and rebuild from scratch.
            progress_callback: Optional callable(current, total, file_path) for progress updates.
        """
        stats = index_repo(
            self.folder_path, self.config,
            force_rebuild=force_rebuild, progress_callback=progress_callback,
        )
        # Reset store to pick up new data
        self._store = None
        return stats

    def search(
        self, query: str, top_k: int = 8, file_glob: str | None = None,
    ) -> list[SearchResult]:
        """Hybrid BM25 + vector search. Auto-indexes if needed."""
        self._ensure_indexed()
        return hybrid_search(
            self.store, self.embedder, query,
            top_k=top_k, file_glob=file_glob,
            config=self.config,
        )

    def ask(self, question: str, top_k: int = 5, file_glob: str | None = None) -> Answer:
        """Ask a question — search + LLM answer synthesis.

        Retrieves the top matching chunks, sends them as context to the
        configured LLM backend, and returns a natural language answer
        with source citations.

        Backend is selected via CODESIGHT_LLM_BACKEND env var (default: claude).
        """
        results = self.search(question, top_k=top_k, file_glob=file_glob)

        if not results:
            return Answer(
                text="No relevant documents found. Try indexing first.",
                sources=[],
                model=self.llm.model_id,
            )

        # Build context from search results
        context_parts = []
        for i, r in enumerate(results, 1):
            context_parts.append(
                f"[Source {i}: {r.file_path}, {r.scope}]\n{r.snippet}"
            )
        context = "\n\n---\n\n".join(context_parts)

        user_prompt = (
            f"Based on the following documents, answer this question:\n\n"
            f"**Question:** {question}\n\n"
            f"**Documents:**\n\n{context}"
        )

        answer_text = self.llm.generate(SYSTEM_PROMPT, user_prompt)

        return Answer(
            text=answer_text,
            sources=results,
            model=self.llm.model_id,
        )

    def status(self) -> RepoStatus:
        """Check index status for this folder."""
        return RepoStatus(
            repo_path=str(self.folder_path),
            indexed=self.store.is_indexed,
            chunk_count=self.store.chunk_count,
            files_indexed=self.store.file_count,
            last_commit=self.store.last_commit,
            last_indexed_at=self.store.last_indexed_at,
            stale=self._is_stale() if self.store.is_indexed else False,
        )

    def _ensure_indexed(self) -> None:
        """Auto-index if not indexed, auto-refresh if stale, rebuild on model mismatch."""
        if not self.store.is_indexed:
            logger.info("No index found for %s — building now...", self.folder_path)
            self.index()
        elif self._embedding_model_changed():
            stored = self.store.fts.get_meta("embedding_model") or "unknown"
            logger.warning(
                "Embedding model changed (%s → %s). Forcing full rebuild.",
                stored, self.config.embedding_model,
            )
            self.index(force_rebuild=True)
        elif self._is_stale():
            logger.info("Index is stale for %s — refreshing...", self.folder_path)
            self.index()

    def _embedding_model_changed(self) -> bool:
        """Check if the configured embedding model differs from the indexed one."""
        stored_model = self.store.fts.get_meta("embedding_model")
        if stored_model is None:
            return False  # legacy index without model tracking — don't force rebuild
        return stored_model != self.config.embedding_model

    def _is_stale(self) -> bool:
        """Check if the index is older than the staleness threshold."""
        ts = self.store.last_indexed_at
        if not ts:
            return True
        try:
            indexed_at = datetime.fromisoformat(ts)
            age = (datetime.now(timezone.utc) - indexed_at).total_seconds()
            return age > self.config.stale_threshold_seconds
        except Exception:
            return True


