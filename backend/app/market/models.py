"""The single value type that leaves the market data layer."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

SourceMode = Literal["simulator", "snapshot", "eod"]
Direction = Literal["up", "down", "flat"]


@dataclass(frozen=True, slots=True)
class PriceUpdate:
    """An immutable price observation.

    ``timestamp`` is Unix **seconds** at this boundary; vendor nanoseconds and milliseconds are
    normalized by the source implementation. The first update for a ticker carries
    ``previous_price == price`` so ``direction`` is ``"flat"`` rather than an error.
    """

    ticker: str
    price: float
    previous_price: float
    timestamp: float = field(default_factory=time.time)
    source: SourceMode = "simulator"

    @property
    def change(self) -> float:
        return round(self.price - self.previous_price, 4)

    @property
    def change_percent(self) -> float:
        if not self.previous_price:
            return 0.0
        return round((self.price - self.previous_price) / self.previous_price * 100.0, 4)

    @property
    def direction(self) -> Direction:
        if self.price > self.previous_price:
            return "up"
        if self.price < self.previous_price:
            return "down"
        return "flat"

    def to_dict(self) -> dict[str, object]:
        """Wire format sent verbatim inside SSE frames."""
        return {
            "ticker": self.ticker,
            "price": self.price,
            "previous_price": self.previous_price,
            "timestamp": self.timestamp,
            "change": self.change,
            "change_percent": self.change_percent,
            "direction": self.direction,
            "source": self.source,
        }
