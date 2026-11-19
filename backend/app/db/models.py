"""Immutable value types returned by the database layer.

The repositories return these instead of ``sqlite3.Row`` objects so callers are not coupled to
SQL column names. Only ``Trade`` exposes ``to_dict()`` — the API trade response reuses it, and
the shape is part of ``planning/API_CONTRACT.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Profile:
    id: str
    cash_balance: float
    created_at: str


@dataclass(frozen=True, slots=True)
class Position:
    ticker: str
    quantity: float
    avg_cost: float
    updated_at: str


@dataclass(frozen=True, slots=True)
class Trade:
    id: str
    ticker: str
    side: str
    quantity: float
    price: float
    executed_at: str

    def to_dict(self) -> dict[str, object]:
        """Wire format for the API trade object and the LLM context."""
        return {
            "id": self.id,
            "ticker": self.ticker,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "executed_at": self.executed_at,
        }


@dataclass(frozen=True, slots=True)
class Snapshot:
    total_value: float
    recorded_at: str


@dataclass(frozen=True, slots=True)
class ChatMessage:
    id: str
    role: str
    content: str
    actions: dict[str, Any] | None
    created_at: str
