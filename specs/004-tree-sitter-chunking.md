# Spec 004: Tree-sitter Chunking

**Status:** planned
**Phase:** Future
**Author:** Juan Martinez
**Created:** 2026-02-24
**Updated:** 2026-02-28

## Problem

The current regex-based chunker splits code files using pattern matching on function/class/block boundaries. This works well for clean, standard code but has known failure modes:

- Regex can't handle nested structures — a function inside a class inside a module gets split at the wrong boundary
- Decorators, multiline signatures, and context managers are often separated from their function bodies
- Languages with unusual syntax (Rust `impl` blocks, Go `func (receiver)`, Ruby `do..end`) need per-language regex patterns that are fragile to maintain
- Document files (PDF, DOCX) don't benefit from tree-sitter, but code files would see significant chunk quality improvement

When a chunk boundary splits a function in the middle, the embedding captures incomplete meaning, and the search result shows broken context. This directly hurts retrieval quality.

## Goals

- Replace regex chunking with tree-sitter AST parsing for all supported code languages
- Chunk boundaries align exactly with AST node boundaries (function, class, method, block)
- Hierarchical chunking: class → method → nested block, with context headers showing the full scope path
- Measurable improvement: Precision@10 improves by at least 10% on a code search benchmark
- Fallback to sliding window chunking for languages without tree-sitter grammar
- No change to the public API — chunking is an internal implementation detail

## Non-Goals

- Full LSP / semantic analysis — that requires a language server, far beyond chunking scope
- Cross-file reference tracking (imports, call graphs) — not needed for chunk-level search
- Document file chunking — PDF/DOCX/PPTX use paragraph-based chunking (spec 001), not AST parsing
- Replacing the sliding window fallback — it stays for unknown languages and plain text files

## Solution

```
Current pipeline:
  file → detect language → regex split on scope boundaries → chunks

New pipeline:
  file → detect language
           ├── tree-sitter grammar available?
           │     Yes → parse AST → walk tree → extract scope nodes → chunks
           │     No  → fallback to sliding window with overlap → chunks
           └── document file? → paragraph chunking (unchanged)
```

### AST-Based Chunking Strategy

1. Parse the file with tree-sitter → get AST
2. Walk the AST top-down, collecting "scope nodes" (function, class, method, struct, impl, module)
3. For each scope node:
   - If the node text fits in `max_chars` → emit as a single chunk
   - If too large → recurse into child scope nodes
   - If a leaf scope is still too large → split by statement boundaries within the node
4. Each chunk gets a context header showing its full scope path:
   ```
   # File: src/auth/jwt.py
   # Scope: class JWTValidator > method validate_token
   # Lines: 45-82
   ```

### Hierarchical Context

The key advantage over regex: tree-sitter gives us the full scope path. A method inside a class inside a module gets a header like `module auth > class JWTValidator > method validate_token`. This context is embedded alongside the code, improving retrieval for queries like "JWT validation" even when the method body doesn't contain those words.

## Implementation Notes

### Key Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Max chunk size | 1500 chars | Same as current — consistency across code and doc chunks |
| Min chunk size | 100 chars | Avoid micro-chunks from small helper functions |
| Overlap | 0 chars | AST boundaries are clean — no overlap needed unlike sliding window |
| Max tree depth | 5 levels | Prevents pathological nesting from creating micro-chunks |
| Scope node types | function, class, method, struct, impl, module, block | Language-dependent, configurable per grammar |

### Supported Languages

| Language | tree-sitter Grammar | Scope Nodes |
|----------|---------------------|-------------|
| Python | `tree-sitter-python` | function_definition, class_definition |
| JavaScript | `tree-sitter-javascript` | function_declaration, class_declaration, arrow_function |
| TypeScript | `tree-sitter-typescript` | function_declaration, class_declaration, interface_declaration |
| Go | `tree-sitter-go` | function_declaration, method_declaration, type_declaration |
| Rust | `tree-sitter-rust` | function_item, impl_item, struct_item, enum_item |
| Java | `tree-sitter-java` | method_declaration, class_declaration, interface_declaration |
| Ruby | `tree-sitter-ruby` | method, class, module |
| PHP | `tree-sitter-php` | function_definition, class_declaration, method_declaration |
| C | `tree-sitter-c` | function_definition, struct_specifier |
| C++ | `tree-sitter-cpp` | function_definition, class_specifier, namespace_definition |

### Dependencies

- New: `tree-sitter>=0.22` — core parsing library
- New: `tree-sitter-languages>=1.10` — pre-built grammar bundle (all 10 languages in one package)
- Depends on: Spec 001 (core search engine — chunk storage and search pipeline)
- Depended on by: None (internal quality improvement)

