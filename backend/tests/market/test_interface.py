"""Health bookkeeping shared by both sources."""

from __future__ import annotations

import pytest

from app.market.interface import HealthTracker, SourceHealth


def test_initial_health_is_disconnected() -> None:
    tracker = HealthTracker("simulator", "seeded")
    health = tracker.health()
    assert health.connected is False
    assert health.consecutive_failures == 0
    assert tracker.consecutive_failures == 0
    assert health.last_success_at is None
    assert health.age_seconds is None
    assert health.last_error is None
    assert health.detail == "seeded"


def test_success_marks_connected_and_clears_the_error() -> None:
    tracker = HealthTracker("eod")
    tracker.failure(RuntimeError("boom"))
    assert tracker.health().connected is False

    tracker.success("2026-11-24 close")
    health = tracker.health()
    assert health.connected is True
    assert health.consecutive_failures == 0
    assert tracker.consecutive_failures == 0
    assert health.last_error is None
    assert health.last_success_at is not None
    assert health.age_seconds == pytest.approx(0.0, abs=0.5)
    assert health.detail == "2026-11-24 close"


def test_failures_accumulate_and_record_the_error_type() -> None:
    tracker = HealthTracker("snapshot")
    tracker.failure(ValueError("nope"))
    assert tracker.health().last_error == "ValueError: nope"
    assert tracker.consecutive_failures == 1

    tracker.failure(ValueError("again"))
    assert tracker.consecutive_failures == 2


def test_long_errors_are_truncated() -> None:
    tracker = HealthTracker("snapshot")
    tracker.failure(RuntimeError("x" * 500))
    assert len(tracker.health().last_error or "") == 200


def test_note_relabels_without_claiming_success_or_failure() -> None:
    tracker = HealthTracker("snapshot", "1/3 tickers")
    tracker.success()
    tracker.note("market closed")

    health = tracker.health()
    assert health.detail == "market closed"
    assert health.connected is True
    assert health.consecutive_failures == 0


def test_set_mode_relabels_the_source() -> None:
    tracker = HealthTracker("snapshot")
    tracker.set_mode("eod")
    assert tracker.health().mode == "eod"


def test_age_is_rounded_to_one_decimal(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 1_000.0}
    monkeypatch.setattr("app.market.interface.time.time", lambda: clock["now"])

    tracker = HealthTracker("simulator")
    tracker.success()
    clock["now"] = 1_002.34

    assert tracker.health().age_seconds == 2.3


def test_source_health_to_dict_matches_the_wire_shape() -> None:
    health = SourceHealth(
        mode="eod",
        connected=True,
        last_success_at=1.0,
        consecutive_failures=0,
        last_error=None,
        detail="close",
        age_seconds=2.5,
    )
    assert health.to_dict() == {
        "mode": "eod",
        "connected": True,
        "last_success_at": 1.0,
        "consecutive_failures": 0,
        "last_error": None,
        "detail": "close",
        "age_seconds": 2.5,
    }
