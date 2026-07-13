"""Language-aware code chunking + document chunking.

Code: tree-sitter AST-based splitting (preferred) → regex boundary fallback → sliding window.
Documents: paragraph-aware splitting with page metadata.
Both get context headers prepended to improve embedding quality.

AST chunking (cAST approach, EMNLP 2025): extract top-level function/class nodes,
merge small siblings (< min_lines), sub-split oversized nodes with windows.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import (
    DEFAULT_CHUNK_MAX_LINES,
    DEFAULT_CHUNK_OVERLAP_LINES,
    DEFAULT_DOC_CHUNK_MAX_CHARS,
    DEFAULT_DOC_CHUNK_OVERLAP_CHARS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Language-specific boundary patterns
# ---------------------------------------------------------------------------

# Each pattern matches the START of a new top-level scope
_BOUNDARY_PATTERNS: dict[str, re.Pattern] = {
    "python": re.compile(r"^(class |def |async def )", re.MULTILINE),
    "javascript": re.compile(
        r"^(export\s+)?(function |class |const \w+ = |let \w+ = |var \w+ = )", re.MULTILINE
    ),
    "typescript": re.compile(
        r"^(export\s+)?(function |class |const \w+ = |let \w+ = |interface |type |enum )",
        re.MULTILINE,
    ),
    "go": re.compile(r"^(func |type )", re.MULTILINE),
    "rust": re.compile(r"^(pub\s+)?(fn |struct |enum |impl |trait |mod )", re.MULTILINE),
    "java": re.compile(
        r"^(public |private |protected )?(static )?(class |interface |enum |void |int |String )",
        re.MULTILINE,
    ),
    "ruby": re.compile(r"^(class |module |def )", re.MULTILINE),
    "php": re.compile(r"^(class |function |public |private |protected )", re.MULTILINE),
    "c": re.compile(r"^(\w+\s+\*?\w+\s*\()", re.MULTILINE),
    "cpp": re.compile(r"^(class |struct |namespace |template |(\w+\s+\*?\w+\s*\())", re.MULTILINE),
}

# Map file extension to language key
_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "java",
    ".scala": "java",
    ".rb": "ruby",
    ".rake": "ruby",
    ".php": "php",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".cs": "java",  # close enough for boundary detection
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Chunk:
    """A single chunk of content with metadata."""

    file_path: str  # relative to folder root
    start_line: int  # 1-indexed (line number for code, page number for docs)
    end_line: int  # 1-indexed, inclusive
    content: str  # raw text
    scope: str  # e.g. "function validate_token" or "page 3" or "section Introduction"
    language: str  # e.g. "python", "pdf", "docx"
    context_header: str  # prepended before embedding
    content_hash: str = field(init=False)

    def __post_init__(self):
        self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()[:16]

    @property
    def embedding_text(self) -> str:
        """Text sent to the embedding model (context header + content)."""
        return f"{self.context_header}\n{self.content}"

    @property
    def chunk_id(self) -> str:
        """Unique ID: file + line range + hash."""
        return f"{self.file_path}:{self.start_line}-{self.end_line}:{self.content_hash}"


# ---------------------------------------------------------------------------
# Scope detection helpers
# ---------------------------------------------------------------------------


def _detect_scope(first_line: str, language: str) -> str:
    """Extract a human-readable scope label from the first line of a chunk."""
    first_line = first_line.strip()
    if not first_line:
        return "module-level"

    # Python: "def foo(...)" -> "function foo"
    if language == "python":
        m = re.match(r"(async\s+)?def\s+(\w+)", first_line)
        if m:
            return f"function {m.group(2)}"
        m = re.match(r"class\s+(\w+)", first_line)
        if m:
            return f"class {m.group(1)}"

    # JS/TS
    if language in ("javascript", "typescript"):
        m = re.match(r"(?:export\s+)?function\s+(\w+)", first_line)
        if m:
            return f"function {m.group(1)}"
        m = re.match(r"(?:export\s+)?class\s+(\w+)", first_line)
        if m:
            return f"class {m.group(1)}"
        m = re.match(r"(?:export\s+)?(?:const|let|var)\s+(\w+)", first_line)
        if m:
            return f"const {m.group(1)}"

    # Go
    if language == "go":
        m = re.match(r"func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)", first_line)
        if m:
            return f"function {m.group(1)}"
        m = re.match(r"type\s+(\w+)", first_line)
        if m:
            return f"type {m.group(1)}"

    # Rust
    if language == "rust":
        m = re.match(r"(?:pub\s+)?fn\s+(\w+)", first_line)
        if m:
            return f"function {m.group(1)}"
        m = re.match(r"(?:pub\s+)?struct\s+(\w+)", first_line)
        if m:
            return f"struct {m.group(1)}"
        m = re.match(r"(?:pub\s+)?impl\s+(\w+)", first_line)
        if m:
            return f"impl {m.group(1)}"

    # Fallback: use the first significant token
    tokens = first_line.split()
    if tokens:
        return tokens[0]
    return "unknown"


def _make_context_header(file_path: str, scope: str, start_line: int, end_line: int) -> str:
    """Build the context header prepended to chunks before embedding."""
    return f"# File: {file_path}\n# Scope: {scope}\n# Lines: {start_line}-{end_line}"


# ---------------------------------------------------------------------------
# Code chunking (existing)
# ---------------------------------------------------------------------------


def _detect_language(file_path: str) -> str:
    """Detect language from file extension."""
    ext = Path(file_path).suffix.lower()
    return _EXT_TO_LANG.get(ext, "unknown")


def chunk_file(
    content: str,
    file_path: str,
    max_lines: int = DEFAULT_CHUNK_MAX_LINES,
    overlap_lines: int = DEFAULT_CHUNK_OVERLAP_LINES,
) -> list[Chunk]:
    """Split a file's content into scope-delimited chunks.

    Strategy:
    1. If we have a language-specific boundary pattern, split on those boundaries.
    2. Each split becomes a chunk (unless it exceeds max_lines, in which case
       we sub-split with overlapping windows).
    3. If no pattern is available, fall back to overlapping windows.
    """
    if not content.strip():
        return []

    lines = content.split("\n")
    language = _detect_language(file_path)
    pattern = _BOUNDARY_PATTERNS.get(language)

    # Prefer AST-based chunking for supported languages — it gives cleaner
    # function/class boundaries and better recall in retrieval benchmarks.
    if language in _AST_SCOPE_TYPES:
        try:
            return chunk_file_ast(content, file_path, max_lines)
        except Exception:
            logger.debug(
                "AST chunking failed for %s (%s) — falling back to regex",
                file_path,
                language,
                exc_info=True,
            )

    if pattern:
        chunks = _split_by_boundaries(lines, file_path, language, pattern, max_lines, overlap_lines)
    else:
        chunks = _split_by_windows(lines, file_path, language, max_lines, overlap_lines)

    return chunks


def _split_by_boundaries(
    lines: list[str],
    file_path: str,
    language: str,
    pattern: re.Pattern,
    max_lines: int,
    overlap_lines: int,
) -> list[Chunk]:
    """Split on regex-detected scope boundaries."""
    # Find all boundary line indices
    boundary_indices = [0]  # always start at line 0
    for i, line in enumerate(lines):
        if i == 0:
            continue
        if pattern.match(line):
            boundary_indices.append(i)

    chunks: list[Chunk] = []
    for idx, start in enumerate(boundary_indices):
        end = boundary_indices[idx + 1] if idx + 1 < len(boundary_indices) else len(lines)
        segment_lines = lines[start:end]

        if len(segment_lines) <= max_lines:
            scope = _detect_scope(segment_lines[0] if segment_lines else "", language)
            header = _make_context_header(file_path, scope, start + 1, end)
            chunk_content = "\n".join(segment_lines)
            chunks.append(
                Chunk(
                    file_path=file_path,
                    start_line=start + 1,
                    end_line=end,
                    content=chunk_content,
                    scope=scope,
                    language=language,
                    context_header=header,
                )
            )
        else:
            # Sub-split large scopes with overlapping windows
            sub_chunks = _split_by_windows(
                segment_lines,
                file_path,
                language,
                max_lines,
                overlap_lines,
                line_offset=start,
            )
            chunks.extend(sub_chunks)

    return chunks


def _split_by_windows(
    lines: list[str],
    file_path: str,
    language: str,
    max_lines: int,
    overlap_lines: int,
    line_offset: int = 0,
) -> list[Chunk]:
    """Fall back to fixed-size overlapping windows."""
    chunks: list[Chunk] = []
    i = 0
    while i < len(lines):
        end = min(i + max_lines, len(lines))
        segment = lines[i:end]
        scope = _detect_scope(segment[0] if segment else "", language)
        start_line = line_offset + i + 1
        end_line = line_offset + end
        header = _make_context_header(file_path, scope, start_line, end_line)
        chunks.append(
            Chunk(
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                content="\n".join(segment),
                scope=scope,
                language=language,
                context_header=header,
            )
        )
        i += max_lines - overlap_lines
        if i >= len(lines):
            break

    return chunks


# ---------------------------------------------------------------------------
# AST-based chunking (tree-sitter — preferred over regex for Python/JS/TS)
# ---------------------------------------------------------------------------

# Top-level node types that define scope boundaries in each language.
_AST_SCOPE_TYPES: dict[str, frozenset[str]] = {
    "python": frozenset(
        {
            "function_definition",
            "async_function_definition",
            "class_definition",
            "decorated_definition",
        }
    ),
    "javascript": frozenset(
        {
            "function_declaration",
            "class_declaration",
            "export_statement",
            "lexical_declaration",  # const/let arrow functions at module level
            "variable_declaration",  # var arrow functions
        }
    ),
    "typescript": frozenset(
        {
            "function_declaration",
            "class_declaration",
            "export_statement",
            "lexical_declaration",
            "variable_declaration",
            "interface_declaration",
            "type_alias_declaration",
        }
    ),
}


def _get_ts_parser(language: str):
    """Return a tree-sitter (Parser, Language) pair for the given language.

    Raises ImportError if the tree-sitter packages are not installed.
    Raises ValueError if the language is not supported.
    """
    from tree_sitter import Language, Parser  # soft dependency

    if language == "python":
        import tree_sitter_python as tslang
    elif language in ("javascript", "typescript"):
        # tree-sitter-javascript handles both JS and TS well enough for chunking
        import tree_sitter_javascript as tslang
    else:
        raise ValueError(f"No tree-sitter grammar for language: {language!r}")

    ts_language = Language(tslang.language())
    parser = Parser(ts_language)
    return parser, ts_language


def _build_chunk_from_lines(
    lines: list[str],
    file_path: str,
    language: str,
    start_line_1idx: int,
) -> Chunk:
    """Build a Chunk from a list of lines with correct 1-based line numbers."""
    content = "\n".join(lines)
    scope = _detect_scope(lines[0] if lines else "", language)
    end_line_1idx = start_line_1idx + len(lines) - 1
    header = _make_context_header(file_path, scope, start_line_1idx, end_line_1idx)
    return Chunk(
        file_path=file_path,
        start_line=start_line_1idx,
        end_line=end_line_1idx,
        content=content,
        scope=scope,
        language=language,
        context_header=header,
    )


def chunk_file_ast(
    content: str,
    file_path: str,
    max_lines: int = DEFAULT_CHUNK_MAX_LINES,
    min_lines: int = 5,
) -> list[Chunk]:
    """Split a file using tree-sitter AST nodes (cAST approach).

    Algorithm:
    1. Parse the file and extract top-level scope nodes (functions, classes).
    2. Merge consecutive tiny nodes (< min_lines) with their next sibling so
       the reranker has enough context per chunk.
    3. Sub-split oversized nodes (> max_lines) using overlapping windows.
    4. Any leading/trailing code not covered by a scope node becomes its own chunk.

    Falls back to chunk_file() if tree-sitter is unavailable or parsing fails.
    """
    if not content.strip():
        return []

    language = _detect_language(file_path)
    if language not in _AST_SCOPE_TYPES:
        # Not a language we have AST support for — caller should use chunk_file()
        raise ValueError(f"AST chunking not supported for language: {language!r}")

    parser, _ = _get_ts_parser(language)
    all_lines = content.split("\n")

    tree = parser.parse(content.encode("utf-8", errors="replace"))
    root = tree.root_node

    scope_types = _AST_SCOPE_TYPES[language]

    # Collect (start_row, end_row) for each top-level scope node (0-indexed rows)
    raw_segments: list[tuple[int, int]] = []
    for child in root.children:
        if child.type in scope_types:
            raw_segments.append((child.start_point[0], child.end_point[0]))
        # Unwrap export_statement to check if it wraps a scoped declaration
        elif child.type == "export_statement":
            for sub in child.children:
                if sub.type in scope_types:
                    raw_segments.append((child.start_point[0], child.end_point[0]))
                    break

    if not raw_segments:
        # No top-level scope nodes found — fall back to window chunking
        return _split_by_windows(all_lines, file_path, language, max_lines, 0)

    # Sort by start line
    raw_segments.sort(key=lambda s: s[0])

    # --- Merge tiny consecutive segments ---
    merged: list[tuple[int, int]] = []
    i = 0
    while i < len(raw_segments):
        seg_start, seg_end = raw_segments[i]
        seg_lines = seg_end - seg_start + 1
        if seg_lines < min_lines and i + 1 < len(raw_segments):
            # Merge with next segment
            next_start, next_end = raw_segments[i + 1]
            merged.append((seg_start, next_end))
            i += 2  # skip both
        else:
            merged.append((seg_start, seg_end))
            i += 1

    # --- Build chunks, sub-splitting oversized segments ---
    chunks: list[Chunk] = []

    # Leading lines before first segment (e.g., imports, module docstring)
    first_seg_start = merged[0][0] if merged else len(all_lines)
    if first_seg_start > 0:
        leading = all_lines[:first_seg_start]
        if any(line.strip() for line in leading):
            chunks.extend(
                _split_by_windows(leading, file_path, language, max_lines, 0)
            )
            chunks.extend(_split_by_windows(leading, file_path, language, max_lines, 0))

    prev_end = first_seg_start
    for seg_start, seg_end in merged:
        # Gap between segments (e.g., module-level constants between functions)
        if seg_start > prev_end:
            gap = all_lines[prev_end:seg_start]
            if any(line.strip() for line in gap):
                chunks.extend(
                    _split_by_windows(gap, file_path, language, max_lines, 0, line_offset=prev_end)
                )

        seg_line_list = all_lines[seg_start : seg_end + 1]
        seg_len = len(seg_line_list)

        if seg_len <= max_lines:
            chunks.append(
                _build_chunk_from_lines(
                    seg_line_list,
                    file_path,
                    language,
                    seg_start + 1,
                )
            )
        else:
            # Sub-split oversized node with no overlap (function boundaries are complete)
            chunks.extend(
                _split_by_windows(
                    seg_line_list, file_path, language, max_lines, 0, line_offset=seg_start
                )
            )

        prev_end = seg_end + 1

    # Trailing lines after last segment
    if prev_end < len(all_lines):
        trailing = all_lines[prev_end:]
        if any(line.strip() for line in trailing):
            chunks.extend(
                _split_by_windows(trailing, file_path, language, max_lines, 0, line_offset=prev_end)
            )

    return chunks


# ---------------------------------------------------------------------------
# Document chunking (new)
# ---------------------------------------------------------------------------


def chunk_document(
    pages: list,  # list[DocumentPage] — import avoided for circular deps
    file_path: str,
    max_chars: int = DEFAULT_DOC_CHUNK_MAX_CHARS,
    overlap_chars: int = DEFAULT_DOC_CHUNK_OVERLAP_CHARS,
) -> list[Chunk]:
    """Split document pages into chunks by paragraph boundaries.

    Each page's text is split into paragraph-sized chunks. The page number
    is used for start_line/end_line, and heading (if any) for scope.
    """
    ext = Path(file_path).suffix.lower().lstrip(".")
    language = ext  # "pdf", "docx", "pptx"

    chunks: list[Chunk] = []

    for page in pages:
        if not page.text.strip():
            continue

        scope = page.heading or f"page {page.page_number}"
        page_chunks = _split_text_by_paragraphs(
            text=page.text,
            file_path=file_path,
            page_number=page.page_number,
            scope=scope,
            language=language,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )
        chunks.extend(page_chunks)

    return chunks


def _split_text_by_paragraphs(
    text: str,
    file_path: str,
    page_number: int,
    scope: str,
    language: str,
    max_chars: int,
    overlap_chars: int,
) -> list[Chunk]:
    """Split text into chunks respecting paragraph boundaries."""
    # Split on double newlines (paragraph breaks)
    paragraphs = re.split(r"\n\s*\n", text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    if not paragraphs:
        return []

    chunks: list[Chunk] = []
    current_text = ""
    chunk_idx = 0

    for para in paragraphs:
        # If adding this paragraph exceeds max_chars, flush current chunk
        if current_text and len(current_text) + len(para) + 2 > max_chars:
            chunk_idx += 1
            header = _make_context_header(
                file_path,
                scope,
                page_number,
                page_number,
            )
            chunks.append(
                Chunk(
                    file_path=file_path,
                    start_line=page_number,
                    end_line=page_number,
                    content=current_text,
                    scope=scope,
                    language=language,
                    context_header=header,
                )
            )
            # Keep overlap from the end of current chunk
            if overlap_chars > 0 and len(current_text) > overlap_chars:
                current_text = current_text[-overlap_chars:]
            else:
                current_text = ""

        if current_text:
            current_text += "\n\n" + para
        else:
            current_text = para

    # Flush remaining text
    if current_text.strip():
        header = _make_context_header(file_path, scope, page_number, page_number)
        chunks.append(
            Chunk(
                file_path=file_path,
                start_line=page_number,
                end_line=page_number,
                content=current_text,
                scope=scope,
                language=language,
                context_header=header,
            )
        )

    return chunks
