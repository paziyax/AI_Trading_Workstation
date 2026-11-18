"""PriceCache behaviour."""

from __future__ import annotations

import pytest

from app.market.cache import PriceCache


def test_first_update_has_no_previous_price() -> None:
    cache = PriceCache()
    update = cache.update("AAPL", 190.0)
    assert update.previous_price == 190.0
    assert update.direction == "flat"


def test_previous_price_is_the_previously_stored_value() -> None:
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    update = cache.update("AAPL", 191.25)
    assert update.previous_price == 190.0
    assert update.change == 1.25
    assert update.direction == "up"


def test_prices_are_rounded_to_two_dp_on_write() -> None:
    cache = PriceCache()
    update = cache.update("AAPL", 190.126)
    assert update.price == 190.13


def test_rounding_makes_deltas_exact_at_cent_precision() -> None:
    cache = PriceCache()
    cache.update("AAPL", 190.1)
    update = cache.update("AAPL", 190.3)
    assert update.change == pytest.approx(0.2, abs=1e-9)


def test_version_increments_on_every_update() -> None:
    cache = PriceCache()
    assert cache.version == 0
    cache.update("AAPL", 190.0)
    cache.update("AAPL", 190.5)
    cache.update("MSFT", 420.0)
    assert cache.version == 3


def test_remove_evicts_without_touching_version() -> None:
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    version = cache.version
    cache.remove("AAPL")
    assert cache.get("AAPL") is None
    assert cache.version == version


def test_remove_unknown_ticker_is_a_noop() -> None:
    cache = PriceCache()
    cache.remove("NOPE")
    assert len(cache) == 0


def test_lookups_are_case_insensitive() -> None:
    cache = PriceCache()
    cache.update("aapl", 190.0)
    assert cache.get("AAPL") is not None
    assert cache.get("AaPl") is not None
    assert cache.get_price("AAPL") == 190.0
    assert "AAPL" in cache


def test_snapshot_is_a_copy() -> None:
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    snapshot = cache.snapshot()
    snapshot["MSFT"] = snapshot["AAPL"]
    snapshot.clear()
    assert set(cache.snapshot()) == {"AAPL"}


def test_get_all_aliases_snapshot() -> None:
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    assert cache.get_all().keys() == cache.snapshot().keys()


def test_timestamp_is_preserved_when_supplied() -> None:
    cache = PriceCache()
    update = cache.update("AAPL", 190.0, timestamp=1794972600.0)
    assert update.timestamp == 1794972600.0


def test_source_is_recorded() -> None:
    cache = PriceCache()
    assert cache.update("AAPL", 190.0, source="eod").source == "eod"
    assert cache.update("MSFT", 420.0).source == "simulator"
