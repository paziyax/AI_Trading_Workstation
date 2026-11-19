"""SQLite connection factory and lazy, idempotent schema bootstrap.

The layer is deliberately synchronous: SQLite calls are sub-millisecond and FinAlly has a single
user. Each repository method opens a short-lived connection, so no connection state leaks between
requests; ``BEGIN IMMEDIATE`` in ``execute_trade`` serializes read-modify-write sequences.

The database path comes from ``FINALLY_DB_PATH`` at the API layer; this class only receives a
filesystem path. ``backend/db/schema.sql`` and ``backend/db/seed.sql`` are the single source of
DDL and seed data.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.db.repositories import PortfolioRepository, WatchlistRepository

SQL_DIR = Path(__file__).resolve().parents[2] / "db"
SCHEMA_FILE = SQL_DIR / "schema.sql"
SEED_FILE = SQL_DIR / "seed.sql"


class Database:
    """Owns the SQLite file and hands out configured connections."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._portfolio: PortfolioRepository | None = None
        self._watchlist: WatchlistRepository | None = None

    @property
    def path(self) -> Path:
        return self._path

    def connect(self) -> sqlite3.Connection:
        """Open a connection with row access by name and the required PRAGMAs.

        The caller owns the connection and must close it. WAL is set on every connection because
        it is a persistent database property once enabled; re-issuing it is a cheap no-op.
        """
        connection = sqlite3.connect(
            self._path,
            timeout=5,
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def initialize(self) -> None:
        """Create the parent directory, apply the schema and seed missing defaults.

        Safe to call on every process start: the schema uses ``IF NOT EXISTS`` and the seed only
        inserts data that is absent (the watchlist is seeded only while it is empty).
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = self.connect()
        try:
            connection.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
            connection.executescript(SEED_FILE.read_text(encoding="utf-8"))
        finally:
            connection.close()

    @property
    def portfolio(self) -> PortfolioRepository:
        if self._portfolio is None:
            self._portfolio = PortfolioRepository(self)
        return self._portfolio

    @property
    def watchlist(self) -> WatchlistRepository:
        if self._watchlist is None:
            self._watchlist = WatchlistRepository(self)
        return self._watchlist
