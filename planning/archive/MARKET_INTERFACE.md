# Market Data Interface

One price API for the whole app: a source (Massive or simulator) pushes into a shared `PriceCache`,
and everything downstream — SSE, portfolio valuation, trade execution, chat context — reads from it
without knowing where prices came from.

## Cheat sheet

| Fact | Value |
|---|---|
| Object that leaves the layer | `PriceUpdate` — frozen, timestamps in **Unix seconds** |
| Source contract | `start` / `stop` / `add_ticker` / `remove_ticker` / `get_tickers` |
| Selection | key + **plan capability** → `snapshot` \| `eod` \| `simulator` |
| Cache rounding | 2 dp; `previous_price` is the previously **stored** (already rounded) value |
| SSE frame | one frame carries **all** tickers; emitted only when `cache.version` changes |
| First update | `previous_price == price` ⇒ `direction == "flat"` |
| Failure rule | hold the last prices, never return a 500 |

## Layers

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

## Data model and contract

```python
@dataclass(frozen=True, slots=True)
class PriceUpdate:
    ticker: str
    price: float
    previous_price: float
    timestamp: float = field(default_factory=time.time)   # Unix SECONDS

    @property
    def change(self) -> float: ...            # price - previous_price, rounded 4dp
    @property
    def change_percent(self) -> float: ...    # 0.0 when previous_price == 0
    @property
    def direction(self) -> str: ...           # "up" | "down" | "flat"
    def to_dict(self) -> dict: ...            # the SSE payload


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

Frozen means no consumer can mutate a cached value; derived fields are computed so they cannot drift
from `price`. Wire format is `to_dict()` verbatim:
`{"ticker": "AAPL", "price": 190.52, "previous_price": 190.41, "timestamp": 1794972600.512,
"change": 0.11, "change_percent": 0.0578, "direction": "up"}`.

**Rules any implementation must satisfy**

1. **Push, don't pull.** The source writes to the cache on its own schedule; it never returns prices to
   callers and never blocks a request handler.
2. **`start()` runs once** with the initial watchlist, seeds the cache before returning where possible,
   and must **not raise** because a vendor call failed — log and keep retrying.
3. **`stop()` is idempotent** and awaited; no cache writes may happen after it returns.
4. **`add_ticker` / `remove_ticker` are no-ops when already/not present.** `remove_ticker` must also
   evict from the cache, or the ticker lingers in the UI. Tickers are uppercased on add.
5. **Background tasks swallow-and-log.** An escaping exception is silently lost or crashes on GC.
6. **`get_tickers()` returns a copy**, never the internal list.

## PriceCache

```python
cache.update(ticker, price, timestamp=None) -> PriceUpdate
cache.get(ticker) -> PriceUpdate | None
cache.get_price(ticker) -> float | None
cache.get_all() -> dict[str, PriceUpdate]      # shallow copy
cache.remove(ticker) -> None
cache.version -> int                            # monotonic counter
```

* A `dict[str, PriceUpdate]` behind a `threading.Lock` — threads, not asyncio, because the Massive path
  writes from `asyncio.to_thread`.
* Prices are rounded to **2 dp on write**. `previous_price` is the previously *stored* value, already
  rounded, so re-rounding is a no-op and deltas are exact at cent precision. Rounding at the boundary
  stops flash animations firing on float noise.
* `version` increments on every update — that is the SSE change-detection primitive.
* **Exactly one writer.** Two writers would interleave and produce meaningless `change` values.

## Source selection

Today `factory.py` chooses on **key presence only**:

```python
def create_market_data_source(price_cache: PriceCache) -> MarketDataSource:
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if api_key:
        return MassiveDataSource(api_key=api_key, price_cache=price_cache)
    return SimulatorDataSource(price_cache=price_cache)
