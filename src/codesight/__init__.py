"""CodeSight — AI-powered document search engine.

Hybrid BM25 + vector retrieval with pluggable LLM answer synthesis.
"""

from .api import CodeSight
from .config import ServerConfig
from .types import Answer, Citation, IndexStats, RepoStatus, SearchResult

__all__ = [
    "CodeSight",
    "ServerConfig",
    "Answer",
    "Citation",
    "IndexStats",
    "RepoStatus",
    "SearchResult",
]