### Implementation Steps

1. Add `tree_sitter_chunker.py` module alongside existing `chunker.py`
2. Implement `chunk_file_ast(file_path, language, max_chars) -> list[Chunk]`
3. In `chunker.py`: route to AST chunker when grammar is available, else fallback
4. Reuse existing `Chunk` dataclass — no schema changes
5. Update context header format to include full scope path
6. Benchmark Precision@10 before/after on test query set

### Code Sketch

```python
# tree_sitter_chunker.py

import tree_sitter_languages

def chunk_file_ast(
    source: str,
    file_path: str,
    language: str,
    max_chars: int = 1500,
) -> list[Chunk]:
    parser = tree_sitter_languages.get_parser(language)
    tree = parser.parse(source.encode())

    chunks = []
    _walk_scope_nodes(tree.root_node, file_path, scope_path=[], chunks=chunks, max_chars=max_chars)
    return chunks

def _walk_scope_nodes(node, file_path, scope_path, chunks, max_chars):
    if _is_scope_node(node):
        text = node.text.decode()
        current_scope = scope_path + [_node_label(node)]

        if len(text) <= max_chars:
            chunks.append(_make_chunk(text, file_path, current_scope, node))
        else:
            # Recurse into children
            for child in node.children:
                _walk_scope_nodes(child, file_path, current_scope, chunks, max_chars)
    else:
        for child in node.children:
            _walk_scope_nodes(child, file_path, scope_path, chunks, max_chars)
```

## Alternatives Considered

### Alternative A: Language Server Protocol (LSP)

Trade-off: Full semantic understanding — knows about types, imports, call graphs. But requires running a language server per language (pyright, tsserver, gopls), massive overhead.
Rejected because: We need chunk boundaries, not semantic analysis. tree-sitter gives us AST structure with zero runtime dependencies beyond the grammar files.

### Alternative B: Improved regex patterns

Trade-off: No new dependencies, incremental improvement. But regex fundamentally can't handle nesting or multi-line constructs reliably.
Rejected because: Diminishing returns — each new edge case requires a more complex regex. tree-sitter handles all edge cases by design since it parses the actual grammar.

### Alternative C: Concrete Syntax Tree (CST) via tree-sitter

Trade-off: CST preserves all whitespace and formatting, more faithful to source. But CST nodes are more granular than needed.
Rejected because: AST-level nodes (function, class) are the right granularity for chunking. CST would require more filtering logic for no practical benefit.

## Edge Cases & Failure Modes

- Syntax errors in source file → tree-sitter produces a partial AST with `ERROR` nodes. Fall back to regex chunking for that file, log warning
- Mixed language files (HTML with embedded JS) → chunk by the outer language (HTML). Embedded script blocks are treated as text within the HTML chunk
- Very deeply nested code (>5 levels) → stop recursing at max depth, emit the remaining subtree as a single chunk even if it exceeds max_chars slightly
- Empty file → skip, no chunks emitted (same as current behavior)
- Binary file misidentified as code → tree-sitter parse fails, fallback to skip
- Single massive function (>5000 chars) → split by statement boundaries within the function body
- Decorator/attribute attached to function → include in the function chunk (tree-sitter AST includes decorators as part of the function node)

## Open Questions

- [ ] Should we use `tree-sitter-languages` (pre-built bundle) or individual grammar packages? Bundle is easier but larger. — @juan
- [ ] What's the minimum tree-sitter version that supports all 10 languages reliably? — @juan
- [ ] Should context headers show the full scope path (`class Foo > method bar`) or just the immediate scope (`method bar`)? Full path is more informative but longer. — @juan
- [ ] Is 1500 chars still the right max chunk size for AST-based chunks? AST boundaries might produce naturally larger coherent units. — @juan

## Acceptance Criteria

- [ ] tree-sitter used for all 10 supported code languages (Python, JS, TS, Go, Rust, Java, Ruby, PHP, C, C++)
- [ ] Hierarchical chunking: class → method → block with full scope path in context header
- [ ] Chunk boundaries align exactly with AST node boundaries — no mid-function splits
- [ ] Fallback to sliding window chunking for unsupported languages (no crash, no empty results)
- [ ] Syntax errors in source → graceful fallback to regex, logged warning
- [ ] Existing `Chunk` dataclass reused — no schema changes to LanceDB or SQLite
- [ ] Precision@10 improves by at least 10% on a benchmark query set (5+ test queries against a code repo)
- [ ] No regression on existing test suite: `uv run --extra dev pytest tests/ -x -v` passes
- [ ] Document files (PDF, DOCX, PPTX) unaffected — still use paragraph chunking
