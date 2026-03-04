"""Pydantic models for engine inputs and outputs."""

from __future__ import annotations

from pydantic import BaseModel


class ChunkRecord(BaseModel):
    """A single chunk stored in the index."""

    chunk_id: str
    repo_path: str
    file_path: str  # relative to folder root
    start_line: int  # line number for code, page number for documents
    end_line: int
    scope: str  # e.g. "function foo" or "page 3" or "section Introduction"
    content: str
    content_hash: str
    language: str  # e.g. "python", "pdf", "docx"


class SearchResult(BaseModel):
    """A single search result."""

    file_path: str
    start_line: int
    end_line: int
    snippet: str
    score: float
    scope: str
    chunk_id: str


class Citation(BaseModel):
    """Claim-level citation attached to an answer."""

    chunk_id: str
    cited_text: str
    claim: str


class IndexStats(BaseModel):
    """Summary returned after indexing."""

    repo_path: str
    files_indexed: int
    chunks_created: int
    chunks_skipped_unchanged: int = 0
    chunks_deleted: int = 0
    total_chunks: int
    elapsed_seconds: float


class RepoStatus(BaseModel):
    """Status info for an indexed folder."""

    repo_path: str
    indexed: bool
    chunk_count: int = 0
    files_indexed: int = 0
    last_commit: str | None = None
    last_indexed_at: str | None = None
    stale: bool = False


class Answer(BaseModel):
    """LLM-generated answer with source citations."""

    text: str
    sources: list[SearchResult]
    model: str
    # SPEC-010-005: Verification fields are additive and backward-compatible.
    grounding_score: float | None = None
    citations: list[Citation] = []
    confidence_level: str = "high"
    retries: int = 0
