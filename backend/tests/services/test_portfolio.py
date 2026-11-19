"""Valuation, market orders and snapshots without the HTTP layer."""

from __future__ import annotations

import pytest

from app.db import Database, TradeError
from app.market import PriceCache
from app.services.portfolio import (
    DEFAULT_INITIAL_CASH,
    PriceUnavailableError,
    build_portfolio,
    execute_trade,
    record_snapshot,
)


def test_empty_account_returns_the_seeded_cash(db: Database, cache: PriceCache) -> None:
    portfolio = build_portfolio(db, cache)

    assert portfolio == {
        "cash_balance": 10_000.0,
        "positions_value": 0.0,
        "total_value": 10_000.0,
        "total_pnl": 0.0,
        "total_pnl_pct": 0.0,
        "unrealized_pnl": 0.0,
        "positions": [],
    }


def test_valuation_matches_the_documented_contract_example(
    db: Database, cache: PriceCache
) -> None:
    cache.update("AAPL", 190.0)
    execute_trade(db, cache, "AAPL", "buy", 10)
    cache.update("AAPL", 191.0)

    portfolio = build_portfolio(db, cache)

    assert portfolio["cash_balance"] == 8100.0
    assert portfolio["positions_value"] == 1910.0
    assert portfolio["total_value"] == 10_010.0
    assert portfolio["total_pnl"] == 10.0
    assert portfolio["total_pnl_pct"] == 0.1
    assert portfolio["unrealized_pnl"] == 10.0
    assert portfolio["positions"] == [
        {
            "ticker": "AAPL",
            "quantity": 10.0,
            "avg_cost": 190.0,
            "current_price": 191.0,
            "market_value": 1910.0,
            "unrealized_pnl": 10.0,
            "unrealized_pnl_pct": 0.5263,
            "weight": 19.08,
        }
    ]


def test_missing_prices_fall_back_to_the_average_cost(
    db: Database, cache: PriceCache
) -> None:
    cache.update("AAPL", 190.0)
    execute_trade(db, cache, "AAPL", "buy", 10)
    cache.remove("AAPL")

    position = build_portfolio(db, cache)["positions"][0]

    assert position["current_price"] == 190.0
    assert position["market_value"] == 1900.0
    assert position["unrealized_pnl"] == 0.0
    assert position["unrealized_pnl_pct"] == 0.0


def test_positions_are_sorted_by_market_value_descending(
    db: Database, cache: PriceCache
) -> None:
    for ticker, price, quantity in [
        ("AAPL", 190.0, 2),
        ("NVDA", 500.0, 2),
        ("MSFT", 420.0, 1),
    ]:
        cache.update(ticker, price)
        execute_trade(db, cache, ticker, "buy", quantity)

    positions = build_portfolio(db, cache)["positions"]

    assert [position["ticker"] for position in positions] == ["NVDA", "MSFT", "AAPL"]
    assert [position["market_value"] for position in positions] == [1000.0, 420.0, 380.0]


def test_weights_are_percent_of_total_value(db: Database, cache: PriceCache) -> None:
    cache.update("AAPL", 190.0)
    execute_trade(db, cache, "AAPL", "buy", 10)
    cache.update("NVDA", 500.0)
    execute_trade(db, cache, "NVDA", "buy", 2)

    portfolio = build_portfolio(db, cache)
    weights = [position["weight"] for position in portfolio["positions"]]

    assert weights == [19.0, 10.0]
    assert portfolio["total_value"] == 10_000.0


def test_initial_cash_override_changes_pnl(db: Database, cache: PriceCache) -> None:
    portfolio = build_portfolio(db, cache, initial_cash=5_000.0)

    assert portfolio["total_pnl"] == 5_000.0
    assert portfolio["total_pnl_pct"] == 100.0


def test_percentages_use_four_decimals(db: Database, cache: PriceCache) -> None:
    cache.update("AAPL", 190.126)
    execute_trade(db, cache, "AAPL", "buy", 3)
    cache.update("AAPL", 191.111)

    position = build_portfolio(db, cache)["positions"][0]

    assert position["avg_cost"] == 190.13
    assert position["unrealized_pnl"] == 2.94
    assert position["unrealized_pnl_pct"] == round(2.94 / (190.13 * 3) * 100, 4)


def test_execute_trade_fills_at_the_cache_price(db: Database, cache: PriceCache) -> None:
    cache.update("AAPL", 190.42)

    trade = execute_trade(db, cache, "aapl", "buy", 1.5)

    assert trade.ticker == "AAPL"
    assert trade.price == 190.42
    assert trade.quantity == 1.5
    assert db.portfolio.get_profile().cash_balance == 9714.37


def test_execute_trade_without_a_price_raises(db: Database, cache: PriceCache) -> None:
    with pytest.raises(PriceUnavailableError, match="No market price available for AAPL"):
        execute_trade(db, cache, "AAPL", "buy", 1)


def test_execute_trade_propagates_domain_errors(db: Database, cache: PriceCache) -> None:
    cache.update("AAPL", 190.0)

    with pytest.raises(TradeError, match="Insufficient cash"):
        execute_trade(db, cache, "AAPL", "buy", 100)

    assert db.portfolio.get_positions() == []


def test_record_snapshot_uses_the_valuation(db: Database, cache: PriceCache) -> None:
    cache.update("AAPL", 190.0)
    execute_trade(db, cache, "AAPL", "buy", 10)
    cache.update("AAPL", 200.0)

    snapshot = record_snapshot(db, cache)

    assert snapshot.total_value == 10_100.0
    assert [point.total_value for point in db.portfolio.list_snapshots(10)] == [10_100.0]


def test_record_snapshot_counts_cash_when_no_prices_exist(
    db: Database, cache: PriceCache
) -> None:
    snapshot = record_snapshot(db, cache)

    assert snapshot.total_value == DEFAULT_INITIAL_CASH
