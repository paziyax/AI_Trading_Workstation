"""Trade execution: math, validation, exact error messages and atomic rollback."""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING

import pytest

from app.db.errors import DatabaseError, TradeError
from app.db.models import Position, Trade

if TYPE_CHECKING:
    from app.db.repositories import PortfolioRepository

T1 = "2026-11-19T15:00:00Z"
T2 = "2026-11-19T15:01:00Z"
T3 = "2026-11-19T15:02:00Z"
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def test_buy_creates_position_and_debits_cash(portfolio: PortfolioRepository) -> None:
    trade = portfolio.execute_trade("AAPL", "buy", 10, 190.0, now=T1)

    assert portfolio.get_profile().cash_balance == 8100.0
    assert portfolio.get_position("AAPL") == Position(
        ticker="AAPL", quantity=10.0, avg_cost=190.0, updated_at=T1
    )
    assert trade == Trade(
        id=trade.id,
        ticker="AAPL",
        side="buy",
        quantity=10.0,
        price=190.0,
        executed_at=T1,
    )
    assert trade.to_dict() == {
        "id": trade.id,
        "ticker": "AAPL",
        "side": "buy",
        "quantity": 10.0,
        "price": 190.0,
        "executed_at": T1,
    }
    assert portfolio.list_trades() == [trade]


def test_buy_normalizes_ticker_and_side(portfolio: PortfolioRepository) -> None:
    trade = portfolio.execute_trade("  aapl ", "BUY", 1, 100.0, now=T1)
    assert trade.ticker == "AAPL"
    assert trade.side == "buy"
    assert portfolio.get_position("aapl") is not None


def test_weighted_average_cost_across_two_buys(portfolio: PortfolioRepository) -> None:
    portfolio.execute_trade("AAPL", "buy", 10, 100.0, now=T1)
    portfolio.execute_trade("AAPL", "buy", 5, 130.0, now=T2)

    position = portfolio.get_position("AAPL")
    assert position is not None
    assert position.quantity == 15.0
    assert position.avg_cost == 110.0
    assert position.updated_at == T2
    assert portfolio.get_profile().cash_balance == 8350.0


def test_weighted_average_cost_rounds_to_six_decimals(portfolio: PortfolioRepository) -> None:
    portfolio.execute_trade("AAPL", "buy", 1, 3.0, now=T1)
    portfolio.execute_trade("AAPL", "buy", 2, 4.0, now=T2)

    position = portfolio.get_position("AAPL")
    assert position is not None
    assert position.avg_cost == round(11 / 3, 6)


def test_fractional_buy_keeps_full_precision(portfolio: PortfolioRepository) -> None:
    portfolio.execute_trade("AAPL", "buy", 1.25, 100.0, now=T1)

    position = portfolio.get_position("AAPL")
    assert position is not None
    assert position.quantity == 1.25
    assert portfolio.get_profile().cash_balance == 9875.0


def test_buy_rounds_cost_to_cents(portfolio: PortfolioRepository) -> None:
    portfolio.execute_trade("AAPL", "buy", 3, 33.333, now=T1)

    assert portfolio.get_profile().cash_balance == 9900.0
    position = portfolio.get_position("AAPL")
    assert position is not None
    assert position.avg_cost == 33.333


def test_buy_for_exactly_all_cash_succeeds(portfolio: PortfolioRepository) -> None:
    portfolio.execute_trade("AAPL", "buy", 100, 100.0, now=T1)

    assert portfolio.get_profile().cash_balance == 0.0
    position = portfolio.get_position("AAPL")
    assert position is not None
    assert position.quantity == 100.0


def test_insufficient_cash_uses_exact_message(portfolio: PortfolioRepository) -> None:
    with pytest.raises(TradeError) as excinfo:
        portfolio.execute_trade("AAPL", "buy", 10, 2000.0, now=T1)

    assert str(excinfo.value) == "Insufficient cash: need $20,000.00, available $10,000.00"
    assert portfolio.get_profile().cash_balance == 10000.0
    assert portfolio.get_positions() == []
    assert portfolio.list_trades() == []


def test_failed_buy_rolls_back_position_and_cash(portfolio: PortfolioRepository) -> None:
    portfolio.execute_trade("AAPL", "buy", 1, 100.0, now=T1)

    with pytest.raises(TradeError):
        portfolio.execute_trade("AAPL", "buy", 1000, 100.0, now=T2)

    assert portfolio.get_profile().cash_balance == 9900.0
    position = portfolio.get_position("AAPL")
    assert position is not None
    assert position.quantity == 1.0
    assert len(portfolio.list_trades()) == 1


def test_sell_partial_updates_quantity_and_keeps_avg_cost(
    portfolio: PortfolioRepository,
) -> None:
    buy = portfolio.execute_trade("AAPL", "buy", 10, 100.0, now=T1)
    sell = portfolio.execute_trade("AAPL", "sell", 4, 120.0, now=T2)

    assert sell.side == "sell"
    assert portfolio.get_profile().cash_balance == 9480.0
    position = portfolio.get_position("AAPL")
    assert position is not None
    assert position.quantity == 6.0
    assert position.avg_cost == 100.0
    assert position.updated_at == T2
    assert [trade.id for trade in portfolio.list_trades()] == [sell.id, buy.id]


def test_sell_all_deletes_the_position(portfolio: PortfolioRepository) -> None:
    portfolio.execute_trade("AAPL", "buy", 10, 100.0, now=T1)
    portfolio.execute_trade("AAPL", "sell", 10, 90.0, now=T2)

    assert portfolio.get_position("AAPL") is None
    assert portfolio.get_positions() == []
    assert portfolio.get_profile().cash_balance == 9900.0


