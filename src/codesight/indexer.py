"""Indexing pipeline: walks files, chunks them, embeds, and stores.

Handles code files (UTF-8 text) and binary documents (PDF, DOCX, PPTX).
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import pathspec

from .chunker import Chunk, chunk_document, chunk_file
from .config import (
    ALWAYS_SKIP_DIRS,
    ALWAYS_SKIP_FILES,
    INDEXABLE_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
    ServerConfig,
)
from .embeddings import Embedder, get_embedder
from .git_utils import current_commit, is_git_repo
from .parsers import extract_text, is_document
from .store import ChunkStore
from .types import IndexStats

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# File walking
# ---------------------------------------------------------------------------


def _load_gitignore(repo_path: Path) -> pathspec.PathSpec | None:
    """Load .gitignore patterns if present."""
    gitignore_path = repo_path / ".gitignore"
    if gitignore_path.exists():
        try:
            with open(gitignore_path, "r") as f:
                return pathspec.PathSpec.from_lines("gitwildmatch", f)
        except Exception:
            pass
    return None


def walk_repo_files(repo_path: str | Path) -> list[Path]:
    """Walk a directory, respecting .gitignore and skip lists.

    Returns absolute paths to indexable files (code + documents).
    """
    repo_path = Path(repo_path).resolve()
    gitignore = _load_gitignore(repo_path)
    files: list[Path] = []

    for dirpath, dirnames, filenames in os.walk(repo_path):
        # Filter out skipped directories IN PLACE (os.walk respects this)
        dirnames[:] = [
            d for d in dirnames
            if d not in ALWAYS_SKIP_DIRS
            and not d.startswith(".")
        ]

        rel_dir = Path(dirpath).relative_to(repo_path)

        # Check gitignore on directory
        if gitignore and gitignore.match_file(str(rel_dir) + "/"):
            dirnames.clear()
            continue

        for fname in filenames:
            # Skip hidden files and always-skip files
            if fname.startswith(".") or fname in ALWAYS_SKIP_FILES:
                continue

            fpath = Path(dirpath) / fname
            rel_path = fpath.relative_to(repo_path)

            # Check extension
            if fpath.suffix.lower() not in INDEXABLE_EXTENSIONS:
                continue

            # Check gitignore
            if gitignore and gitignore.match_file(str(rel_path)):
                continue

            # Check file size
            try:
                if fpath.stat().st_size > MAX_FILE_SIZE_BYTES:
                    continue
            except OSError:
                continue

            files.append(fpath)

    return files


# ---------------------------------------------------------------------------
# Indexing pipeline
# ---------------------------------------------------------------------------


def _log_progress(current: int, total: int, message: str) -> None:
    """Print progress feedback to stderr for CLI users."""
    import sys
    if total > 0:
        pct = (current / total) * 100
        bar_len = 30
        filled = int(bar_len * current // total)
        bar = "=" * filled + "-" * (bar_len - filled)
        msg = f"\r  [{bar}] {pct:5.1f}% ({current}/{total}) {message[:50]:<50}"
        print(msg, end="", file=sys.stderr, flush=True)
        if current == total:
            print(file=sys.stderr)  # newline at completion


def index_repo(
    repo_path: str | Path,
    config: ServerConfig | None = None,
    force_rebuild: bool = False,
    progress_callback: callable | None = None,
) -> IndexStats:
    """Full or incremental index of a folder.

    Handles both code files and binary documents (PDF, DOCX, PPTX).
    If force_rebuild is True, deletes existing index first.
    """
    start_time = time.time()
    config = config or ServerConfig()
    repo_path = Path(repo_path).resolve()

    if not repo_path.is_dir():
        raise ValueError(f"Not a directory: {repo_path}")

    embedder = get_embedder(
        config.embedding_model, config.embedding_dim,
        backend=config.embedding_backend,
    )
    store = ChunkStore(repo_path, embedding_dim=config.embedding_dim)

    # Store canonical path
    store.repo_canonical_path = str(repo_path)

    if force_rebuild and store.is_indexed:
        logger.info("Force rebuild: clearing existing index for %s", repo_path)

    # Walk all indexable files
    files = walk_repo_files(repo_path)
    logger.info("Found %d indexable files in %s", len(files), repo_path)

    total_chunks_created = 0
    total_chunks_skipped = 0
    total_files_indexed = 0

    # Process files in batches for embedding efficiency
    batch_chunks: list[Chunk] = []
    BATCH_SIZE = 64

    total_files = len(files)
    _log_progress(0, total_files, "Starting indexing...")

    for file_idx, fpath in enumerate(files, 1):
        rel_path = str(fpath.relative_to(repo_path))

        # Route: binary documents vs text files
        if is_document(fpath):
            chunks = _chunk_document_file(fpath, rel_path, config)
        else:
            chunks = _chunk_text_file(fpath, rel_path, config)

        if not chunks:
            continue

        # Get existing chunk hashes for this file
        existing_hashes = store.fts.get_chunk_hashes(rel_path)

        total_files_indexed += 1

        # Progress feedback every 10 files or at completion
        if file_idx % 10 == 0 or file_idx == total_files:
            _log_progress(file_idx, total_files, f"Processing: {rel_path}")
            if progress_callback is not None:
                progress_callback(file_idx, total_files, rel_path)

        # Determine which chunks need (re-)embedding
        new_chunk_ids = {c.chunk_id for c in chunks}
        old_chunk_ids = set(existing_hashes.keys())

        # If the file changed, remove all old chunks for it
        if new_chunk_ids != old_chunk_ids:
            store.delete_file_chunks(rel_path)

        for chunk in chunks:
            if chunk.content_hash in existing_hashes.values() and not force_rebuild:
                total_chunks_skipped += 1
                continue
            batch_chunks.append(chunk)

        # Flush batch when large enough
        if len(batch_chunks) >= BATCH_SIZE:
            _embed_and_store_batch(batch_chunks, embedder, store)
            total_chunks_created += len(batch_chunks)
            batch_chunks = []

    # Flush remaining
    if batch_chunks:
        _embed_and_store_batch(batch_chunks, embedder, store)
        total_chunks_created += len(batch_chunks)

    # Update metadata
    commit = current_commit(repo_path) if is_git_repo(repo_path) else None
    if commit:
        store.last_commit = commit
    store.touch_indexed()
    store.fts.set_meta("embedding_model", config.embedding_model)

    elapsed = time.time() - start_time
    logger.info(
        "Indexed %s: %d files, %d chunks created, %d skipped in %.1fs",
        repo_path, total_files_indexed, total_chunks_created, total_chunks_skipped, elapsed,
    )

    return IndexStats(
        repo_path=str(repo_path),
        files_indexed=total_files_indexed,
        chunks_created=total_chunks_created,
        chunks_skipped_unchanged=total_chunks_skipped,
        total_chunks=store.chunk_count,
        elapsed_seconds=round(elapsed, 2),
    )


def _chunk_text_file(fpath: Path, rel_path: str, config: ServerConfig) -> list[Chunk]:
    """Read and chunk a text-based file (code, markdown, etc.)."""
    try:
        content = fpath.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        logger.warning("Could not read %s: %s", fpath, e)
        return []

    if not content.strip():
        return []

    return chunk_file(
        content,
        file_path=rel_path,
        max_lines=config.chunk_max_lines,
        overlap_lines=config.chunk_overlap_lines,
    )


def _chunk_document_file(fpath: Path, rel_path: str, config: ServerConfig) -> list[Chunk]:
    """Parse and chunk a binary document (PDF, DOCX, PPTX)."""
    try:
        pages = extract_text(fpath)
    except Exception as e:
        logger.warning("Could not parse document %s: %s", fpath, e)
        return []

    if not pages:
        return []

    return chunk_document(
        pages,
        file_path=rel_path,
        max_chars=config.doc_chunk_max_chars,
        overlap_chars=config.doc_chunk_overlap_chars,
    )


def _embed_and_store_batch(chunks: list[Chunk], embedder: Embedder, store: ChunkStore) -> None:
    """Embed a batch of chunks and store them."""
    texts = [c.embedding_text for c in chunks]
    vectors = embedder.embed(texts)

    chunk_ids = [c.chunk_id for c in chunks]
    metadatas = [
        {
            "file_path": c.file_path,
            "start_line": c.start_line,
            "end_line": c.end_line,
            "scope": c.scope,
            "language": c.language,
            "content_hash": c.content_hash,
            "content": c.content,
        }
        for c in chunks
    ]

    store.upsert_chunks(chunk_ids, vectors, metadatas)
