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
from .verify import (
    REFUSAL_TEXT,
    GroundingScorer,
    VerificationConfig,
    confidence_decision,
    rewrite_query,
)

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
        self._verifier: GroundingScorer | None = None

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

    @property
    def verifier(self) -> GroundingScorer:
        if self._verifier is None:
            self._verifier = GroundingScorer()
        return self._verifier

    def index(self, force_rebuild: bool = False) -> IndexStats:
        """Index all documents in the folder.

        Handles code files, text files, PDFs, DOCX, and PPTX.
        Unchanged files are skipped (content hash dedup).
        """
        stats = index_repo(self.folder_path, self.config, force_rebuild=force_rebuild)
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
        verify_cfg = VerificationConfig(
            verify_enabled=self.config.verify,
            high_threshold_claude=self.config.verify_high_claude,
            high_threshold_other=self.config.verify_high_other,
            low_threshold=self.config.verify_low,
            max_retries=self.config.verify_max_retries,
            timeout_seconds=self.config.verify_timeout_seconds,
            short_text_chars=self.config.verify_short_text_chars,
        )

        retries = 0
        current_question = question

        while True:
            results = self.search(current_question, top_k=top_k, file_glob=file_glob)
            if not results:
                # EDGE-010-006: Empty retrieved context skips verification.
                return Answer(
                    text="No relevant documents found. Try indexing first.",
                    sources=[],
                    model=self.llm.model_id,
                    grounding_score=None,
                    citations=[],
                    confidence_level="low",
                    retries=retries,
                )

            context = self._build_context(results)
            user_prompt = (
                "Based on the following documents, answer this question:\n\n"
                f"**Question:** {current_question}\n\n"
                f"**Documents:**\n\n{context}"
            )

            llm_response = self.llm.generate_with_citations(
                SYSTEM_PROMPT,
                user_prompt,
                sources=results,
            )
            answer_text = llm_response.text
            citations = llm_response.citations

            # SPEC-010-006: Verification can be disabled globally via config/env.
            if not verify_cfg.verify_enabled:
                return Answer(
                    text=answer_text,
                    sources=results,
                    model=self.llm.model_id,
                    grounding_score=None,
                    citations=[],
                    confidence_level="high",
                    retries=retries,
                )

            # SPEC-010-001: Grounding score is computed for verified ask() responses.
            grounding_score = self.verifier.score(
                answer_text,
                results,
                timeout_seconds=verify_cfg.timeout_seconds,
                short_text_chars=verify_cfg.short_text_chars,
            )

            decision, confidence_level = confidence_decision(
                grounding_score=grounding_score,
                citations=citations,
                answer_text=answer_text,
                is_claude_backend=self.config.llm_backend == "claude",
                config=verify_cfg,
            )

            if decision == "pass":
                if confidence_level in ("low", "medium"):
                    answer_text = (
                        f"{answer_text}\n\n"
                        "[Low confidence: verify against cited sources "
                        "before relying on this answer.]"
                    )
                return Answer(
                    text=answer_text,
                    sources=results,
                    model=self.llm.model_id,
                    grounding_score=grounding_score,
                    citations=citations,
                    confidence_level=confidence_level,
                    retries=retries,
                )

            # SPEC-010-003: Retry low-confidence responses with bounded attempts.
            if decision == "retry" and retries < verify_cfg.max_retries:
                retries += 1
                current_question = rewrite_query(
                    self.llm,
                    original_question=question,
                    low_confidence_answer=answer_text,
                    sources=results,
                )
                continue

            # EDGE-010-003: Retries exhausted -> transparent refusal + raw sources.
            return Answer(
                text=REFUSAL_TEXT,
                sources=results,
                model=self.llm.model_id,
                grounding_score=grounding_score,
                citations=citations,
                confidence_level="refused",
                retries=retries,
            )

    def _build_context(self, results: list[SearchResult]) -> str:
        context_parts = []
        for idx, item in enumerate(results, 1):
            context_parts.append(f"[Source {idx}: {item.file_path}, {item.scope}]\n{item.snippet}")
        return "\n\n---\n\n".join(context_parts)

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
