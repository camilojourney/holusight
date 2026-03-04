"""Teams bot activity handler that routes questions to CodeSight.ask()."""

from __future__ import annotations

import logging
import re
from typing import Any

from ..api import CodeSight
from .cards import answer_card, error_card, no_index_card

try:
    from botbuilder.core import ActivityHandler, CardFactory, TurnContext
    from botbuilder.schema import Activity, ActivityTypes
except ImportError:  # pragma: no cover - exercised when optional deps are absent
    class ActivityTypes:
        message = "message"
        typing = "typing"

    class Activity:  # type: ignore[no-redef]
        # SPEC-012-001: Fallback Activity shim keeps tests runnable without botbuilder installed.
        def __init__(self, *, type: str | None = None, text: str | None = None, attachments=None):
            self.type = type
            self.text = text
            self.attachments = attachments or []

    class CardFactory:  # type: ignore[no-redef]
        @staticmethod
        # SPEC-012-002: Fallback card factory preserves adaptive-card attachment shape.
        def adaptive_card(payload: dict[str, Any]) -> dict[str, Any]:
            return {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": payload,
            }

    class TurnContext:  # type: ignore[no-redef]
        @staticmethod
        # SPEC-012-005: Mention-removal shim keeps method availability in test runtime.
        def remove_recipient_mention(_activity: Any) -> None:
            return

    class ActivityHandler:  # type: ignore[no-redef]
        # SPEC-012-001: Fallback on_turn dispatches message activities to on_message_activity().
        async def on_turn(self, turn_context: Any) -> None:
            activity_type = getattr(getattr(turn_context, "activity", None), "type", None)
            if activity_type == ActivityTypes.message:
                await self.on_message_activity(turn_context)

        # SPEC-012-001: Fallback interface enforces subclass message handler implementation.
        async def on_message_activity(self, turn_context: Any) -> None:
            raise NotImplementedError

logger = logging.getLogger(__name__)

NON_TEXT_ERROR = (
    "I can only answer text questions. "
    "Try asking something like: What are the payment terms?"
)
LLM_FALLBACK = (
    "I'm having trouble connecting to the AI service. "
    "Search still works - here are the most relevant documents:"
)


class TeamsBot(ActivityHandler):
    """Bot Framework activity handler that wraps CodeSight ask/search behavior."""

    # SPEC-012-001: Teams bot is initialized with shared CodeSight engine instance.
    def __init__(self, engine: CodeSight, *, bot_app_id: str | None = None) -> None:
        super().__init__()
        self.engine = engine
        self.bot_app_id = bot_app_id

    # SPEC-012-001: Incoming text messages invoke ask() and return adaptive card responses.
    async def on_message_activity(self, turn_context: TurnContext) -> None:
        activity = turn_context.activity
        if self._is_channel_message(activity) and not self._is_mentioned(activity):
            # EDGE-012-008: Channel messages without @mention are intentionally ignored.
            return

        raw_text = getattr(activity, "text", "") or ""
        question = self._strip_mentions(raw_text)
        if not question:
            # EDGE-012-004: Non-text messages receive explicit prompt for text-only usage.
            await self._send_card(turn_context, error_card(NON_TEXT_ERROR))
            return

        question, was_truncated = self._truncate_question(question)
        await turn_context.send_activity(Activity(type=ActivityTypes.typing))

        status = self.engine.status()
        if not status.indexed or status.chunk_count == 0:
            # EDGE-012-001: No-index status returns setup guidance card.
            await self._send_card(turn_context, no_index_card())
            return

        try:
            answer = self.engine.ask(question, top_k=5)
        except Exception:
            # EDGE-012-002: ask() failures fall back to search() results in user-safe response.
            logger.exception("bot.message.error")
            fallback_results = self.engine.search(question, top_k=5)
            fallback_text = self._format_search_fallback(fallback_results)
            await self._send_card(turn_context, error_card(fallback_text))
            return

        answer_text = answer.text
        if len(answer_text) > 2000:
            # EDGE-012-006: Teams answer payload is truncated to card-safe size with follow-up hint.
            answer_text = (
                f"{answer_text[:1997]}...\n\n"
                "Ask a more specific question for a detailed answer."
            )

        note = "Question truncated to 500 characters." if was_truncated else None
        card = answer_card(
            answer_text=answer_text,
            confidence_level=answer.confidence_level,
            sources=answer.sources,
            note=note,
        )
        await self._send_card(turn_context, card)

    # SPEC-012-005: Bot distinguishes channel messages from 1:1 messages.
    def _is_channel_message(self, activity: Any) -> bool:
        conversation = getattr(activity, "conversation", None)
        conversation_type = getattr(conversation, "conversation_type", None)
        return str(conversation_type or "").lower() == "channel"

    # SPEC-012-005: Channel replies are restricted to messages that mention the bot.
    def _is_mentioned(self, activity: Any) -> bool:
        entities = getattr(activity, "entities", None) or []
        recipient = getattr(activity, "recipient", None)
        recipient_id = getattr(recipient, "id", None)
        candidate_ids = {value for value in [self.bot_app_id, recipient_id] if value}

        for entity in entities:
            if getattr(entity, "type", None) != "mention":
                continue
            mentioned = getattr(entity, "mentioned", None)
            mentioned_id = getattr(mentioned, "id", None)
            if candidate_ids and mentioned_id in candidate_ids:
                return True
        return "<at>" in (getattr(activity, "text", "") or "")

    # SPEC-012-005: Mention markup is removed before forwarding clean question text to ask().
    def _strip_mentions(self, text: str) -> str:
        cleaned = re.sub(r"<at>.*?</at>", " ", text, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", cleaned).strip()

    # EDGE-012-003: Overlong questions are truncated to 500 chars before processing.
    def _truncate_question(self, question: str) -> tuple[str, bool]:
        if len(question) <= 500:
            return question, False
        return question[:500], True

    # SPEC-012-002: Adaptive cards are sent as bot attachments through TurnContext.
    async def _send_card(self, turn_context: TurnContext, payload: dict[str, Any]) -> None:
        attachment = CardFactory.adaptive_card(payload)
        message = Activity(type=ActivityTypes.message, attachments=[attachment])
        await turn_context.send_activity(message)

    # EDGE-012-002: LLM fallback message includes ranked search paths and ranges.
    def _format_search_fallback(self, results: list[Any]) -> str:
        lines = [LLM_FALLBACK]
        for item in results:
            file_path = getattr(item, "file_path", "unknown")
            start_line = getattr(item, "start_line", "?")
            end_line = getattr(item, "end_line", "?")
            lines.append(f"- {file_path} ({start_line}-{end_line})")
        return "\n".join(lines)
