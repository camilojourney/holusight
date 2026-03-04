from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import codesight.bot.app as bot_app
from codesight.bot.cards import answer_card, error_card, no_index_card
from codesight.bot.teams import LLM_FALLBACK, NON_TEXT_ERROR, TeamsBot
from codesight.types import Answer, RepoStatus, SearchResult


class _StubEngine:
    def __init__(self) -> None:
        self.ask_calls: list[str] = []
        self.search_calls: list[str] = []
        self.status_value = RepoStatus(
            repo_path="/tmp/data",
            indexed=True,
            chunk_count=2,
            files_indexed=1,
            stale=False,
        )
        self.ask_result = Answer(text="Default answer", sources=[_mk_result()], model="stub:model")
        self.ask_error: Exception | None = None
        self.search_result = [_mk_result()]

    def status(self) -> RepoStatus:
        return self.status_value

    def ask(self, question: str, top_k: int = 5) -> Answer:
        self.ask_calls.append(question)
        if self.ask_error:
            raise self.ask_error
        return self.ask_result

    def search(self, question: str, top_k: int = 5):
        self.search_calls.append(question)
        return self.search_result[:top_k]


class _FakeTurnContext:
    def __init__(self, activity):
        self.activity = activity
        self.sent: list[object] = []

    async def send_activity(self, activity):
        self.sent.append(activity)
        return activity


def _mk_result() -> SearchResult:
    return SearchResult(
        file_path="drive/doc1__contract.pdf",
        start_line=3,
        end_line=4,
        snippet="payment terms",
        score=1.0,
        scope="page 3",
        chunk_id="chunk-1",
    )


def _mk_activity(*, text: str | None, conversation_type: str = "personal", entities=None):
    return SimpleNamespace(
        text=text,
        type="message",
        conversation=SimpleNamespace(conversation_type=conversation_type),
        entities=entities or [],
        recipient=SimpleNamespace(id="bot-id"),
    )


def _extract_card(turn_context: _FakeTurnContext) -> dict:
    message = turn_context.sent[-1]
    return message.attachments[0]["content"]


@pytest.mark.asyncio
async def test_SPEC_012_001_bot_receives_message_calls_ask_and_returns_card():
    """SPEC-012-001: Bot routes text questions to ask() and replies with adaptive card."""
    engine = _StubEngine()
    bot = TeamsBot(engine, bot_app_id="bot-id")
    turn_context = _FakeTurnContext(_mk_activity(text="What are payment terms?"))

    await bot.on_message_activity(turn_context)

    assert engine.ask_calls == ["What are payment terms?"]
    assert turn_context.sent[0].type == "typing"
    assert (
        turn_context.sent[1].attachments[0]["contentType"]
        == "application/vnd.microsoft.card.adaptive"
    )


def test_SPEC_012_002_answer_card_contains_confidence_and_expandable_sources():
    """SPEC-012-002: Adaptive card includes confidence text and source action set."""
    card = answer_card(
        answer_text="Answer text",
        confidence_level="high",
        sources=[_mk_result()],
        note=None,
    )

    assert card["type"] == "AdaptiveCard"
    assert "High Confidence" in card["body"][0]["text"]
    assert card["body"][-1]["actions"][0]["type"] == "Action.ShowCard"


@pytest.mark.asyncio
async def test_SPEC_012_004_typing_indicator_is_sent_before_answer_card():
    """SPEC-012-004: Bot emits typing activity before executing answer response."""
    engine = _StubEngine()
    bot = TeamsBot(engine, bot_app_id="bot-id")
    turn_context = _FakeTurnContext(_mk_activity(text="Summarize week 3 notes"))

    await bot.on_message_activity(turn_context)

    assert turn_context.sent[0].type == "typing"
    assert turn_context.sent[1].type == "message"


@pytest.mark.asyncio
async def test_SPEC_012_005_channel_requires_mention_and_responds_when_mentioned():
    """SPEC-012-005: Channel messages need @mention, personal messages do not."""
    engine = _StubEngine()
    bot = TeamsBot(engine, bot_app_id="bot-id")

    channel_without_mention = _FakeTurnContext(
        _mk_activity(text="help", conversation_type="channel")
    )
    await bot.on_message_activity(channel_without_mention)
    assert channel_without_mention.sent == []

    mention = SimpleNamespace(type="mention", mentioned=SimpleNamespace(id="bot-id"))
    channel_with_mention = _FakeTurnContext(
        _mk_activity(
            text="<at>CodeSight</at> help",
            conversation_type="channel",
            entities=[mention],
        )
    )
    await bot.on_message_activity(channel_with_mention)
    assert engine.ask_calls[-1] == "help"


