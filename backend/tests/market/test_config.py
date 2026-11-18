"""Environment parsing and plan capability model."""

from __future__ import annotations

import pytest

from app.market.config import ConfigurationError, MarketDataConfig, Plan


def test_defaults_with_empty_environment() -> None:
    config = MarketDataConfig.from_env({})
    assert config.api_key == ""
    assert config.plan is Plan.BASIC
    assert config.source == "auto"
    assert config.poll_interval == 15.0
    assert config.event_probability == pytest.approx(0.001)
    assert config.eod_refresh_seconds == 1800
    assert config.eod_lookback_days == 5


def test_reads_the_documented_variables() -> None:
    config = MarketDataConfig.from_env(
        {
            "MASSIVE_API_KEY": "  key  ",
            "MASSIVE_PLAN": "starter",
            "MARKET_DATA_SOURCE": "simulator",
            "MASSIVE_POLL_INTERVAL": "5",
            "SIM_EVENT_PROBABILITY": "0.01",
            "MASSIVE_EOD_REFRESH": "60",
            "MASSIVE_EOD_LOOKBACK": "3",
        }
    )
    assert config.api_key == "key"
    assert config.plan is Plan.STARTER
    assert config.source == "simulator"
    assert config.poll_interval == 5.0
    assert config.event_probability == pytest.approx(0.01)
    assert config.eod_refresh_seconds == 60
    assert config.eod_lookback_days == 3


def test_free_plan_enforces_a_fifteen_second_floor() -> None:
    config = MarketDataConfig.from_env({"MASSIVE_POLL_INTERVAL": "2"})
    assert config.poll_interval == 15.0


def test_paid_plan_allows_fast_polling() -> None:
    config = MarketDataConfig.from_env({"MASSIVE_PLAN": "advanced", "MASSIVE_POLL_INTERVAL": "2"})
    assert config.poll_interval == 2.0


def test_paid_plan_still_has_a_lower_bound() -> None:
    config = MarketDataConfig.from_env({"MASSIVE_PLAN": "starter", "MASSIVE_POLL_INTERVAL": "0.1"})
    assert config.poll_interval == 2.0


@pytest.mark.parametrize(
    "env",
    [
        {"MARKET_DATA_SOURCE": "stockmarket"},
        {"MASSIVE_PLAN": "platinum"},
        {"MASSIVE_POLL_INTERVAL": "soon"},
        {"MARKET_DATA_SOURCE": "massive"},
    ],
)
def test_invalid_configuration_raises(env: dict[str, str]) -> None:
    with pytest.raises(ConfigurationError):
        MarketDataConfig.from_env(env)


def test_massive_source_with_key_is_allowed() -> None:
    config = MarketDataConfig.from_env(
        {"MASSIVE_API_KEY": "key", "MARKET_DATA_SOURCE": "massive"}
    )
    assert config.source == "massive"


def test_plan_capabilities() -> None:
    assert Plan.BASIC.supports_snapshots is False
    assert Plan.STARTER.supports_snapshots is True
    assert Plan.DEVELOPER.supports_snapshots is True
    assert Plan.ADVANCED.supports_snapshots is True
    assert Plan.BASIC.snapshot_delay_minutes == 0
    assert Plan.STARTER.snapshot_delay_minutes == 15
    assert Plan.ADVANCED.snapshot_delay_minutes == 0
    assert Plan.BASIC.min_poll_interval == 15.0
    assert Plan.ADVANCED.min_poll_interval == 2.0
