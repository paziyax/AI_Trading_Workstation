"""FinAlly database package.

Public surface (see ``planning/DB_CONTRACT.md``)::

    from app.db import Database, TradeError

    db = Database("db/finally.db")
    db.initialize()
    db.portfolio.execute_trade("AAPL", "buy", 10, 190.0)
    db.watchlist.add("PYPL")

The API layer must use these objects and never write SQL itself.
"""

from __future__ import annotations

from app.db.database import Database
from app.db.errors import DatabaseError, TradeError
from app.db.models import ChatMessage, Position, Profile, Snapshot, Trade
from app.db.repositories import PortfolioRepository, WatchlistRepository

__all__ = [
    "ChatMessage",
    "Database",
    "DatabaseError",
    "PortfolioRepository",
    "Position",
    "Profile",
    "Snapshot",
    "Trade",
    "TradeError",
    "WatchlistRepository",
]