def test_sell_float_dust_remainder_deletes_the_position(
    portfolio: PortfolioRepository,
) -> None:
    portfolio.execute_trade("AAPL", "buy", 0.3, 100.0, now=T1)
    portfolio.execute_trade("AAPL", "sell", 0.1, 100.0, now=T2)
    portfolio.execute_trade("AAPL", "sell", 0.2, 100.0, now=T3)

    assert portfolio.get_position("AAPL") is None
    assert portfolio.get_profile().cash_balance == 10000.0


def test_sell_without_a_position_uses_exact_message(portfolio: PortfolioRepository) -> None:
    with pytest.raises(TradeError) as excinfo:
        portfolio.execute_trade("TSLA", "sell", 1, 100.0, now=T1)

    assert str(excinfo.value) == "No position in TSLA to sell"
    assert portfolio.get_profile().cash_balance == 10000.0
    assert portfolio.list_trades() == []


def test_oversell_uses_exact_message_and_rolls_back(portfolio: PortfolioRepository) -> None:
    portfolio.execute_trade("AAPL", "buy", 5, 100.0, now=T1)

    with pytest.raises(TradeError) as excinfo:
        portfolio.execute_trade("AAPL", "sell", 10, 100.0, now=T2)

    assert str(excinfo.value) == "Cannot sell 10 AAPL: only 5 owned"
    assert portfolio.get_profile().cash_balance == 9500.0
    position = portfolio.get_position("AAPL")
    assert position is not None
    assert position.quantity == 5.0
    assert len(portfolio.list_trades()) == 1


def test_fractional_oversell_message_uses_compact_numbers(
    portfolio: PortfolioRepository,
) -> None:
    portfolio.execute_trade("AAPL", "buy", 0.25, 100.0, now=T1)

    with pytest.raises(TradeError) as excinfo:
        portfolio.execute_trade("AAPL", "sell", 0.5, 100.0, now=T2)

    assert str(excinfo.value) == "Cannot sell 0.5 AAPL: only 0.25 owned"


def test_sell_rounds_proceeds_to_cents(portfolio: PortfolioRepository) -> None:
    portfolio.execute_trade("AAPL", "buy", 1, 100.0, now=T1)
    portfolio.execute_trade("AAPL", "sell", 1, 33.333, now=T2)

    assert portfolio.get_profile().cash_balance == 9933.33
    assert portfolio.get_position("AAPL") is None


def test_buy_after_partial_sell_weights_against_remaining_quantity(
    portfolio: PortfolioRepository,
) -> None:
    portfolio.execute_trade("AAPL", "buy", 10, 100.0, now=T1)
    portfolio.execute_trade("AAPL", "sell", 4, 110.0, now=T2)
    portfolio.execute_trade("AAPL", "buy", 4, 130.0, now=T3)

    position = portfolio.get_position("AAPL")
    assert position is not None
    assert position.quantity == 10.0
    assert position.avg_cost == 112.0
    assert portfolio.get_profile().cash_balance == 8920.0


def test_invalid_side_raises_value_error(portfolio: PortfolioRepository) -> None:
    with pytest.raises(ValueError, match="Invalid side"):
        portfolio.execute_trade("AAPL", "hold", 1, 100.0)


@pytest.mark.parametrize("quantity", [0, -1.5, float("nan"), float("inf")])
def test_invalid_quantity_raises_value_error(
    portfolio: PortfolioRepository, quantity: float
) -> None:
    with pytest.raises(ValueError, match="Quantity"):
        portfolio.execute_trade("AAPL", "buy", quantity, 100.0)


@pytest.mark.parametrize("price", [0, -0.01, float("nan"), float("inf")])
def test_invalid_price_raises_value_error(portfolio: PortfolioRepository, price: float) -> None:
    with pytest.raises(ValueError, match="Price"):
        portfolio.execute_trade("AAPL", "buy", 1, price)


def test_trade_timestamps_default_to_utc_now(portfolio: PortfolioRepository) -> None:
    trade = portfolio.execute_trade("AAPL", "buy", 1, 100.0)

    assert TIMESTAMP_RE.match(trade.executed_at)
    position = portfolio.get_position("AAPL")
    assert position is not None
    assert position.updated_at == trade.executed_at


def test_trade_ids_are_unique_uuid4(portfolio: PortfolioRepository) -> None:
    first = portfolio.execute_trade("AAPL", "buy", 1, 10.0, now=T1)
    second = portfolio.execute_trade("MSFT", "buy", 1, 20.0, now=T2)

    assert first.id != second.id
    assert uuid.UUID(first.id).version == 4
    assert uuid.UUID(second.id).version == 4


def test_trade_log_is_newest_first_and_limited(portfolio: PortfolioRepository) -> None:
    for timestamp, price in ((T1, 100.0), (T2, 101.0), (T3, 102.0)):
        portfolio.execute_trade("AAPL", "buy", 1, price, now=timestamp)

    assert [trade.executed_at for trade in portfolio.list_trades()] == [T3, T2, T1]
    assert [trade.executed_at for trade in portfolio.list_trades(limit=2)] == [T3, T2]
    assert portfolio.list_trades(limit=0) == []


def test_execute_trade_does_not_write_a_snapshot(portfolio: PortfolioRepository) -> None:
    portfolio.execute_trade("AAPL", "buy", 1, 100.0, now=T1)
    assert portfolio.list_snapshots() == []


def test_trade_error_is_a_database_error() -> None:
    assert issubclass(TradeError, DatabaseError)
