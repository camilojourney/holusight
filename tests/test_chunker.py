"""Tests for the chunking pipeline."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from codesight.chunker import _detect_language, _detect_scope, chunk_file, chunk_file_ast


class TestDetectLanguage:
    def test_python(self):
        assert _detect_language("src/main.py") == "python"

    def test_javascript(self):
        assert _detect_language("app.js") == "javascript"

    def test_typescript(self):
        assert _detect_language("component.tsx") == "typescript"

    def test_go(self):
        assert _detect_language("main.go") == "go"

    def test_unknown(self):
        assert _detect_language("readme.md") == "unknown"

    def test_case_insensitive(self):
        # _detect_language lowercases the extension, so .PY maps to python
        assert _detect_language("Main.PY") == "python"


class TestDetectScope:
    def test_python_function(self):
        assert _detect_scope("def hello():", "python") == "function hello"

    def test_python_async_function(self):
        assert _detect_scope("async def fetch_data():", "python") == "function fetch_data"

    def test_python_class(self):
        assert _detect_scope("class MyService:", "python") == "class MyService"

    def test_empty_line(self):
        assert _detect_scope("", "python") == "module-level"

    def test_go_function(self):
        assert _detect_scope("func main()", "go") == "function main"

    def test_rust_struct(self):
        assert _detect_scope("pub struct Config {", "rust") == "struct Config"


class TestChunkFile:
    def test_empty_content_returns_empty(self):
        assert chunk_file("", "test.py") == []
        assert chunk_file("   \n  \n  ", "test.py") == []

    def test_small_python_file(self):
        content = "def hello():\n    return 'world'\n"
        chunks = chunk_file(content, "hello.py")
        assert len(chunks) >= 1
        assert chunks[0].language == "python"
        assert chunks[0].file_path == "hello.py"

    def test_chunk_has_content_hash(self):
        content = "def test(): pass"
        chunks = chunk_file(content, "test.py")
        assert len(chunks) == 1
        assert len(chunks[0].content_hash) == 16  # sha256[:16]

    def test_chunk_id_format(self):
        content = "def test(): pass"
        chunks = chunk_file(content, "test.py")
        cid = chunks[0].chunk_id
        # Format: file_path:start-end:hash
        parts = cid.split(":")
        assert len(parts) == 3
        assert parts[0] == "test.py"

    def test_context_header_present(self):
        content = "def test(): pass"
        chunks = chunk_file(content, "test.py")
        header = chunks[0].context_header
        assert "# File: test.py" in header
        assert "# Scope:" in header
        assert "# Lines:" in header

    def test_embedding_text_includes_header(self):
        content = "def test(): pass"
        chunks = chunk_file(content, "test.py")
        emb_text = chunks[0].embedding_text
        assert emb_text.startswith("# File:")
        assert "def test(): pass" in emb_text

    def test_multiple_functions_produce_multiple_chunks(self):
        # Functions need 6+ lines to stay separate when AST chunker is active (min_lines=5)
        content = "\n".join(
            [
                "def foo():",
                "    a = 1",
                "    b = 2",
                "    c = 3",
                "    d = 4",
                "    return a + b + c + d",
                "",
                "def bar():",
                "    x = 10",
                "    y = 20",
                "    z = 30",
                "    w = 40",
                "    t = 50",
                "    return x + y + z + w + t",
            ]
        )
        chunks = chunk_file(content, "multi.py")
        assert len(chunks) >= 2

    def test_unknown_language_uses_windows(self):
        content = "\n".join(f"line {i}" for i in range(50))
        chunks = chunk_file(content, "data.txt", max_lines=20, overlap_lines=5)
        assert len(chunks) >= 2


class TestContentHashDedup:
    def test_same_content_same_hash(self):
        content = "def test(): pass"
        c1 = chunk_file(content, "a.py")
        c2 = chunk_file(content, "a.py")
        assert c1[0].content_hash == c2[0].content_hash

    def test_different_content_different_hash(self):
        c1 = chunk_file("def foo(): pass", "a.py")
        c2 = chunk_file("def bar(): pass", "a.py")
        assert c1[0].content_hash != c2[0].content_hash


# ---------------------------------------------------------------------------
# AST chunking tests (tree-sitter)
# ---------------------------------------------------------------------------

# Skip all AST tests if tree-sitter is not installed
_ts_available = True
try:
    import tree_sitter  # noqa: F401
    import tree_sitter_python  # noqa: F401
except ImportError:
    _ts_available = False

pytestmark_ts = pytest.mark.skipif(not _ts_available, reason="tree-sitter not installed")


class TestChunkFileAST:
    """Tests for chunk_file_ast() — requires tree-sitter to be installed."""

    @pytestmark_ts
    def test_two_functions_produce_two_chunks(self):
        """Two Python functions each >= min_lines → 2 separate chunks."""
        # Each function has 6 lines (> default min_lines=5), so they stay separate
        content = "\n".join(
            [
                "def alpha():",
                "    a = 1",
                "    b = 2",
                "    c = 3",
                "    d = 4",
                "    return a + b + c + d",
                "",
                "def beta():",
                "    x = 10",
                "    y = 20",
                "    z = 30",
                "    w = 40",
                "    t = 50",
                "    return x + y + z + w + t",
            ]
        )
        chunks = chunk_file_ast(content, "funcs.py")
        names = [c.scope for c in chunks]
        assert any("alpha" in n for n in names)
        assert any("beta" in n for n in names)

    @pytestmark_ts
    def test_empty_content_returns_empty(self):
        chunks = chunk_file_ast("", "empty.py")
        assert chunks == []

    @pytestmark_ts
    def test_chunk_has_correct_file_path(self):
        content = "def foo():\n    pass\n"
        chunks = chunk_file_ast(content, "src/mymodule.py")
        assert all(c.file_path == "src/mymodule.py" for c in chunks)

    @pytestmark_ts
    def test_chunk_has_context_header(self):
        content = "def greet():\n    print('hello')\n"
        chunks = chunk_file_ast(content, "greet.py")
        assert len(chunks) >= 1
        assert "# File: greet.py" in chunks[0].context_header
        assert "# Scope:" in chunks[0].context_header

    @pytestmark_ts
    def test_small_functions_merged(self):
        """Two consecutive tiny functions (< min_lines=5) should be merged into one chunk."""
        # Each function is 2 lines — well below min_lines=5
        content = "def a():\n    pass\n\ndef b():\n    pass\n"
        chunks = chunk_file_ast(content, "tiny.py", min_lines=5)
        # With merging, both tiny functions should collapse into 1 chunk
        assert len(chunks) == 1

    @pytestmark_ts
    def test_large_function_subsplit(self):
        """A function exceeding max_lines should be sub-split into multiple chunks."""
        # Build a function with 30 lines (> max_lines=10)
        body_lines = "\n".join(f"    x_{i} = {i}" for i in range(28))
        content = f"def big_function():\n{body_lines}\n    return x_0\n"
        chunks = chunk_file_ast(content, "big.py", max_lines=10)
        assert len(chunks) >= 2

    @pytestmark_ts
    def test_leading_imports_become_separate_chunk(self):
        """Module-level imports before the first function → own chunk."""
        content = "import os\nimport sys\n\ndef main():\n    pass\n"
        chunks = chunk_file_ast(content, "main.py")
        # Should have at least 2 chunks: imports + main function
        assert len(chunks) >= 2

    @pytestmark_ts
    def test_javascript_functions_chunked(self):
        """JS file with 2 substantial functions → at least 2 chunks."""
        # Each function body is 6+ lines to exceed default min_lines=5
        content = "\n".join(
            [
                "function hello() {",
                "    const a = 1;",
                "    const b = 2;",
                "    const c = 3;",
                "    const d = 4;",
                "    return a + b + c + d;",
                "}",
                "",
                "function goodbye() {",
                "    const x = 10;",
                "    const y = 20;",
                "    const z = 30;",
                "    const w = 40;",
                "    const t = 50;",
                "    return x + y + z + w + t;",
                "}",
            ]
        )
        chunks = chunk_file_ast(content, "funcs.js")
        assert len(chunks) >= 2

    @pytestmark_ts
    def test_chunk_file_uses_ast_for_python(self):
        """chunk_file() delegates to AST chunker for Python when tree-sitter is available."""
        # Use 6-line functions so they stay separate (above default min_lines=5)
        content = "\n".join(
            [
                "def foo():",
                "    a = 1",
                "    b = 2",
                "    c = 3",
                "    d = 4",
                "    return a + b + c + d",
                "",
                "def bar():",
                "    x = 10",
                "    y = 20",
                "    z = 30",
                "    w = 40",
                "    t = 50",
                "    return x + y + z + w + t",
            ]
        )
        chunks = chunk_file(content, "test.py")
        scopes = [c.scope for c in chunks]
        assert any("foo" in s for s in scopes)
        assert any("bar" in s for s in scopes)

    def test_fallback_when_tree_sitter_unavailable(self):
        """chunk_file() falls back to regex when tree-sitter raises ImportError."""
        content = "def foo():\n    return 1\n\ndef bar():\n    return 2\n"

        with patch("codesight.chunker.chunk_file_ast", side_effect=ImportError("no tree-sitter")):
            chunks = chunk_file(content, "test.py")

        # Regex fallback should still produce chunks
        assert len(chunks) >= 1

    @pytestmark_ts
    def test_class_with_methods_chunked_as_one(self):
        """A class definition (including its methods) counts as one top-level node."""
        content = (
            "class MyClass:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
            "\n"
            "    def method(self):\n"
            "        return self.x\n"
        )
        chunks = chunk_file_ast(content, "cls.py")
        # The whole class is one AST node → one chunk (unless it exceeds max_lines)
        assert len(chunks) == 1
        assert "class MyClass" in chunks[0].scope or "MyClass" in chunks[0].scope
