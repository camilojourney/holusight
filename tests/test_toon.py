"""Tests for the compact TOON encoder (codesight.toon).

TOON is an output-boundary projection only - nothing in this codebase
parses TOON back into Python, so these tests check the encoder's output
shape directly rather than a round-trip (see tests/test_cli_axi.py for
the JSON round-trip tests that exercise the actual lossless contract).
"""

from __future__ import annotations

from enum import Enum

import pytest

from codesight.toon import to_toon


def test_scalar_keys():
    out = to_toon({"a": "x", "b": 1, "c": True, "d": None})
    assert out == "a: x\nb: 1\nc: true\nd: null\n"


def test_nested_mapping():
    out = to_toon({"snapshot": {"commit": "abc123", "dirty": False}})
    assert out == "snapshot:\n  commit: abc123\n  dirty: false\n"


def test_empty_dict_value():
    out = to_toon({"egress": {}})
    assert out == "egress: (empty)\n"


def test_uniform_dict_list_renders_as_table():
    out = to_toon(
        {
            "tasks": [
                {"id": "1", "title": "Fix auth bug", "status": "open"},
                {"id": "2", "title": "Add pagination", "status": "closed"},
            ]
        }
    )
    lines = out.splitlines()
    assert lines[0] == "tasks[2]{id,title,status}:"
    assert lines[1] == "  1,Fix auth bug,open"
    assert lines[2] == "  2,Add pagination,closed"


def test_list_of_scalars_no_bullets():
    out = to_toon({"help": ["Run `x`", "Run `y`"]})
    assert out == "help[2]:\n  Run `x`\n  Run `y`\n"


def test_empty_list_is_explicit():
    out = to_toon({"evidence": []})
    assert out == "evidence[0]: (empty)\n"


def test_csv_cell_quotes_commas_and_quotes():
    out = to_toon({"rows": [{"a": "has,comma", "b": 'has"quote'}]})
    lines = out.splitlines()
    assert lines[0] == "rows[1]{a,b}:"
    assert lines[1] == '  "has,comma","has""quote"'


def test_non_uniform_dict_list_falls_back_to_blocks():
    out = to_toon({"items": [{"a": 1}, {"a": 1, "b": 2}]})
    # Non-uniform key sets can't share one table header.
    assert "items[2]:" in out
    assert "{a,b}" not in out


def test_list_containing_nested_dict_falls_back_to_blocks():
    out = to_toon({"items": [{"a": {"nested": 1}}]})
    lines = out.splitlines()
    assert lines[0] == "items[1]:"
    assert "a:" in out
    assert "nested: 1" in out


def test_enum_value_serialized_not_repr():
    class Status(str, Enum):
        UP_TO_DATE = "up_to_date"

    out = to_toon({"status": Status.UP_TO_DATE})
    assert out == "status: up_to_date\n"
    assert "Status." not in out


def test_rejects_non_dict_payload():
    with pytest.raises(TypeError):
        to_toon(["not", "a", "dict"])  # type: ignore[arg-type]


def test_deeply_nested_roundish_shape_matches_axi_examples():
    out = to_toon(
        {
            "task": {
                "number": 42,
                "title": "Fix auth bug",
                "state": "open",
                "checks": "3/3 passed",
            }
        }
    )
    assert out == (
        "task:\n"
        "  number: 42\n"
        "  title: Fix auth bug\n"
        "  state: open\n"
        "  checks: 3/3 passed\n"
    )
