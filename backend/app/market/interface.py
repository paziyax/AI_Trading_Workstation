"""The market data source contract and shared health bookkeeping."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from app.market.models import SourceMode


@dataclass(frozen=True, slots=True)
class SourceHealth:
    """Snapshot of a source's health, rendered by the header connection dot."""

    mode: SourceMode
    connected: bool
    last_success_at: float | None
    consecutive_failures: int
    last_error: str | None
    detail: str
    age_seconds: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "connected": self.connected,
            "last_success_at": self.last_success_at,
            "consecutive_failures": self.consecutive_failures,
            "last_error": self.last_error,
            "detail": self.detail,
            "age_seconds": self.age_seconds,
        }


class HealthTracker:
    """Data-driven health: consumers derive the dot from age and failures, not a state machine."""

    def __init__(self, mode: SourceMode, detail: str = "") -> None:
        self._mode = mode
        self._detail = detail
        self._last_success: float | None = None
        self._failures = 0
        self._last_error: str | None = None

    def success(self, detail: str | None = None) -> None:
        self._last_success = time.time()
        self._failures = 0
        self._last_error = None
        if detail is not None:
            self._detail = detail

    def failure(self, exc: BaseException) -> None:
        self._failures += 1
        self._last_error = f"{type(exc).__name__}: {exc}"[:200]

    def note(self, detail: str) -> None:
        """Relabel without claiming success or failure (e.g. "market closed")."""
        self._detail = detail

    def set_mode(self, mode: SourceMode) -> None:
        self._mode = mode

    @property
    def consecutive_failures(self) -> int:
        return self._failures

    def health(self) -> SourceHealth:
        age = None if self._last_success is None else round(time.time() - self._last_success, 1)
        return SourceHealth(
            mode=self._mode,
            connected=self._last_success is not None and self._failures == 0,
            last_success_at=self._last_success,
            consecutive_failures=self._failures,
            last_error=self._last_error,
            detail=self._detail,
            age_seconds=age,
        )


class MarketDataSource(ABC):
    """Pushes prices into a ``PriceCache``.

    Implementations never return prices to callers and never block a request handler. These rules
    are enforced by ``tests/market/test_conformance.py``.

    1. Push, don't pull: the cache is the only exit.
    2. ``start()`` runs once, seeds the cache where possible, and must not raise because a vendor
       call failed.
    3. ``stop()`` is idempotent; no cache writes may occur after it returns.
    4. ``add_ticker`` / ``remove_ticker`` are no-ops when already/not present; removal evicts the
       cache entry too.
    5. Background tasks swallow-and-log.
    6. ``get_tickers()`` returns a copy; tickers are uppercased at the boundary.
    """

    name: ClassVar[str]

    @property
    @abstractmethod
    def mode(self) -> SourceMode: ...

    @abstractmethod
    async def start(self, tickers: list[str]) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None: ...

    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None: ...

    @abstractmethod
    def get_tickers(self) -> list[str]: ...

    @abstractmethod
    def health(self) -> SourceHealth: ...
