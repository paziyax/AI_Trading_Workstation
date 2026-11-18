# Market Data Backend — Implementation Design

How to build the market data layer end to end: one interface, two implementations (simulator and
Massive), one shared cache, one SSE stream. Code is written for **Python 3.12 / numpy 2 / massive
2.10+** and matches `backend/pyproject.toml`.

Companion references (read for the *why*, this document for the *what*):
`archive/MASSIVE_API.md` (endpoints, entitlements, timestamps), `archive/MARKET_INTERFACE.md`
(contract), `archive/MARKET_SIMULATOR.md` (model), `PLAN.md` §6 (requirements).

**Status:** the application code was removed from the repository, so this is a greenfield build.
Everything below is code to write, not code to modify.

---

## 1. Module map

```
backend/app/market/
├── __init__.py          # public exports
├── models.py            # PriceUpdate
├── interface.py         # MarketDataSource, SourceMode, SourceHealth, HealthTracker
├── cache.py             # PriceCache
├── config.py            # MarketDataConfig, Plan, ConfigurationError
├── seed_prices.py       # SEED_PRICES, TICKER_PARAMS, correlation tables
├── simulator.py         # GBMSimulator + SimulatorDataSource
├── massive_client.py    # MassiveDataSource (snapshot + eod modes)
├── factory.py           # create_market_data_source()
└── stream.py            # create_stream_router() → GET /api/stream/prices
```

Dependency direction is strictly one-way:

```
config ─┐
models ─┼─▶ interface ─▶ cache ─▶ stream
        │                    ▲
        ├─▶ simulator ───────┤
        ├─▶ massive_client ──┤
        └─▶ factory ─────────┘
```

`cache`, `models`, `stream` never import `simulator` or `massive_client`. That is what makes the
source swappable and the tests fast.

**Additions beyond `PLAN.md` §8** (all optional, all backward compatible):

| Addition | Why |
|---|---|
| `MASSIVE_PLAN` env var | Key presence does not imply snapshot access; without it a free key 403-loops |
| `MARKET_DATA_SOURCE` env var | Force the simulator for demos/CI even when a key exists |
| `GET /api/market/status` | The header's connection dot needs mode + staleness, not just prices |
| `PriceUpdate.source` | Lets the UI label prices "simulated" / "delayed" / "EOD" |

---

## 2. Configuration and capability

The single most important rule: **a key is not a capability.** A Basic key can call grouped-daily but
gets `403` on every snapshot endpoint.

### `config.py`

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class ConfigurationError(RuntimeError):
    """Invalid or contradictory market data configuration."""


class Plan(str, Enum):
    BASIC = "basic"
    STARTER = "starter"
    DEVELOPER = "developer"
    ADVANCED = "advanced"

    @property
    def supports_snapshots(self) -> bool:
        return self is not Plan.BASIC

    @property
    def snapshot_delay_minutes(self) -> int:
        return {"basic": 0, "starter": 15, "developer": 15, "advanced": 0}[self.value]

    @property
    def min_poll_interval(self) -> float:
        return 15.0 if self is Plan.BASIC else 2.0


def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, default).strip().lower()


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    try:
        return float(raw) if raw else default
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number, got {raw!r}") from exc


@dataclass(frozen=True, slots=True)
class MarketDataConfig:
    api_key: str
    plan: Plan
    source: str                     # auto | massive | simulator
    poll_interval: float            # seconds, snapshot mode
    event_probability: float        # simulator
    eod_refresh_seconds: int        # how often to re-check for a new session
    eod_lookback_days: int          # holiday tolerance

    @classmethod
    def from_env(cls) -> "MarketDataConfig":
        api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
        source = _env_str("MARKET_DATA_SOURCE", "auto")
        if source not in {"auto", "massive", "simulator"}:
            raise ConfigurationError(
                f"MARKET_DATA_SOURCE must be auto|massive|simulator, got {source!r}"
            )
        try:
            plan = Plan(_env_str("MASSIVE_PLAN", "basic"))
        except ValueError as exc:
            raise ConfigurationError(f"Unknown MASSIVE_PLAN {exc}") from exc

        if source == "massive" and not api_key:
            raise ConfigurationError("MARKET_DATA_SOURCE=massive requires MASSIVE_API_KEY")

        poll_interval = max(plan.min_poll_interval, _env_float("MASSIVE_POLL_INTERVAL", 15.0))
        return cls(
            api_key=api_key,
            plan=plan,
            source=source,
            poll_interval=poll_interval,
            event_probability=_env_float("SIM_EVENT_PROBABILITY", 0.001),
            eod_refresh_seconds=int(_env_float("MASSIVE_EOD_REFRESH", 1800)),
            eod_lookback_days=int(_env_float("MASSIVE_EOD_LOOKBACK", 5)),
        )
