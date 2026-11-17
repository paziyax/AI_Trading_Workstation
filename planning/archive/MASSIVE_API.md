# Massive API (formerly Polygon.io)

Market data for FinAlly. **A free Basic key is an end-of-day source.** Everything faster is a paid
endpoint. Base URL `https://api.massive.com`; Python package `massive` (not `polygon-api-client`).

Verified 18 Nov 2026 against the official docs, the client source (v2.10.0), and live probes: a Basic
key returns `403` on snapshots, a bad `timespan` returns `400` enumerating the valid values, and a
Sunday date returns `200` with an empty result set.

## Cheat sheet

| Fact | Value |
|---|---|
| Free tier | **5 calls/min**, end-of-day recency, 2-year history |
| Free tier cannot | snapshots (`403`), WebSocket, flat files |
| Free tier can | grouped daily (**1 call = whole market**), custom bars, prev close, market status |
| Auth | `MASSIVE_API_KEY` — one key for REST **and** WebSocket |
| Timestamps | snapshot `lastTrade.t` / `updated` = **nanoseconds**; bar `t` = **milliseconds** |
| Price precedence | `lastTrade.p` → `min.c` → `day.c` → `prevDay.c`, guarding `None` at each step |
| `403 NOT_AUTHORIZED` | plan problem, not network → degrade, never retry |
| Requirements | Python ≥ 3.10, `uv add massive` |

## Plan entitlements

From the live product payload on `massive.com/pricing` (`content.name` / `slug`: `stocks_basic`,
`stocks_starter`, `stocks_developer`, `stocks_advanced`):

| Capability | Basic (free) | Starter ($29) | Developer ($79) | Advanced ($199) |
|---|---|---|---|---|
| API calls | **5 / minute** | unlimited* | unlimited* | unlimited* |
| Data recency | **end of day** | 15-min delayed | 15-min delayed | real-time |
| History | 2 years | 5 years | 10 years | 20+ years |
| **Snapshots** | **not included** | included | included | included |
| Minute aggregates | included | included | included | included |
| Second aggregates | — | included | included | included |
| Trades (`T`) | — | — | included | included |
| Quotes / NBBO (`Q`) | — | — | — | included |
| WebSocket | **not available** | aggregates | + trades | + quotes |
| Flat files (S3) | not available | included | included | included |

\* The pricing page says "Unlimited API Calls"; practical ceilings still apply. Keep rates modest and
use **one WebSocket connection per asset class** — the server rejects a second for the same class.

**What this means for a free key**

1. **Snapshots do not work.** A "key present ⇒ poll snapshots" rule produces a 403 loop and an empty UI.
2. **"Real-time" is impossible.** The best available data is daily bars; the UI must say so.
3. **5 calls/min is the entire budget.** Per-ticker endpoints cost 1 call *each* → 10 tickers = 2
   minutes of budget. Batch with grouped daily instead.
4. Minute aggregates *are* included on Basic, so intraday chart history is available — one refresh
   per day.

## Endpoints and plan floor

| Goal | Endpoint | Calls for N | Floor |
|---|---|---|---|
| Live-ish watchlist quotes | `GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=A,B` | **1** | Starter |
| One ticker detail | `GET /v2/snapshot/locale/us/markets/stocks/tickers/{ticker}` | 1 | Starter |
| Whole-market EOD | `GET /v2/aggs/grouped/locale/us/market/stocks/{date}` | **1** | Basic |
| OHLC history | `GET /v2/aggs/ticker/{t}/range/{mult}/{timespan}/{from}/{to}` | 1 | Basic |
| Previous session OHLC | `GET /v2/aggs/ticker/{ticker}/prev` | 1 | Basic |
| Open/close + pre/after market | `GET /v1/open-close/{ticker}/{date}` | 1 | Basic |
| Is the market open? | `GET /v1/marketstatus/now` | 1 | Basic |
| True tick stream | WebSocket `T.*` | 1 conn | Developer+ |

### Snapshot fields (Starter+)

`lastTrade` is **`null` on Starter/Developer** (no trades entitlement) and outside hours. Code reading
`snap.last_trade.price` unconditionally fails on every plan below Advanced.

| Field | Notes |
|---|---|
| `day` | today's aggregate; resets at the open |
| `prevDay` | previous session — best source for "previous close" |
| `min` | latest minute bar; usually present once prints exist, still guard `None` |
| `lastTrade` | `p`, `s`, `x`, `t` (**ns**) — plan-dependent |
| `updated` | Unix **nanoseconds** |

```python
snaps = client.get_snapshot_all(
    market_type=SnapshotMarketType.STOCKS,      # or the string "stocks"
    tickers=["AAPL", "MSFT", "NVDA"],
)   # -> list[TickerSnapshot]
```