def test_SPEC_012_007_resolve_data_path_prefers_cli_then_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """SPEC-012-007: Bot app path resolution prioritizes explicit arg over env and cwd."""
    env_path = tmp_path / "env-data"
    monkeypatch.setenv("CODESIGHT_BOT_DATA_PATH", str(env_path))

    resolved = bot_app._resolve_data_path(str(tmp_path / "cli-data"))
    assert resolved == (tmp_path / "cli-data").resolve()


@pytest.mark.asyncio
async def test_EDGE_012_001_no_index_state_returns_sync_instruction():
    """EDGE-012-001: Missing index returns setup guidance card."""
    engine = _StubEngine()
    engine.status_value = RepoStatus(
        repo_path="/tmp/data",
        indexed=False,
        chunk_count=0,
        files_indexed=0,
        stale=False,
    )
    bot = TeamsBot(engine, bot_app_id="bot-id")
    turn_context = _FakeTurnContext(_mk_activity(text="hello"))

    await bot.on_message_activity(turn_context)
    card = _extract_card(turn_context)
    assert "I haven't indexed any documents yet" in card["body"][0]["text"]


@pytest.mark.asyncio
async def test_EDGE_012_002_llm_failure_falls_back_to_search_results():
    """EDGE-012-002: ask() errors fall back to search result list message."""
    engine = _StubEngine()
    engine.ask_error = RuntimeError("LLM unavailable")
    bot = TeamsBot(engine, bot_app_id="bot-id")
    turn_context = _FakeTurnContext(_mk_activity(text="question"))

    await bot.on_message_activity(turn_context)

    card = _extract_card(turn_context)
    assert LLM_FALLBACK in card["body"][0]["text"]
    assert "drive/doc1__contract.pdf" in card["body"][0]["text"]
    assert engine.search_calls == ["question"]


@pytest.mark.asyncio
async def test_EDGE_012_003_questions_over_500_chars_are_truncated_with_note():
    """EDGE-012-003: Overlong question input is truncated and noted in response card."""
    engine = _StubEngine()
    bot = TeamsBot(engine, bot_app_id="bot-id")
    long_question = "Q" * 700
    turn_context = _FakeTurnContext(_mk_activity(text=long_question))

    await bot.on_message_activity(turn_context)

    assert len(engine.ask_calls[0]) == 500
    card = _extract_card(turn_context)
    notes = [part["text"] for part in card["body"] if part.get("isSubtle")]
    assert "Question truncated to 500 characters." in notes[0]


@pytest.mark.asyncio
async def test_EDGE_012_004_non_text_message_receives_helpful_error_card():
    """EDGE-012-004: Empty/non-text inputs return explicit text-only guidance."""
    engine = _StubEngine()
    bot = TeamsBot(engine, bot_app_id="bot-id")
    turn_context = _FakeTurnContext(_mk_activity(text=None))

    await bot.on_message_activity(turn_context)

    card = _extract_card(turn_context)
    assert NON_TEXT_ERROR in card["body"][0]["text"]


@pytest.mark.asyncio
async def test_EDGE_012_006_answer_over_2000_chars_is_truncated_with_hint():
    """EDGE-012-006: Long answers are capped for Teams card limits with follow-up guidance."""
    engine = _StubEngine()
    engine.ask_result = Answer(
        text="A" * 2500,
        sources=[_mk_result()],
        model="stub:model",
        confidence_level="high",
    )
    bot = TeamsBot(engine, bot_app_id="bot-id")
    turn_context = _FakeTurnContext(_mk_activity(text="Explain all details"))

    await bot.on_message_activity(turn_context)

    card = _extract_card(turn_context)
    answer_text = card["body"][1]["text"]
    assert len(answer_text) < 2100
    assert "Ask a more specific question for a detailed answer." in answer_text


def test_EDGE_012_007_missing_optional_deps_raises_clear_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
):
    """EDGE-012-007: Missing teams deps are rejected with install guidance."""
    monkeypatch.setattr(bot_app, "web", None)
    monkeypatch.setattr(bot_app, "BotFrameworkAdapterSettings", None)
    with pytest.raises(RuntimeError, match="optional dependency group 'teams'"):
        bot_app._require_teams_dependencies()


def test_EDGE_012_001_no_index_card_builder_message():
    """EDGE-012-001: no_index_card() returns the required setup instruction string."""
    card = no_index_card()
    assert "codesight sync" in card["body"][0]["text"]


def test_EDGE_012_002_error_card_builder_wraps_message():
    """EDGE-012-002: error_card() includes supplied failure message text."""
    card = error_card("error text")
    assert card["body"][0]["text"] == "error text"
