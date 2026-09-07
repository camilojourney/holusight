"""Document character bounds, lossless splitting, and citation stability."""

import hashlib
import re

import pytest

from codesight.chunker import chunk_document
from codesight.parsers import DocumentPage


@pytest.mark.parametrize("max_chars,overlap", [(20, 0), (20, 2), (20, 19), (1, 0)])
@pytest.mark.parametrize("text", [
    pytest.param("x" * 100, id="unbroken"),
    pytest.param("漢字🙂é" * 31, id="unicode"),
    pytest.param("abcdefghij" * 2, id="exact-limit"),
    pytest.param("first  word\tsecond\nthird word" * 3, id="internal-whitespace"),
])
def test_oversized_paragraph_uses_bounded_overlapping_windows(text, max_chars, overlap):
    chunks = chunk_document([DocumentPage(text, 7, "Overview")], "a.pdf", max_chars, overlap)
    expected = []
    start = 0
    while True:
        expected.append(text[start:start + max_chars])
        if start + max_chars >= len(text):
            break
        start += max_chars - overlap
    assert [c.content for c in chunks] == expected
    assert all(0 < len(c.content) <= max_chars for c in chunks)
    for chunk in chunks:
        assert (chunk.start_line, chunk.end_line, chunk.scope) == (7, 7, "Overview")
        assert chunk.file_path == "a.pdf"
        assert chunk.language == "pdf"
        digest = hashlib.sha256(chunk.content.encode()).hexdigest()[:16]
        assert chunk.content_hash == digest
        assert chunk.chunk_id == f"a.pdf:7-7:{digest}"
    assert chunks == chunk_document(
        [DocumentPage(text, 7, "Overview")], "a.pdf", max_chars, overlap,
    )


@pytest.mark.parametrize("overlap", [0, 2, 19])
@pytest.mark.parametrize("text", [
    "abcdefghijklmnopqr\n\nstuvwxyz0123456789AB\n\nCDEF",
    "first\n\n" + "漢字🙂é" * 25 + "\n\nlast",
    "  first  \n \n second \n\n third  ",
])
def test_paragraph_and_overlap_carryover_preserve_order(text, overlap):
    chunks = chunk_document([DocumentPage(text, 3)], "a.docx", 20, overlap)
    assert all(0 < len(c.content) <= 20 for c in chunks)
    # Remove only the exact carried suffix, then ignore existing whitespace normalization.
    restored = chunks[0].content
    for previous, chunk in zip(chunks, chunks[1:]):
        carried = overlap if len(previous.content) > overlap else 0
        if carried:
            assert chunk.content[:carried] == previous.content[-carried:]
        restored += chunk.content[carried:]
    assert re.sub(r"\s", "", restored) == re.sub(r"\s", "", text)
    if overlap == 2:
        normalized = "\n\n".join(p.strip() for p in re.split(r"\n\s*\n", text) if p.strip())
        assert restored == normalized
    assert all((c.start_line, c.end_line, c.scope) == (3, 3, "page 3") for c in chunks)


def test_near_limit_paragraph_after_overlap_is_split_not_dropped():
    chunks = chunk_document(
        [DocumentPage("abcdefghijklmnopqr\n\nstuvwxyz0123456789AB", 1)], "a.pdf", 20, 2,
    )
    assert [c.content for c in chunks] == [
        "abcdefghijklmnopqr", "qr\n\nstuvwxyz01234567", "6789AB",
    ]


def test_short_pages_and_exact_limit_retain_existing_content_and_anchors():
    pages = [
        DocumentPage("  first\n\n second  ", 2, "Summary"),
        DocumentPage("z" * 20, 8),
        DocumentPage(" \n ", 9),
    ]
    chunks = chunk_document(pages, "short.docx", 20, 2)
    assert [c.content for c in chunks] == ["first\n\nsecond", "z" * 20]
    assert [(c.start_line, c.end_line, c.scope) for c in chunks] == [
        (2, 2, "Summary"), (8, 8, "page 8"),
    ]
    assert chunks[0].context_header == "# File: short.docx\n# Scope: Summary\n# Lines: 2-2"
    assert chunks[1].context_header == "# File: short.docx\n# Scope: page 8\n# Lines: 8-8"


@pytest.mark.parametrize("max_chars,overlap", [(0, 0), (-1, 0), (20, -1), (20, 20), (20, 21)])
@pytest.mark.parametrize("pages", [[], [DocumentPage("text", 1)]])
def test_document_windows_reject_nonprogressing_parameters(max_chars, overlap, pages):
    with pytest.raises(ValueError, match="max_chars > 0 and 0 <= overlap_chars < max_chars"):
        chunk_document(pages, "a.pdf", max_chars, overlap)


def test_short_paragraph_control_retains_greedy_boundaries_and_overlap():
    chunks = chunk_document(
        [DocumentPage("alpha\n\nbravo\n\ncharlie\n\ndelta", 1)], "a.pdf", 20, 2,
    )
    assert [c.content for c in chunks] == ["alpha\n\nbravo", "vo\n\ncharlie\n\ndelta"]
