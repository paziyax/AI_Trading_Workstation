"""Session-open tracking and the watchlist service helpers."""

from __future__ import annotations

from app.db import Database
from app.market import PriceCache
from app.services.prices import (
    SessionOpenTracker,
    add_watchlist_ticker,
    build_watchlist,
    remove_watchlist_ticker,
)
from tests.api.conftest import FakeMarketSource


def test_tracker_records_the_first_price_it_sees() -> None:
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    tracker = SessionOpenTracker()

    opens = tracker.observe(cache)

    assert opens == {"AAPL": 190.0}
    assert tracker.open_price("AAPL") == 190.0
    assert tracker.open_price("aapl") == 190.0


def test_tracker_keeps_the_first_price_after_updates() -> None:
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    tracker = SessionOpenTracker()
    tracker.observe(cache)
    cache.update("AAPL", 195.0)

    tracker.observe(cache)

    assert tracker.open_price("AAPL") == 190.0


def test_tracker_returns_none_for_unseen_tickers() -> None:
    tracker = SessionOpenTracker()

    assert tracker.open_price("AAPL") is None
    assert len(tracker) == 0


def test_observe_returns_a_copy() -> None:
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    tracker = SessionOpenTracker()

    opens = tracker.observe(cache)
    opens["AAPL"] = 1.0

    assert tracker.open_price("AAPL") == 190.0


def test_forget_and_clear() -> None:
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    cache.update("MSFT", 420.0)
    tracker = SessionOpenTracker()
    tracker.observe(cache)

    tracker.forget("aapl")
    assert tracker.open_price("AAPL") is None
    assert len(tracker) == 1

    tracker.clear()
    assert len(tracker) == 0


def test_build_watchlist_returns_nulls_without_prices(
    db: Database, cache: PriceCache
) -> None:
    payload = build_watchlist(db, cache, SessionOpenTracker())

    assert len(payload["tickers"]) == 10
    assert payload["tickers"][0] == {
        "ticker": "AAPL",
        "price": None,
        "previous_price": None,
        "change": None,
        "change_pct": None,
        "open_price": None,
        "timestamp": None,
    }


def test_build_watchlist_measures_change_from_the_session_open(
    db: Database, cache: PriceCache
) -> None:
    cache.update("AAPL", 190.0)
    tracker = SessionOpenTracker()
    build_watchlist(db, cache, tracker)
    cache.update("AAPL", 191.0)

    item = build_watchlist(db, cache, tracker)["tickers"][0]

    assert item["price"] == 191.0
    assert item["previous_price"] == 190.0
    assert item["open_price"] == 190.0
    assert item["change"] == 1.0
    assert item["change_pct"] == 0.5263


def test_build_watchlist_preserves_insertion_order(
    db: Database, cache: PriceCache
) -> None:
    payload = build_watchlist(db, cache, SessionOpenTracker())

    assert [item["ticker"] for item in payload["tickers"]] == db.watchlist.list_tickers()


async def test_add_watchlist_ticker_persists_and_notifies_source(
    db: Database, cache: PriceCache
) -> None:
    source = FakeMarketSource().bind(cache)

    added = await add_watchlist_ticker(db, source, "pypl")

    assert added is True
    assert source.added == ["PYPL"]
    assert "PYPL" in db.watchlist.list_tickers()


async def test_add_watchlist_ticker_reports_duplicates(
    db: Database, cache: PriceCache
) -> None:
    source = FakeMarketSource().bind(cache)
    await add_watchlist_ticker(db, source, "PYPL")

    added = await add_watchlist_ticker(db, source, "pypl")

    assert added is False
    assert source.added == ["PYPL"]


async def test_remove_watchlist_ticker_updates_source_and_tracker(
    db: Database, cache: PriceCache
) -> None:
    source = FakeMarketSource().bind(cache)
    cache.update("GOOGL", 175.0)
    tracker = SessionOpenTracker()
    tracker.observe(cache)

    removed = await remove_watchlist_ticker(db, source, "googl", tracker=tracker)

    assert removed is True
    assert source.removed == ["GOOGL"]
    assert tracker.open_price("GOOGL") is None
    assert "GOOGL" not in db.watchlist.list_tickers()


async def test_remove_watchlist_ticker_reports_unknown_tickers(
    db: Database, cache: PriceCache
) -> None:
    source = FakeMarketSource().bind(cache)

    removed = await remove_watchlist_ticker(db, source, "ZZZZ")

    assert removed is False
    assert source.removed == []
