"""Fixtures for the service-layer suite: a real database and cache, no HTTP."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.db import Database
from app.market import PriceCache


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "finally.db")
    database.initialize()
    return database


@pytest.fixture
def cache() -> PriceCache:
    return PriceCache()
