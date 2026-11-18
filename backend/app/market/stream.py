"""Server-Sent Events streaming of the price cache."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.market.cache import PriceCache

logger = logging.getLogger(__name__)

RETRY_FRAME = "retry: 1000\n\n"
KEEPALIVE_FRAME = ": keep-alive\n\n"


async def price_event_stream(
    cache: PriceCache,
    is_disconnected: Callable[[], Awaitable[bool]],
    *,
    interval: float = 0.5,
    keepalive: float = 15.0,
) -> AsyncIterator[str]:
    """Yield SSE frames for the whole price map.

    One frame carries all tickers, so the client replaces its price dictionary wholesale:
    idempotent and order-independent. Frames are emitted only when ``cache.version`` changes,
    which means an EOD source sends one frame per session rather than repeating identical
    payloads. A comment frame is emitted when idle so proxies do not drop the connection.
    """
    yield RETRY_FRAME
    last_version = -1
    idle = 0.0

    while not await is_disconnected():
        version = cache.version
        if version != last_version:
            last_version = version
            payload = {ticker: update.to_dict() for ticker, update in cache.snapshot().items()}
            if payload:
                yield f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"
            idle = 0.0
        else:
            idle += interval
            if idle >= keepalive:
                yield KEEPALIVE_FRAME
                idle = 0.0
        await asyncio.sleep(interval)


def create_stream_router(cache: PriceCache, *, interval: float = 0.5) -> APIRouter:
    router = APIRouter(prefix="/api/stream", tags=["market"])

    @router.get("/prices")
    async def stream_prices(request: Request) -> StreamingResponse:
        async def disconnected() -> bool:
            return await request.is_disconnected()

        return StreamingResponse(
            price_event_stream(cache, disconnected, interval=interval),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return router