### Custom bars

* `timespan`: `minute` | `hour` | `day` | `week` | `month` | `quarter` | `year` (confirmed by a live
  `400` that enumerates exactly these).
* `from` / `to`: `YYYY-MM-DD` or Unix **ms**, **inclusive**, interpreted in Eastern Time.
* `adjusted` defaults `true` (split-adjusted) — keep it for display.
* `limit` max **50000**, default 5000; it caps *base* aggregates, not returned bars.
* Gaps mean "no trading", never an error.

```python
bars = list(client.list_aggs(
    ticker="AAPL", multiplier=1, timespan="day",
    from_="2026-01-01", to="2026-11-17",
    adjusted=True, sort="asc", limit=50000,
))   # Agg: open high low close volume vwap timestamp(ms) transactions otc
```

`list_aggs` is a generator that follows `next_url` (pagination is on by default).

### Grouped daily — the Basic workhorse

One bar for **every** U.S. ticker on one date, in one call.

```python
rows = client.get_grouped_daily_aggs(date="2026-11-17", adjusted=True, include_otc=False)
by_ticker = {r.ticker: r for r in rows}      # ticker comes from the "T" field
```

* **Non-trading date ⇒ HTTP `200` + empty result set** (verified, Sunday 2026-11-15). Validate
  emptiness, not the status code.
* `t` is in **ms**. Payload is 10k+ rows / a few MB — fetch once per session, cache it, never poll.

### Previous close and market status

```python
prev = client.get_previous_close_agg(ticker="AAPL")   # ONE object, not a list
```

`GET /v1/marketstatus/now` returns `market` ∈ `open` | `closed` | `extended-hours`, plus `earlyHours`
/ `afterHours`. Use it to skip polling when closed and to pick the last valid trading date.

## Gotchas

| Topic | Reality |
|---|---|
| Timestamp units | snapshots → **ns**, bars → **ms**. Mixing them shifts dates by decades. |
| `day.c` | today's close-so-far, *not* yesterday's — that's `prevDay.c` |
| Snapshot clearing | cleared **3:30 AM Eastern** (docs say EST), repopulating from ~4:00 AM ET. Empty arrays then are normal. |
| Empty bar window | no trades ⇒ no bar. Not an error. |
| Ticker case | symbols are case-sensitive; uppercase before sending. |
| `next_url` | followed automatically by the client; `pagination=False` caps at `limit`. |

## Recipes

### 1. Watchlist poll — Starter and above

```python
from massive import RESTClient
from massive.rest.models import SnapshotMarketType


def _to_seconds(ts: int | None) -> float | None:
    """Snapshots give ns, bars give ms; normalize everything to Unix seconds."""
    if ts is None:
        return None
    if ts > 10**17:
        return ts / 1e9          # nanoseconds
    if ts > 10**12:
        return ts / 1e3          # milliseconds
    return float(ts)


def poll_watchlist(client: RESTClient, tickers: list[str]) -> dict[str, tuple[float, float | None]]:
    """One call for the whole watchlist -> {ticker: (price, ts_seconds)}."""
    snaps = client.get_snapshot_all(
        market_type=SnapshotMarketType.STOCKS,
        tickers=[t.upper() for t in tickers],
    )
    out: dict[str, tuple[float, float | None]] = {}
    for snap in snaps:
        for bar, field in (
            (snap.last_trade, "price"), (snap.min, "close"),
            (snap.day, "close"), (snap.prev_day, "close"),
        ):
            value = getattr(bar, field, None) if bar is not None else None
            if value is not None:
                out[snap.ticker] = (float(value), _to_seconds(getattr(bar, "timestamp", None)))
                break
    return out
```

### 2. End-of-day prices — the free-tier path

```python
from datetime import date, timedelta

MAX_LOOKBACK_DAYS = 5          # long weekend + a holiday


def previous_trading_day(start: date) -> date:
    """Step back to the previous weekday. Holidays can't be known locally — probe the API."""
    d = start - timedelta(days=1)
    while d.weekday() >= 5:          # Sat=5, Sun=6
        d -= timedelta(days=1)
    return d


def eod_prices(
    client: RESTClient, tickers: list[str], today: date
) -> tuple[date, dict[str, float]]:
    """Return (trading_date, {ticker: close}) for the most recent session with data.

    A non-trading date is a SUCCESSFUL empty response, so emptiness — not an exception —
    is the signal to step back another day.
    """
    wanted = {t.upper() for t in tickers}
    day = previous_trading_day(today)

    for _ in range(MAX_LOOKBACK_DAYS):
        rows = client.get_grouped_daily_aggs(date=day.isoformat(), adjusted=True)
        prices = {r.ticker: r.close for r in rows if r.ticker in wanted and r.close is not None}
        if prices:
            return day, prices
        day = previous_trading_day(day)      # holiday, or not yet published

    raise RuntimeError(f"No grouped-daily data in the last {MAX_LOOKBACK_DAYS} sessions")
```

