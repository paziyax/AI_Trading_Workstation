"""Thread-safe price cache: one writer, many readers, one version counter."""

from __future__ import annotations

import threading
import time

from app.market.models import PriceUpdate, SourceMode


class PriceCache:
    """Latest price per ticker, guarded by a lock.

    ``threading.Lock`` rather than asyncio primitives because the Massive path writes from
    ``asyncio.to_thread``. Exactly one producer writes; ``version`` increments on every write and
    is the SSE change-detection primitive.

    Prices are rounded to 2 dp on write, so ``change`` is exact at cent precision and flash
    animations never fire on float noise. ``previous_price`` is the previously *stored* value,
    which is already rounded.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._prices: dict[str, PriceUpdate] = {}
        self._version = 0

    def update(
        self,
        ticker: str,
        price: float,
        *,
        source: SourceMode = "simulator",
        timestamp: float | None = None,
    ) -> PriceUpdate:
        ticker = ticker.strip().upper()
        value = round(float(price), 2)
        with self._lock:
            previous = self._prices.get(ticker)
            update = PriceUpdate(
                ticker=ticker,
                price=value,
                previous_price=previous.price if previous is not None else value,
                timestamp=time.time() if timestamp is None else timestamp,
                source=source,
            )
            self._prices[ticker] = update
            self._version += 1
            return update

    def get(self, ticker: str) -> PriceUpdate | None:
        with self._lock:
            return self._prices.get(ticker.strip().upper())

    def get_price(self, ticker: str) -> float | None:
        update = self.get(ticker)
        return None if update is None else update.price

    def snapshot(self) -> dict[str, PriceUpdate]:
        """Shallow copy of the whole map, safe to serialize."""
        with self._lock:
            return dict(self._prices)

    def get_all(self) -> dict[str, PriceUpdate]:
        """Alias for :meth:`snapshot`, kept for the interface documented in the planning notes."""
        return self.snapshot()

    def remove(self, ticker: str) -> None:
        with self._lock:
            self._prices.pop(ticker.strip().upper(), None)

    @property
    def version(self) -> int:
        with self._lock:
            return self._version

    def __len__(self) -> int:
        with self._lock:
            return len(self._prices)

    def __contains__(self, ticker: object) -> bool:
        return isinstance(ticker, str) and self.get(ticker) is not None
