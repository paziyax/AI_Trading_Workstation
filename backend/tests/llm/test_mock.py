"""Deterministic mock-client behaviour: zero network, zero randomness, no sleeps."""

from __future__ import annotations

from typing import Any

import pytest

from app.llm.client import create_chat_client
from app.llm.mock import MockChatClient
from app.llm.prompts import build_context
from tests.llm.conftest import make_config, sample_portfolio, sample_watchlist


@pytest.fixture
def client() -> MockChatClient:
    return MockChatClient()


async def complete(
    client: MockChatClient,
    message: str,
    *,
    portfolio: dict[str, Any] | None = None,
    watchlist: list[dict[str, Any]] | None = None,
    history: list[tuple[str, str]] | None = None,
) -> Any:
    account = sample_portfolio() if portfolio is None else portfolio
    tickers = sample_watchlist() if watchlist is None else watchlist
    return await client.complete(
        user_message=message,
        context=build_context(account, tickers, []),
        portfolio=account,
        history=history or [],
    )


async def test_buy_message_produces_a_buy_trade(client: MockChatClient) -> None:
    response = await complete(client, "Buy 5 AAPL")

    assert len(response.trades) == 1
    assert response.trades[0].ticker == "AAPL"
    assert response.trades[0].side == "buy"
    assert response.trades[0].quantity == 5.0
    assert response.watchlist_changes == []
    assert response.message.startswith("[mock] ")
    assert "buy 5 AAPL" in response.message


async def test_sell_message_produces_a_sell_trade(client: MockChatClient) -> None:
    response = await complete(client, "sell 2.5 MSFT")

    assert [(trade.ticker, trade.side, trade.quantity) for trade in response.trades] == [
        ("MSFT", "sell", 2.5)
    ]
    assert response.message.startswith("[mock] ")


async def test_add_message_produces_a_watchlist_add(client: MockChatClient) -> None:
    response = await complete(client, "add PYPL")

    assert response.trades == []
    assert [(change.ticker, change.action) for change in response.watchlist_changes] == [
        ("PYPL", "add")
    ]
    assert response.message.startswith("[mock] ")


async def test_remove_message_produces_a_watchlist_remove(client: MockChatClient) -> None:
    response = await complete(client, "remove TSLA")

    assert [(change.ticker, change.action) for change in response.watchlist_changes] == [
        ("TSLA", "remove")
    ]
    assert response.message.startswith("[mock] ")


async def test_multiple_actions_are_all_captured(client: MockChatClient) -> None:
    response = await complete(client, "Buy 5 AAPL, sell 2 MSFT, add PYPL and remove TSLA")

    assert [(trade.side, trade.quantity, trade.ticker) for trade in response.trades] == [
        ("buy", 5.0, "AAPL"),
        ("sell", 2.0, "MSFT"),
    ]
    assert [(change.action, change.ticker) for change in response.watchlist_changes] == [
        ("add", "PYPL"),
        ("remove", "TSLA"),
    ]
    assert response.message.startswith("[mock] Executing 4 actions:")
    assert "buy 5 AAPL" in response.message
    assert "sell 2 MSFT" in response.message
    assert "add PYPL to the watchlist" in response.message
    assert "remove TSLA from the watchlist" in response.message


async def test_matching_is_case_insensitive_and_tickers_are_uppercased(
    client: MockChatClient,
) -> None:
    response = await complete(client, "BUY 5 aapl THEN add pypl")

    assert response.trades[0].ticker == "AAPL"
    assert response.trades[0].side == "buy"
    assert response.watchlist_changes[0].ticker == "PYPL"
    assert response.watchlist_changes[0].action == "add"


async def test_dollar_signs_and_fractional_quantities_are_accepted(
    client: MockChatClient,
) -> None:
    response = await complete(client, "buy 0.25 $brk.b")

    assert response.trades[0].ticker == "BRK.B"
    assert response.trades[0].quantity == 0.25


async def test_ticker_named_like_a_watchlist_verb_is_not_double_counted(
    client: MockChatClient,
) -> None:
    response = await complete(client, "buy 5 ADD")

    assert [(trade.ticker, trade.side) for trade in response.trades] == [("ADD", "buy")]
    assert response.watchlist_changes == []


async def test_repeated_intents_keep_text_order(client: MockChatClient) -> None:
    response = await complete(client, "buy 1 AAPL and then buy 2 AAPL")

    assert [trade.quantity for trade in response.trades] == [1.0, 2.0]


async def test_zero_quantity_is_ignored(client: MockChatClient) -> None:
    response = await complete(client, "buy 0 AAPL")

    assert response.trades == []
    assert response.message.startswith("[mock] ")
    assert "Executing" not in response.message


async def test_negative_quantity_is_ignored(client: MockChatClient) -> None:
    response = await complete(client, "buy -3 AAPL")

    assert response.trades == []
    assert response.message.startswith("[mock] ")


async def test_missing_ticker_is_ignored(client: MockChatClient) -> None:
    response = await complete(client, "buy 5")

    assert response.trades == []
    assert response.message.startswith("[mock] ")


async def test_no_intent_returns_a_portfolio_summary(client: MockChatClient) -> None:
    response = await complete(client, "How is my portfolio doing?")

    assert response.trades == []
    assert response.watchlist_changes == []
    assert response.message.startswith("[mock] ")
    assert "$8,100.00" in response.message
    assert "1 open position" in response.message
    assert "2 tickers" in response.message


async def test_no_intent_handles_an_empty_account(client: MockChatClient) -> None:
    account = {"cash_balance": 0.0, "positions": []}

    response = await complete(client, "hello", portfolio=account, watchlist=[])

    assert response.message.startswith("[mock] ")
    assert "$0.00" in response.message
    assert "0 open positions" in response.message
    assert "0 tickers" in response.message


async def test_single_ticker_watchlist_is_counted(client: MockChatClient) -> None:
    response = await complete(client, "hello", watchlist=[{"ticker": "AAPL", "price": 191.0}])

    assert "1 ticker on your watchlist" in response.message


async def test_watchlist_count_falls_back_to_a_portfolio_key(client: MockChatClient) -> None:
    account = {"cash_balance": 100.0, "positions": [], "watchlist": ["AAPL", "MSFT", "NVDA"]}

    response = await client.complete(
        user_message="hello", context="", portfolio=account, history=[]
    )

    assert "3 tickers" in response.message


async def test_history_is_accepted_but_unused(client: MockChatClient) -> None:
    without_history = await complete(client, "Buy 5 AAPL", history=[])
    with_history = await complete(
        client,
        "Buy 5 AAPL",
        history=[("user", "something else"), ("assistant", "an older reply")],
    )

    assert with_history == without_history


async def test_mock_makes_no_network_calls(
    client: MockChatClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.llm.client as client_module

    async def explode(**_: Any) -> Any:
        raise AssertionError("the mock client must never call the network")

    monkeypatch.setattr(client_module.litellm, "acompletion", explode)

    response = await complete(client, "Buy 5 AAPL")

    assert response.trades[0].ticker == "AAPL"


async def test_mock_selected_by_config_makes_no_network_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.llm.client as client_module

    async def explode(**_: Any) -> Any:
        raise AssertionError("the mock client must never call the network")

    monkeypatch.setattr(client_module.litellm, "acompletion", explode)

    chosen = create_chat_client(make_config(mock=True))
    response = await chosen.complete(
        user_message="sell 2 AAPL",
        context=build_context(sample_portfolio(), sample_watchlist(), []),
        portfolio=sample_portfolio(),
        history=[],
    )

    assert response.message.startswith("[mock] ")
    assert response.trades[0].side == "sell"
