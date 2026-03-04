"""Aiohttp entry point for Microsoft Teams bot hosting."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from ..api import CodeSight
from .teams import TeamsBot

try:
    from aiohttp import web
except ImportError:  # pragma: no cover - exercised when optional deps are absent
    web = None

try:
    from botbuilder.core import BotFrameworkAdapterSettings, TurnContext
    from botbuilder.integration.aiohttp import BotFrameworkHttpAdapter
    from botbuilder.schema import Activity
except ImportError:  # pragma: no cover - exercised when optional deps are absent
    BotFrameworkAdapterSettings = None
    BotFrameworkHttpAdapter = None
    TurnContext = Any
    Activity = None

logger = logging.getLogger(__name__)


# SPEC-012-007: Bot server path resolves searchable index root from CLI/env defaults.
def _resolve_data_path(data_path: str | None = None) -> Path:
    candidate = data_path or os.environ.get("CODESIGHT_BOT_DATA_PATH") or "."
    return Path(candidate).expanduser().resolve()


# SPEC-012-007: Teams bot runtime validates optional dependencies before booting server.
def _require_teams_dependencies() -> None:
    if web is None or BotFrameworkAdapterSettings is None or BotFrameworkHttpAdapter is None:
        raise RuntimeError(
            "Teams bot support requires optional dependency group 'teams' "
            "(install with: pip install -e '.[teams]')."
        )


# EDGE-012-007: Adapter-level errors are logged and user receives safe fallback message.
async def _on_turn_error(turn_context: TurnContext, error: Exception) -> None:
    logger.exception("bot.message.error", exc_info=error)
    await turn_context.send_activity("The bot encountered an error while processing your request.")


# SPEC-012-007: aiohttp app exposes Bot Framework /api/messages endpoint.
def create_bot_app(
    *,
    data_path: str | None = None,
    engine: CodeSight | None = None,
) -> Any:
    _require_teams_dependencies()
    assert web is not None
    assert BotFrameworkAdapterSettings is not None
    assert BotFrameworkHttpAdapter is not None
    assert Activity is not None

    app_id = os.environ.get("CODESIGHT_BOT_APP_ID", "")
    app_secret = os.environ.get("CODESIGHT_BOT_APP_SECRET", "")

    settings = BotFrameworkAdapterSettings(app_id, app_secret)
    adapter = BotFrameworkHttpAdapter(settings)
    adapter.on_turn_error = _on_turn_error

    if engine is None:
        engine = CodeSight(_resolve_data_path(data_path))
    bot = TeamsBot(engine, bot_app_id=app_id)

    # SPEC-012-001: Incoming Bot Framework activities are routed to TeamsBot handler.
    async def messages(request: web.Request) -> web.Response:
        if "application/json" not in request.headers.get("Content-Type", ""):
            return web.Response(status=415)

        body = await request.json()
        activity = Activity().deserialize(body)
        auth_header = request.headers.get("Authorization", "")

        try:
            response = await adapter.process_activity(activity, auth_header, bot.on_turn)
        except Exception as exc:
            message = str(exc).lower()
            if "unauthorized" in message or "authentication" in message:
                # EDGE-012-007: Token/auth validation failures return 401 to Bot Framework.
                logger.exception("bot.message.error auth")
                return web.Response(status=401)
            raise

        if response:
            return web.json_response(data=response.body, status=response.status)
        return web.Response(status=201)

    app = web.Application()
    app.router.add_post("/api/messages", messages)
    return app


# SPEC-012-007: `codesight bot` launches aiohttp Teams endpoint on configured port.
def run_bot_server(*, data_path: str | None = None) -> None:
    _require_teams_dependencies()
    assert web is not None

    port = int(os.environ.get("CODESIGHT_BOT_PORT", "3978"))
    app = create_bot_app(data_path=data_path)
    web.run_app(app, host="0.0.0.0", port=port)
