"""PriceUpdate value semantics."""

from __future__ import annotations

import dataclasses

import pytest

from app.market.models import PriceUpdate


def test_first_update_is_flat() -> None:
    update = PriceUpdate(ticker="AAPL", price=190.0, previous_price=190.0)
    assert update.direction == "flat"
    assert update.change == 0.0
    assert update.change_percent == 0.0


def test_direction_up_and_down() -> None:
    up = PriceUpdate(ticker="AAPL", price=190.5, previous_price=190.0)
    down = PriceUpdate(ticker="AAPL", price=189.5, previous_price=190.0)
    assert up.direction == "up"
    assert down.direction == "down"
    assert up.change == 0.5
    assert down.change == -0.5


def test_change_percent_is_four_dp() -> None:
    update = PriceUpdate(ticker="AAPL", price=190.11, previous_price=190.0)
    assert update.change_percent == pytest.approx(0.0579, abs=1e-4)


def test_change_percent_guards_zero_previous() -> None:
    update = PriceUpdate(ticker="AAPL", price=10.0, previous_price=0.0)
    assert update.change_percent == 0.0


def test_to_dict_matches_wire_contract() -> None:
    update = PriceUpdate(
        ticker="AAPL", price=190.52, previous_price=190.41, timestamp=1794972600.512
    )
    payload = update.to_dict()
    assert payload == {
        "ticker": "AAPL",
        "price": 190.52,
        "previous_price": 190.41,
        "timestamp": 1794972600.512,
        "change": 0.11,
        "change_percent": pytest.approx(0.0578, abs=1e-4),
        "direction": "up",
        "source": "simulator",
    }


def test_update_is_immutable() -> None:
    update = PriceUpdate(ticker="AAPL", price=190.0, previous_price=190.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        update.price = 191.0  # type: ignore[misc]


def test_timestamp_defaults_to_now() -> None:
    first = PriceUpdate(ticker="AAPL", price=190.0, previous_price=190.0)
    second = PriceUpdate(ticker="AAPL", price=190.0, previous_price=190.0)
    assert first.timestamp > 1_600_000_000
    assert second.timestamp >= first.timestamp
