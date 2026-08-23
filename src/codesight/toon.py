"""Compact TOON (Token-Oriented Object Notation) encoder for AXI output.

TOON is an agent-facing *projection* of a payload, not a storage format.
JSON stays the lossless canonical contract everywhere in this package
(returned by every function in :mod:`codesight.axi_providers` and
:mod:`codesight.cli_axi`); TOON is generated from the same in-memory
``dict``/``list``/scalar structure only at the CLI's output boundary,
per the installed AXI skill ("Convert to TOON at the output boundary -
keep internal logic on JSON") and spec 011's ``--format toon`` default.

This encoder is intentionally one-directional (encode only). Nothing in
this codebase parses TOON back into Python - every round-trip test in
``tests/test_toon.py`` exercises JSON, not TOON, for exactly that reason.

Rendering rules (matching the examples in ``~/.claude/skills/axi/SKILL.md``
and ``specs/011-holusight-product-architecture-research.md``):

- A scalar-valued key renders as ``key: value``.
- A nested mapping renders as ``key:`` followed by an indented block.
- A list of dicts that all share the same keys renders as a compact
  table: ``key[N]{f1,f2,f3}:`` followed by one comma-joined row per item.
- A list of dicts with non-uniform keys renders as ``key[N]:`` followed
  by one indented nested block per item (no table header, since there is
  no single column set to share).
- A list of scalars renders as ``key[N]:`` followed by one indented line
  per item (matching the ``help[2]:`` example in the AXI skill - no
  bullet markers).
- An empty list renders inline as ``key[0]: (empty)`` so the zero state
  is unambiguous (AXI section 5, "definitive empty states").
"""

from __future__ import annotations

from enum import Enum
from typing import Any

_INDENT = "  "


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool, Enum))


def _scalar_str(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _csv_cell(value: Any) -> str:
    """Render one table cell. Quote if it contains a comma, quote, or newline."""
    s = _scalar_str(value)
    if any(ch in s for ch in (",", '"', "\n")):
        return '"' + s.replace('"', '""') + '"'
    return s


def _uniform_dict_list(items: list[Any]) -> list[str] | None:
    """Return the shared ordered key list if every item is a dict with the
    same keys (in the same order as the first item), else None."""
    if not items or not all(isinstance(item, dict) for item in items):
        return None
    first_keys = list(items[0].keys())
    for item in items[1:]:
        if list(item.keys()) != first_keys:
            return None
    # Table rows only make sense when every value is itself a scalar -
    # nested structures fall back to the per-item block form.
    if not all(_is_scalar(v) for item in items for v in item.values()):
        return None
    return first_keys


def _encode_list(key: str, items: list[Any], indent: int) -> list[str]:
    pad = _INDENT * indent
    n = len(items)
    if n == 0:
        return [f"{pad}{key}[0]: (empty)"]

    if all(_is_scalar(v) for v in items):
        lines = [f"{pad}{key}[{n}]:"]
        for v in items:
            lines.append(f"{pad}{_INDENT}{_scalar_str(v)}")
        return lines

    uniform_keys = _uniform_dict_list(items)
    if uniform_keys is not None:
        header = ",".join(uniform_keys)
        lines = [f"{pad}{key}[{n}]{{{header}}}:"]
        for item in items:
            row = ",".join(_csv_cell(item[k]) for k in uniform_keys)
            lines.append(f"{pad}{_INDENT}{row}")
        return lines

    # Non-uniform items (mixed shape, or a dict containing nested
    # lists/dicts) - one indented block per item, no table header.
    lines = [f"{pad}{key}[{n}]:"]
    for item in items:
        if isinstance(item, dict):
            lines.extend(_encode_mapping(item, indent + 1))
        elif isinstance(item, list):
            lines.extend(_encode_list("-", item, indent + 1))
        else:
            lines.append(f"{pad}{_INDENT}{_scalar_str(item)}")
    return lines


def _encode_mapping(mapping: dict[str, Any], indent: int) -> list[str]:
    pad = _INDENT * indent
    lines: list[str] = []
    for key, value in mapping.items():
        if _is_scalar(value):
            lines.append(f"{pad}{key}: {_scalar_str(value)}")
        elif isinstance(value, list):
            lines.extend(_encode_list(key, value, indent))
        elif isinstance(value, dict):
            if not value:
                lines.append(f"{pad}{key}: (empty)")
            else:
                lines.append(f"{pad}{key}:")
                lines.extend(_encode_mapping(value, indent + 1))
        else:
            lines.append(f"{pad}{key}: {_scalar_str(value)}")
    return lines


def to_toon(payload: dict[str, Any]) -> str:
    """Encode a JSON-shaped ``dict`` as compact TOON text.

    ``payload`` must already be plain ``dict``/``list``/scalar data (e.g.
    the output of ``SomeModel.model_dump()``), not a Pydantic model.
    """
    if not isinstance(payload, dict):
        raise TypeError(f"to_toon() expects a dict payload, got {type(payload).__name__}")
    lines = _encode_mapping(payload, indent=0)
    return "\n".join(lines) + ("\n" if lines else "")
