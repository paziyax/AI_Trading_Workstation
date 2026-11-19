"""Chat orchestration: one assistant turn, its side effects and the transcript.

The flow is deliberately linear and mirrors the REST endpoints:

1. read the transcript *before* the new user message is stored;
2. build the portfolio and watchlist payloads fresh, then render the prompt context;
3. call the client (mock or live) once, with structured output;
4. execute every requested action through the same services as the REST routes,
   recording a per-action outcome instead of aborting on the first failure;
5. persist both turns, then return the refreshed portfolio.

No action failure can turn a successful model reply into an HTTP error; only an
unavailable assistant (``LLMError``) does, and even then the user message is kept.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.db import Database, DatabaseError
from app.llm import (
    ChatClient,
    LLMError,
    LLMResponse,
    TradeAction,
    WatchlistChange,
    build_context,
)
from app.market.cache import PriceCache
from app.market.interface import MarketDataSource
from app.services.portfolio import (
    DEFAULT_INITIAL_CASH,
    PriceUnavailableError,
    build_portfolio,
    execute_trade,
    record_snapshot,
)
from app.services.prices import (
    SessionOpenTracker,
    add_watchlist_ticker,
    build_watchlist,
    remove_watchlist_ticker,
)

HISTORY_LIMIT = 10
TRADE_LIMIT = 10


class ChatUnavailableError(RuntimeError):
    """The assistant could not answer; the API maps this to HTTP 503."""


@dataclass(frozen=True, slots=True)
class ChatOutcome:
    """What the chat route needs to answer: reply text, actions, refreshed portfolio."""

    message: str
    actions: dict[str, list[dict[str, Any]]]
    portfolio: dict[str, Any]


async def handle_chat(
    repo: Database,
    cache: PriceCache,
    chat_client: ChatClient,
    user_message: str,
    *,
    tracker: SessionOpenTracker | None = None,
    source: MarketDataSource | None = None,
    initial_cash: float = DEFAULT_INITIAL_CASH,
) -> ChatOutcome:
    """Run one chat turn end to end."""

    text = str(user_message).strip()
    active_tracker = tracker if tracker is not None else SessionOpenTracker()

    history = repo.portfolio.recent_chat(HISTORY_LIMIT)
    portfolio_payload = build_portfolio(repo, cache, initial_cash=initial_cash)
    watchlist_payload = build_watchlist(repo, cache, active_tracker)
    recent_trades = [trade.to_dict() for trade in repo.portfolio.list_trades(TRADE_LIMIT)]
    context = build_context(portfolio_payload, watchlist_payload["tickers"], recent_trades)

    try:
        response = await chat_client.complete(
            user_message=text,
            context=context,
            portfolio=portfolio_payload,
            history=[(message.role, message.content) for message in history],
        )
    except LLMError as exc:
        repo.portfolio.record_chat("user", text)
        raise ChatUnavailableError(f"AI assistant unavailable: {exc}") from exc

    repo.portfolio.record_chat("user", text)
    actions = await _apply_actions(
        repo, cache, response, source=source, tracker=active_tracker
    )
    repo.portfolio.record_chat("assistant", response.message, actions)
    return ChatOutcome(
        message=response.message,
        actions=actions,
        portfolio=build_portfolio(repo, cache, initial_cash=initial_cash),
    )


async def _apply_actions(
    repo: Database,
    cache: PriceCache,
    response: LLMResponse,
    *,
    source: MarketDataSource | None,
    tracker: SessionOpenTracker,
) -> dict[str, list[dict[str, Any]]]:
    trades: list[dict[str, Any]] = []
    for action in response.trades:
        result = _apply_trade(repo, cache, action)
        if result["status"] == "executed":
            record_snapshot(repo, cache)
        trades.append(result)
    changes = [
        await _apply_watchlist_change(repo, source, change, tracker)
        for change in response.watchlist_changes
    ]
    return {"trades": trades, "watchlist_changes": changes}


def _apply_trade(
    repo: Database,
    cache: PriceCache,
    action: TradeAction,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ticker": action.ticker,
        "side": action.side,
        "quantity": round(float(action.quantity), 6),
        "status": "failed",
        "price": _cached_price(cache, action.ticker),
        "error": None,
    }
    try:
        trade = execute_trade(repo, cache, action.ticker, action.side, action.quantity)
    except PriceUnavailableError as exc:
        result.update(price=None, error=str(exc))
        return result
    except (DatabaseError, ValueError) as exc:
        # TradeError is a DatabaseError: every domain or repository failure is reported
        # as a failed action instead of aborting the whole chat turn.
        result.update(error=str(exc))
        return result
    result.update(
        status="executed",
        quantity=round(trade.quantity, 6),
        price=round(trade.price, 2),
    )
    return result


async def _apply_watchlist_change(
    repo: Database,
    source: MarketDataSource | None,
    change: WatchlistChange,
    tracker: SessionOpenTracker,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ticker": change.ticker,
        "action": change.action,
        "status": "failed",
        "error": None,
    }
    if change.action == "add":
        added = await add_watchlist_ticker(repo, source, change.ticker)
        if not added:
            result["error"] = f"{change.ticker} is already in the watchlist"
            return result
    else:
        removed = await remove_watchlist_ticker(
            repo, source, change.ticker, tracker=tracker
        )
        if not removed:
            result["error"] = f"{change.ticker} is not in the watchlist"
            return result
    result["status"] = "executed"
    return result


def _cached_price(cache: PriceCache, ticker: str) -> float | None:
    price = cache.get_price(ticker)
    return None if price is None else round(price, 2)
