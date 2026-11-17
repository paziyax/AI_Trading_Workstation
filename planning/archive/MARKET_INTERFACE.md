# Market Data Interface — Unified Python API

How FinAlly exposes one price API regardless of vendor: a single abstract interface with two
implementations (**Massive** when a key is configured, **GBM simulator** otherwise), a shared
thread-safe price cache, and a FastAPI SSE stream. Downstream code — portfolio valuation, trade
execution, the SSE endpoint, the frontend — is source-agnostic.

**Scope of this document:** the contract, the as-built implementation, the selection rules, and the
gaps to close. It describes the design being adopted; it does not change application code.

---

## 1. Design goals

| Goal | Consequence |
|---|---|
| One price type everywhere | `PriceUpdate` is the only object that leaves the market layer |
| Swap data sources without touching consumers | `MarketDataSource` ABC + factory |
| No I/O in request handlers | Producers push into `PriceCache`; consumers only read |
| Single-user now, multi-user later | Cache keyed by ticker, written by one producer task |
| Fail soft | A vendor outage degrades to stale prices, never a 500 |
| Testable without a network | Both implementations hide behind the ABC; the simulator is deterministic-capable |

---

## 2. Layer map

```
                  ┌────────────────────────────────────────────┐
 MASSIVE_API_KEY  │  factory.create_market_data_source(cache)  │
   set / unset ──▶│                                            │
                  └───────────────┬────────────────────────────┘
                                  │ returns an unstarted source
        ┌─────────────────────────┴──────────────────────────┐
        ▼                                                    ▼
 MassiveDataSource                                   SimulatorDataSource
 (REST poll → snapshots/EOD)                        (asyncio loop → GBMSimulator.step)
        │                                                    │
        └────────────────────┬───────────────────────────────┘
                             ▼
                      PriceCache  (thread-safe; version counter)
                             │
        ┌────────────────────┼─────────────────────┬──────────────────┐
        ▼                    ▼                     ▼                  ▼
  SSE /api/stream/prices  portfolio valuation   trade execution   chat context
```

---

## 3. Data model — `PriceUpdate`

`backend/app/market/models.py`

```python
@dataclass(frozen=True, slots=True)
class PriceUpdate:
    ticker: str
    price: float
    previous_price: float
    timestamp: float = field(default_factory=time.time)   # Unix SECONDS

    @property
    def change(self) -> float: ...            # price - previous_price, rounded to 4dp
    @property
    def change_percent(self) -> float: ...    # % vs previous_price, 0.0 if previous_price == 0
    @property
    def direction(self) -> str: ...           # "up" | "down" | "flat"

    def to_dict(self) -> dict: ...            # JSON/SSE payload
```

Rules that make it safe to share:

* **Immutable.** `frozen=True` → no consumer can mutate a cached value; no defensive copies needed.
* **Derived fields are computed, not stored.** `change`, `change_percent`, `direction` cannot drift
  out of sync with `price`/`previous_price`.
* **`timestamp` is Unix seconds (float)** at this boundary. Vendor timestamps (ns, ms) are normalized
  by the source implementation — see `MASSIVE_API.md` §6.
* **First update for a ticker** has `previous_price == price` ⇒ `direction == "flat"`. Consumers must
  not interpret a missing "previous" as an error.

Wire format (`to_dict()`), sent verbatim inside SSE events:

```json
{
  "ticker": "AAPL",
  "price": 190.52,
  "previous_price": 190.41,
  "timestamp": 1794972600.512,
  "change": 0.11,
  "change_percent": 0.0578,
  "direction": "up"
}
```

---

## 4. `MarketDataSource` — the contract

`backend/app/market/interface.py`

```python
class MarketDataSource(ABC):
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
```

### Contract rules (must hold for any new implementation)

1. **Push, don't pull.** The source writes to `PriceCache` on its own schedule. It never returns
   prices to callers and never blocks a request handler.
2. **`start()` is called exactly once**, after construction, with the initial watchlist. It must seed
   the cache before returning where possible (so the first SSE frame is populated) and must not raise
   because a vendor call failed — log and keep retrying.
3. **`stop()` is idempotent** and awaited. After it returns, no further cache writes may occur.
4. **`add_ticker()` / `remove_ticker()` are no-ops when the ticker is already/not present.**
   `remove_ticker()` must also evict from the cache, or the ticker will linger in the UI.
