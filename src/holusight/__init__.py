"""Holusight — AI-powered document search engine.

Hybrid BM25 + vector retrieval with pluggable LLM answer synthesis.
"""

from .api import Holusight
from .config import ServerConfig
from .types import Answer, IndexStats, RepoStatus, SearchResult

__all__ = [
    "Holusight",
    "ServerConfig",
    "Answer",
    "IndexStats",
    "RepoStatus",
    "SearchResult",
]
