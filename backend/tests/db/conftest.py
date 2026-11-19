"""Fixtures for the database suite: one freshly initialized database per test."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.db import Database, PortfolioRepository, WatchlistRepository


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "finally.db")
    database.initialize()
    return database


@pytest.fixture
def portfolio(db: Database) -> PortfolioRepository:
    return db.portfolio


@pytest.fixture
def watchlist(db: Database) -> WatchlistRepository:
    return db.watchlist
