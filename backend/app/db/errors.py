"""Database-layer exceptions.

``TradeError`` is the only domain error the API maps to HTTP 400. Validation errors raised as
``ValueError`` describe malformed input rather than a violated trading rule.
"""

from __future__ import annotations


class DatabaseError(RuntimeError):
    """Base error for database-layer failures (missing schema, missing profile, ...)."""


class TradeError(DatabaseError):
    """A trade request violated a trading rule (cash, holdings, missing position)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