**Cost:** 1 call per refresh for the entire watchlist. That is the whole daily budget of the free tier.

**When today's data appears is not documented** (unverified). Trigger "after 16:00 ET plus a buffer"
and let the empty-result retry above be the real guard.

#### Prefilling charts with real intraday bars (Basic)

```python
def prefill_intraday(client: RESTClient, ticker: str, day: date) -> list[tuple[float, float]]:
    """One day of 1-minute closes: [(unix_seconds, close), ...]. One call per ticker."""
    bars = client.list_aggs(
        ticker=ticker, multiplier=1, timespan="minute",
        from_=day.isoformat(), to=day.isoformat(), limit=50000,
    )
    return [(b.timestamp / 1000.0, b.close) for b in bars if b.close is not None]
```

Ten default tickers = 10 calls ≈ 2 minutes of the 5/min budget. Run once at startup or once per day,
throttled — never inside a request handler. Bar timestamps are **ms**.

**Honesty rules for a Basic build:** label the UI "End of day"; drop the live dot and the green/red
flash animations; keep the AI and portfolio math fully working on stale prices, as long as the price
shown is the price used for the trade.

### 3. Async wrapper

`RESTClient` is synchronous and thread-safe; never call it on the event loop.

```python
async def fetch_snapshots(client: RESTClient, tickers: list[str]):
    return await asyncio.to_thread(
        lambda: client.get_snapshot_all(
            market_type=SnapshotMarketType.STOCKS, tickers=tickers
        )
    )
```

### 4. WebSocket — paid only

```python
from massive import WebSocketClient

# Same MASSIVE_API_KEY as REST — WebSocketClient() reads it from the environment.
ws = WebSocketClient(subscriptions=["AM.AAPL", "AM.MSFT"])
ws.run(handle_msg=handle_msg)
```

Channels: `A` (second bars), `AM` (minute bars), `T` (trades), `Q` (quotes), plus `LULD`, `FMV`, `NOI`.
The free Basic tier has **no** WebSocket entitlement. FinAlly should not adopt it in v1: SSE plus a
poller already solves the browser side, and WS would add reconnect/backpressure work for no gain.

## Errors and limits

| Signal | Meaning | Handling |
|---|---|---|
| `AuthError` at construction | no key | fall back to the simulator |
| `401` | invalid / revoked key | log once, red status, no hot retry |
| `403` / `NOT_AUTHORIZED` | endpoint not in plan | **degrade to EOD**, stop retrying |
| `429` | rate limited | exponential backoff with jitter |
| `5xx` / timeout | transient | retry, keep last prices |
| empty `tickers` array | closed, or post-3:30 AM clear | hold last prices, never zero them |
| `BadResponse` | non-2xx after retries | log the body, treat as transient |

**Free tier = 5 calls/minute**, a hard bucket. **Unverified:** whether a `429` carries `Retry-After`,
and whether the window is fixed or sliding — so back off **≥ 60 s** rather than trusting headers. The
client's own urllib3 `Retry` uses `backoff_factor=0.1` (derived sleeps ≈ 0.1/0.2/0.4 s, computed from
urllib3 semantics, not documented), which is far too short; wrap the poll loop in 15 → 30 → 60 → 120 s.

Also: pause when `marketstatus` says closed, cache EOD results by date, add ±10% jitter, and never let
one bad ticker abort a batch.

## Testing

* No network in unit tests — inject a fake client, and patch the symbol your module imports rather than
  `massive.RESTClient` itself.
* Cover the plan matrix: `Basic + snapshot → 403 → EOD`, `Starter → lastTrade is None`,
  `post-clear → empty array`. Assert timestamp normalization for ns, ms, s, and `None`.
* Record real responses into `backend/tests/fixtures/` where a key allows it. **Snapshots cannot be
  recorded on a free key** (403) — synthesise those fixtures with both `lastTrade`-present and
  `lastTrade`-absent shapes.

## Sources

All accessed 18 Nov 2026.

* Docs — <https://massive.com/docs/rest/quickstart>, `/rest/stocks/snapshots/*`,
  `/rest/stocks/aggregates/*`, `/rest/stocks/market-operations/market-status`,
  `/websocket/quickstart`, `/flat-files/quickstart`.
* Plans and entitlements — <https://massive.com/pricing>
* Python client (v2.10.0, MIT, Python ≥ 3.10) — <https://github.com/massive-com/client-python>,
  <https://pypi.org/project/massive/>
* Agent-friendly index — <https://massive.com/docs/llms.txt>