5. **Background tasks swallow-and-log.** A transient vendor error must not kill the loop; an exception
   escaping a task would be silently lost or crash the app on garbage collection.
6. **Tickers are normalized to uppercase** by `add_ticker` before use.
7. **`get_tickers()` returns a copy**, never the internal list.

---

## 5. `PriceCache` — single point of truth

`backend/app/market/cache.py`

```python
cache.update(ticker, price, timestamp=None) -> PriceUpdate
cache.get(ticker) -> PriceUpdate | None
cache.get_price(ticker) -> float | None
cache.get_all() -> dict[str, PriceUpdate]      # shallow copy
cache.remove(ticker) -> None
cache.version -> int                            # monotonic counter
len(cache) / ticker in cache
```

Implementation notes:

* Backed by a `dict[str, PriceUpdate]` guarded by a `threading.Lock`. Threads (not asyncio primitives)
  because the cache is written from `asyncio.to_thread` call sites in the Massive path.
* Prices are **rounded to 2 decimals** on write. `previous_price` is the previously **stored** value,
  which is already rounded, so re-rounding it is a no-op — deltas are exact at cent precision. Rounding
  at the boundary keeps flash animations from firing on float noise.
* `version` increments on **every** update. This is the SSE change-detection primitive: a client can
  sleep-poll `version` cheaply and only serialize `get_all()` when it actually changed.
* `remove()` does not reset `version` and does not rewrite other entries.

**Producer/consumer rule:** exactly one producer writes at a time (the factory guarantees this), but
there may be many readers. Do not add a second writer without revisiting the version/`previous_price`
semantics — two writers would interleave and produce meaningless `change` values.

---

## 6. Factory — source selection

`backend/app/market/factory.py` (as built):

```python
def create_market_data_source(price_cache: PriceCache) -> MarketDataSource:
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if api_key:
        return MassiveDataSource(api_key=api_key, price_cache=price_cache)
    return SimulatorDataSource(price_cache=price_cache)
```

Public import surface (`backend/app/market/__init__.py`):

```python
from app.market import (
    PriceCache, PriceUpdate, MarketDataSource,
    create_market_data_source, create_stream_router,
)
```

### 6.1 The requirement

> Use Massive automatically when `MASSIVE_API_KEY` is configured; otherwise fall back to the simulator.

That is satisfied literally today. Two refinements make it correct in practice:

**(a) Key presence ≠ endpoint access.** Per `MASSIVE_API.md` §3, the free (Basic) plan does **not**
include snapshots. A key-only check therefore routes free-tier users into a 403 loop. Recommended
selection:

```
MASSIVE_API_KEY empty                      → SimulatorDataSource
MASSIVE_API_KEY set + snapshot capability  → MassiveDataSource(mode="snapshot")   # Starter+
MASSIVE_API_KEY set + no snapshot access   → MassiveDataSource(mode="eod")        # Basic
```

Capability can come from an explicit `MASSIVE_PLAN` env var (`basic|starter|developer|advanced`),
or from a one-time probe at startup (first snapshot call → 403 ⇒ degrade). Prefer the env var: it is
deterministic, testable, and costs zero API calls.

**(b) An escape hatch.** Add `MARKET_DATA_SOURCE=auto|massive|simulator` (default `auto`). Demo
environments and E2E tests need the simulator *even when a key exists*; `auto` keeps today's UX.

### 6.2 Selection matrix

| `MARKET_DATA_SOURCE` | `MASSIVE_API_KEY` | Plan | Result |
|---|---|---|---|
| `auto` | empty | — | Simulator |
| `auto` | set | Starter+ | Massive, snapshot polling |
| `auto` | set | Basic | Massive, EOD mode |
| `simulator` | any | any | Simulator (explicit override) |
| `massive` | empty | — | **Startup error** — fail fast and loud |
| `massive` | set | Basic | Massive, EOD mode (+ warning log) |

---

## 7. Massive implementation — behavioral contract

`backend/app/market/massive_client.py` (as built) plus the changes it needs to satisfy the contract.

**As built**

