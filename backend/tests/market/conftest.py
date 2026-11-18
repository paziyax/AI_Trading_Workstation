"""Shared fixtures and test doubles for the market data suite."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

from app.market.config import MarketDataConfig, Plan

DEFAULT_TICKERS = ["AAPL", "MSFT", "NVDA"]
TRADING_DAY = date(2026, 11, 25)  # Wednesday before Thanksgiving 2026


def make_config(**overrides: Any) -> MarketDataConfig:
    base = {
        "api_key": "",
        "plan": Plan.BASIC,
        "source": "auto",
        "poll_interval": 15.0,
        "event_probability": 0.0,
        "eod_refresh_seconds": 1800,
        "eod_lookback_days": 5,
    }
    return MarketDataConfig(**{**base, **overrides})


def bar(**fields: Any) -> SimpleNamespace:
    return SimpleNamespace(**fields)


def snapshot(
    ticker: str,
    *,
    last_trade: Any = None,
    minute: Any = None,
    day: Any = None,
    prev_day: Any = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        ticker=ticker,
        last_trade=last_trade,
        min=minute,
        day=day,
        prev_day=prev_day,
    )


def row(ticker: str, close: float) -> SimpleNamespace:
    return SimpleNamespace(ticker=ticker, close=close)


class FakeMassiveClient:
    """Stands in for ``massive.RESTClient``.

    ``snapshot_failures`` is a list of exceptions to raise on consecutive snapshot calls (None
    means "succeed"); once the list is exhausted the client succeeds.
    """

    def __init__(
        self,
        *,
        prices: dict[str, float] | None = None,
        eod: dict[str, list[SimpleNamespace]] | None = None,
        market: str = "open",
        snapshot_failures: list[BaseException | None] | None = None,
    ) -> None:
        self.prices = prices or {"AAPL": 190.12, "MSFT": 420.5, "NVDA": 801.25}
        self.eod = eod or {}
        self.market = market
        self.snapshot_failures = list(snapshot_failures or [])
        self.calls = {"snapshot": 0, "eod": [], "status": 0}

    def _next_snapshot_failure(self) -> BaseException | None:
        self.calls["snapshot"] += 1
        if self.snapshot_failures:
            return self.snapshot_failures.pop(0)
        return None

    def get_snapshot_all(self, market_type: Any = None, tickers: Any = None) -> list[Any]:
        failure = self._next_snapshot_failure()
        if failure is not None:
            raise failure
        wanted = [tickers] if isinstance(tickers, str) else list(tickers or self.prices)
        return [
            snapshot(
                ticker,
                last_trade=bar(price=self.prices[ticker], timestamp=1794972600512000000),
                minute=bar(close=self.prices[ticker], timestamp=1794972600000),
                day=bar(close=self.prices[ticker], timestamp=1794972600000),
            )
            for ticker in wanted
            if ticker in self.prices
        ]

    def get_grouped_daily_aggs(self, date: Any, adjusted: bool = True) -> list[Any]:
        self.calls["eod"].append(date)
        return list(self.eod.get(str(date), []))

    def get_market_status(self) -> SimpleNamespace:
        self.calls["status"] += 1
        return SimpleNamespace(market=self.market)
