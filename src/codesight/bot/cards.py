"""Adaptive Card builders for Teams bot responses."""

from __future__ import annotations

from typing import Any


# SPEC-012-002: Confidence badges map answer confidence to visual labels/colors.
def _confidence_badge(confidence_level: str) -> tuple[str, str]:
    mapping = {
        "high": ("High", "good"),
        "medium": ("Medium", "warning"),
        "low": ("Low", "attention"),
        "refused": ("Refused", "attention"),
    }
    return mapping.get(confidence_level, ("Low", "attention"))


# SPEC-012-003: Source metadata is rendered with path and page/line ranges.
def _source_lines(sources: list[Any]) -> list[str]:
    lines: list[str] = []
    for source in sources:
        file_path = getattr(source, "file_path", "unknown")
        start_line = getattr(source, "start_line", "?")
        end_line = getattr(source, "end_line", "?")
        scope = getattr(source, "scope", "")
        lines.append(f"- {file_path} ({start_line}-{end_line}) {scope}".strip())
    return lines


# SPEC-012-002: Successful answers are formatted as Adaptive Cards with expandable sources.
def answer_card(
    *,
    answer_text: str,
    confidence_level: str,
    sources: list[Any],
    note: str | None = None,
) -> dict[str, Any]:
    badge_text, badge_color = _confidence_badge(confidence_level)
    source_lines = _source_lines(sources)
    source_text = "\n".join(source_lines) if source_lines else "No sources provided."
    body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": f"{badge_text} Confidence",
            "weight": "Bolder",
            "color": badge_color,
        },
        {
            "type": "TextBlock",
            "text": answer_text,
            "wrap": True,
        },
    ]

    if note:
        body.append({"type": "TextBlock", "text": note, "isSubtle": True, "wrap": True})

    body.append(
        {
            "type": "ActionSet",
            "actions": [
                {
                    "type": "Action.ShowCard",
                    "title": f"Sources ({len(source_lines)})",
                    "card": {
                        "type": "AdaptiveCard",
                        "version": "1.5",
                        "body": [{"type": "TextBlock", "text": source_text, "wrap": True}],
                    },
                }
            ],
        }
    )

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": body,
    }


# EDGE-012-002: Error cards provide fallback guidance when ask() fails.
def error_card(message: str) -> dict[str, Any]:
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": [
            {
                "type": "TextBlock",
                "text": message,
                "wrap": True,
                "color": "attention",
            }
        ],
    }


# EDGE-012-001: No-index state returns explicit setup instruction for admins.
def no_index_card() -> dict[str, Any]:
    return error_card(
        "I haven't indexed any documents yet. Ask your admin to run `codesight sync`."
    )