```

`.env` additions (all optional):

```bash
MASSIVE_API_KEY=
MASSIVE_PLAN=basic          # basic | starter | developer | advanced
MARKET_DATA_SOURCE=auto     # auto | massive | simulator
MASSIVE_POLL_INTERVAL=15
```

**Default `MASSIVE_PLAN=basic` is deliberate.** Guessing "paid" produces a 403 loop and an empty UI;
guessing "free" produces correct end-of-day prices. Optimistic defaults are the wrong way round here.

---

## 3. `models.py` — the only shape that leaves the layer

```python
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

SourceMode = Literal["simulator", "snapshot", "eod"]
Direction = Literal["up", "down", "flat"]


@dataclass(frozen=True, slots=True)
class PriceUpdate:
    ticker: str
    price: float
    previous_price: float
    timestamp: float = field(default_factory=time.time)   # Unix SECONDS
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
```

Rules: frozen (no consumer mutation), derived fields computed (cannot drift), **seconds** at this
boundary (vendor ns/ms normalized by the source), and the first update has `previous_price == price`
so `direction == "flat"` — never an error.

---

## 4. `interface.py` — the contract

```python
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from app.market.models import SourceMode


@dataclass(frozen=True, slots=True)
class SourceHealth:
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
    """Shared bookkeeping so the header dot is data-driven, not a state machine."""

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
        """Update the label without claiming success or failure (e.g. 'market closed')."""
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
    """Push prices into a PriceCache. Never returns prices, never blocks a request."""

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
```

The six invariants every implementation must honour (and the conformance tests enforce):

1. **Push, don't pull.** No method returns a price; the cache is the only exit.
2. `start()` seeds the cache before returning where possible and **must not raise** because a vendor
   call failed — log, record health, keep going.
3. `stop()` is idempotent; after it returns, no cache writes occur.
4. `add_ticker` / `remove_ticker` are no-ops when already/not present; `remove_ticker` evicts the
   cache entry too.
5. Background tasks swallow-and-log; an escaping exception is lost or crashes on GC.
6. `get_tickers()` returns a copy; tickers are uppercased at the boundary.

---

## 5. `cache.py` — single writer, many readers

```python
from __future__ import annotations

import threading
import time

from app.market.models import PriceUpdate, SourceMode


class PriceCache:
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
            return self._prices.get(ticker.upper())

    def get_price(self, ticker: str) -> float | None:
        update = self.get(ticker)
        return None if update is None else update.price

    def snapshot(self) -> dict[str, PriceUpdate]:
        with self._lock:
            return dict(self._prices)

    def remove(self, ticker: str) -> None:
        with self._lock:
            self._prices.pop(ticker.upper(), None)

    @property
    def version(self) -> int:
        with self._lock:
            return self._version

    def __len__(self) -> int:
        with self._lock:
            return len(self._prices)

    def __contains__(self, ticker: object) -> bool:
        return isinstance(ticker, str) and self.get(ticker) is not None
```

* `threading.Lock`, not asyncio primitives: the Massive path writes from `asyncio.to_thread`.
* Round to 2 dp **on write**. `previous_price` is the previously stored value, already rounded, so
  re-rounding is a no-op and `change` is exact at cent precision. This is also what stops flash
  animations firing on float noise.
* `version` increments on every write; it is the only change-detection primitive SSE needs.
* **One writer only.** Two would interleave and produce meaningless `change` values.

---

## 6. Simulator

### 6.1 `seed_prices.py`

```python
SEED_PRICES: dict[str, float] = {
    "AAPL": 190.00, "GOOGL": 175.00, "MSFT": 420.00, "AMZN": 185.00, "TSLA": 250.00,
    "NVDA": 800.00, "META": 500.00, "JPM": 195.00, "V": 280.00, "NFLX": 600.00,
}

