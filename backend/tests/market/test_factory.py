"""Source selection is driven by key presence and plan capability, not key presence alone."""

from __future__ import annotations

import pytest

from app.market.cache import PriceCache
from app.market.config import ConfigurationError, Plan
from app.market.factory import create_market_data_source
from app.market.massive_client import MassiveDataSource
from app.market.simulator import SimulatorDataSource
from tests.market.conftest import make_config


def test_explicit_simulator_source_ignores_the_key() -> None:
    source = create_market_data_source(
        PriceCache(), make_config(api_key="key", source="simulator")
    )
    assert isinstance(source, SimulatorDataSource)


def test_auto_without_key_uses_the_simulator() -> None:
    source = create_market_data_source(PriceCache(), make_config(api_key="", source="auto"))
    assert isinstance(source, SimulatorDataSource)


def test_auto_with_key_and_basic_plan_uses_eod_massive() -> None:
    source = create_market_data_source(
        PriceCache(), make_config(api_key="key", source="auto", plan=Plan.BASIC)
    )
    assert isinstance(source, MassiveDataSource)
    assert source.mode == "eod"


def test_auto_with_key_and_paid_plan_uses_snapshots() -> None:
    source = create_market_data_source(
        PriceCache(), make_config(api_key="key", source="auto", plan=Plan.STARTER)
    )
    assert isinstance(source, MassiveDataSource)
    assert source.mode == "snapshot"


def test_explicit_massive_with_key_is_allowed() -> None:
    source = create_market_data_source(
        PriceCache(), make_config(api_key="key", source="massive", plan=Plan.ADVANCED)
    )
    assert isinstance(source, MassiveDataSource)


def test_explicit_massive_without_key_is_a_configuration_error() -> None:
    with pytest.raises(ConfigurationError):
        create_market_data_source(
            PriceCache(), make_config(api_key="", source="massive")
        )
