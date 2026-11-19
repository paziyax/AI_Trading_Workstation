"""Service layer: valuation, trade execution, snapshots, prices and chat orchestration.

The API routers stay thin: they validate the wire input, call one service function and map
domain errors to status codes. Everything that touches the database or the LLM lives here.
"""

from __future__ import annotations

from app.services.chat import ChatOutcome, ChatUnavailableError, handle_chat
from app.services.portfolio import (
    DEFAULT_INITIAL_CASH,
    TICKER_PATTERN,
    PriceUnavailableError,
    build_portfolio,
    execute_trade,
    normalize_ticker,
    record_snapshot,
)
from app.services.prices import (
    SessionOpenTracker,
    add_watchlist_ticker,
    build_watchlist,
    remove_watchlist_ticker,
)

__all__ = [
    "DEFAULT_INITIAL_CASH",
    "TICKER_PATTERN",
    "ChatOutcome",
    "ChatUnavailableError",
    "PriceUnavailableError",
    "SessionOpenTracker",
    "add_watchlist_ticker",
    "build_portfolio",
    "build_watchlist",
    "execute_trade",
    "handle_chat",
    "normalize_ticker",
    "record_snapshot",
    "remove_watchlist_ticker",
]
