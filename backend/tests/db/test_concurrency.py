"""Sequential concurrency smoke tests: independent connections share one consistent ledger."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from app.db import Database

if TYPE_CHECKING:
    from app.db.repositories import PortfolioRepository

T1 = "2026-11-19T15:00:00Z"
T2 = "2026-11-19T15:01:00Z"


def test_trades_from_two_instances_keep_cash_consistent(tmp_path: Path) -> None:
    path = tmp_path / "finally.db"
    first = Database(path)
    first.initialize()
    second = Database(path)
    second.initialize()

    buy = first.portfolio.execute_trade("AAPL", "buy", 10, 100.0, now=T1)
    sell = second.portfolio.execute_trade("AAPL", "sell", 4, 110.0, now=T2)

    assert first.portfolio.get_profile().cash_balance == 9440.0
    assert second.portfolio.get_profile().cash_balance == 9440.0

    position = second.portfolio.get_position("AAPL")
    assert position is not None
    assert position.quantity == 6.0
    assert position.avg_cost == 100.0

    assert second.portfolio.list_trades() == [sell, buy]


def test_many_sequential_trades_sum_to_the_expected_cash(
    portfolio: PortfolioRepository,
) -> None:
    for index in range(20):
        portfolio.execute_trade("AAPL", "buy", 1, 100.0, now=f"2026-11-19T15:{index:02d}:00Z")
    for index in range(5):
        portfolio.execute_trade("AAPL", "sell", 1, 100.0, now=f"2026-11-19T16:{index:02d}:00Z")

    assert portfolio.get_profile().cash_balance == 8500.0
    position = portfolio.get_position("AAPL")
    assert position is not None
    assert position.quantity == 15.0
    assert len(portfolio.list_trades()) == 25
