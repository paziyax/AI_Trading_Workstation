"""Deterministic, network-free chat client used when ``LLM_MOCK=true``.

The mock exists so E2E tests and offline development are stable: same input, same
output, no network, no randomness, no sleeps. It recognises the four intents documented
in ``API_CONTRACT.md`` (``buy``, ``sell``, ``add``, ``remove``), preserves their order in
the sentence, and always replies with text that starts with ``[mock] ``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.llm.schemas import LLMResponse, TradeAction, WatchlistChange

TRADE_RE = re.compile(
    r"\b(buy|sell)\s+([0-9]+(?:\.[0-9]+)?)\s+\$?([a-z][a-z0-9.\-]{0,9})\b",
    re.IGNORECASE,
)
WATCHLIST_RE = re.compile(
    r"\b(add|remove)\s+\$?([a-z][a-z0-9.\-]{0,9})\b",
    re.IGNORECASE,
)
WATCHLIST_COUNT_RE = re.compile(
    r"^##\s+Watchlist\s+\((\d+)\s+tickers?\)",
    re.IGNORECASE | re.MULTILINE,
)


class MockChatClient:
    """Rule-based :class:`~app.llm.client.ChatClient` implementation."""

    async def complete(
        self,
        *,
        user_message: str,
        context: str,
        portfolio: dict,
        history: list[tuple[str, str]],
    ) -> LLMResponse:
        """Parse ``user_message`` and return the requested actions.

        ``context`` is only used to report the watchlist size in the no-intent summary;
        ``history`` is accepted for interface parity and deliberately ignored.
        """

        trades, changes = _parse_actions(user_message)
        if trades or changes:
            message = _action_summary(trades, changes)
        else:
            message = _portfolio_summary(portfolio, context)
        return LLMResponse(message=message, trades=trades, watchlist_changes=changes)


def _parse_actions(message: str) -> tuple[list[TradeAction], list[WatchlistChange]]:
    text = message or ""
    trade_spans: list[tuple[int, int]] = []
    events: list[tuple[int, TradeAction | WatchlistChange]] = []

    for match in TRADE_RE.finditer(text):
        # Any add/remove word inside a trade phrase ("buy 5 ADD") is part of the trade.
        trade_spans.append(match.span())
        quantity = float(match.group(2))
        if quantity <= 0:
            continue
        side = "buy" if match.group(1).lower() == "buy" else "sell"
        events.append(
            (
                match.start(),
                TradeAction(ticker=match.group(3).upper(), side=side, quantity=quantity),
            )
        )

    for match in WATCHLIST_RE.finditer(text):
        if any(start <= match.start() < end for start, end in trade_spans):
            continue
        action = "add" if match.group(1).lower() == "add" else "remove"
        events.append(
            (match.start(), WatchlistChange(ticker=match.group(2).upper(), action=action))
        )

    events.sort(key=lambda event: event[0])
    trades = [event for _, event in events if isinstance(event, TradeAction)]
    changes = [event for _, event in events if isinstance(event, WatchlistChange)]
    return trades, changes


def _action_summary(trades: list[TradeAction], changes: list[WatchlistChange]) -> str:
    parts = [f"{trade.side} {_quantity(trade.quantity)} {trade.ticker}" for trade in trades]
    parts.extend(
        f"{change.action} {change.ticker} "
        f"{'to' if change.action == 'add' else 'from'} the watchlist"
        for change in changes
    )
    noun = "action" if len(parts) == 1 else "actions"
    return f"[mock] Executing {len(parts)} {noun}: " + "; ".join(parts) + "."


def _portfolio_summary(portfolio: Mapping[str, Any], context: str) -> str:
    account = portfolio if isinstance(portfolio, Mapping) else {}
    cash = _money(account.get("cash_balance"))
    positions = _count(account.get("positions"))
    tickers = _watchlist_count(context, account)
    return (
        f"[mock] You have {cash} in cash, {_plural(positions, 'open position')} "
        f"and {_plural(tickers, 'ticker')} on your watchlist. "
        "Ask me to buy or sell shares, or to add or remove a ticker."
    )


def _watchlist_count(context: str, portfolio: Mapping[str, Any]) -> int:
    match = WATCHLIST_COUNT_RE.search(context or "")
    if match:
        return int(match.group(1))
    listed = portfolio.get("watchlist")
    return len(listed) if isinstance(listed, (list, tuple)) else 0


def _count(value: Any) -> int:
    return len(value) if isinstance(value, (list, tuple)) else 0


def _money(value: Any) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "$0.00"
    return f"${amount:,.2f}"


def _quantity(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    noun = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {noun}"
