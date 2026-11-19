"""Connection setup, schema shape and idempotent seed behaviour."""

from __future__ import annotations

import re
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path

import pytest

from app.db import Database
from app.db.errors import DatabaseError
from app.db.repositories import PortfolioRepository, WatchlistRepository

DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def test_path_property_accepts_str_and_path(tmp_path: Path) -> None:
    target = tmp_path / "finally.db"
    assert Database(target).path == target
    assert Database(str(target)).path == target


def test_initialize_creates_missing_directories(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "data" / "finally.db"
    Database(path).initialize()
    assert path.is_file()


def test_initialize_accepts_an_existing_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "finally.db"
    path.write_bytes(b"")
    Database(path).initialize()
    assert Database(path).portfolio.get_profile().cash_balance == 10000.0


def test_schema_creates_expected_tables_and_indexes(db: Database) -> None:
    expected_tables = {
        "users_profile",
        "watchlist",
        "positions",
        "trades",
        "portfolio_snapshots",
        "chat_messages",
    }
    expected_indexes = {
        "idx_trades_user_executed",
        "idx_portfolio_snapshots_user_recorded",
        "idx_chat_messages_user_created",
        "idx_watchlist_user",
    }
    with closing(db.connect()) as conn:
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        indexes = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
        }
    assert tables >= expected_tables
    assert indexes >= expected_indexes


def test_connect_applies_required_pragmas(db: Database) -> None:
    with closing(db.connect()) as conn:
        assert conn.row_factory is sqlite3.Row
        assert conn.isolation_level is None
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_connect_rows_support_mapping_access(db: Database) -> None:
    with closing(db.connect()) as conn:
        row = conn.execute("SELECT id, cash_balance FROM users_profile").fetchone()
    assert row["id"] == "default"
    assert row["cash_balance"] == 10000.0


def test_initialize_is_idempotent(db: Database) -> None:
    db.initialize()
    db.initialize()
    Database(db.path).initialize()

    with closing(db.connect()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM users_profile").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0] == 10
    assert db.watchlist.list_tickers() == DEFAULT_TICKERS


def test_profile_seed_contents(db: Database) -> None:
    profile = db.portfolio.get_profile()
    assert profile.id == "default"
    assert profile.cash_balance == 10000.0
    assert TIMESTAMP_RE.match(profile.created_at)


def test_seed_watchlist_ids_are_uuid4_and_timestamps_are_iso(db: Database) -> None:
    with closing(db.connect()) as conn:
        rows = conn.execute("SELECT id, added_at FROM watchlist").fetchall()
    assert len(rows) == 10
    for row in rows:
        assert uuid.UUID(row["id"]).version == 4
        assert TIMESTAMP_RE.match(row["added_at"])


def test_initialize_preserves_cash_and_watchlist_edits(db: Database) -> None:
    db.portfolio.set_cash_balance(4321.5)
    db.watchlist.remove("AAPL")
    db.watchlist.add("PYPL")

    Database(db.path).initialize()

    assert db.portfolio.get_profile().cash_balance == 4321.5
    tickers = db.watchlist.list_tickers()
    assert "AAPL" not in tickers
    assert tickers[-1] == "PYPL"
    assert len(tickers) == 10


def test_initialize_does_not_resurrect_removed_tickers(db: Database) -> None:
    removed = ["AAPL", "TSLA", "NFLX"]
    for ticker in removed:
        assert db.watchlist.remove(ticker)

    Database(db.path).initialize()

    assert db.watchlist.list_tickers() == [
        ticker for ticker in DEFAULT_TICKERS if ticker not in removed
    ]


def test_initialize_reseeds_only_when_the_watchlist_is_empty(db: Database) -> None:
    for ticker in DEFAULT_TICKERS:
        assert db.watchlist.remove(ticker)

    Database(db.path).initialize()

    # The seed contract is "empty watchlist means fresh install": an entirely cleared
    # watchlist is indistinguishable from a new database, so the defaults return.
    assert db.watchlist.list_tickers() == DEFAULT_TICKERS


def test_initialize_preserves_trade_history(db: Database) -> None:
    trade = db.portfolio.execute_trade("AAPL", "buy", 1, 100.0)
    Database(db.path).initialize()
    assert [item.id for item in db.portfolio.list_trades()] == [trade.id]
    assert db.portfolio.get_position("AAPL") is not None


def test_missing_profile_raises_database_error(db: Database) -> None:
    with closing(db.connect()) as conn:
        conn.execute("DELETE FROM users_profile")

    with pytest.raises(DatabaseError, match="users_profile"):
        db.portfolio.get_profile()
    with pytest.raises(DatabaseError, match="users_profile"):
        db.portfolio.set_cash_balance(1.0)


def test_repositories_are_constructed_once(db: Database) -> None:
    assert isinstance(db.portfolio, PortfolioRepository)
    assert isinstance(db.watchlist, WatchlistRepository)
    assert db.portfolio is db.portfolio
    assert db.watchlist is db.watchlist


def test_schema_constraints_are_enforced(db: Database) -> None:
    with closing(db.connect()) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO watchlist (id, ticker, added_at) VALUES (?, ?, ?)",
            (str(uuid.uuid4()), "AAPL", "2026-11-19T15:00:00Z"),
        )
    with closing(db.connect()) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO trades (id, ticker, side, quantity, price, executed_at)
            VALUES (?, 'AAPL', 'hold', 1, 100, '2026-11-19T15:00:00Z')
            """,
            (str(uuid.uuid4()),),
        )
