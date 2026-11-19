"""Portfolio valuation, market-order execution and snapshot recording.

All money handed to the API is rounded to 2 dp here (the wire contract), while share
quantities keep full precision in the database and are rounded only for display. A
position whose ticker has no cached price is valued at its average cost, so the portfolio
never reports a phantom loss when a source is still warming up.
"""

from __future__ import annotations

import re
from typing import Any

from app.db import Database, Position, Snapshot, Trade
from app.market.cache import PriceCache

DEFAULT_INITIAL_CASH = 10_000.0

TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


class PriceUnavailableError(LookupError):
    """The price cache has no entry for a ticker; the API maps this to HTTP 400."""


def normalize_ticker(value: str) -> str:
    """Uppercase and validate a ticker, raising ``ValueError`` when malformed."""

    ticker = str(value).strip().upper()
    if not TICKER_PATTERN.fullmatch(ticker):
        raise ValueError(f"Invalid ticker: {value!r}")
    return ticker


def execute_trade(
    repo: Database,
    cache: PriceCache,
    ticker: str,
    side: str,
    quantity: float,
) -> Trade:
    """Fill a market order at the current cache price.

    Validation and atomicity belong to the repository; this function only supplies the
    price (and the friendly error when there is none).
    """

    symbol = normalize_ticker(ticker)
    price = cache.get_price(symbol)
    if price is None:
        raise PriceUnavailableError(f"No market price available for {symbol}")
    return repo.portfolio.execute_trade(symbol, side, quantity, price)


def build_portfolio(
    repo: Database,
    cache: PriceCache,
    *,
    initial_cash: float = DEFAULT_INITIAL_CASH,
) -> dict[str, Any]:
    """The ``GET /api/portfolio`` payload, priced from the cache."""

    profile = repo.portfolio.get_profile()
    cash = round(float(profile.cash_balance), 2)
    rows = [_position_row(position, cache) for position in repo.portfolio.get_positions()]
    rows.sort(key=lambda row: (-row["market_value"], row["ticker"]))

    positions_value = round(sum(row["market_value"] for row in rows), 2)
    total_value = round(cash + positions_value, 2)
    unrealized_pnl = round(sum(row["unrealized_pnl"] for row in rows), 2)
    total_pnl = round(total_value - initial_cash, 2)
    for row in rows:
        row["weight"] = _percent(row["market_value"], total_value, digits=2)

    return {
        "cash_balance": cash,
        "positions_value": positions_value,
        "total_value": total_value,
        "total_pnl": total_pnl,
        "total_pnl_pct": _percent(total_pnl, initial_cash, digits=4),
        "unrealized_pnl": unrealized_pnl,
        "positions": rows,
    }


def record_snapshot(repo: Database, cache: PriceCache) -> Snapshot:
    """Append the current total value to the P&L history."""

    portfolio = build_portfolio(repo, cache)
    return repo.portfolio.add_snapshot(portfolio["total_value"])


def _position_row(position: Position, cache: PriceCache) -> dict[str, Any]:
    cached = cache.get(position.ticker)
    current_price = round(cached.price, 2) if cached is not None else round(position.avg_cost, 2)
    market_value = round(position.quantity * current_price, 2)
    cost_basis = position.avg_cost * position.quantity
    unrealized_pnl = round((current_price - position.avg_cost) * position.quantity, 2)
    return {
        "ticker": position.ticker,
        "quantity": round(position.quantity, 6),
        "avg_cost": round(position.avg_cost, 2),
        "current_price": current_price,
        "market_value": market_value,
        "unrealized_pnl": unrealized_pnl,
        "unrealized_pnl_pct": _percent(unrealized_pnl, cost_basis, digits=4),
        "weight": 0.0,
    }


def _percent(part: float, whole: float, *, digits: int) -> float:
    if not whole:
        return 0.0
    return round(part / whole * 100.0, digits)