```

That satisfies the stated requirement but routes free-tier users into a 403 loop, because a key does
not grant snapshot access. Correct behaviour:

```
MASSIVE_API_KEY empty                      → SimulatorDataSource
MASSIVE_API_KEY set + snapshot capability  → MassiveDataSource(mode="snapshot")   # Starter+
MASSIVE_API_KEY set + no snapshot access   → MassiveDataSource(mode="eod")        # Basic
```

Read the capability from an explicit `MASSIVE_PLAN` env var (`basic|starter|developer|advanced`) rather
than probing — deterministic, testable, zero API calls. Add `MARKET_DATA_SOURCE=auto|massive|simulator`
as an escape hatch so demos and E2E tests can force the simulator even when a key exists.

| `MARKET_DATA_SOURCE` | Key | Plan | Result |
|---|---|---|---|
| `auto` | empty | — | Simulator |
| `auto` | set | Starter+ | Massive, snapshot polling |
| `auto` | set | Basic | Massive, EOD mode |
| `simulator` | any | any | Simulator (override) |
| `massive` | empty | — | startup error — fail loud |
| `massive` | set | Basic | Massive, EOD mode (+ warning log) |

**EOD mode:** one `get_grouped_daily_aggs` per session plus a `marketstatus` gate; write each close once
and mark the cycle complete. Do not poll. Surface `mode: "eod"` and the data date so the frontend can
label prices honestly.

**Snapshot mode:** one `get_snapshot_all` per cycle for the whole watchlist, called through
`asyncio.to_thread`, errors caught per cycle and per ticker. The current implementation reads
`last_trade.price` unconditionally (null on Starter/Developer), divides nanoseconds by 1000, and has no
403 handling — see the backlog.

## SSE contract

```python
router = create_stream_router(price_cache)   # APIRouter, prefix="/api/stream"
# GET /api/stream/prices  →  text/event-stream
```

| Aspect | Contract |
|---|---|
| Headers | `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no` |
| First frame | `retry: 1000\n\n` |
| Data frame | `data: {"AAPL": {...}, "MSFT": {...}}\n\n` — a **map of all tickers** |
| Cadence | loop every 500 ms; emit only when `cache.version` changed; nothing when empty |
| Disconnect | `await request.is_disconnected()` → break and log |

Call `create_stream_router()` **once** at startup — it registers on a module-level `APIRouter`, so a
second call duplicates the route. Because the payload replaces the whole map, the frontend simply swaps
its price dictionary: idempotent and order-independent.

## Lifecycle

```
startup   cache = PriceCache(); source = create_market_data_source(cache)
          await source.start(initial_watchlist)          # must precede the first request
          app.include_router(create_stream_router(cache))
shutdown  await source.stop()                            # idempotent, no writes after
```

Starting lazily means the first paint shows an empty watchlist; skipping `stop()` leaves uvicorn
cancelling a task mid-write and the HTTP pool dangling.

## Failure behaviour

| Situation | Cache | UI |
|---|---|---|
| Normal | updates every tick | green dot |
| 429 / 5xx (transient) | holds, keeps retrying | yellow dot |
| 401 / 403 | holds, stops retrying, logs once | red dot + "market data unavailable" |
| Market closed | holds close prices | yellow + "closed" |
| EOD plan | one write per session | yellow + "EOD" |

Derive the dot from **data, not a state machine**: expose `last_success_at`, `consecutive_failures`,
and `mode` (`simulator|snapshot|eod`), and let the header compute staleness. That survives any future
reconnect-logic change without UI work.

## Backlog — documented vs implemented

| Item | Status |
|---|---|
| ABC, factory, cache with version counter, SSE change detection | implemented |
| Simulator seeding the cache before the first tick | implemented |
| Massive immediate first poll, `to_thread` offload, per-cycle/per-ticker isolation | implemented |
| `lastTrade` fallback chain (`min.c` → `day.c` → `prevDay.c`) | **gap** |
| Snapshot timestamp ns → s normalization | **gap** (currently `/1000`) |
| Plan capability detection + EOD mode for Basic | **gap** |
| `MASSIVE_POLL_INTERVAL`, backoff with jitter, market-status gate | **gap** |
| `MARKET_DATA_SOURCE` explicit override | **gap** |
| Structured source health for the header dot | **gap** |
| Shared conformance suite across both sources | **partial** (per-module tests only) |

## Testing

A shared conformance suite: `start()` populates the cache; `start → stop` produces no further `version`
increments; `add_ticker` is idempotent and `get_tickers()` returns a copy; `remove_ticker` evicts from
both source and cache; a raised cycle exception does not kill the loop; `PriceUpdate` invariants hold;
SSE sends `retry: 1000` then data only on version change. Plus source-specific tests: Massive timestamp
normalization and `lastTrade`-absent payloads, simulator determinism with a seeded RNG.

## Sources

* This repository: `planning/PLAN.md` §6 and §8, `backend/app/market/*`, `planning/archive/MARKET_DATA_SUMMARY.md`.
* Massive endpoints, entitlements and timestamp units — `MASSIVE_API.md`.
* Simulator model — `MARKET_SIMULATOR.md`.
* `abc`, `dataclasses(frozen=True, slots=True)`, `threading.Lock`, `asyncio.to_thread`, Server-Sent
  Events, FastAPI `StreamingResponse` — standard-library/framework docs, accessed 18 Nov 2026.
