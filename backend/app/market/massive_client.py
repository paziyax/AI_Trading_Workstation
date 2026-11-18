"""Massive (formerly Polygon.io) REST source.

Two modes, one class: ``snapshot`` polls the multi-ticker snapshot endpoint (Starter and above),
``eod`` fetches one grouped-daily response per session (Basic / free). The class can downgrade
from snapshot to EOD at runtime if the account turns out to lack the entitlement.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from massive import RESTClient
from massive.exceptions import AuthError, BadResponse
from massive.rest.models import SnapshotMarketType

from app.market.cache import PriceCache
from app.market.config import MarketDataConfig
from app.market.interface import HealthTracker, MarketDataSource, SourceHealth
from app.market.models import SourceMode

logger = logging.getLogger(__name__)

NS_THRESHOLD = 10**17
MS_THRESHOLD = 10**12

ClientFactory = Callable[[str], Any]
TodayProvider = Callable[[], date]


def to_unix_seconds(ts: int | None) -> float | None:
    """Normalize a Massive timestamp to Unix seconds.

    Snapshots report nanoseconds (``lastTrade.t``, ``updated``); bars report milliseconds
    (``t``). Dividing nanoseconds by 1e3 yields dates roughly 50,000 years out.
    """
    if ts is None:
        return None
    if ts > NS_THRESHOLD:
        return ts / 1e9
    if ts > MS_THRESHOLD:
        return ts / 1e3
    return float(ts)


def extract_price(snapshot: Any) -> tuple[float, float | None] | None:
    """Best available price for a snapshot, with its timestamp in Unix seconds.

    Precedence: ``lastTrade.p`` -> ``min.c`` -> ``day.c`` -> ``prevDay.c``. Which fields exist
    depends on plan (trades are Developer+) and time of day, so every step is guarded.
    """
    for bar, field in (
        (getattr(snapshot, "last_trade", None), "price"),
        (getattr(snapshot, "min", None), "close"),
        (getattr(snapshot, "day", None), "close"),
        (getattr(snapshot, "prev_day", None), "close"),
    ):
        if bar is None:
            continue
        value = getattr(bar, field, None)
        if value is not None:
            return float(value), to_unix_seconds(getattr(bar, "timestamp", None))
    return None


def is_not_entitled(exc: BadResponse) -> bool:
    """Detect a plan-entitlement failure.

    The client raises ``BadResponse`` with the decoded response body only — there is no status
    code to inspect — so the 403 is identified by the body it actually returns.
    """
    text = str(exc).lower()
    return "not_authorized" in text or "not entitled" in text


def previous_trading_day(start: date) -> date:
    """Step back to the previous weekday. Holidays can only be detected by querying."""
    day = start - timedelta(days=1)
    while day.weekday() >= 5:  # Sat=5, Sun=6
        day -= timedelta(days=1)
    return day


class MassiveDataSource(MarketDataSource):
    name = "massive"

    def __init__(
        self,
        cache: PriceCache,
        config: MarketDataConfig,
        *,
        client_factory: ClientFactory | None = None,
        today: TodayProvider | None = None,
    ) -> None:
        self._cache = cache
        self._config = config
        self._client_factory: ClientFactory = client_factory or (
            lambda api_key: RESTClient(api_key=api_key)
        )
        self._today: TodayProvider = today or date.today
        self._tickers: set[str] = set()
        self._client: Any | None = None
        self._mode: SourceMode = "snapshot" if config.plan.supports_snapshots else "eod"
        self._health = HealthTracker(self._mode)
        self._task: asyncio.Task[None] | None = None
        self._eod_day: date | None = None
        self._market_open = True
        self._status_checked_at: float = 0.0

    # -- introspection ----------------------------------------------------
    @property
    def mode(self) -> SourceMode:
        return self._mode

    def health(self) -> SourceHealth:
        return self._health.health()

    def get_tickers(self) -> list[str]:
        return sorted(self._tickers)

    # -- lifecycle --------------------------------------------------------
    async def start(self, tickers: list[str]) -> None:
        if self._task is not None:
            return
        self._tickers = {t.strip().upper() for t in tickers}

        try:
            self._client = self._client_factory(self._config.api_key)
        except AuthError as exc:
            self._health.failure(exc)
            raise

        if self._mode == "snapshot":
            try:
                await self._refresh_snapshot()
            except BadResponse as exc:
                if is_not_entitled(exc):
                    logger.warning("Snapshot endpoint not entitled; falling back to EOD mode")
                    self._enter_eod_mode()
                else:
                    # A transient failure at startup must not stop the app from booting.
                    logger.warning("Initial snapshot poll failed: %s", exc)
                    self._health.failure(exc)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Initial snapshot poll failed: %s", exc)
                self._health.failure(exc)

        if self._mode == "eod":
            try:
                await self._refresh_eod()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Initial EOD fetch failed: %s", exc)
                self._health.failure(exc)
            self._task = asyncio.create_task(self._eod_loop(), name="massive-eod")
        else:
            self._task = asyncio.create_task(self._poll_loop(), name="massive-poll")

    async def stop(self) -> None:
        if self._task is None:
            return
        task, self._task = self._task, None
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def add_ticker(self, ticker: str) -> None:
        ticker = ticker.strip().upper()
        if ticker in self._tickers:
            return
        self._tickers.add(ticker)
        if self._client is None:
            return
        if self._mode == "eod":
            try:
                await self._refresh_eod(force=True)  # otherwise the row stays blank until tomorrow
            except Exception as exc:  # noqa: BLE001 - never fail a watchlist add
                logger.exception("EOD refresh after add_ticker(%s) failed", ticker)
                self._health.failure(exc)

    async def remove_ticker(self, ticker: str) -> None:
        ticker = ticker.strip().upper()
        self._tickers.discard(ticker)
        self._cache.remove(ticker)

    # -- snapshot mode ----------------------------------------------------
    async def _poll_loop(self) -> None:
        while True:
            delay = self._config.poll_interval
            try:
                if await self._is_market_closed():
                    self._health.note("market closed")
                else:
                    await self._refresh_snapshot()
            except BadResponse as exc:
                if is_not_entitled(exc):
                    logger.warning("Lost snapshot entitlement; switching to EOD mode")
                    self._enter_eod_mode()
                    try:
                        await self._refresh_eod()
                    except Exception:  # noqa: BLE001
                        logger.exception("EOD bootstrap after downgrade failed")
                    # This task is about to end, so hand the loop over explicitly.
                    self._task = asyncio.create_task(self._eod_loop(), name="massive-eod")
                    return
                self._health.failure(exc)
                delay = self._backoff_delay()
            except Exception as exc:  # noqa: BLE001
                logger.exception("snapshot poll failed")
                self._health.failure(exc)
                delay = self._backoff_delay()
            await asyncio.sleep(self._jitter(delay))

    async def _refresh_snapshot(self) -> None:
        batch = await asyncio.to_thread(self._fetch_snapshot_batch)
        for ticker, (price, ts) in batch.items():
            self._cache.update(ticker, price, source="snapshot", timestamp=ts)
        self._health.success(f"{len(batch)}/{len(self._tickers)} tickers")

    def _fetch_snapshot_batch(self) -> dict[str, tuple[float, float | None]]:
        snaps = self._client.get_snapshot_all(
            market_type=SnapshotMarketType.STOCKS, tickers=sorted(self._tickers)
        )
        out: dict[str, tuple[float, float | None]] = {}
        for snap in snaps or []:
            extracted = extract_price(snap)
            ticker = getattr(snap, "ticker", None)
            if extracted is not None and ticker:
                out[ticker] = extracted
        return out

    async def _is_market_closed(self) -> bool:
        now = time.monotonic()
        if now - self._status_checked_at < 60:
            return not self._market_open
        status = await asyncio.to_thread(self._client.get_market_status)
        self._market_open = status.market in {"open", "extended-hours"}
        self._status_checked_at = now
        return not self._market_open

    # -- EOD mode ---------------------------------------------------------
    async def _eod_loop(self) -> None:
        while True:
            await asyncio.sleep(self._config.eod_refresh_seconds)
            try:
                await self._refresh_eod()
            except Exception as exc:  # noqa: BLE001
                logger.exception("EOD refresh failed")
                self._health.failure(exc)

    async def _refresh_eod(self, *, force: bool = False) -> None:
        if not self._tickers:
            return
        day, prices = await asyncio.to_thread(self._fetch_eod)
        stale = force or self._eod_day != day or any(
            self._cache.get(t) is None for t in self._tickers
        )
        if stale:
            for ticker, price in prices.items():
                self._cache.update(ticker, price, source="eod")
            self._eod_day = day
        self._health.success(f"{day.isoformat()} close")

    def _fetch_eod(self) -> tuple[date, dict[str, float]]:
        wanted = set(self._tickers)
        day = previous_trading_day(self._today())

        # A non-trading date is HTTP 200 with an empty result set, so emptiness — not an
        # exception — is the signal to step back another day.
        for _ in range(self._config.eod_lookback_days):
            rows = self._client.get_grouped_daily_aggs(date=day.isoformat(), adjusted=True)
            prices = {
                row.ticker: row.close
                for row in rows or []
                if row.ticker in wanted and row.close is not None
            }
            if prices:
                return day, prices
            day = previous_trading_day(day)

        raise RuntimeError(
            f"No grouped-daily data in the last {self._config.eod_lookback_days} sessions"
        )

    def _enter_eod_mode(self) -> None:
        self._mode = "eod"
        self._health.set_mode("eod")

    # -- helpers ----------------------------------------------------------
    def _backoff_delay(self) -> float:
        failures = max(1, self._health.consecutive_failures)
        return min(300.0, 15.0 * (2 ** (failures - 1)))

    @staticmethod
    def _jitter(seconds: float) -> float:
        return seconds * random.uniform(0.9, 1.1)
