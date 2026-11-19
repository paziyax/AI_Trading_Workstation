"""Chat endpoint: one assistant turn, executed actions, refreshed portfolio."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import (
    CacheDep,
    ChatClientDep,
    DatabaseDep,
    MarketSourceDep,
    SessionTrackerDep,
    SettingsDep,
)
from app.services import ChatUnavailableError, handle_chat

router = APIRouter(prefix="/api/chat", tags=["chat"])

MAX_MESSAGE_LENGTH = 2000


class ChatRequest(BaseModel):
    """Body of ``POST /api/chat``; whitespace is trimmed before the length check."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)


@router.post("")
async def post_chat(
    payload: ChatRequest,
    database: DatabaseDep,
    cache: CacheDep,
    chat_client: ChatClientDep,
    source: MarketSourceDep,
    tracker: SessionTrackerDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    try:
        outcome = await handle_chat(
            database,
            cache,
            chat_client,
            payload.message,
            tracker=tracker,
            source=source,
            initial_cash=settings.initial_cash,
        )
    except ChatUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "message": outcome.message,
        "actions": outcome.actions,
        "portfolio": outcome.portfolio,
    }
