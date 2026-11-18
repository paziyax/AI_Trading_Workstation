"""Source selection: key presence plus plan capability."""

from __future__ import annotations

import logging

from app.market.cache import PriceCache
from app.market.config import ConfigurationError, MarketDataConfig
from app.market.interface import MarketDataSource
from app.market.massive_client import MassiveDataSource
from app.market.simulator import SimulatorDataSource

logger = logging.getLogger(__name__)


def create_market_data_source(
    cache: PriceCache, config: MarketDataConfig
) -> MarketDataSource:
    """Return an unstarted source for this configuration."""
    if config.source == "simulator":
        return SimulatorDataSource(cache, config)

    if not config.api_key:
        if config.source == "massive":
            raise ConfigurationError("MARKET_DATA_SOURCE=massive requires MASSIVE_API_KEY")
        return SimulatorDataSource(cache, config)

    if not config.plan.supports_snapshots:
        logger.info("MASSIVE_PLAN=%s: using end-of-day mode", config.plan.value)
    return MassiveDataSource(cache, config)
