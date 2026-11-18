"""Market data layer: one interface, two sources, one shared cache, one SSE stream."""

from app.market.cache import PriceCache
from app.market.config import ConfigurationError, MarketDataConfig, Plan
from app.market.factory import create_market_data_source
from app.market.interface import MarketDataSource, SourceHealth
from app.market.models import PriceUpdate
from app.market.stream import create_stream_router, price_event_stream

__all__ = [
    "ConfigurationError",
    "MarketDataConfig",
    "MarketDataSource",
    "Plan",
    "PriceCache",
    "PriceUpdate",
    "SourceHealth",
    "create_market_data_source",
    "create_stream_router",
    "price_event_stream",
]
