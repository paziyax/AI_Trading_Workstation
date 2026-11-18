"""Simulator lifecycle and cache integration."""

from __future__ import annotations

import asyncio

import pytest

from app.market.cache import PriceCache
from app.market.seed_prices import SEED_PRICES
from app.market.simulator import SimulatorDataSource
from tests.market.conftest import make_config


@pytest.fixture
def cache() -> PriceCache:
    return PriceCache()


async def test_start_seeds_the_cache_before_the_first_tick(cache: PriceCache) -> None:
    source = SimulatorDataSource(cache, make_config(), interval=0.01)
    await source.start(["AAPL", "MSFT"])
    try:
        assert set(cache.snapshot()) == {"AAPL", "MSFT"}
        assert cache.get_price("AAPL") == pytest.approx(SEED_PRICES["AAPL"])
    finally:
        await source.stop()


async def test_loop_writes_prices_after_start(cache: PriceCache) -> None:
    source = SimulatorDataSource(cache, make_config(), interval=0.01)
    await source.start(["AAPL"])
    try:
        await asyncio.sleep(0.05)
        assert cache.version > 1
    finally:
        await source.stop()


async def test_stop_halts_cache_writes(cache: PriceCache) -> None:
    source = SimulatorDataSource(cache, make_config(), interval=0.01)
    await source.start(["AAPL", "MSFT"])
    await asyncio.sleep(0.05)
    version = cache.version
    assert version > 2
    await source.stop()
    await asyncio.sleep(0.05)
    assert cache.version == version


async def test_stop_is_idempotent(cache: PriceCache) -> None:
    source = SimulatorDataSource(cache, make_config(), interval=0.01)
    await source.start(["AAPL"])
    await source.stop()
    await source.stop()
    assert source.health().mode == "simulator"


async def test_add_ticker_seeds_the_cache_immediately(cache: PriceCache) -> None:
    source = SimulatorDataSource(cache, make_config(), interval=0.01)
    await source.start(["AAPL"])
    try:
        await source.add_ticker("tsla")
        assert cache.get_price("TSLA") == pytest.approx(SEED_PRICES["TSLA"])
        assert "TSLA" in source.get_tickers()
    finally:
        await source.stop()


async def test_add_ticker_is_idempotent(cache: PriceCache) -> None:
    source = SimulatorDataSource(cache, make_config(), interval=0.01)
    await source.start(["AAPL"])
    try:
        await source.add_ticker("AAPL")
        assert source.get_tickers().count("AAPL") == 1
    finally:
        await source.stop()


async def test_remove_ticker_evicts_the_cache(cache: PriceCache) -> None:
    source = SimulatorDataSource(cache, make_config(), interval=0.01)
    await source.start(["AAPL", "MSFT"])
    try:
        await source.remove_ticker("AAPL")
        assert cache.get("AAPL") is None
        assert source.get_tickers() == ["MSFT"]
    finally:
        await source.stop()


async def test_get_tickers_returns_a_copy(cache: PriceCache) -> None:
    source = SimulatorDataSource(cache, make_config(), interval=0.01)
    await source.start(["AAPL"])
    try:
        tickers = source.get_tickers()
        tickers.append("HACK")
        assert source.get_tickers() == ["AAPL"]
    finally:
        await source.stop()


async def test_one_bad_tick_does_not_kill_the_loop(cache: PriceCache) -> None:
    source = SimulatorDataSource(cache, make_config(), interval=0.01)
    await source.start(["AAPL"])

    calls = {"n": 0}
    original = source._sim.step  # noqa: SLF001

    def flaky_step() -> dict[str, float]:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return original()

    source._sim.step = flaky_step  # type: ignore[method-assign]  # noqa: SLF001
    try:
        await asyncio.sleep(0.08)
        assert calls["n"] > 1, "loop stopped after the failed tick"
        assert cache.version > 1, "loop never recovered"
    finally:
        await source.stop()


async def test_health_reports_simulator_mode(cache: PriceCache) -> None:
    source = SimulatorDataSource(cache, make_config(), interval=0.01)
    await source.start(["AAPL"])
    try:
        health = source.health()
        assert health.mode == "simulator"
        assert health.connected is True
        assert health.last_success_at is not None
        assert health.age_seconds is not None
    finally:
        await source.stop()


async def test_start_is_idempotent(cache: PriceCache) -> None:
    source = SimulatorDataSource(cache, make_config(), interval=0.01)
    await source.start(["AAPL"])
    try:
        await source.start(["MSFT"])
        assert source.get_tickers() == ["AAPL"]
    finally:
        await source.stop()
