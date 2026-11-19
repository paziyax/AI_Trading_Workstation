"""``POST /api/chat``: orchestration, action reporting, persistence and mock mode."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.llm import LLMError, WatchlistChange
from tests.api.conftest import (
    FakeMarketSource,
    StubChatClient,
    build_app,
    buy,
    chat_response,
    sell,
)

CHAT_URL = "/api/chat"


def post(client: TestClient, message: str) -> Any:
    return client.post(CHAT_URL, json={"message": message})


def messages(app: Any) -> list[Any]:
    return app.state.db.portfolio.recent_chat(20)


def test_chat_executes_a_trade_and_reports_the_action(
    app: Any, client: TestClient, chat_client: StubChatClient
) -> None:
    chat_client.response = chat_response("Bought five.", trades=[buy("AAPL", 5)])

    response = post(client, "Buy 5 AAPL")

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Bought five."
    assert body["actions"] == {
        "trades": [
            {
                "ticker": "AAPL",
                "side": "buy",
                "quantity": 5.0,
                "status": "executed",
                "price": 190.0,
                "error": None,
            }
        ],
        "watchlist_changes": [],
    }
    assert body["portfolio"]["cash_balance"] == 9050.0
    assert body["portfolio"]["positions"][0]["quantity"] == 5.0
    assert len(client.get("/api/portfolio/history").json()["points"]) == 2


def test_chat_executes_watchlist_changes(
    client: TestClient, chat_client: StubChatClient
) -> None:
    chat_client.response = chat_response(
        "Updated the watchlist.",
        changes=[
            WatchlistChange(ticker="PYPL", action="add"),
            WatchlistChange(ticker="GOOGL", action="remove"),
        ],
    )

    body = post(client, "Add PYPL and remove GOOGL").json()

    assert body["actions"]["watchlist_changes"] == [
        {"ticker": "PYPL", "action": "add", "status": "executed", "error": None},
        {"ticker": "GOOGL", "action": "remove", "status": "executed", "error": None},
    ]
    tickers = [item["ticker"] for item in client.get("/api/watchlist").json()["tickers"]]
    assert "PYPL" in tickers
    assert "GOOGL" not in tickers


def test_a_failed_action_does_not_fail_the_request(
    client: TestClient, chat_client: StubChatClient
) -> None:
    chat_client.response = chat_response(
        "One worked, one did not.",
        trades=[buy("AAPL", 1000), buy("MSFT", 1)],
    )

    response = post(client, "Buy a lot")

    assert response.status_code == 200
    actions = response.json()["actions"]["trades"]
    assert actions[0]["status"] == "failed"
    assert actions[0]["error"] == "Insufficient cash: need $190,000.00, available $10,000.00"
    assert actions[0]["price"] == 190.0
    assert actions[1]["status"] == "executed"
    assert actions[1]["error"] is None
    assert response.json()["portfolio"]["cash_balance"] == 9580.0


def test_trading_a_ticker_without_a_price_reports_a_failed_action(
    client: TestClient, chat_client: StubChatClient
) -> None:
    chat_client.response = chat_response("No price.", trades=[buy("ZZZZ", 1)])

    body = post(client, "Buy ZZZZ").json()

    action = body["actions"]["trades"][0]
    assert action["status"] == "failed"
    assert action["price"] is None
    assert action["error"] == "No market price available for ZZZZ"
    assert body["portfolio"]["positions"] == []


def test_duplicate_watchlist_add_reports_a_failed_action(
    client: TestClient, chat_client: StubChatClient
) -> None:
    chat_client.response = chat_response(
        "Already there.", changes=[WatchlistChange(ticker="AAPL", action="add")]
    )

    body = post(client, "Add AAPL").json()

    assert body["actions"]["watchlist_changes"][0] == {
        "ticker": "AAPL",
        "action": "add",
        "status": "failed",
        "error": "AAPL is already in the watchlist",
    }


def test_removing_an_unwatched_ticker_reports_a_failed_action(
    client: TestClient, chat_client: StubChatClient
) -> None:
    chat_client.response = chat_response(
        "Not there.", changes=[WatchlistChange(ticker="ZZZZ", action="remove")]
    )

    body = post(client, "Remove ZZZZ").json()

    assert body["actions"]["watchlist_changes"][0]["status"] == "failed"
    assert body["actions"]["watchlist_changes"][0]["error"] == "ZZZZ is not in the watchlist"


def test_llm_error_returns_503_and_keeps_the_user_message(
    app: Any, client: TestClient, chat_client: StubChatClient
) -> None:
    chat_client.error = LLMError("provider exploded")

    response = post(client, "What should I buy?")

    assert response.status_code == 503
    assert response.json() == {"detail": "AI assistant unavailable: provider exploded"}
    stored = messages(app)
    assert [(message.role, message.content) for message in stored] == [
        ("user", "What should I buy?")
    ]


def test_both_turns_are_persisted_with_serialized_actions(
    app: Any, client: TestClient, chat_client: StubChatClient
) -> None:
    chat_client.response = chat_response("Done.", trades=[buy("AAPL", 2)])

    post(client, "Buy 2 AAPL")

    stored = messages(app)
    assert [message.role for message in stored] == ["user", "assistant"]
    assert stored[0].content == "Buy 2 AAPL"
    assert stored[0].actions is None
    assert stored[1].content == "Done."
    assert stored[1].actions is not None
    assert stored[1].actions["trades"][0]["status"] == "executed"
    assert stored[1].actions["trades"][0]["ticker"] == "AAPL"
    assert stored[1].actions["watchlist_changes"] == []


def test_history_is_sent_to_the_client_without_the_new_message(
    app: Any, client: TestClient, chat_client: StubChatClient
) -> None:
    post(client, "hello")
    post(client, "again")

    assert chat_client.calls[0]["history"] == []
    assert chat_client.calls[1]["history"] == [
        ("user", "hello"),
        ("assistant", "[stub] Done."),
    ]


def test_context_is_built_from_the_live_portfolio(
    client: TestClient, chat_client: StubChatClient
) -> None:
    buy_body = chat_response("Buying.", trades=[buy("AAPL", 3)])
    chat_client.response = buy_body
    post(client, "Buy 3 AAPL")
    chat_client.response = chat_response()
    post(client, "How am I doing?")

    context = chat_client.calls[1]["context"]
    assert "## Portfolio summary" in context
    assert "## Watchlist (10 tickers)" in context
    assert "AAPL" in context
    assert chat_client.calls[1]["portfolio"]["cash_balance"] == 9430.0


def test_message_is_trimmed_before_the_llm_and_the_database(
    app: Any, client: TestClient, chat_client: StubChatClient
) -> None:
    post(client, "   How is my portfolio?   ")

    assert chat_client.calls[0]["user_message"] == "How is my portfolio?"
    assert messages(app)[0].content == "How is my portfolio?"


@pytest.mark.parametrize("message", ["", "   ", "\n\t"])
def test_empty_messages_are_rejected(client: TestClient, message: str) -> None:
    assert post(client, message).status_code == 422


def test_message_length_is_bounded(client: TestClient, chat_client: StubChatClient) -> None:
    assert post(client, "x" * 2001).status_code == 422
    assert post(client, "x" * 2000).status_code == 200


def test_missing_message_is_rejected(client: TestClient) -> None:
    assert client.post(CHAT_URL, json={}).status_code == 422


def test_no_actions_returns_empty_arrays_and_the_current_portfolio(
    client: TestClient, chat_client: StubChatClient
) -> None:
    body = post(client, "How am I doing?").json()

    assert body["actions"] == {"trades": [], "watchlist_changes": []}
    assert body["portfolio"] == client.get("/api/portfolio").json()
    assert len(client.get("/api/portfolio/history").json()["points"]) == 1


def test_sell_action_reduces_the_position(
    client: TestClient, chat_client: StubChatClient
) -> None:
    client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "quantity": 5, "side": "buy"},
    )
    chat_client.response = chat_response("Sold.", trades=[sell("AAPL", 2)])

    body = post(client, "Sell 2 AAPL").json()

    assert body["actions"]["trades"][0]["status"] == "executed"
    assert body["portfolio"]["positions"][0]["quantity"] == 3.0


def test_mock_mode_runs_end_to_end_without_network(
    settings: Any,
    source: FakeMarketSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_MOCK", "true")
    app = build_app(settings, source=source)

    with TestClient(app) as client:
        trade_response = client.post(CHAT_URL, json={"message": "buy 3 AAPL"})
        watchlist_response = client.post(CHAT_URL, json={"message": "add PYPL"})

    trade_body = trade_response.json()
    assert trade_response.status_code == 200
    assert trade_body["message"].startswith("[mock]")
    assert trade_body["actions"]["trades"][0]["status"] == "executed"
    assert trade_body["actions"]["trades"][0]["ticker"] == "AAPL"
    assert trade_body["portfolio"]["cash_balance"] == 9430.0

    assert watchlist_response.status_code == 200
    assert watchlist_response.json()["message"].startswith("[mock]")
    assert watchlist_response.json()["actions"]["watchlist_changes"][0]["status"] == (
        "executed"
    )
