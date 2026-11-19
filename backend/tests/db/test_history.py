"""Portfolio snapshots and chat persistence."""

from __future__ import annotations

import json
import re
import uuid
from contextlib import closing
from typing import TYPE_CHECKING

import pytest

from app.db import Database
from app.db.models import ChatMessage, Snapshot

if TYPE_CHECKING:
    from app.db.repositories import PortfolioRepository

T1 = "2026-11-19T15:00:00Z"
T2 = "2026-11-19T15:01:00Z"
T3 = "2026-11-19T15:02:00Z"
T4 = "2026-11-19T15:03:00Z"
T5 = "2026-11-19T15:04:00Z"
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def test_add_snapshot_returns_the_recorded_point(portfolio: PortfolioRepository) -> None:
    snapshot = portfolio.add_snapshot(10000.0, now=T1)

    assert snapshot == Snapshot(total_value=10000.0, recorded_at=T1)
    assert portfolio.list_snapshots() == [snapshot]


def test_snapshot_totals_are_rounded_to_cents(portfolio: PortfolioRepository) -> None:
    snapshot = portfolio.add_snapshot(1234.567, now=T1)
    assert snapshot.total_value == 1234.57


def test_snapshot_timestamp_defaults_to_utc_now(portfolio: PortfolioRepository) -> None:
    snapshot = portfolio.add_snapshot(10000.0)
    assert TIMESTAMP_RE.match(snapshot.recorded_at)


def test_snapshots_are_oldest_first_and_limited(portfolio: PortfolioRepository) -> None:
    timestamps = [T1, T2, T3, T4, T5]
    for index, timestamp in enumerate(timestamps, start=1):
        portfolio.add_snapshot(float(index), now=timestamp)

    assert [point.total_value for point in portfolio.list_snapshots()] == [
        1.0,
        2.0,
        3.0,
        4.0,
        5.0,
    ]
    assert portfolio.list_snapshots(limit=2) == [
        Snapshot(total_value=4.0, recorded_at=T4),
        Snapshot(total_value=5.0, recorded_at=T5),
    ]
    assert portfolio.list_snapshots(limit=0) == []


def test_record_user_message_without_actions(portfolio: PortfolioRepository) -> None:
    message = portfolio.record_chat("user", "How is my portfolio?", now=T1)

    assert message.role == "user"
    assert message.content == "How is my portfolio?"
    assert message.actions is None
    assert message.created_at == T1
    assert portfolio.recent_chat() == [message]


def test_chat_actions_survive_the_json_round_trip(
    db: Database, portfolio: PortfolioRepository
) -> None:
    actions = {
        "trades": [
            {
                "ticker": "AAPL",
                "side": "buy",
                "quantity": 5.0,
                "status": "executed",
                "price": 191.0,
                "error": None,
            }
        ],
        "watchlist_changes": [
            {"ticker": "PYPL", "action": "add", "status": "executed", "error": None}
        ],
    }
    message = portfolio.record_chat("assistant", "Bought 5 AAPL.", actions, now=T1)

    loaded = portfolio.recent_chat()
    assert loaded == [message]
    assert loaded[0].actions == actions

    with closing(db.connect()) as conn:
        stored = conn.execute("SELECT actions FROM chat_messages").fetchone()["actions"]
    assert isinstance(stored, str)
    assert json.loads(stored) == actions


def test_recent_chat_returns_the_last_messages_oldest_first(
    portfolio: PortfolioRepository,
) -> None:
    for index, timestamp in enumerate([T1, T2, T3, T4, T5], start=1):
        portfolio.record_chat("user", f"message {index}", now=timestamp)

    assert [message.content for message in portfolio.recent_chat(limit=3)] == [
        "message 3",
        "message 4",
        "message 5",
    ]
    assert len(portfolio.recent_chat()) == 5
    assert portfolio.recent_chat(limit=0) == []


def test_chat_message_ids_are_unique_uuid4(portfolio: PortfolioRepository) -> None:
    first = portfolio.record_chat("user", "one", now=T1)
    second = portfolio.record_chat("assistant", "two", now=T2)

    assert first.id != second.id
    assert uuid.UUID(first.id).version == 4
    assert uuid.UUID(second.id).version == 4


def test_chat_timestamp_defaults_to_utc_now(portfolio: PortfolioRepository) -> None:
    message = portfolio.record_chat("user", "hello")
    assert TIMESTAMP_RE.match(message.created_at)


def test_invalid_chat_role_raises_value_error(portfolio: PortfolioRepository) -> None:
    with pytest.raises(ValueError, match="role"):
        portfolio.record_chat("system", "hello")
    assert portfolio.recent_chat() == []


def test_non_dict_actions_raise_value_error(portfolio: PortfolioRepository) -> None:
    with pytest.raises(ValueError, match="actions"):
        portfolio.record_chat("assistant", "hello", actions=["not", "a", "dict"])


def test_chat_message_model_holds_parsed_actions(portfolio: PortfolioRepository) -> None:
    actions = {"trades": [], "watchlist_changes": []}
    portfolio.record_chat("assistant", "done", actions, now=T1)
    message = portfolio.recent_chat()[0]

    assert isinstance(message, ChatMessage)
    assert message.actions == actions
