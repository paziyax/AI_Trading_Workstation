"""Repositories: every SQL statement in FinAlly lives in this module.

``PortfolioRepository`` owns cash, positions, trade execution, portfolio snapshots and chat
history; ``WatchlistRepository`` owns the ticker list. Both are constructed from a ``Database``
instance and open a short-lived connection per call.

Money rules: cash is stored rounded to 2 dp, average cost to 6 dp, snapshot totals to 2 dp.
Share quantities keep full float precision; the API rounds for display.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.db.errors import DatabaseError, TradeError
from app.db.models import ChatMessage, Position, Profile, Snapshot, Trade

if TYPE_CHECKING:
    from app.db.database import Database

USER_ID = "default"

_CHAT_ROLES = ("user", "assistant")
_TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")

_PROFILE_COLUMNS = "id, cash_balance, created_at"
_POSITION_COLUMNS = "ticker, quantity, avg_cost, updated_at"
_TRADE_COLUMNS = "id, ticker, side, quantity, price, executed_at"
_CHAT_COLUMNS = "id, role, content, actions, created_at"


def _utc_now() -> str:
    """ISO-8601 UTC timestamp with second precision and a trailing ``Z``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id() -> str:
    return str(uuid.uuid4())


def _profile_from_row(row: sqlite3.Row) -> Profile:
    return Profile(
        id=row["id"],
        cash_balance=float(row["cash_balance"]),
        created_at=row["created_at"],
    )


def _position_from_row(row: sqlite3.Row) -> Position:
    return Position(
        ticker=row["ticker"],
        quantity=float(row["quantity"]),
        avg_cost=float(row["avg_cost"]),
        updated_at=row["updated_at"],
    )


def _trade_from_row(row: sqlite3.Row) -> Trade:
    return Trade(
        id=row["id"],
        ticker=row["ticker"],
        side=row["side"],
        quantity=float(row["quantity"]),
        price=float(row["price"]),
        executed_at=row["executed_at"],
    )


def _snapshot_from_row(row: sqlite3.Row) -> Snapshot:
    return Snapshot(total_value=float(row["total_value"]), recorded_at=row["recorded_at"])


def _chat_from_row(row: sqlite3.Row) -> ChatMessage:
    raw_actions = row["actions"]
    actions: dict[str, Any] | None = None if raw_actions is None else json.loads(raw_actions)
    return ChatMessage(
        id=row["id"],
        role=row["role"],
        content=row["content"],
        actions=actions,
        created_at=row["created_at"],
    )


