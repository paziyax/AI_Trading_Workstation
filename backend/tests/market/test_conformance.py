"""Contract tests every MarketDataSource implementation must satisfy."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import date, timedelta

import pytest

from app.market.cache import PriceCache
from app.market.config import Plan
from app.market.interface import MarketDataSource
from app.market.massive_client import MassiveDataSource
from app.market.simulator import SimulatorDataSource
from tests.market.conftest import DEFAULT_TICKERS, FakeMassiveClient, make_config, row

EOD_DAY = date(2026, 11, 24)
PRICES = {ticker: 100.0 + index for index, ticker in enumerate(DEFAULT_TICKERS)}
EOD_ROWS = [row(ticker, price) for ticker, price in PRICES.items()]
TSLA_PRICE = 250.0

SourceFactory = Callable[[PriceCache], MarketDataSource]


def _next_day() -> date:
    return EOD_DAY + timedelta(days=1)


def _eod_client() -> FakeMassiveClient:
    tickers = [*DEFAULT_TICKERS, "TSLA"]
    return FakeMassiveClient(
        eod={str(EOD_DAY): [row(t, PRICES.get(t, TSLA_PRICE)) for t in tickers]}
    )


def _snapshot_client() -> FakeMassiveClient:
    return FakeMassiveClient(prices={**PRICES, "TSLA": TSLA_PRICE})


def make_simulator(cache: PriceCache, *, interval: float = 3600.0) -> MarketDataSource:
    return SimulatorDataSource(cache, make_config(), interval=interval)


def make_massive_eod(cache: PriceCache, *, refresh: int = 3600) -> MarketDataSource:
    return MassiveDataSource(
        cache,
        make_config(api_key="key", plan=Plan.BASIC, eod_refresh_seconds=refresh),
        client_factory=lambda _: _eod_client(),
        today=_next_day,
    )


def make_massive_snapshot(cache: PriceCache, *, poll: float = 3600.0) -> MarketDataSource:
    return MassiveDataSource(
        cache,
        make_config(api_key="key", plan=Plan.STARTER, poll_interval=poll),
        client_factory=lambda _: _snapshot_client(),
        today=_next_day,
    )


SOURCE_FACTORIES: dict[str, SourceFactory] = {
    "simulator": make_simulator,
    "massive-eod": make_massive_eod,
    "massive-snapshot": make_massive_snapshot,
}

FAST_FACTORIES: dict[str, SourceFactory] = {
    "simulator": lambda cache: make_simulator(cache, interval=0.01),
    "massive-snapshot": lambda cache: make_massive_snapshot(cache, poll=0.01),
}


@pytest.fixture(params=sorted(SOURCE_FACTORIES))
def kind(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture
async def running(kind: str) -> AsyncIterator[tuple[PriceCache, MarketDataSource]]:
    cache = PriceCache()
    source = SOURCE_FACTORIES[kind](cache)
    await source.start(DEFAULT_TICKERS)
    try:
        yield cache, source
    finally:
        await source.stop()


async def wait_until(predicate: Callable[[], bool], timeout: float = 2.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return predicate()


async def test_start_populates_the_cache_for_every_ticker(
    running: tuple[PriceCache, MarketDataSource],
) -> None:
    cache, source = running
    assert source.get_tickers() == DEFAULT_TICKERS
    for ticker in DEFAULT_TICKERS:
        update = cache.get(ticker)
        assert update is not None, ticker
        assert update.price > 0


async def test_health_mode_matches_the_source_mode(
    running: tuple[PriceCache, MarketDataSource],
) -> None:
    _, source = running
    assert source.mode in {"simulator", "snapshot", "eod"}
    health = source.health()
    assert health.mode == source.mode
    assert health.connected is True
    assert health.last_success_at is not None


async def test_get_tickers_returns_a_defensive_copy(
    running: tuple[PriceCache, MarketDataSource],
) -> None:
    _, source = running
    tickers = source.get_tickers()
    tickers.append("HACK")
    assert "HACK" not in source.get_tickers()


async def test_add_ticker_is_idempotent_and_registers_the_ticker(
    running: tuple[PriceCache, MarketDataSource],
) -> None:
    cache, source = running
    await source.add_ticker("tsla")
    await source.add_ticker("TSLA")
    assert source.get_tickers().count("TSLA") == 1
    if source.mode != "snapshot":
        # Snapshot mode picks the new ticker up on its next poll; the others seed immediately.
        assert cache.get_price("TSLA") is not None


async def test_remove_ticker_evicts_the_cache_and_is_idempotent(
    running: tuple[PriceCache, MarketDataSource],
) -> None:
    cache, source = running
    await source.remove_ticker("aapl")
    await source.remove_ticker("AAPL")
    assert "AAPL" not in source.get_tickers()
    assert cache.get("AAPL") is None


async def test_stop_is_idempotent(running: tuple[PriceCache, MarketDataSource]) -> None:
    _, source = running
    await source.stop()
    await source.stop()
    assert source.health().mode == source.mode


@pytest.mark.parametrize("name", sorted(SOURCE_FACTORIES))
async def test_lowercase_start_input_is_normalized(name: str) -> None:
    cache = PriceCache()
    source = SOURCE_FACTORIES[name](cache)
    await source.start([ticker.lower() for ticker in DEFAULT_TICKERS])
    try:
        assert source.get_tickers() == DEFAULT_TICKERS
        for ticker in DEFAULT_TICKERS:
            assert cache.get_price(ticker) is not None
    finally:
        await source.stop()


@pytest.mark.parametrize("name", sorted(FAST_FACTORIES))
async def test_stop_freezes_the_cache(name: str) -> None:
    cache = PriceCache()
    source = FAST_FACTORIES[name](cache)
    await source.start(DEFAULT_TICKERS)
    try:
        assert await wait_until(lambda: cache.version > 5)
    finally:
        await source.stop()

    version = cache.version
    await asyncio.sleep(0.1)
    assert cache.version == version
