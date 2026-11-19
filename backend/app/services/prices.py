"""Session-open tracking and the watchlist read model.

``open_price`` is the first price this API process observed for a ticker, not a vendor
session open: the simulator and the Massive source are both agnostic to trading sessions,
and the frontend only needs a stable reference for the "change" column. The tracker is
thread-safe because the Massive source writes the cache from ``asyncio.to_thread``.

The add/remove helpers are shared by the REST routes and the chat orchestration so a ticker
requested by the assistant goes through exactly the same repository and source calls as a
manual edit.
"""

from __future__ import annotations

import threading

from app.db import Database
from app.market.cache import PriceCache
from app.market.interface import MarketDataSource
from app.services.portfolio import normalize_ticker


class SessionOpenTracker:
    """First observed price per ticker for the lifetime of this process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._opens: dict[str, float] = {}

    def observe(self, cache: PriceCache) -> dict[str, float]:
        """Record every not-yet-seen price in ``cache`` and return a copy of all opens."""

        snapshot = cache.snapshot()
        with self._lock:
            for ticker, update in snapshot.items():
                self._opens.setdefault(ticker.strip().upper(), update.price)
            return dict(self._opens)

    def open_price(self, ticker: str) -> float | None:
        with self._lock:
            return self._opens.get(str(ticker).strip().upper())

    def forget(self, ticker: str) -> None:
        """Drop one ticker so a later re-add starts a fresh session."""

        with self._lock:
            self._opens.pop(str(ticker).strip().upper(), None)

    def clear(self) -> None:
        with self._lock:
            self._opens.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._opens)


def build_watchlist(
    repo: Database,
    cache: PriceCache,
    tracker: SessionOpenTracker,
) -> dict[str, list[dict[str, object]]]:
    """The ``GET /api/watchlist`` payload, in insertion order."""

    opens = tracker.observe(cache)
    items: list[dict[str, object]] = []
    for ticker in repo.watchlist.list_tickers():
        items.append(_watchlist_item(ticker, cache, opens.get(ticker)))
    return {"tickers": items}


def _watchlist_item(
    ticker: str,
    cache: PriceCache,
    open_price: float | None,
) -> dict[str, object]:
    update = cache.get(ticker)
    if update is None or open_price is None:
        return {
            "ticker": ticker,
            "price": None,
            "previous_price": None,
            "change": None,
            "change_pct": None,
            "open_price": None,
            "timestamp": None,
        }

    price = round(update.price, 2)
    open_value = round(float(open_price), 2)
    change = round(price - open_value, 2)
    change_pct = round(change / open_value * 100.0, 4) if open_value else 0.0
    return {
        "ticker": ticker,
        "price": price,
        "previous_price": round(update.previous_price, 2),
        "change": change,
        "change_pct": change_pct,
        "open_price": open_value,
        "timestamp": update.timestamp,
    }


async def add_watchlist_ticker(
    repo: Database,
    source: MarketDataSource | None,
    ticker: str,
) -> bool:
    """Persist a ticker and tell the source about it; ``False`` means already present."""

    symbol = normalize_ticker(ticker)
    if not repo.watchlist.add(symbol):
        return False
    if source is not None:
        await source.add_ticker(symbol)
    return True


async def remove_watchlist_ticker(
    repo: Database,
    source: MarketDataSource | None,
    ticker: str,
    *,
    tracker: SessionOpenTracker | None = None,
) -> bool:
    """Remove a ticker everywhere; ``False`` means it was not watched."""

    symbol = normalize_ticker(ticker)
    if not repo.watchlist.remove(symbol):
        return False
    if source is not None:
        await source.remove_ticker(symbol)
    if tracker is not None:
        tracker.forget(symbol)
    return True