def _upsert_position(
    conn: sqlite3.Connection,
    ticker: str,
    quantity: float,
    avg_cost: float,
    updated_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (user_id, ticker) DO UPDATE SET
            quantity = excluded.quantity,
            avg_cost = excluded.avg_cost,
            updated_at = excluded.updated_at
        """,
        (_new_id(), USER_ID, ticker, quantity, avg_cost, updated_at),
    )


class PortfolioRepository:
    """Cash, positions, trades, snapshots and chat messages for the default user."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def get_profile(self) -> Profile:
        with closing(self._db.connect()) as conn:
            row = conn.execute(
                f"SELECT {_PROFILE_COLUMNS} FROM users_profile WHERE id = ?",
                (USER_ID,),
            ).fetchone()
        if row is None:
            raise DatabaseError(
                "users_profile row 'default' is missing; call Database.initialize() first"
            )
        return _profile_from_row(row)

    def set_cash_balance(self, cash: float) -> None:
        """Maintenance/test helper: overwrite the cash balance (rounded to 2 dp)."""
        with closing(self._db.connect()) as conn:
            cursor = conn.execute(
                "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
                (round(float(cash), 2), USER_ID),
            )
            updated = cursor.rowcount
        if updated == 0:
            raise DatabaseError(
                "users_profile row 'default' is missing; call Database.initialize() first"
            )

    def get_positions(self) -> list[Position]:
        with closing(self._db.connect()) as conn:
            rows = conn.execute(
                f"SELECT {_POSITION_COLUMNS} FROM positions "
                "WHERE user_id = ? ORDER BY ticker ASC",
                (USER_ID,),
            ).fetchall()
        return [_position_from_row(row) for row in rows]

    def get_position(self, ticker: str) -> Position | None:
        symbol = str(ticker).strip().upper()
        with closing(self._db.connect()) as conn:
            row = conn.execute(
                f"SELECT {_POSITION_COLUMNS} FROM positions WHERE user_id = ? AND ticker = ?",
                (USER_ID, symbol),
            ).fetchone()
        return None if row is None else _position_from_row(row)

    def execute_trade(
        self,
        ticker: str,
        side: str,
        quantity: float,
        price: float,
        *,
        now: str | None = None,
    ) -> Trade:
        """Validate and fill a market order atomically.

        One ``BEGIN IMMEDIATE`` transaction covers the cash check, the position mutation, the
        cash update and the trade-log insert. Any error (including ``TradeError``) rolls the
        whole thing back, so a rejected trade leaves no trace.
        """
        symbol = str(ticker).strip().upper()
        action = str(side).strip().lower()
        qty = float(quantity)
        unit_price = float(price)

        if action not in ("buy", "sell"):
            raise ValueError(f"Invalid side: {side!r} (expected 'buy' or 'sell')")
        if not math.isfinite(qty) or qty <= 0:
            raise ValueError("Quantity must be a positive number")
        if not math.isfinite(unit_price) or unit_price <= 0:
            raise ValueError("Price must be a positive number")

        executed_at = now or _utc_now()
        trade = Trade(
            id=_new_id(),
            ticker=symbol,
            side=action,
            quantity=qty,
            price=unit_price,
            executed_at=executed_at,
        )

        conn = self._db.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            profile_row = conn.execute(
                "SELECT cash_balance FROM users_profile WHERE id = ?",
                (USER_ID,),
            ).fetchone()
            if profile_row is None:
                raise DatabaseError(
                    "users_profile row 'default' is missing; call Database.initialize() first"
                )
            cash = float(profile_row["cash_balance"])

            if action == "buy":
                cost = round(qty * unit_price, 2)
                if cash + 1e-9 < cost:
                    raise TradeError(
                        f"Insufficient cash: need ${cost:,.2f}, available ${cash:,.2f}"
                    )
                cash = round(cash - cost, 2)
                existing = conn.execute(
                    "SELECT quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?",
                    (USER_ID, symbol),
                ).fetchone()
                if existing is None:
                    position_quantity = qty
                    avg_cost = round(unit_price, 6)
                else:
                    old_quantity = float(existing["quantity"])
                    old_avg_cost = float(existing["avg_cost"])
                    position_quantity = old_quantity + qty
                    avg_cost = round(
                        (old_quantity * old_avg_cost + qty * unit_price) / position_quantity,
                        6,
                    )
                _upsert_position(conn, symbol, position_quantity, avg_cost, executed_at)
            else:
                existing = conn.execute(
                    "SELECT quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?",
                    (USER_ID, symbol),
                ).fetchone()
                if existing is None:
                    raise TradeError(f"No position in {symbol} to sell")
                held = float(existing["quantity"])
                if qty > held + 1e-9:
                    raise TradeError(f"Cannot sell {qty:g} {symbol}: only {held:g} owned")
                cash = round(cash + round(qty * unit_price, 2), 2)
                remaining = held - qty
                if remaining < 1e-9:
                    conn.execute(
                        "DELETE FROM positions WHERE user_id = ? AND ticker = ?",
                        (USER_ID, symbol),
                    )
                else:
                    conn.execute(
                        "UPDATE positions SET quantity = ?, updated_at = ? "
                        "WHERE user_id = ? AND ticker = ?",
                        (remaining, executed_at, USER_ID, symbol),
                    )

            conn.execute(
                "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
                (cash, USER_ID),
            )
            conn.execute(
                """
                INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade.id,
                    USER_ID,
                    trade.ticker,
                    trade.side,
                    trade.quantity,
                    trade.price,
                    trade.executed_at,
                ),
            )
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

        return trade

    def list_trades(self, limit: int = 100) -> list[Trade]:
        """Most recent trades first; ties are broken by insertion order."""
        with closing(self._db.connect()) as conn:
            rows = conn.execute(
                f"SELECT {_TRADE_COLUMNS} FROM trades WHERE user_id = ? "
                "ORDER BY executed_at DESC, rowid DESC LIMIT ?",
                (USER_ID, max(0, int(limit))),
            ).fetchall()
        return [_trade_from_row(row) for row in rows]

    def add_snapshot(self, total_value: float, *, now: str | None = None) -> Snapshot:
        """Append a portfolio-value point (rounded to 2 dp, like every money value)."""
        snapshot = Snapshot(
            total_value=round(float(total_value), 2),
            recorded_at=now or _utc_now(),
        )
        with closing(self._db.connect()) as conn:
            conn.execute(
                """
                INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at)
                VALUES (?, ?, ?, ?)
                """,
                (_new_id(), USER_ID, snapshot.total_value, snapshot.recorded_at),
            )
        return snapshot

    def list_snapshots(self, limit: int = 500) -> list[Snapshot]:
        """Oldest first, limited to the most recent ``limit`` points."""
        with closing(self._db.connect()) as conn:
            rows = conn.execute(
                "SELECT total_value, recorded_at FROM portfolio_snapshots "
                "WHERE user_id = ? ORDER BY recorded_at DESC, rowid DESC LIMIT ?",
                (USER_ID, max(0, int(limit))),
            ).fetchall()
        return [_snapshot_from_row(row) for row in reversed(rows)]

    def record_chat(
        self,
        role: str,
        content: str,
        actions: dict | None = None,
        *,
        now: str | None = None,
    ) -> ChatMessage:
        """Persist one chat turn; ``actions`` is stored as JSON text."""
        normalized_role = str(role).strip().lower()
        if normalized_role not in _CHAT_ROLES:
            raise ValueError(f"Invalid chat role: {role!r}")
        if actions is not None and not isinstance(actions, dict):
            raise ValueError("actions must be a dict or None")

        message = ChatMessage(
            id=_new_id(),
            role=normalized_role,
            content=str(content),
            actions=actions,
            created_at=now or _utc_now(),
        )
        payload = None if actions is None else json.dumps(actions)
        with closing(self._db.connect()) as conn:
            conn.execute(
                """
                INSERT INTO chat_messages (id, user_id, role, content, actions, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message.id,
                    USER_ID,
                    message.role,
                    message.content,
                    payload,
                    message.created_at,
                ),
            )
        return message

    def recent_chat(self, limit: int = 20) -> list[ChatMessage]:
        """The last ``limit`` messages, oldest first (prompt order)."""
        with closing(self._db.connect()) as conn:
            rows = conn.execute(
                f"SELECT {_CHAT_COLUMNS} FROM chat_messages WHERE user_id = ? "
                "ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (USER_ID, max(0, int(limit))),
            ).fetchall()
        return [_chat_from_row(row) for row in reversed(rows)]


