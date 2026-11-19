"""Portfolio-context rendering and message assembly."""

from __future__ import annotations

from typing import Any

from app.llm.prompts import MAX_HISTORY_MESSAGES, build_context, build_messages


def test_context_contains_account_totals(
    portfolio: dict[str, Any], watchlist: list[dict[str, Any]], recent_trades: list[dict[str, Any]]
) -> None:
    context = build_context(portfolio, watchlist, recent_trades)

    assert "## Portfolio summary" in context
    assert "- Cash: $8,100.00" in context
    assert "- Positions value: $1,910.00" in context
    assert "- Total value: $10,010.00" in context
    assert "- Total P&L: +$10.00 (+0.10%)" in context
    assert "- Unrealized P&L: +$10.00" in context


def test_context_contains_positions_with_weight_and_pnl(
    portfolio: dict[str, Any], watchlist: list[dict[str, Any]], recent_trades: list[dict[str, Any]]
) -> None:
    context = build_context(portfolio, watchlist, recent_trades)

    assert "## Positions (1)" in context
    assert "| Ticker | Qty | Avg cost | Price | Value | P&L | P&L % | Weight |" in context
    assert "| AAPL | 10 | $190.00 | $191.00 | $1,910.00 | +$10.00 | +0.53% | 19.08% |" in context


def test_context_contains_watchlist_prices(
    portfolio: dict[str, Any], watchlist: list[dict[str, Any]], recent_trades: list[dict[str, Any]]
) -> None:
    context = build_context(portfolio, watchlist, recent_trades)

    assert "## Watchlist (2 tickers)" in context
    assert "| AAPL | $191.00 | +$0.20 | +0.10% |" in context
    assert "| MSFT | $420.50 | -$0.50 | -0.12% |" in context


def test_context_contains_recent_trades(
    portfolio: dict[str, Any], watchlist: list[dict[str, Any]], recent_trades: list[dict[str, Any]]
) -> None:
    context = build_context(portfolio, watchlist, recent_trades)

    assert "## Recent trades (1)" in context
    assert "- 2026-11-19T15:38:22Z | BUY 10 AAPL @ $190.00" in context


def test_empty_account_does_not_crash() -> None:
    context = build_context(
        {"cash_balance": 10000.0, "positions_value": 0.0, "total_value": 10000.0, "positions": []},
        [],
        [],
    )

    assert "- Cash: $10,000.00" in context
    assert "## Positions (0)" in context
    assert "- No open positions." in context
    assert "## Watchlist (0 tickers)" in context
    assert "- No tickers on the watchlist." in context
    assert "## Recent trades (0)" in context
    assert "- No trades yet." in context


def test_totally_empty_dicts_do_not_crash() -> None:
    context = build_context({}, [], [])

    assert "n/a" in context
    assert "## Positions (0)" in context


def test_missing_and_none_values_render_as_na() -> None:
    portfolio = {
        "cash_balance": None,
        "total_value": None,
        "positions": [
            {
                "ticker": "AAPL",
                "quantity": None,
                "avg_cost": None,
                "current_price": None,
                "market_value": None,
                "unrealized_pnl": None,
                "unrealized_pnl_pct": None,
                "weight": None,
            }
        ],
    }
    watchlist = [{"ticker": "MSFT", "price": None, "change": None, "change_pct": None}]
    trades = [{"ticker": "AAPL"}]

    context = build_context(portfolio, watchlist, trades)

    assert "| AAPL | n/a | n/a | n/a | n/a | n/a | n/a | n/a |" in context
    assert "| MSFT | n/a | n/a | n/a |" in context
    assert "unknown time" in context


def test_missing_weight_is_computed_from_market_value() -> None:
    portfolio = {
        "cash_balance": 0.0,
        "total_value": 200.0,
        "positions": [{"ticker": "AAPL", "quantity": 1.0, "market_value": 50.0}],
    }

    context = build_context(portfolio, [], [])

    assert "25.00%" in context


def test_fractional_quantities_keep_their_decimals() -> None:
    portfolio = {
        "cash_balance": 0.0,
        "total_value": 10.0,
        "positions": [{"ticker": "AAPL", "quantity": 0.125, "market_value": 10.0}],
    }

    context = build_context(portfolio, [], [])

    assert "| AAPL | 0.125 |" in context


def test_single_watchlist_ticker_uses_a_singular_header() -> None:
    context = build_context(
        {"cash_balance": 0.0, "total_value": 0.0, "positions": []},
        [{"ticker": "AAPL", "price": 1.0}],
        [],
    )

    assert "## Watchlist (1 ticker)" in context


def test_context_is_deterministic(
    portfolio: dict[str, Any], watchlist: list[dict[str, Any]], recent_trades: list[dict[str, Any]]
) -> None:
    first = build_context(portfolio, watchlist, recent_trades)
    second = build_context(portfolio, watchlist, recent_trades)

    assert first == second


def test_build_messages_puts_persona_and_context_in_the_system_prompt() -> None:
    messages = build_messages(user_message="How am I doing?", context="- Cash: $10,000.00", history=[])

    assert [message["role"] for message in messages] == ["system", "user"]
    assert "FinAlly" in messages[0]["content"]
    assert "# Current portfolio context" in messages[0]["content"]
    assert "- Cash: $10,000.00" in messages[0]["content"]
    assert messages[-1] == {"role": "user", "content": "How am I doing?"}


def test_build_messages_caps_history_to_the_last_ten_turns() -> None:
    history = [("user", f"question {index}") for index in range(15)]

    messages = build_messages(user_message="latest", context="", history=history)

    assert len(messages) == 1 + MAX_HISTORY_MESSAGES + 1
    assert messages[1]["content"] == "question 5"
    assert messages[10]["content"] == "question 14"
    assert messages[-1]["content"] == "latest"


def test_build_messages_drops_a_leading_assistant_turn() -> None:
    history = [("assistant", "orphan reply"), ("user", "question"), ("assistant", "answer")]

    messages = build_messages(user_message="follow-up", context="", history=history)

    assert [message["role"] for message in messages] == ["system", "user", "assistant", "user"]
    assert messages[1]["content"] == "question"


def test_build_messages_accepts_mapping_history_rows() -> None:
    history = [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "answer"},
    ]

    messages = build_messages(user_message="follow-up", context="", history=history)

    assert [message["role"] for message in messages] == ["system", "user", "assistant", "user"]


def test_build_messages_skips_malformed_history() -> None:
    history: list[Any] = [
        ("system", "ignored"),
        ("user", "   "),
        ("user",),
        ("assistant", "kept"),
        {"role": "tool", "content": "ignored"},
    ]

    messages = build_messages(user_message="hi", context="", history=history)

    # The kept assistant turn is dropped because it now leads the history.
    assert [message["role"] for message in messages] == ["system", "user"]
