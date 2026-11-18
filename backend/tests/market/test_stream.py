"""SSE framing: one frame carries every ticker, and only changes are emitted."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest

from app.market.cache import PriceCache
from app.market.stream import KEEPALIVE_FRAME, RETRY_FRAME, create_stream_router, price_event_stream


class FakeRequest:
    def __init__(self, disconnect_after: int | None = None) -> None:
        self.calls = 0
        self._disconnect_after = disconnect_after

    async def is_disconnected(self) -> bool:
        self.calls += 1
        if self._disconnect_after is None:
            return False
        return self.calls > self._disconnect_after


def always_connected() -> Callable[[], Any]:
    async def check() -> bool:
        return False

    return check


async def take(stream: AsyncIterator[str], count: int) -> list[str]:
    frames: list[str] = []
    async for frame in stream:
        frames.append(frame)
        if len(frames) >= count:
            break
    return frames


def populate(cache: PriceCache) -> None:
    cache.update("AAPL", 190.1)
    cache.update("MSFT", 420.0)
    cache.update("AAPL", 190.55)


async def test_first_frame_is_a_retry_hint() -> None:
    cache = PriceCache()
    frames = await take(price_event_stream(cache, always_connected()), 1)
    assert frames == [RETRY_FRAME]


async def test_data_frame_carries_all_tickers_with_wire_fields() -> None:
    cache = PriceCache()
    populate(cache)

    frames = await take(price_event_stream(cache, always_connected(), interval=0.001), 2)
    assert frames[0] == RETRY_FRAME
    assert frames[1].startswith("data: ")

    payload = json.loads(frames[1][len("data: ") :].strip())
    assert set(payload) == {"AAPL", "MSFT"}
    assert payload["AAPL"]["price"] == 190.55
    assert payload["AAPL"]["previous_price"] == 190.1
    assert payload["AAPL"]["direction"] == "up"
    assert payload["AAPL"]["source"] == "simulator"
    for field in ("ticker", "price", "previous_price", "timestamp", "change", "change_percent"):
        assert field in payload["MSFT"]


async def test_frames_are_only_emitted_when_the_version_changes() -> None:
    cache = PriceCache()
    populate(cache)

    # An idle cache yields a keepalive instead of repeating the unchanged payload.
    frames = await take(
        price_event_stream(cache, always_connected(), interval=0.001, keepalive=0.002), 3
    )
    assert sum(frame.startswith("data: ") for frame in frames) == 1
    assert frames[2] == KEEPALIVE_FRAME

    # A cache write produces a fresh frame on the next stream.
    cache.update("AAPL", 191.0)
    frames = await take(price_event_stream(cache, always_connected(), interval=0.001), 2)
    payload = json.loads(frames[1][len("data: ") :].strip())
    assert payload["AAPL"]["price"] == 191.0


async def test_keepalive_comment_is_emitted_when_idle() -> None:
    cache = PriceCache()
    populate(cache)

    frames = await take(
        price_event_stream(cache, always_connected(), interval=0.001, keepalive=0.002), 4
    )
    assert frames[0] == RETRY_FRAME
    assert frames[1].startswith("data: ")
    assert frames[2] == KEEPALIVE_FRAME
    assert frames[3] == KEEPALIVE_FRAME


async def test_empty_cache_emits_keepalive_but_no_empty_data_frame() -> None:
    cache = PriceCache()
    frames = await take(
        price_event_stream(cache, always_connected(), interval=0.001, keepalive=0.001), 2
    )
    assert frames[0] == RETRY_FRAME
    assert frames[1] == KEEPALIVE_FRAME


async def test_stream_ends_when_the_client_disconnects() -> None:
    cache = PriceCache()
    populate(cache)

    async def disconnected() -> bool:
        return True

    frames = [frame async for frame in price_event_stream(cache, disconnected)]
    assert frames == [RETRY_FRAME]


async def test_router_streams_after_a_data_frame_then_stops() -> None:
    cache = PriceCache()
    populate(cache)

    router = create_stream_router(cache, interval=0.001)
    assert [route.path for route in router.routes] == ["/api/stream/prices"]

    request = FakeRequest(disconnect_after=1)
    response = await router.routes[0].endpoint(request)  # type: ignore[attr-defined]

    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"

    frames = [frame async for frame in response.body_iterator]  # type: ignore[union-attr]
    assert frames[0] == RETRY_FRAME
    assert frames[1].startswith("data: ")
    assert len(frames) == 2
    assert request.calls == 2


@pytest.mark.parametrize("interval", [0.001, 0.01])
async def test_frame_interval_is_respected(interval: float) -> None:
    cache = PriceCache()
    populate(cache)
    frames = await take(price_event_stream(cache, always_connected(), interval=interval), 2)
    assert len(frames) == 2