class WatchlistRepository:
    """The user's watched tickers, kept in insertion order."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def list_tickers(self) -> list[str]:
        with closing(self._db.connect()) as conn:
            rows = conn.execute(
                "SELECT ticker FROM watchlist WHERE user_id = ? "
                "ORDER BY added_at ASC, rowid ASC",
                (USER_ID,),
            ).fetchall()
        return [row["ticker"] for row in rows]

    def add(self, ticker: str) -> bool:
        """Add a ticker; returns ``False`` when it is already watched."""
        symbol = str(ticker).strip().upper()
        if not _TICKER_PATTERN.fullmatch(symbol):
            raise ValueError(f"Invalid ticker: {ticker!r}")
        with closing(self._db.connect()) as conn:
            before = conn.total_changes
            conn.execute(
                """
                INSERT INTO watchlist (id, user_id, ticker, added_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (user_id, ticker) DO NOTHING
                """,
                (_new_id(), USER_ID, symbol, _utc_now()),
            )
            return conn.total_changes > before

    def remove(self, ticker: str) -> bool:
        """Remove a ticker; returns ``False`` when it is not present."""
        symbol = str(ticker).strip().upper()
        with closing(self._db.connect()) as conn:
            cursor = conn.execute(
                "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?",
                (USER_ID, symbol),
            )
            return cursor.rowcount > 0