* `start()` creates the `RESTClient`, performs an **immediate first poll** (cache warm instantly),
  then spawns `_poll_loop` under `asyncio.create_task(..., name="massive-poller")`.
* The synchronous client is called through `asyncio.to_thread(self._fetch_snapshots)` — the event loop
  never blocks.
* One `get_snapshot_all(tickers=...)` call per cycle covers the whole watchlist.
* Failures are caught **per cycle** (logged, loop continues) and **per ticker** (a snapshot missing
  `lastTrade` is skipped, not fatal).
* `remove_ticker()` also evicts from the cache.

**Required changes for correctness on real accounts**

| # | Issue | Why it matters |
|---|---|---|
| 1 | Reads `snap.last_trade.price` unconditionally | `last_trade` is `None` on Starter/Developer (no trades entitlement) and outside hours → every ticker skipped |
| 2 | Divides `last_trade.timestamp` by `1000.0` | Snapshot timestamps are **nanoseconds**; `/1e3` produces year ~52,000 |
| 3 | No 403 handling | Basic plan loops on a forbidden endpoint forever |
| 4 | Fixed 15 s interval, no backoff | 429s are retried by urllib3 three times (~0.7 s total), then the cycle is skipped and immediately retried 15 s later — never actually waiting out the bucket |
| 5 | No market-status awareness | Burns the free budget overnight and on weekends |
| 6 | No "stale" signalling | The UI cannot distinguish "market closed" from "vendor down" |

The corrected extraction/normalization helpers are in `MASSIVE_API.md` §7.1; the mode split is in §6.1.

**Massive EOD mode** (Basic): one grouped-daily call per session (`get_grouped_daily_aggs`) plus
`/v1/marketstatus/now`; write each watchlist ticker's close into the cache once, and mark the cycle
complete. Do not poll. Surface `mode: "eod"` and the data date so the frontend can label prices as
end-of-day instead of implying live streaming.

---

## 8. Simulator implementation — behavioral contract

See `MARKET_SIMULATOR.md` for the model. Interface-level guarantees:

* `start()` constructs `GBMSimulator(tickers=...)`, seeds the cache with initial prices (so SSE has
  data before the first tick), then starts `_run_loop` at 0.5 s.
* Each iteration: `prices = sim.step()` → `cache.update()` per ticker → `asyncio.sleep(interval)`.
  Exceptions are logged and the loop continues.
* `add_ticker()` seeds the new ticker's price into the cache immediately (no blank row in the UI).
* `remove_ticker()` removes from the simulation *and* the cache.

---

## 9. SSE streaming contract

`backend/app/market/stream.py`

```python
router = create_stream_router(price_cache)   # APIRouter, prefix="/api/stream"
# GET /api/stream/prices  →  text/event-stream
```

| Aspect | Contract |
|---|---|
| Content type | `text/event-stream` |
| Headers | `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no` |
| First frame | `retry: 1000\n\n` (browser auto-reconnect delay) |
| Data frame | `data: {"AAPL": {...PriceUpdate.to_dict()...}, "MSFT": {...}}\n\n` |
| Cadence | Loop every 500 ms; **emit only when `cache.version` changed** |
| Empty cache | Emit nothing (no `{}` frames) |
| Disconnect | Detected via `await request.is_disconnected()` → break, log |
| Cancellation | `asyncio.CancelledError` logged, not re-raised as an error |
| Fan-out | One generator per connected client; each reads the same cache |

Notes:

* The payload is a **map of all tickers**, not one event per ticker. The frontend replaces its price
  map wholesale — simple, idempotent, and order-independent.
* `create_stream_router()` registers routes on a **module-level** `APIRouter`. Call it **once** at app
  startup; calling it twice would register the route twice.
* Version-based emission means a slow source (Massive EOD) naturally produces few frames instead of
  hammering clients with identical payloads.

---

## 10. Lifecycle

```
App startup
  cache  = PriceCache()
  source = create_market_data_source(cache)      # no I/O yet
  await source.start(initial_watchlist)          # seeds cache, spawns task
  app.state.market = (cache, source)
  app.include_router(create_stream_router(cache))
  await source.add_ticker("TSLA")                # on watchlist add

Request path
  GET  /api/portfolio   → cache.get_price(t) for each position
  POST /api/portfolio/trade → validate against cache.get_price(t), then persist
  POST /api/chat        → serialize cache snapshot into the LLM context

Shutdown (FastAPI lifespan)
  await source.stop()                            # idempotent; no writes afterwards
```

