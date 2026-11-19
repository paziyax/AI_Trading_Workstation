"""Prompt text and portfolio context rendering for the FinAlly assistant.

``build_context`` turns the plain dictionaries returned by ``GET /api/portfolio`` and
``GET /api/watchlist`` into a compact markdown briefing. It is intentionally defensive:
the LLM must still get a usable prompt when a position is missing a price or the account
is empty.

The ``## Watchlist (N ticker(s))`` header is also read by the mock client to report the
watchlist size without a second data source.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

MAX_HISTORY_MESSAGES = 10

SYSTEM_PROMPT = """\
You are FinAlly, an AI trading assistant embedded in a simulated trading workstation.

How to behave:
- Be concise and data-driven. Cite cash, portfolio value, position weights and P&L when
  they matter to the answer. Two to five sentences is usually enough.
- You can execute market orders and manage the watchlist. Trades fill instantly at the
  current price with no fees and no confirmation step, so only trade when the user asks
  for it or clearly agrees.
- Buys need sufficient cash and sells need sufficient shares. If a request would fail,
  explain the constraint and propose a smaller size instead of forcing it.
- Never invent prices, holdings or tickers that are not in the context. You may suggest
  new tickers, and you may add them to the watchlist when the user asks or agrees.
- All prices are simulated and the cash is virtual; this is a practice environment.

Output contract:
- Always return structured JSON with exactly these keys: "message", "trades" and
  "watchlist_changes".
- "message" is the only text the user sees: make it self-contained.
- "trades" is a list of {"ticker", "side", "quantity"} with side "buy" or "sell".
- "watchlist_changes" is a list of {"ticker", "action"} with action "add" or "remove".
- Use empty arrays when no action is needed. Never wrap the JSON in prose or code fences.
"""


def build_messages(
    *,
    user_message: str,
    context: str,
    history: list[tuple[str, str]] | None,
) -> list[dict[str, str]]:
    """Assemble the chat completion messages: persona + context, history, user turn."""

    system = SYSTEM_PROMPT.rstrip()
    if context and context.strip():
        system = f"{system}\n\n# Current portfolio context\n\n{context.strip()}"

    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    messages.extend({"role": role, "content": content} for role, content in _recent_turns(history))
    messages.append({"role": "user", "content": user_message})
    return messages


def build_context(portfolio: dict, watchlist: list[dict], recent_trades: list[dict]) -> str:
    """Render a compact markdown briefing of account state for the model."""

    account = portfolio if isinstance(portfolio, Mapping) else {}
    tickers = [item for item in watchlist or [] if isinstance(item, Mapping)]
    trades = [item for item in recent_trades or [] if isinstance(item, Mapping)]

    total_value = _as_float(account.get("total_value"))
    positions = _positions(account)
    lines = [
        "## Portfolio summary",
        f"- Cash: {_money(account.get('cash_balance'))}",
        f"- Positions value: {_money(account.get('positions_value'))}",
        f"- Total value: {_money(total_value)}",
        f"- Total P&L: {_signed_money(account.get('total_pnl'))} "
        f"({_signed_pct(account.get('total_pnl_pct'))})",
        f"- Unrealized P&L: {_signed_money(account.get('unrealized_pnl'))}",
        "",
        f"## Positions ({len(positions)})",
    ]

    if not positions:
        lines.append("- No open positions.")
    else:
        lines.extend(
            [
                "| Ticker | Qty | Avg cost | Price | Value | P&L | P&L % | Weight |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for position in positions:
            weight = _as_float(position.get("weight"))
            if weight is None:
                weight = _weight_from_values(position, total_value)
            lines.append(
                "| {ticker} | {qty} | {avg_cost} | {price} | {value} | {pnl} | {pnl_pct} | "
                "{weight} |".format(
                    ticker=_text(position.get("ticker"), "?"),
                    qty=_quantity(position.get("quantity")),
                    avg_cost=_money(position.get("avg_cost")),
                    price=_money(position.get("current_price")),
                    value=_money(position.get("market_value")),
                    pnl=_signed_money(position.get("unrealized_pnl")),
                    pnl_pct=_signed_pct(position.get("unrealized_pnl_pct")),
                    weight=_percent(weight),
                )
            )

    ticker_noun = "ticker" if len(tickers) == 1 else "tickers"
    lines.extend(["", f"## Watchlist ({len(tickers)} {ticker_noun})"])
    if not tickers:
        lines.append("- No tickers on the watchlist.")
    else:
        lines.extend(
            [
                "| Ticker | Price | Session change | Change % |",
                "| --- | --- | --- | --- |",
            ]
        )
        for item in tickers:
            lines.append(
                "| {ticker} | {price} | {change} | {change_pct} |".format(
                    ticker=_text(item.get("ticker"), "?"),
                    price=_money(item.get("price")),
                    change=_signed_money(item.get("change")),
                    change_pct=_signed_pct(item.get("change_pct")),
                )
            )

    lines.extend(["", f"## Recent trades ({len(trades)})"])
    if not trades:
        lines.append("- No trades yet.")
    else:
        for trade in trades:
            lines.append(
                "- {when} | {side} {qty} {ticker} @ {price}".format(
                    when=_text(trade.get("executed_at"), "unknown time"),
                    side=_text(trade.get("side"), "?").upper(),
                    qty=_quantity(trade.get("quantity")),
                    ticker=_text(trade.get("ticker"), "?"),
                    price=_money(trade.get("price")),
                )
            )

    return "\n".join(lines)


def _recent_turns(history: Sequence[Any] | None) -> list[tuple[str, str]]:
    """Keep the last few well-formed turns, starting with the user.

    Accepts ``(role, content)`` tuples as required by the contract and, defensively,
    mapping rows with ``role``/``content`` keys.
    """

    turns: list[tuple[str, str]] = []
    for item in history or []:
        role: Any
        content: Any
        if isinstance(item, Mapping):
            role, content = item.get("role"), item.get("content")
        else:
            try:
                role, content = item
            except (TypeError, ValueError):
                continue
        role = str(role).strip().lower() if role is not None else ""
        content = str(content).strip() if content is not None else ""
        if role not in {"user", "assistant"} or not content:
            continue
        turns.append((role, content))

    turns = turns[-MAX_HISTORY_MESSAGES:]
    while turns and turns[0][0] == "assistant":
        turns.pop(0)
    return turns


def _positions(account: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [item for item in account.get("positions") or [] if isinstance(item, Mapping)]


def _weight_from_values(position: Mapping[str, Any], total_value: float | None) -> float | None:
    market_value = _as_float(position.get("market_value"))
    if market_value is None or not total_value:
        return None
    return market_value / total_value * 100.0


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _text(value: Any, fallback: str) -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _money(value: Any) -> str:
    amount = _as_float(value)
    return "n/a" if amount is None else f"${amount:,.2f}"


def _signed_money(value: Any) -> str:
    amount = _as_float(value)
    if amount is None:
        return "n/a"
    sign = "+" if amount >= 0 else "-"
    return f"{sign}${abs(amount):,.2f}"


def _signed_pct(value: Any) -> str:
    amount = _as_float(value)
    if amount is None:
        return "n/a"
    sign = "+" if amount >= 0 else "-"
    return f"{sign}{abs(amount):.2f}%"


def _percent(value: Any) -> str:
    amount = _as_float(value)
    return "n/a" if amount is None else f"{amount:.2f}%"


def _quantity(value: Any) -> str:
    amount = _as_float(value)
    if amount is None:
        return "n/a"
    if amount.is_integer():
        return str(int(amount))
    return f"{amount:.4f}".rstrip("0").rstrip(".")
