"""Massive source lifecycle: EOD mode, snapshot mode, downgrade, ticker churn."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date, timedelta

import pytest
from massive.exceptions import AuthError, BadResponse

from app.market.cache import PriceCache
from app.market.config import Plan
from app.market.massive_client import MassiveDataSource
from tests.market.conftest import FakeMassiveClient, make_config, row

EOD_DAY = date(2026, 11, 24)  # Tuesday
EOD_ROWS = [row("AAPL", 190.11), row("MSFT", 420.5), row("NVDA", 801.25)]
SNAPSHOT_TS_NS = 1794972600512000000
SNAPSHOT_TS_S = 1794972600.512

NOT_ENTITLED = BadResponse(
    '{"status":"NOT_AUTHORIZED","message":"You are not entitled to this data."}'
)


def day_after(day: date) -> Callable[[], date]:
    return lambda: day + timedelta(days=1)


def eod_source(
    cache: PriceCache,
    client: FakeMassiveClient,
    *,
    today: Callable[[], date] = day_after(EOD_DAY),
) -> MassiveDataSource:
    return MassiveDataSource(
        cache,
        make_config(api_key="key", plan=Plan.BASIC, eod_refresh_seconds=3600),
        client_factory=lambda _: client,
        today=today,
    )


def snapshot_source(
    cache: PriceCache,
    client: FakeMassiveClient,
    *,
    poll_interval: float = 3600.0,
) -> MassiveDataSource:
    return MassiveDataSource(
        cache,
        make_config(api_key="key", plan=Plan.STARTER, poll_interval=poll_interval),
        client_factory=lambda _: client,
        today=day_after(EOD_DAY),
    )


async def wait_until(predicate: Callable[[], bool], timeout: float = 2.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return predicate()


# -- EOD mode ---------------------------------------------------------------


async def test_basic_plan_starts_in_eod_mode_and_seeds_the_cache() -> None:
    cache = PriceCache()
    client = FakeMassiveClient(eod={str(EOD_DAY): EOD_ROWS})
    source = eod_source(cache, client)

    await source.start(["aapl", "MSFT", "NVDA"])
    try:
        assert source.mode == "eod"
        assert source.get_tickers() == ["AAPL", "MSFT", "NVDA"]
        assert cache.get_price("AAPL") == 190.11
        assert cache.snapshot()["NVDA"].source == "eod"
        assert source.health().connected is True
        assert source.health().detail == f"{EOD_DAY.isoformat()} close"
        assert client.calls["snapshot"] == 0
    finally:
        await source.stop()


async def test_eod_ignores_tickers_that_are_not_watched() -> None:
    cache = PriceCache()
    client = FakeMassiveClient(eod={str(EOD_DAY): [*EOD_ROWS, row("TSLA", 250.0)]})

    source = eod_source(cache, client)
    await source.start(["AAPL"])
    try:
        assert set(cache.snapshot()) == {"AAPL"}
    finally:
        await source.stop()


async def test_eod_walks_back_over_a_holiday() -> None:
    cache = PriceCache()
    friday = date(2026, 11, 20)
    thursday = date(2026, 11, 19)
    monday = date(2026, 11, 23)
    client = FakeMassiveClient(
        eod={
            str(friday): [],  # market holiday: HTTP 200, empty result set
            str(thursday): EOD_ROWS,
        }
    )

    source = eod_source(cache, client, today=lambda: monday)
    await source.start(["AAPL", "MSFT"])
    try:
        assert client.calls["eod"] == [str(friday), str(thursday)]
        assert cache.get_price("MSFT") == 420.5
        assert source.health().detail == f"{thursday.isoformat()} close"
    finally:
        await source.stop()


async def test_eod_exhaustion_is_reported_but_does_not_block_startup() -> None:
    cache = PriceCache()
    client = FakeMassiveClient(eod={})
    source = eod_source(cache, client)

    await source.start(["AAPL"])  # must not raise
    try:
        health = source.health()
        assert health.connected is False
        assert health.consecutive_failures == 1
        assert health.last_error is not None
        assert "RuntimeError" in health.last_error
        assert cache.get("AAPL") is None
        assert len(client.calls["eod"]) == 5  # eod_lookback_days
    finally:
        await source.stop()


async def test_eod_does_not_rewrite_unchanged_prices() -> None:
    cache = PriceCache()
    client = FakeMassiveClient(eod={str(EOD_DAY): EOD_ROWS})
    source = eod_source(cache, client)

    await source.start(["AAPL", "MSFT"])
    try:
        version = cache.version
        await source._refresh_eod()  # noqa: SLF001
        assert cache.version == version

        await source._refresh_eod(force=True)  # noqa: SLF001
        assert cache.version == version + 2
    finally:
        await source.stop()


async def test_add_ticker_forces_an_eod_refresh() -> None:
    cache = PriceCache()
    client = FakeMassiveClient(eod={str(EOD_DAY): EOD_ROWS})
    source = eod_source(cache, client)

    await source.start(["AAPL"])
    try:
        assert cache.get("MSFT") is None
        await source.add_ticker("msft")
        assert cache.get_price("MSFT") == 420.5
        assert "MSFT" in source.get_tickers()
    finally:
        await source.stop()


async def test_add_ticker_never_raises_when_the_refresh_fails() -> None:
    cache = PriceCache()
    client = FakeMassiveClient(eod={str(EOD_DAY): EOD_ROWS})
    source = eod_source(cache, client)

    await source.start(["AAPL"])
    try:
        client.eod = {}  # vendor now returns nothing
        await source.add_ticker("MSFT")  # must not raise
        assert "MSFT" in source.get_tickers()
        assert cache.get("MSFT") is None
        assert source.health().consecutive_failures >= 1
    finally:
        await source.stop()


async def test_remove_ticker_evicts_the_cache_and_is_idempotent() -> None:
    cache = PriceCache()
    client = FakeMassiveClient(eod={str(EOD_DAY): EOD_ROWS})
    source = eod_source(cache, client)

    await source.start(["AAPL", "MSFT"])
    try:
        await source.remove_ticker("aapl")
        await source.remove_ticker("AAPL")
        assert source.get_tickers() == ["MSFT"]
        assert cache.get("AAPL") is None
        assert cache.get_price("MSFT") == 420.5
    finally:
        await source.stop()


async def test_start_and_stop_are_idempotent() -> None:
    cache = PriceCache()
    client = FakeMassiveClient(eod={str(EOD_DAY): EOD_ROWS})
    source = eod_source(cache, client)

    await source.start(["AAPL"])
    await source.start(["MSFT"])  # second start is a no-op
    assert source.get_tickers() == ["AAPL"]

    await source.stop()
    version = cache.version
    await source.stop()
    assert cache.version == version


async def test_add_ticker_before_start_only_records_the_ticker() -> None:
    cache = PriceCache()
    client = FakeMassiveClient(eod={str(EOD_DAY): EOD_ROWS})
    source = eod_source(cache, client)

    await source.add_ticker("msft")
    assert source.get_tickers() == ["MSFT"]
    assert cache.get("MSFT") is None


# -- snapshot mode ----------------------------------------------------------


async def test_starter_plan_seeds_from_snapshots_with_second_resolution() -> None:
    cache = PriceCache()
    client = FakeMassiveClient()
    source = snapshot_source(cache, client)

    await source.start(["AAPL", "MSFT"])
    try:
        assert source.mode == "snapshot"
        update = cache.get("AAPL")
        assert update is not None
        assert update.price == 190.12
        assert update.timestamp == pytest.approx(SNAPSHOT_TS_S)
        assert update.source == "snapshot"
        assert client.calls["eod"] == []
    finally:
        await source.stop()


async def test_add_ticker_in_snapshot_mode_arrives_with_the_next_poll() -> None:
    cache = PriceCache()
    client = FakeMassiveClient(prices={"AAPL": 190.0, "MSFT": 420.0})
    source = snapshot_source(cache, client, poll_interval=0.02)

    await source.start(["AAPL"])
    try:
        await source.add_ticker("msft")
        assert "MSFT" in source.get_tickers()
        assert cache.get("MSFT") is None
        assert await wait_until(lambda: cache.get_price("MSFT") == 420.0)
    finally:
        await source.stop()


async def test_snapshot_health_counts_responded_tickers() -> None:
    cache = PriceCache()
    client = FakeMassiveClient(prices={"AAPL": 190.0, "MSFT": 420.0})
    source = snapshot_source(cache, client)

    await source.start(["AAPL", "MSFT", "NVDA"])
    try:
        assert source.health().detail == "2/3 tickers"
        assert cache.get("NVDA") is None
    finally:
        await source.stop()


async def test_lost_entitlement_at_start_downgrades_to_eod() -> None:
    cache = PriceCache()
    client = FakeMassiveClient(
        eod={str(EOD_DAY): EOD_ROWS},
        snapshot_failures=[NOT_ENTITLED],
    )
    source = snapshot_source(cache, client)

    await source.start(["AAPL"])
    try:
        assert source.mode == "eod"
        assert cache.get_price("AAPL") == 190.11
        assert source.health().mode == "eod"
    finally:
        await source.stop()


async def test_lost_entitlement_mid_loop_hands_over_to_eod() -> None:
    cache = PriceCache()
    client = FakeMassiveClient(
        prices={"AAPL": 190.5},
        eod={str(EOD_DAY): [row("AAPL", 189.99)]},
        snapshot_failures=[None, NOT_ENTITLED],
    )
    source = snapshot_source(cache, client, poll_interval=0.01)

    await source.start(["AAPL"])
    try:
        assert source.mode == "snapshot"
        assert cache.get_price("AAPL") == 190.5
        assert await wait_until(lambda: source.mode == "eod" and cache.get_price("AAPL") == 189.99)
    finally:
        await source.stop()


async def test_transient_snapshot_errors_recover() -> None:
    cache = PriceCache()
    transient = BadResponse('{"status":"ERROR","error":"upstream boom"}')
    client = FakeMassiveClient(prices={"AAPL": 190.0}, snapshot_failures=[None, transient])
    source = snapshot_source(cache, client, poll_interval=0.01)
    source._backoff_delay = lambda: 0.01  # type: ignore[method-assign]  # noqa: SLF001

    await source.start(["AAPL"])
    try:
        assert source.health().consecutive_failures == 0
        assert await wait_until(lambda: client.calls["snapshot"] >= 3)
        assert source.health().connected is True
        assert source.health().last_error is None
    finally:
        await source.stop()


async def test_closed_market_skips_snapshot_requests() -> None:
    cache = PriceCache()
    client = FakeMassiveClient(prices={"AAPL": 190.0}, market="closed")
    source = snapshot_source(cache, client, poll_interval=0.01)

    await source.start(["AAPL"])
    try:
        assert client.calls["snapshot"] == 1  # startup seed only
        await asyncio.sleep(0.08)
        assert client.calls["snapshot"] == 1
        assert client.calls["status"] == 1  # status cached for 60 s
        assert source.health().detail == "market closed"
    finally:
        await source.stop()


async def test_auth_failure_on_client_construction_propagates() -> None:
    cache = PriceCache()

    def factory(_: str) -> FakeMassiveClient:
        raise AuthError("bad api key")

    source = MassiveDataSource(
        cache,
        make_config(api_key="nope", plan=Plan.STARTER),
        client_factory=factory,
    )

    with pytest.raises(AuthError):
        await source.start(["AAPL"])

    health = source.health()
    assert health.connected is False
    assert health.consecutive_failures == 1
    assert "AuthError" in (health.last_error or "")
    await source.stop()  # never started: still safe


# -- failure handling -------------------------------------------------------


@pytest.mark.parametrize(
    "failure",
    [BadResponse('{"status":"ERROR","error":"boom"}'), RuntimeError("boom")],
    ids=["bad-response", "unexpected"],
)
async def test_startup_snapshot_failure_degrades_without_crashing(
    failure: BaseException,
) -> None:
    cache = PriceCache()
    client = FakeMassiveClient(prices={"AAPL": 190.0}, snapshot_failures=[failure])
    source = snapshot_source(cache, client)

    await source.start(["AAPL"])  # must not raise
    try:
        assert source.mode == "snapshot"
        health = source.health()
        assert health.connected is False
        assert health.consecutive_failures == 1
        assert cache.get("AAPL") is None
    finally:
        await source.stop()


async def test_unexpected_poll_errors_back_off_then_recover() -> None:
    cache = PriceCache()
    client = FakeMassiveClient(
        prices={"AAPL": 190.0}, snapshot_failures=[None, RuntimeError("boom")]
    )
    source = snapshot_source(cache, client, poll_interval=0.01)
    source._backoff_delay = lambda: 0.01  # type: ignore[method-assign]  # noqa: SLF001

    await source.start(["AAPL"])
    try:
        assert await wait_until(lambda: client.calls["snapshot"] >= 3)
        assert source.health().consecutive_failures == 0
        assert source.health().connected is True
    finally:
        await source.stop()


async def test_mid_loop_downgrade_survives_an_empty_eod_response() -> None:
    cache = PriceCache()
    client = FakeMassiveClient(
        prices={"AAPL": 190.0}, eod={}, snapshot_failures=[None, NOT_ENTITLED]
    )
    source = snapshot_source(cache, client, poll_interval=0.01)

    await source.start(["AAPL"])
    try:
        def handed_over() -> bool:
            task = source._task  # noqa: SLF001
            return (
                source.mode == "eod"
                and task is not None
                and task.get_name() == "massive-eod"
            )

        assert await wait_until(handed_over)
        assert source.health().mode == "eod"
        assert cache.get_price("AAPL") == 190.0  # last good snapshot is held
    finally:
        await source.stop()


async def test_eod_loop_reports_failures_and_recovers() -> None:
    cache = PriceCache()
    client = FakeMassiveClient(eod={str(EOD_DAY): EOD_ROWS})
    source = MassiveDataSource(
        cache,
        # Sub-second refresh is a test-only acceleration.
        make_config(api_key="key", plan=Plan.BASIC, eod_refresh_seconds=0.05),
        client_factory=lambda _: client,
        today=day_after(EOD_DAY),
    )

    await source.start(["AAPL"])
    try:
        client.eod = {}
        assert await wait_until(lambda: source.health().consecutive_failures >= 1)
        assert source.health().connected is False
        assert cache.get_price("AAPL") == 190.11  # stale price is held

        client.eod = {str(EOD_DAY): EOD_ROWS}
        assert await wait_until(lambda: source.health().connected is True)
    finally:
        await source.stop()


async def test_eod_refresh_without_tickers_never_calls_the_vendor() -> None:
    client = FakeMassiveClient()
    source = eod_source(PriceCache(), client)

    await source._refresh_eod()  # noqa: SLF001
    assert client.calls["eod"] == []


# -- retry policy -----------------------------------------------------------


def test_backoff_doubles_and_caps_at_five_minutes() -> None:
    source = eod_source(PriceCache(), FakeMassiveClient())
    assert source._backoff_delay() == 15.0  # noqa: SLF001

    delays = []
    for _ in range(6):
        source._health.failure(RuntimeError("boom"))  # noqa: SLF001
        delays.append(source._backoff_delay())  # noqa: SLF001

    assert delays == [15.0, 30.0, 60.0, 120.0, 240.0, 300.0]


@pytest.mark.parametrize("seconds", [1.0, 15.0, 300.0])
def test_jitter_stays_within_ten_percent(seconds: float) -> None:
    samples = [MassiveDataSource._jitter(seconds) for _ in range(200)]
    assert min(samples) >= seconds * 0.9
    assert max(samples) <= seconds * 1.1
