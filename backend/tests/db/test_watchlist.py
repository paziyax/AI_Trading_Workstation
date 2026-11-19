"""Watchlist: seed order, add/remove semantics, normalization and validation."""

from __future__ import annotations

import uuid
from contextlib import closing
from typing import TYPE_CHECKING

import pytest

from app.db import Database

if TYPE_CHECKING:
    from app.db.repositories import WatchlistRepository

DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]


def test_seed_contains_the_default_tickers_in_order(watchlist: WatchlistRepository) -> None:
    assert watchlist.list_tickers() == DEFAULT_TICKERS


def test_add_appends_and_returns_true(watchlist: WatchlistRepository) -> None:
    assert watchlist.add("PYPL") is True

    tickers = watchlist.list_tickers()
    assert tickers[-1] == "PYPL"
    assert len(tickers) == len(DEFAULT_TICKERS) + 1


def test_add_duplicate_returns_false_and_does_not_duplicate(
    watchlist: WatchlistRepository,
) -> None:
    assert watchlist.add("AAPL") is False

    tickers = watchlist.list_tickers()
    assert tickers == DEFAULT_TICKERS
    assert tickers.count("AAPL") == 1


def test_add_is_case_insensitive_for_duplicates(watchlist: WatchlistRepository) -> None:
    assert watchlist.add("aapl") is False
    assert watchlist.list_tickers() == DEFAULT_TICKERS


def test_add_normalizes_surrounding_whitespace_and_case(
    watchlist: WatchlistRepository,
) -> None:
    assert watchlist.add("  pypl ") is True
    assert watchlist.list_tickers()[-1] == "PYPL"


def test_single_letter_and_dotted_tickers_are_valid(watchlist: WatchlistRepository) -> None:
    assert watchlist.add("A") is True
    assert watchlist.add("BRK.B") is True
    assert watchlist.list_tickers()[-2:] == ["A", "BRK.B"]


def test_remove_returns_true_and_preserves_remaining_order(
    watchlist: WatchlistRepository,
) -> None:
    assert watchlist.remove("MSFT") is True

    assert watchlist.list_tickers() == [
        ticker for ticker in DEFAULT_TICKERS if ticker != "MSFT"
    ]


def test_remove_missing_ticker_returns_false(watchlist: WatchlistRepository) -> None:
    assert watchlist.remove("PYPL") is False
    assert watchlist.remove("AAPL") is True
    assert watchlist.remove("AAPL") is False
    assert watchlist.list_tickers() == [
        ticker for ticker in DEFAULT_TICKERS if ticker != "AAPL"
    ]


def test_remove_normalizes_case(watchlist: WatchlistRepository) -> None:
    assert watchlist.remove("aapl") is True
    assert "AAPL" not in watchlist.list_tickers()


def test_remove_then_add_moves_the_ticker_to_the_end(
    watchlist: WatchlistRepository,
) -> None:
    assert watchlist.remove("MSFT") is True
    assert watchlist.add("MSFT") is True

    tickers = watchlist.list_tickers()
    assert tickers[-1] == "MSFT"
    assert tickers.count("MSFT") == 1
    assert len(tickers) == len(DEFAULT_TICKERS)


@pytest.mark.parametrize(
    "ticker",
    ["", "   ", "1AAPL", "AAPL!", "AA PL", "aa_pl", "TOOLONGTICK"],
)
def test_invalid_tickers_raise_value_error(
    watchlist: WatchlistRepository, ticker: str
) -> None:
    with pytest.raises(ValueError, match="Invalid ticker"):
        watchlist.add(ticker)
    assert watchlist.list_tickers() == DEFAULT_TICKERS


def test_added_tickers_persist_across_instances(db: Database) -> None:
    db.watchlist.add("PYPL")
    db.watchlist.remove("AAPL")

    reopened = Database(db.path)
    reopened.initialize()

    tickers = reopened.watchlist.list_tickers()
    assert tickers[-1] == "PYPL"
    assert "AAPL" not in tickers


def test_seed_rows_have_uuid4_ids(db: Database) -> None:
    with closing(db.connect()) as conn:
        ids = [row["id"] for row in conn.execute("SELECT id FROM watchlist")]
    assert len(ids) == len(DEFAULT_TICKERS)
    assert all(uuid.UUID(identifier).version == 4 for identifier in ids)
