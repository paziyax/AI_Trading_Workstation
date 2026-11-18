"""GBM price simulator: pure math plus a thin asyncio adapter."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import random

import numpy as np

from app.market.cache import PriceCache
from app.market.config import MarketDataConfig
from app.market.interface import HealthTracker, MarketDataSource, SourceHealth
from app.market.models import SourceMode
from app.market.seed_prices import (
    CORRELATION_GROUPS,
    CROSS_GROUP_CORR,
    DEFAULT_PARAMS,
    SEED_PRICES,
    TICKER_PARAMS,
    TSLA_CORR,
    UNKNOWN_SEED_RANGE,
)

logger = logging.getLogger(__name__)


class GBMSimulator:
    """Geometric Brownian motion with correlated moves and occasional jump events.

    ``dt`` is a fraction of a **trading year** (252 days x 6.5 h), so one 500 ms tick advances
    500 ms of market time and ``sigma`` is comparable to real annualized volatility. If the tick
    rate changes, ``dt`` must be recomputed or volatility silently rescales.
    """

    TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600  # 5,896,800
    DEFAULT_DT = 0.5 / TRADING_SECONDS_PER_YEAR  # ~8.478e-8

    def __init__(
        self,
        tickers: list[str],
        *,
        dt: float = DEFAULT_DT,
        event_probability: float = 0.001,
        np_rng: np.random.Generator | None = None,
        py_rng: random.Random | None = None,
    ) -> None:
        if not 0.0 <= event_probability <= 1.0:
            raise ValueError("event_probability must be within [0, 1]")
        if dt <= 0:
            raise ValueError("dt must be positive")

        self._dt = dt
        self._event_probability = event_probability
        self._np_rng = np_rng or np.random.default_rng()
        self._py_rng = py_rng or random.Random()
        self._tickers: list[str] = []
        self._prices: dict[str, float] = {}
        self._params: dict[str, dict[str, float]] = {}
        self._cholesky: np.ndarray | None = None
        for ticker in tickers:
            self._add_internal(ticker)
        self._rebuild_cholesky()

    @property
    def dt(self) -> float:
        return self._dt

    def step(self) -> dict[str, float]:
        """Advance one tick and return ``{ticker: rounded_price}``."""
        n = len(self._tickers)
        if n == 0:
            return {}

        z = self._np_rng.standard_normal(n)
        if self._cholesky is not None:
            z = self._cholesky @ z

        out: dict[str, float] = {}
        for i, ticker in enumerate(self._tickers):
            params = self._params[ticker]
            sigma = params["sigma"]
            drift = (params["mu"] - 0.5 * sigma * sigma) * self._dt
            diffusion = sigma * math.sqrt(self._dt) * float(z[i])
            price = self._prices[ticker] * math.exp(drift + diffusion)

            if self._py_rng.random() < self._event_probability:
                magnitude = self._py_rng.uniform(0.02, 0.05)
                price *= 1.0 + magnitude * self._py_rng.choice((-1, 1))

            self._prices[ticker] = max(price, 0.01)  # floor: no underflow to zero
            out[ticker] = round(self._prices[ticker], 2)
        return out

    def add_ticker(self, ticker: str) -> None:
        if ticker.strip().upper() in self._prices:
            return
        self._add_internal(ticker)
        self._rebuild_cholesky()

    def remove_ticker(self, ticker: str) -> None:
        ticker = ticker.strip().upper()
        if ticker not in self._prices:
            return
        self._prices.pop(ticker)
        self._params.pop(ticker)
        self._tickers.remove(ticker)
        self._rebuild_cholesky()

    def get_price(self, ticker: str) -> float | None:
        price = self._prices.get(ticker.strip().upper())
        return None if price is None else round(price, 2)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    def _add_internal(self, ticker: str) -> None:
        ticker = ticker.strip().upper()
        if ticker in self._prices:
            return
        self._tickers.append(ticker)
        self._prices[ticker] = SEED_PRICES.get(
            ticker, round(self._py_rng.uniform(*UNKNOWN_SEED_RANGE), 2)
        )
        self._params[ticker] = dict(TICKER_PARAMS.get(ticker, DEFAULT_PARAMS))

    def _rebuild_cholesky(self) -> None:
        n = len(self._tickers)
        if n <= 1:
            self._cholesky = None
            return

        corr = np.eye(n)
        for i in range(n):
            for j in range(i + 1, n):
                rho = self._pairwise_correlation(self._tickers[i], self._tickers[j])
                corr[i, j] = rho
                corr[j, i] = rho

        try:
            self._cholesky = np.linalg.cholesky(corr)
        except np.linalg.LinAlgError:
            # Arbitrary correlations may not be positive definite. Never crash a watchlist edit:
            # jitter the diagonal, and degrade to independent draws if even that fails.
            try:
                self._cholesky = np.linalg.cholesky(corr + 1e-8 * np.eye(n))
            except np.linalg.LinAlgError:
                logger.warning("Correlation matrix not positive definite; using independent draws")
                self._cholesky = None

    @staticmethod
    def _pairwise_correlation(a: str, b: str) -> float:
        if "TSLA" in (a, b):
            return TSLA_CORR
        for members, rho in CORRELATION_GROUPS.values():
            if a in members and b in members:
                return rho
        return CROSS_GROUP_CORR


class SimulatorDataSource(MarketDataSource):
    """Async adapter: lifecycle, timing, cache writes. All math lives in ``GBMSimulator``."""

    name = "simulator"

    def __init__(
        self,
        cache: PriceCache,
        config: MarketDataConfig,
        *,
        interval: float = 0.5,
    ) -> None:
        self._cache = cache
        self._config = config
        self._interval = interval
        self._sim = GBMSimulator([], event_probability=config.event_probability)
        self._health = HealthTracker("simulator", f"{interval:g} s ticks")
        self._task: asyncio.Task[None] | None = None

    @property
    def mode(self) -> SourceMode:
        return "simulator"

    def health(self) -> SourceHealth:
        return self._health.health()

    def get_tickers(self) -> list[str]:
        return self._sim.get_tickers()

    async def start(self, tickers: list[str]) -> None:
        if self._task is not None:
            return
        for ticker in tickers:
            self._sim.add_ticker(ticker)
        # Seed the cache so the first SSE frame and the first paint are populated.
        for ticker in self._sim.get_tickers():
            price = self._sim.get_price(ticker)
            if price is not None:
                self._cache.update(ticker, price, source="simulator")
        self._health.success()
        self._task = asyncio.create_task(self._run_loop(), name="simulator-loop")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def add_ticker(self, ticker: str) -> None:
        self._sim.add_ticker(ticker)
        price = self._sim.get_price(ticker)
        if price is not None:  # no blank row in the UI
            self._cache.update(ticker, price, source="simulator")

    async def remove_ticker(self, ticker: str) -> None:
        self._sim.remove_ticker(ticker)
        self._cache.remove(ticker)

    async def _run_loop(self) -> None:
        while True:
            try:
                for ticker, price in self._sim.step().items():
                    self._cache.update(ticker, price, source="simulator")
                self._health.success()
            except Exception as exc:  # noqa: BLE001 - one bad tick must not kill the feed
                logger.exception("simulator tick failed")
                self._health.failure(exc)
            await asyncio.sleep(self._interval)