Two unwritten-but-required details:

1. **Always `await source.stop()` in the lifespan shutdown.** Otherwise uvicorn cancels the task
   mid-write; harmless today, but it produces noisy shutdown logs and leaves the Massive client's
   connection pool dangling.
2. **Start the source before the first request**, not lazily on first poll, or the first paint shows
   an empty watchlist.

---

## 11. Degradation and health

| Situation | Cache behavior | UI signal |
|---|---|---|
| Normal | Updates every tick | green dot |
| Vendor 429 / 5xx (transient) | Holds last prices, keeps retrying | yellow dot |
| Vendor 401/403 | Holds last prices, stops retrying, logs once | red dot + "market data unavailable" |
| Market closed | Holds close prices | yellow dot + "closed" |
| EOD plan | One write per session | yellow dot + "EOD" |
| Simulator | Updates every 500 ms | green dot |

Health should be **data-driven, not state-machine-driven**: expose `last_success_at`,
`consecutive_failures`, `mode` (`simulator|snapshot|eod`), and let the header derive the dot from
age. This survives reconnect logic changes without UI work.

---

## 12. Testing contract

Every implementation must pass a shared conformance suite:

1. `start()` populates the cache for all requested tickers (given a fake vendor/first step).
2. `start()` → `stop()` → no further `version` increments.
3. `add_ticker()` is idempotent; `get_tickers()` reflects it and returns a copy.
4. `remove_ticker()` evicts from both source and cache.
5. A raised exception inside one poll/step cycle does **not** terminate the loop.
6. `PriceUpdate` invariants: first update `flat`; `change`/`change_percent`/`direction` consistent.
7. SSE: emits `retry: 1000` then data frames only on version change; stops on disconnect.

Plus source-specific tests: Massive timestamp normalization and `lastTrade`-absent payloads;
simulator determinism with a seeded RNG.

---

## 13. File layout

```
backend/app/market/
├── __init__.py        # public re-exports (5 symbols)
├── models.py          # PriceUpdate
├── interface.py       # MarketDataSource ABC
├── cache.py           # PriceCache (+ version counter)
├── seed_prices.py     # SEED_PRICES, TICKER_PARAMS, correlation constants
├── simulator.py       # GBMSimulator + SimulatorDataSource
├── massive_client.py  # MassiveDataSource
├── factory.py         # create_market_data_source()
└── stream.py          # create_stream_router() → GET /api/stream/prices
```

`backend/tests/market/` mirrors this 1:1 (`test_models`, `test_cache`, `test_simulator`,
`test_simulator_source`, `test_factory`, `test_massive`).

---

## 14. Backlog — documented vs implemented

| Item | Status |
|---|---|
| ABC, factory, cache with version counter, SSE change detection | implemented |
| Simulator seeding cache before first tick | implemented |
| Massive immediate first poll, `to_thread` offload, per-cycle/per-ticker error isolation | implemented |
| `lastTrade` fallback chain (`min.c` → `day.c` → `prevDay.c`) | **gap** |
| Snapshot timestamp ns → s normalization | **gap** (currently `/1000`) |
| Plan capability detection + EOD mode for Basic | **gap** |
| `MASSIVE_POLL_INTERVAL`, exponential backoff with jitter, market-status gate | **gap** |
| `MARKET_DATA_SOURCE` explicit override | **gap** |
| Structured source health for the header dot | **gap** |
| Shared conformance test suite across both sources | **partial** (per-module tests only) |

---

## 15. Sources

* This repository: `planning/PLAN.md` (§6 Market Data, §8 API Endpoints), `backend/AGENTS.md`,
  `planning/archive/MARKET_DATA_SUMMARY.md`.
* Massive REST/WebSocket documentation and plan entitlements — see `MASSIVE_API.md` §12.
* Python `abc`, `dataclasses(frozen=True, slots=True)`, `threading.Lock`, `asyncio.to_thread`,
  Server-Sent Events (`text/event-stream`), FastAPI `StreamingResponse` — standard-library and
  framework documentation, accessed 18 Nov 2026.