TICKER_PARAMS: dict[str, dict[str, float]] = {
    "AAPL": {"sigma": 0.22, "mu": 0.05}, "GOOGL": {"sigma": 0.25, "mu": 0.05},
    "MSFT": {"sigma": 0.20, "mu": 0.05}, "AMZN": {"sigma": 0.28, "mu": 0.05},
    "TSLA": {"sigma": 0.50, "mu": 0.03}, "NVDA": {"sigma": 0.40, "mu": 0.08},
    "META": {"sigma": 0.30, "mu": 0.05}, "JPM": {"sigma": 0.18, "mu": 0.04},
    "V": {"sigma": 0.17, "mu": 0.04}, "NFLX": {"sigma": 0.35, "mu": 0.05},
}

DEFAULT_PARAMS = {"sigma": 0.25, "mu": 0.05}

# name -> (members, correlation)
CORRELATION_GROUPS: dict[str, tuple[frozenset[str], float]] = {
    "tech": (frozenset({"AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "NFLX"}), 0.6),
    "finance": (frozenset({"JPM", "V"}), 0.5),
}
TSLA_CORR = 0.3          # checked first: TSLA does its own thing
CROSS_GROUP_CORR = 0.3
UNKNOWN_SEED_RANGE = (50.0, 300.0)
```

Constants only. Any derived value (matrix, drift) is computed in `simulator.py`, or it goes stale and
becomes untestable.

### 6.2 `GBMSimulator` — pure math, no I/O, no asyncio

```python
from __future__ import annotations

import math
import random

import numpy as np

from app.market.seed_prices import (
    CORRELATION_GROUPS, CROSS_GROUP_CORR, DEFAULT_PARAMS, SEED_PRICES,
    TICKER_PARAMS, TSLA_CORR, UNKNOWN_SEED_RANGE,
)


class GBMSimulator:
    TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600          # 5,896,800
    DEFAULT_DT = 0.5 / TRADING_SECONDS_PER_YEAR           # ≈ 8.478e-8

    def __init__(
        self,
        tickers: list[str],
        *,
        dt: float = DEFAULT_DT,
        event_probability: float = 0.001,
        np_rng: np.random.Generator | None = None,
        py_rng: random.Random | None = None,
    ) -> None:
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

    # -- public API -------------------------------------------------------
    def step(self) -> dict[str, float]:
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
            self._prices[ticker] = max(price, 0.01)      # floor: no underflow to zero
            out[ticker] = round(self._prices[ticker], 2)
        return out

    def add_ticker(self, ticker: str) -> None:
        if ticker.upper() in self._prices:
            return
        self._add_internal(ticker)
        self._rebuild_cholesky()

    def remove_ticker(self, ticker: str) -> None:
        ticker = ticker.upper()
        if ticker not in self._prices:
            return
        self._prices.pop(ticker)
        self._params.pop(ticker)
        self._tickers.remove(ticker)
        self._rebuild_cholesky()

    def get_price(self, ticker: str) -> float | None:
        price = self._prices.get(ticker.upper())
        return None if price is None else round(price, 2)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    # -- internals --------------------------------------------------------
    def _add_internal(self, ticker: str) -> None:
        ticker = ticker.upper()
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
                corr[i, j] = corr[j, i] = rho
        try:
            self._cholesky = np.linalg.cholesky(corr)
        except np.linalg.LinAlgError:
            # An arbitrary correlation set may not be positive definite. Never crash a watchlist
            # edit: jitter the diagonal, and fall back to independent draws if that fails too.
            try:
                self._cholesky = np.linalg.cholesky(corr + 1e-8 * np.eye(n))
            except np.linalg.LinAlgError:
                self._cholesky = None

    @staticmethod
    def _pairwise_correlation(a: str, b: str) -> float:
        if "TSLA" in (a, b):
            return TSLA_CORR
        for members, rho in CORRELATION_GROUPS.values():
            if a in members and b in members:
                return rho
        return CROSS_GROUP_CORR
```

Why these numbers: `dt` is a fraction of a **trading year** (252 × 6.5 h), so one 500 ms tick is
500 ms of market time and `sigma` is directly comparable to real annualized volatility. Change the tick
rate and you must recompute `dt`, or volatility silently rescales. `mu` is irrelevant at these horizons
(`0.05 · dt` per tick ≈ 4e-9) — it exists so the model is a proper GBM, not to make trends.

### 6.3 `SimulatorDataSource`

```python
from __future__ import annotations

import asyncio
import contextlib
import logging

from app.market.cache import PriceCache
from app.market.config import MarketDataConfig
from app.market.interface import HealthTracker, MarketDataSource, SourceHealth
from app.market.models import SourceMode
from app.market.simulator import GBMSimulator

logger = logging.getLogger(__name__)


class SimulatorDataSource(MarketDataSource):
    name = "simulator"

    def __init__(self, cache: PriceCache, config: MarketDataConfig, *, interval: float = 0.5) -> None:
        self._cache = cache
        self._config = config
        self._interval = interval
        self._sim = GBMSimulator([], event_probability=config.event_probability)
        self._health = HealthTracker("simulator", "0.5 s ticks")
        self._task: asyncio.Task[None] | None = None

    @property
    def mode(self) -> SourceMode:
        return "simulator"

    def health(self) -> SourceHealth:
        return self._health.health()

    def get_tickers(self) -> list[str]:
        return self._sim.get_tickers()

    async def start(self, tickers: list[str]) -> None:
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
        if price is not None:                       # no blank row in the UI
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
            except Exception as exc:                # noqa: BLE001 - one bad tick must not kill the feed
                logger.exception("simulator tick failed")
                self._health.failure(exc)
            await asyncio.sleep(self._interval)
```

Determinism for tests: pass `np_rng=np.random.default_rng(42)` and `py_rng=random.Random(42)` to
`GBMSimulator`; the sequence replays byte-identically.

---

## 7. Massive source

Two modes, one class. `snapshot` polls the multi-ticker snapshot endpoint (Starter+). `eod` fetches
one grouped-daily response per session (Basic). The class can **downgrade** from snapshot to EOD at
runtime if the account turns out to lack the entitlement.

### 7.1 Normalization helpers

```python
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from massive.exceptions import BadResponse

NS_THRESHOLD = 10**17
MS_THRESHOLD = 10**12


def to_unix_seconds(ts: int | None) -> float | None:
    """Massive gives nanoseconds for snapshots and milliseconds for bars. Normalize to seconds."""
    if ts is None:
        return None
    if ts > NS_THRESHOLD:
        return ts / 1e9
    if ts > MS_THRESHOLD:
        return ts / 1e3
    return float(ts)


def extract_price(snapshot: Any) -> tuple[float, float | None] | None:
    """Best available price for a snapshot. Precedence: lastTrade -> min -> day -> prevDay."""
    for bar, field in (
        (snapshot.last_trade, "price"),
        (snapshot.min, "close"),
        (snapshot.day, "close"),
        (snapshot.prev_day, "close"),
    ):
        if bar is None:
            continue
        value = getattr(bar, field, None)
        if value is not None:
            return float(value), to_unix_seconds(getattr(bar, "timestamp", None))
    return None


def is_not_entitled(exc: BadResponse) -> bool:
    """The client raises BadResponse with the response BODY only — there is no status code."""
    text = str(exc).lower()
    return "not_authorized" in text or "not entitled" in text


def previous_trading_day(start: date) -> date:
    """Step back to the previous weekday. Holidays are detected by querying, not by guessing."""
    day = start - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day
```

`is_not_entitled` matters: `massive` wraps every non-200 into `BadResponse(body_text)`, so a 403 and a
500 look identical unless you inspect the body. `NOT_AUTHORIZED` + "not entitled" is what the API
actually returns on a Basic key.

### 7.2 Snapshot mode

Both methods in 7.2 and 7.3 belong to `MassiveDataSource` — they are shown separately only to keep
`start()`/loops readable.

```python
def _fetch_snapshot_batch(self) -> dict[str, tuple[float, float | None]]:
    snaps = self._client.get_snapshot_all(
        market_type=SnapshotMarketType.STOCKS, tickers=sorted(self._tickers)
    )
    out: dict[str, tuple[float, float | None]] = {}
    for snap in snaps:
        extracted = extract_price(snap)
        if extracted is not None and snap.ticker:
            out[snap.ticker] = extracted
    return out
```

Called through `asyncio.to_thread` — the client is synchronous and must never run on the event loop.
Missing tickers are normal (delisted, mistyped, outside session): skip them, never abort the batch.

### 7.3 EOD mode

```python
def _fetch_eod(self) -> tuple[date, dict[str, float]]:
    wanted = set(self._tickers)
    day = previous_trading_day(date.today())

    for _ in range(self._config.eod_lookback_days):
        rows = self._client.get_grouped_daily_aggs(date=day.isoformat(), adjusted=True)
        prices = {r.ticker: r.close for r in rows if r.ticker in wanted and r.close is not None}
        if prices:
            return day, prices
        day = previous_trading_day(day)      # holiday, or not published yet

    raise RuntimeError(
        f"No grouped-daily data in the last {self._config.eod_lookback_days} sessions"
    )
```

A non-trading date is HTTP **200 with an empty result set**, not an error — so emptiness, not an
exception, drives the loop. One call fetches the entire watchlist; that is the whole daily budget on a
free key.

### 7.4 `MassiveDataSource`

```python
from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
from datetime import date

from massive import RESTClient
from massive.exceptions import AuthError, BadResponse
from massive.rest.models import SnapshotMarketType

from app.market.cache import PriceCache
from app.market.config import MarketDataConfig
from app.market.interface import HealthTracker, MarketDataSource, SourceHealth
from app.market.models import SourceMode

logger = logging.getLogger(__name__)


class MassiveDataSource(MarketDataSource):
    name = "massive"

    def __init__(self, cache: PriceCache, config: MarketDataConfig) -> None:
        self._cache = cache
        self._config = config
        self._tickers: set[str] = set()
        self._client: RESTClient | None = None
        self._mode: SourceMode = "snapshot" if config.plan.supports_snapshots else "eod"
        self._health = HealthTracker(self._mode)
        self._task: asyncio.Task[None] | None = None
        self._eod_day: date | None = None
        self._market_open = True
        self._status_checked_at: float = 0.0

    @property
    def mode(self) -> SourceMode:
        return self._mode

    def health(self) -> SourceHealth:
        return self._health.health()

    def get_tickers(self) -> list[str]:
        return sorted(self._tickers)

    # -- lifecycle --------------------------------------------------------
    async def start(self, tickers: list[str]) -> None:
        self._tickers = {t.strip().upper() for t in tickers}
        try:
            self._client = RESTClient(api_key=self._config.api_key)
        except AuthError:
            self._health.failure(RuntimeError("invalid MASSIVE_API_KEY"))
            raise

        if self._mode == "snapshot":
            try:
                await self._refresh_snapshot()
            except BadResponse as exc:
                if not is_not_entitled(exc):
                    # A transient 500 at startup must not prevent the app from booting: record it
                    # and let the poll loop retry.
                    logger.warning("Initial snapshot poll failed: %s", exc)
                    self._health.failure(exc)
                else:
                    logger.warning("Snapshot endpoint not entitled; falling back to EOD mode")
                    self._enter_eod_mode()

        if self._mode == "eod":
            await self._refresh_eod()
            self._task = asyncio.create_task(self._eod_loop(), name="massive-eod")
        else:
            self._task = asyncio.create_task(self._poll_loop(), name="massive-poll")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def add_ticker(self, ticker: str) -> None:
        ticker = ticker.strip().upper()
        if ticker in self._tickers:
            return
        self._tickers.add(ticker)
        if self._mode == "eod":
            try:
                await self._refresh_eod(force=True)  # otherwise the row stays blank until tomorrow
            except Exception as exc:                 # noqa: BLE001 - never fail a watchlist add
                logger.exception("EOD refresh after add_ticker(%s) failed", ticker)
                self._health.failure(exc)

    async def remove_ticker(self, ticker: str) -> None:
        self._tickers.discard(ticker.strip().upper())
        self._cache.remove(ticker)

    # -- snapshot mode ----------------------------------------------------
    async def _poll_loop(self) -> None:
        while True:
            delay = self._config.poll_interval
            try:
                if await self._is_market_closed():
                    self._health.note("market closed")
                else:
                    await self._refresh_snapshot()
                    delay = self._config.poll_interval
            except BadResponse as exc:
                if is_not_entitled(exc):
                    logger.warning("Lost snapshot entitlement; switching to EOD mode")
                    self._enter_eod_mode()
                    try:
                        await self._refresh_eod()
                    except Exception:                 # noqa: BLE001
                        logger.exception("EOD bootstrap after downgrade failed")
                    # This task is about to end, so hand the loop over explicitly.
                    self._task = asyncio.create_task(self._eod_loop(), name="massive-eod")
                    return
                self._health.failure(exc)
                delay = self._backoff_delay()
            except Exception as exc:                 # noqa: BLE001
                logger.exception("snapshot poll failed")
                self._health.failure(exc)
                delay = self._backoff_delay()
            await asyncio.sleep(self._jitter(delay))

    async def _refresh_snapshot(self) -> None:
        batch = await asyncio.to_thread(self._fetch_snapshot_batch)
        for ticker, (price, ts) in batch.items():
            self._cache.update(ticker, price, source="snapshot", timestamp=ts)
        self._health.success(f"{len(batch)}/{len(self._tickers)} tickers")

    async def _is_market_closed(self) -> bool:
        now = time.monotonic()
        if now - self._status_checked_at < 60:
            return not self._market_open
        status = await asyncio.to_thread(self._client.get_market_status)
        self._market_open = status.market in {"open", "extended-hours"}
        self._status_checked_at = now
        return not self._market_open

    # -- EOD mode ---------------------------------------------------------
    async def _eod_loop(self) -> None:
        while True:
            await asyncio.sleep(self._config.eod_refresh_seconds)
            try:
                await self._refresh_eod()
            except Exception as exc:                 # noqa: BLE001
                logger.exception("EOD refresh failed")
                self._health.failure(exc)

    async def _refresh_eod(self, *, force: bool = False) -> None:
        if not self._tickers:
            return
        day, prices = await asyncio.to_thread(self._fetch_eod)
        if not force and self._eod_day == day and all(
            self._cache.get(t) is not None for t in self._tickers
        ):
            self._health.success(f"{day.isoformat()} close")
            return
        for ticker, price in prices.items():
            self._cache.update(ticker, price, source="eod")
        self._eod_day = day
        self._health.success(f"{day.isoformat()} close")

    def _enter_eod_mode(self) -> None:
        self._mode = "eod"
        self._health.set_mode("eod")

    # -- helpers ----------------------------------------------------------
    def _backoff_delay(self) -> float:
        failures = max(1, self._health.consecutive_failures)
        return min(300.0, 15.0 * (2 ** (failures - 1)))

    @staticmethod
    def _jitter(seconds: float) -> float:
        return seconds * random.uniform(0.9, 1.1)
```

One implementation detail that is easy to get wrong: **do not read `snap.last_trade.price`
unconditionally.** It is `None` on Starter and Developer (no trades entitlement) and outside hours. The
precedence chain in `extract_price` is what makes one code path work on every plan.

---

## 8. `factory.py` — selection

```python
from __future__ import annotations

import logging

from app.market.cache import PriceCache
from app.market.config import MarketDataConfig
from app.market.interface import MarketDataSource
from app.market.massive_client import MassiveDataSource
from app.market.simulator import SimulatorDataSource

logger = logging.getLogger(__name__)


def create_market_data_source(
    cache: PriceCache, config: MarketDataConfig
) -> MarketDataSource:
    if config.source == "simulator":
        return SimulatorDataSource(cache, config)

    if not config.api_key:
        if config.source == "massive":
            raise RuntimeError("MARKET_DATA_SOURCE=massive requires MASSIVE_API_KEY")
        return SimulatorDataSource(cache, config)

    if not config.plan.supports_snapshots:
        logger.info("MASSIVE_PLAN=%s: using end-of-day mode", config.plan.value)
    return MassiveDataSource(cache, config)
```

| `MARKET_DATA_SOURCE` | Key | Plan | Result |
|---|---|---|---|
| `auto` | empty | — | simulator |
| `auto` | set | basic | Massive, EOD |
| `auto` | set | starter+ | Massive, snapshot |
| `simulator` | any | any | simulator |
| `massive` | empty | — | startup error |

---

## 9. `stream.py` — SSE

```python
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.market.cache import PriceCache

logger = logging.getLogger(__name__)

KEEPALIVE_SECONDS = 15.0


def create_stream_router(cache: PriceCache, *, interval: float = 0.5) -> APIRouter:
    router = APIRouter(prefix="/api/stream", tags=["market"])

    @router.get("/prices")
    async def stream_prices(request: Request) -> StreamingResponse:
        async def event_stream():
            yield "retry: 1000\n\n"
            last_version = -1
            idle = 0.0
            while True:
                if await request.is_disconnected():
                    break
                version = cache.version
                if version != last_version:
                    last_version = version
                    payload = {t: u.to_dict() for t, u in cache.snapshot().items()}
                    if payload:
                        yield f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"
                    idle = 0.0
                else:
                    idle += interval
                    if idle >= KEEPALIVE_SECONDS:      # proxies kill silent streams
                        yield ": keep-alive\n\n"
                        idle = 0.0
                await asyncio.sleep(interval)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return router
```

Contract: one frame carries **all** tickers as a map, so the frontend replaces its price dictionary
wholesale — idempotent and order-independent. Emitting only on `version` change means an EOD source
sends one frame per session instead of hammering clients with identical payloads. Call
`create_stream_router()` **once** at startup; it registers on a fresh router each call, but wiring it
twice would duplicate the route.

> The `: keep-alive` comment line matters in EOD mode: EventSource handles comments as no-ops, and a
> totally silent stream gets dropped by reverse proxies (and by some browsers after ~5 minutes).

---

## 10. App wiring

```python
# backend/app/market/__init__.py
from app.market.cache import PriceCache
from app.market.config import ConfigurationError, MarketDataConfig, Plan
from app.market.factory import create_market_data_source
from app.market.interface import MarketDataSource, SourceHealth
from app.market.models import PriceUpdate
from app.market.stream import create_stream_router

__all__ = [
    "ConfigurationError", "MarketDataConfig", "MarketDataSource", "Plan",
    "PriceCache", "PriceUpdate", "SourceHealth",
    "create_market_data_source", "create_stream_router",
]
```

```python
# backend/app/main.py (lifespan excerpt)
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, Request


@dataclass
class MarketContext:
    cache: PriceCache
    source: MarketDataSource


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = MarketDataConfig.from_env()
    cache = PriceCache()
    source = create_market_data_source(cache, config)

    watchlist = load_watchlist()                 # from SQLite; seeds on first run
    await source.start(watchlist)                # must precede the first request

    app.state.market = MarketContext(cache=cache, source=source)
    app.include_router(create_stream_router(cache))
    try:
        yield
    finally:
        await source.stop()                      # idempotent; no writes afterwards


def market(request: Request) -> MarketContext:
    return request.app.state.market


@market_router.get("/api/market/status")
async def market_status(request: Request) -> dict[str, object]:
    ctx = market(request)
    return {"source": ctx.source.name, **ctx.source.health().to_dict()}
```

Routes consume prices through the cache only:

```python
# valuation, trading and the LLM context all do this
price = market(request).cache.get_price(ticker)
if price is None:
    raise HTTPException(status_code=409, detail=f"No price available for {ticker}")
```

The watchlist API keeps the source in sync:

```python
@router.post("/api/watchlist")
async def add_ticker(body: WatchlistAdd, request: Request) -> dict[str, str]:
    ticker = body.ticker.strip().upper()
    insert_watchlist_row(ticker)                      # SQLite first
    await market(request).source.add_ticker(ticker)   # then the price source
    return {"ticker": ticker}


@router.delete("/api/watchlist/{ticker}")
async def delete_ticker(ticker: str, request: Request) -> dict[str, str]:
    delete_watchlist_row(ticker)
    await market(request).source.remove_ticker(ticker)
    return {"ticker": ticker}
```

Order matters on add: persist first, then subscribe. If the source call fails you keep the row and the
next startup picks it up; the reverse order loses the ticker.

`GET /api/market/status` response:

```json
{
  "source": "massive",
  "mode": "eod",
  "connected": true,
  "last_success_at": 1794998400.0,
  "age_seconds": 42.1,
  "consecutive_failures": 0,
  "last_error": null,
  "detail": "2026-11-17 close"
}
```

The header renders: `mode == "simulator"` → green "SIM"; `mode` `snapshot`/`eod` with `age_seconds`
under 2× the poll interval → green/yellow with a "EOD" or "DELAYED" badge; `connected == false` → red.

---

## 11. Failure behaviour

| Signal | Detection | Behaviour | UI |
|---|---|---|---|
| Missing key | `config.api_key == ""` | simulator | SIM badge |
| Bad key | `AuthError` at `RESTClient()` | startup fails (explicit) or simulator (`auto`) | red |
| Snapshot not entitled | `BadResponse` + `is_not_entitled` | switch to EOD **once**, never retry the 403 | EOD badge |
| `429` | `BadResponse`, body mentions rate | backoff `15 → 30 → 60 → 120 → 300 s`, ±10% jitter | yellow |
| `5xx` / timeout | any `BadResponse` / `OSError` | retry, keep last prices | yellow |
| Market closed | `get_market_status().market == "closed"` | skip the poll entirely | "closed" |
| Empty snapshot array | `len(batch) == 0` | hold prices, do not zero them | unchanged |
| Holiday date (EOD) | empty results | step back a day, up to 5 | unchanged |
| Tick raises in loop | `except Exception` | log, record health, continue | yellow |

Never return a 500 from a market-data failure. Consumers see a stale price and a status endpoint that
says why.

---

## 12. Testing

```python
# backend/tests/market/test_conformance.py
import asyncio

import pytest

from app.market.cache import PriceCache
from app.market.config import MarketDataConfig, Plan


def make_config(**overrides) -> MarketDataConfig:
    base = dict(
        api_key="", plan=Plan.BASIC, source="auto", poll_interval=15.0,
        event_probability=0.0, eod_refresh_seconds=1800, eod_lookback_days=5,
    )
    return MarketDataConfig(**{**base, **overrides})


@pytest.mark.parametrize("factory", [simulator_factory, fake_massive_factory])
async def test_conformance(factory):
    cache = PriceCache()
    source = factory(cache, make_config())
    await source.start(["AAPL", "MSFT"])
    assert cache.version > 0
    assert len(cache.snapshot()) == 2

    version = cache.version
    await source.stop()
    await asyncio.sleep(0.05)
    assert cache.version == version          # no writes after stop

    await source.add_ticker("NVDA")
    await source.add_ticker("NVDA")          # idempotent
    assert "NVDA" in source.get_tickers()

    await source.remove_ticker("NVDA")
    assert cache.get("NVDA") is None         # evicted, not just unsubscribed
```

Required cases beyond the conformance suite:

| Area | Test |
|---|---|
| Extraction | `extract_price` returns `min.close` when `last_trade is None`; `prev_day` last; `None` when all empty |
| Timestamps | `to_unix_seconds` on ns, ms, seconds, and `None`; ns value must not produce year 52,000 |
| EOD | holiday week: Sat → Fri → Thu (holiday, empty) → Wed, exactly 3 calls, then `RuntimeError` after 5 |
| EOD | add_ticker forces a refresh so the new row is populated immediately |
| 403 | fake client raising `BadResponse('{"status":"NOT_AUTHORIZED"}')` degrades to EOD and stops calling snapshots |
| Simulator | prices finite and `> 0` over 10k ticks; fixed seeds replay identically |
| Simulator | Pearson ρ within ±0.1 of target over 5k steps — catches a transposed Cholesky factor |
| Simulator | `step()` keys equal the tracked tickers, all rounded to 2 dp |
| SSE | first frame is `retry: 1000`; data only on version change; keep-alive after 15 s idle |

Fixtures: record real responses for the endpoints a key can reach (grouped daily, prev close, market
status). **Snapshot fixtures cannot be recorded on a free key** — synthesise both shapes,
`lastTrade`-present and `lastTrade`-absent.

---

## 13. Build order

1. `models.py` + `cache.py` + `config.py` — no dependencies, test first.
2. `interface.py` (ABC + `HealthTracker`) and the conformance test skeleton.
3. `seed_prices.py` + `GBMSimulator`; unit-test the math before wiring asyncio.
4. `SimulatorDataSource`; verify `start()` seeds the cache before the first tick.
5. `stream.py` + mount it; confirm frames appear in `curl -N http://localhost:8000/api/stream/prices`.
6. `factory.py`; then `main.py` lifespan with the simulator only — the app is fully usable here.
7. `massive_client.py` helpers (`to_unix_seconds`, `extract_price`, `is_not_entitled`) with unit tests;
   then EOD mode (works on any key, including free), then snapshot mode.
8. `/api/market/status` and the header dot.

Stop after step 6 and you have a complete product. Steps 7–8 add real data without changing a single
consumer, which is the point of the interface.

---

## 14. Acceptance criteria

- [ ] `MASSIVE_API_KEY` unset → app streams simulated prices at ~2 Hz; all 10 default tickers priced.
- [ ] `MASSIVE_API_KEY` set + `MASSIVE_PLAN=basic` → one grouped-daily call per session; no 403s in the
  log; status reports `mode: "eod"` and the data date.
- [ ] `MASSIVE_API_KEY` set + `MASSIVE_PLAN=starter` → snapshot polling every ≥ 15 s; one call per cycle.
- [ ] `MARKET_DATA_SOURCE=simulator` with a key present → simulator (used by E2E tests).
- [ ] Killing the network mid-run leaves prices frozen and the status endpoint reporting the failure —
  never a 500.
- [ ] `stop()` then a 100 ms wait → `cache.version` unchanged.
- [ ] Removing a ticker removes its row from the UI on the next SSE frame.
