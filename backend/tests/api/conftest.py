"""Fixtures and doubles for the HTTP suite: no network, no sleeping, no real market."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.llm import LLMResponse, TradeAction, WatchlistChange
from app.main import create_app
from app.market import MarketDataSource, PriceCache, SourceHealth
from app.market.interface import HealthTracker

DEFAULT_PRICES: dict[str, float] = {
    "AAPL": 190.0,
    "GOOGL": 175.0,
    "MSFT": 420.0,
    "AMZN": 185.0,
    "TSLA": 250.0,
    "NVDA": 500.0,
    "META": 600.0,
    "JPM": 200.0,
    "V": 290.0,
    "NFLX": 700.0,
}
NEW_TICKER_PRICE = 100.0
SEED_TICKERS = list(DEFAULT_PRICES)


class FakeMarketSource(MarketDataSource):
    """In-memory source that writes to the app cache and records every lifecycle call."""

    name = "fake"

    def __init__(self, prices: dict[str, float] | None = None) -> None:
        self.prices = dict(DEFAULT_PRICES if prices is None else prices)
        self.cache: PriceCache | None = None
        self.started_with: list[str] = []
        self.added: list[str] = []
        self.removed: list[str] = []
        self.starts = 0
        self.stops = 0
        self.start_error: BaseException | None = None
        self._health = HealthTracker("simulator", "fake")

    def bind(self, cache: PriceCache) -> FakeMarketSource:
        self.cache = cache
        return self

    @property
    def mode(self) -> str:
        return "simulator"

    async def start(self, tickers: list[str]) -> None:
        self.starts += 1
        self.started_with = list(tickers)
        if self.start_error is not None:
            self._health.failure(self.start_error)
            raise self.start_error
        for ticker in tickers:
            self.publish(ticker)
        self._health.success()

    async def stop(self) -> None:
        self.stops += 1

    async def add_ticker(self, ticker: str) -> None:
        symbol = ticker.strip().upper()
        self.added.append(symbol)
        self.prices.setdefault(symbol, NEW_TICKER_PRICE)
        self.publish(symbol)

    async def remove_ticker(self, ticker: str) -> None:
        symbol = ticker.strip().upper()
        self.removed.append(symbol)
        self.prices.pop(symbol, None)
        if self.cache is not None:
            self.cache.remove(symbol)

    def get_tickers(self) -> list[str]:
        return list(self.prices)

    def health(self) -> SourceHealth:
        return self._health.health()

    def publish(self, ticker: str, price: float | None = None) -> None:
        """Push a price into the cache (and remember it for later restarts)."""

        symbol = ticker.strip().upper()
        if price is not None:
            self.prices[symbol] = price
        if self.cache is not None:
            self.cache.update(symbol, self.prices[symbol], source="simulator")


class StubChatClient:
    """ChatClient double: records calls, returns a canned structured response."""

    def __init__(
        self,
        response: LLMResponse | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.response = response if response is not None else chat_response()
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        *,
        user_message: str,
        context: str,
        portfolio: dict,
        history: list[tuple[str, str]],
    ) -> LLMResponse:
        self.calls.append(
            {
                "user_message": user_message,
                "context": context,
                "portfolio": portfolio,
                "history": list(history),
            }
        )
        if self.error is not None:
            raise self.error
        return self.response


def chat_response(
    message: str = "[stub] Done.",
    trades: list[TradeAction] | None = None,
    changes: list[WatchlistChange] | None = None,
) -> LLMResponse:
    return LLMResponse(
        message=message,
        trades=trades or [],
        watchlist_changes=changes or [],
    )


def buy(ticker: str, quantity: float) -> TradeAction:
    return TradeAction(ticker=ticker, side="buy", quantity=quantity)


def sell(ticker: str, quantity: float) -> TradeAction:
    return TradeAction(ticker=ticker, side="sell", quantity=quantity)


def build_app(
    settings: Settings,
    *,
    source: FakeMarketSource | None = None,
    chat_client: StubChatClient | None = None,
) -> FastAPI:
    """Create an app and bind the fake source to the app's cache."""

    application = create_app(settings=settings, source=source, chat_client=chat_client)
    if source is not None:
        source.bind(application.state.cache)
    return application


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        db_path=tmp_path / "db" / "finally.db",
        static_dir=tmp_path / "static-missing",
        initial_cash=10_000.0,
        snapshot_interval=3600.0,
    )


@pytest.fixture
def source() -> FakeMarketSource:
    return FakeMarketSource()


@pytest.fixture
def chat_client() -> StubChatClient:
    return StubChatClient()


@pytest.fixture
def app(settings: Settings, source: FakeMarketSource, chat_client: StubChatClient) -> FastAPI:
    return build_app(settings, source=source, chat_client=chat_client)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
