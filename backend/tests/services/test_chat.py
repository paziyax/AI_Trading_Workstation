"""Chat orchestration without HTTP: actions, persistence, errors, context."""

from __future__ import annotations

import pytest

from app.db import Database
from app.llm import LLMError, WatchlistChange
from app.market import PriceCache
from app.services.chat import ChatUnavailableError, handle_chat
from app.services.prices import SessionOpenTracker
from tests.api.conftest import FakeMarketSource, StubChatClient, buy, chat_response, sell


def roles(db: Database) -> list[tuple[str, str]]:
    return [(message.role, message.content) for message in db.portfolio.recent_chat(20)]


async def test_executes_a_trade_and_returns_the_refreshed_portfolio(
    db: Database, cache: PriceCache
) -> None:
    cache.update("AAPL", 190.0)
    client = StubChatClient(chat_response("Bought two.", trades=[buy("AAPL", 2)]))

    outcome = await handle_chat(db, cache, client, "Buy 2 AAPL")

    assert outcome.message == "Bought two."
    assert outcome.actions["trades"] == [
        {
            "ticker": "AAPL",
            "side": "buy",
            "quantity": 2.0,
            "status": "executed",
            "price": 190.0,
            "error": None,
        }
    ]
    assert outcome.portfolio["cash_balance"] == 9620.0
    assert outcome.portfolio["positions"][0]["quantity"] == 2.0


async def test_persists_both_turns_with_the_actions(
    db: Database, cache: PriceCache
) -> None:
    cache.update("AAPL", 190.0)
    client = StubChatClient(chat_response("Done.", trades=[buy("AAPL", 1)]))

    await handle_chat(db, cache, client, "Buy 1 AAPL")

    assert roles(db) == [("user", "Buy 1 AAPL"), ("assistant", "Done.")]
    assistant = db.portfolio.recent_chat(1)[0]
    assert assistant.actions is not None
    assert assistant.actions["trades"][0]["status"] == "executed"


async def test_writes_a_snapshot_after_every_executed_trade(
    db: Database, cache: PriceCache
) -> None:
    cache.update("AAPL", 190.0)
    cache.update("MSFT", 420.0)
    client = StubChatClient(
        chat_response("Two trades.", trades=[buy("AAPL", 1), buy("MSFT", 1)])
    )

    await handle_chat(db, cache, client, "Buy both")

    assert len(db.portfolio.list_snapshots(10)) == 2


async def test_writes_no_snapshot_without_trades(
    db: Database, cache: PriceCache
) -> None:
    client = StubChatClient(chat_response("Just chatting."))

    await handle_chat(db, cache, client, "Hello")

    assert db.portfolio.list_snapshots(10) == []


async def test_a_failing_action_does_not_abort_the_turn(
    db: Database, cache: PriceCache
) -> None:
    cache.update("AAPL", 190.0)
    cache.update("MSFT", 420.0)
    client = StubChatClient(
        chat_response(
            "One failed.",
            trades=[sell("AAPL", 5), buy("MSFT", 1)],
            changes=[WatchlistChange(ticker="NOTREAL", action="remove")],
        )
    )

    outcome = await handle_chat(db, cache, client, "Do things")

    failed, executed = outcome.actions["trades"]
    assert failed["status"] == "failed"
    assert failed["error"] == "No position in AAPL to sell"
    assert executed["status"] == "executed"
    assert outcome.actions["watchlist_changes"][0]["status"] == "failed"
    assert outcome.portfolio["positions"][0]["ticker"] == "MSFT"


async def test_trade_without_a_price_is_reported(
    db: Database, cache: PriceCache
) -> None:
    client = StubChatClient(chat_response("Nope.", trades=[buy("ZZZZ", 1)]))

    outcome = await handle_chat(db, cache, client, "Buy ZZZZ")

    action = outcome.actions["trades"][0]
    assert action["status"] == "failed"
    assert action["price"] is None
    assert action["error"] == "No market price available for ZZZZ"


async def test_watchlist_changes_go_through_the_source(
    db: Database, cache: PriceCache
) -> None:
    source = FakeMarketSource().bind(cache)
    client = StubChatClient(
        chat_response(
            "Updated.",
            changes=[
                WatchlistChange(ticker="PYPL", action="add"),
                WatchlistChange(ticker="GOOGL", action="remove"),
            ],
        )
    )

    outcome = await handle_chat(db, cache, client, "Update", source=source)

    assert [change["status"] for change in outcome.actions["watchlist_changes"]] == [
        "executed",
        "executed",
    ]
    assert source.added == ["PYPL"]
    assert source.removed == ["GOOGL"]
    assert "GOOGL" not in db.watchlist.list_tickers()


async def test_duplicate_watchlist_add_is_reported(
    db: Database, cache: PriceCache
) -> None:
    client = StubChatClient(
        chat_response("Already.", changes=[WatchlistChange(ticker="AAPL", action="add")])
    )

    outcome = await handle_chat(db, cache, client, "Add AAPL")

    change = outcome.actions["watchlist_changes"][0]
    assert change["status"] == "failed"
    assert change["error"] == "AAPL is already in the watchlist"


async def test_llm_error_raises_unavailable_and_keeps_the_message(
    db: Database, cache: PriceCache
) -> None:
    client = StubChatClient(error=LLMError("provider exploded"))

    with pytest.raises(ChatUnavailableError) as excinfo:
        await handle_chat(db, cache, client, "  What now?  ")

    assert str(excinfo.value) == "AI assistant unavailable: provider exploded"
    assert roles(db) == [("user", "What now?")]


async def test_history_is_passed_oldest_first_without_the_new_message(
    db: Database, cache: PriceCache
) -> None:
    db.portfolio.record_chat("user", "question one")
    db.portfolio.record_chat("assistant", "answer one")
    client = StubChatClient(chat_response("Answer two."))

    await handle_chat(db, cache, client, "question two")

    assert client.calls[0]["history"] == [
        ("user", "question one"),
        ("assistant", "answer one"),
    ]
    assert client.calls[0]["user_message"] == "question two"


async def test_context_describes_the_live_watchlist(
    db: Database, cache: PriceCache
) -> None:
    cache.update("AAPL", 191.0)
    tracker = SessionOpenTracker()
    client = StubChatClient(chat_response("Fine."))

    await handle_chat(db, cache, client, "Status?", tracker=tracker)

    context = client.calls[0]["context"]
    assert "## Portfolio summary" in context
    assert "## Watchlist (10 tickers)" in context
    assert "| AAPL | $191.00 |" in context
