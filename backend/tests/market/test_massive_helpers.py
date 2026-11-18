"""Normalization and detection helpers used by the Massive source."""

from __future__ import annotations

from datetime import date

import pytest
from massive.exceptions import BadResponse

from app.market.massive_client import (
    extract_price,
    is_not_entitled,
    previous_trading_day,
    to_unix_seconds,
)
from tests.market.conftest import bar, snapshot

NOT_ENTITLED_BODY = (
    '{"status":"NOT_AUTHORIZED","request_id":"abc",'
    '"message":"You are not entitled to this data. Please upgrade your plan at '
    'https://massive.com/pricing."}'
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (1794972600512000000, 1794972600.512),  # snapshot: nanoseconds
        (1794972600000, 1794972600.0),          # bar: milliseconds
        (1794972600, 1794972600.0),             # already seconds
        (None, None),
    ],
)
def test_to_unix_seconds_normalizes_by_magnitude(raw: int | None, expected: float | None) -> None:
    result = to_unix_seconds(raw)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


def test_last_trade_wins_when_present() -> None:
    snap = snapshot(
        "AAPL",
        last_trade=bar(price=190.5, timestamp=1794972600000),
        minute=bar(close=190.4),
        day=bar(close=190.3),
        prev_day=bar(close=190.0),
    )
    assert extract_price(snap) == (190.5, 1794972600.0)


def test_falls_back_to_the_minute_bar_without_trades_entitlement() -> None:
    snap = snapshot(
        "AAPL",
        minute=bar(close=190.4, timestamp=1794972600000),
        day=bar(close=190.3),
        prev_day=bar(close=190.0),
    )
    assert extract_price(snap) == (190.4, 1794972600.0)


def test_falls_back_to_the_day_bar() -> None:
    snap = snapshot("AAPL", minute=bar(close=None), day=bar(close=190.3), prev_day=bar(close=190))
    assert extract_price(snap) == (190.3, None)


def test_falls_back_to_the_previous_day() -> None:
    snap = snapshot("AAPL", day=bar(close=None), prev_day=bar(close=190.0))
    assert extract_price(snap) == (190.0, None)


def test_returns_none_when_everything_is_empty() -> None:
    assert extract_price(snapshot("AAPL")) is None


def test_not_entitled_is_detected_from_the_body() -> None:
    assert is_not_entitled(BadResponse(NOT_ENTITLED_BODY)) is True
    assert is_not_entitled(BadResponse('{"status":"NOT_AUTHORIZED"}')) is True


def test_other_failures_are_not_treated_as_entitlement() -> None:
    assert is_not_entitled(BadResponse('{"status":"ERROR","error":"boom"}')) is False
    assert is_not_entitled(BadResponse("HTTP 500")) is False


@pytest.mark.parametrize(
    ("start", "expected"),
    [
        (date(2026, 11, 23), date(2026, 11, 20)),  # Monday -> Friday
        (date(2026, 11, 22), date(2026, 11, 20)),  # Sunday -> Friday
        (date(2026, 11, 28), date(2026, 11, 27)),  # Saturday -> Friday
        (date(2026, 11, 25), date(2026, 11, 24)),  # Wednesday -> Tuesday
    ],
)
def test_previous_trading_day_skips_weekends(start: date, expected: date) -> None:
    assert previous_trading_day(start) == expected
