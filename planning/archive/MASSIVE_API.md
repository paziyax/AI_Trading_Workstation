# Massive API (formerly Polygon.io) — Integration Reference

Reference documentation for retrieving **real-time and end-of-day (EOD) market data for multiple
tickers** from [Massive](https://massive.com) using its REST API and the official `massive` Python
client, as used by FinAlly.

**Verified:** 18 Nov 2026 against the official docs (`massive.com/docs`), the official Python client
source (`massive-com/client-python`), and the live pricing/entitlement data. Python client version
checked: **2.10.0**.

> **Rebrand note.** Polygon.io became **Massive.com on 30 Oct 2025**. API keys and integrations keep
> working unchanged. The base URL is now `https://api.massive.com`; `https://api.polygon.io`
> remains supported "for an extended period". The Python package is `massive` (not `polygon-api-client`).

---

## 1. At a glance

| Item | Value |
|---|---|
| REST base URL | `https://api.massive.com` (legacy `https://api.polygon.io`) |
| WebSocket URLs | `wss://socket.massive.com/{market}` (real-time), `wss://delayed.massive.com/{market}` (15-min delayed) |
| Auth | `Authorization: Bearer <API_KEY>` header, or `?apiKey=<API_KEY>` query param |
| Python client | `massive` — MIT, requires **Python ≥ 3.10**, deps: `urllib3`, `websockets`, `certifi` |
| Install | `uv add massive` (or `pip install -U massive`) |
| FinAlly env var | `MASSIVE_API_KEY` — read automatically by `RESTClient()` |
| Default host in FinAlly | `api.massive.com` (via the client) |

The client reads `MASSIVE_API_KEY` from the environment if no key is passed, so
`RESTClient()` and `RESTClient(api_key=...)` are equivalent when the env var is set.

---

## 2. Authentication

```python
from massive import RESTClient

client = RESTClient()                    # uses MASSIVE_API_KEY
client = RESTClient(api_key="<KEY>")     # explicit
```

Raw HTTP:

```http
GET /v2/aggs/ticker/AAPL/prev HTTP/1.1
Host: api.massive.com
Authorization: Bearer <API_KEY>
```

**One key, both transports.** The same `MASSIVE_API_KEY` authenticates REST **and** WebSocket — there
is no separate streaming credential. `WebSocketClient()` defaults to the `MASSIVE_API_KEY` environment
variable (`massive/websocket/__init__.py`, `env_key = "MASSIVE_API_KEY"`), exactly like `RESTClient()`,
so neither client needs the key passed explicitly. What the key *unlocks* differs by plan: generating
a key is free, but **WebSocket access itself requires a paid plan** (see §3).

If the key is missing/empty, the client raises `AuthError` at construction. HTTP-level failures raise
`BadResponse` (body included) after retries are exhausted. Never log the key — the client masks it in
`trace=True` output, but your own logging must not echo `MASSIVE_API_KEY`.

---

## 3. Plan entitlements and rate limits

This table is the **single most important operational fact** for FinAlly. It is taken from the live
product data on `massive.com/pricing` (18 Nov 2026). The four product names below come from that same
payload (`content.name` / `slug`: `stocks_basic`, `stocks_starter`, `stocks_developer`,
`stocks_advanced`), not from inference:

| Capability | Basic (free) | Starter ($29/mo) | Developer ($79/mo) | Advanced ($199/mo) |
|---|---|---|---|---|
| API calls | **5 / minute** | Unlimited* | Unlimited* | Unlimited* |
| Data recency | **End of day** | 15-min delayed | 15-min delayed | Real-time |
| History | 2 years | 5 years | 10 years | 20+ years |
| **Snapshot endpoints** | **not included** | included | included | included |
| Minute aggregates (REST) | included | included | included | included |
| Second aggregates | — | included | included | included |
| Trades (`T`) | — | — | included | included |
| Quotes / NBBO (`Q`) | — | — | — | included |
| WebSocket | **not available** | aggregates (min + sec) | + trades | + quotes |
| Flat files (S3 bulk) | not available | included | included | included |

\* The pricing page says "Unlimited API Calls". Practical ceilings still apply: keep sustained request
rates modest (the historical guidance is ≲100 req/s) and use **one WebSocket connection per asset
class** (the server rejects a second concurrent connection for the same asset class).

### Implications for FinAlly

1. **A free key cannot poll snapshots.** `GET /v2/snapshot/locale/us/markets/stocks/tickers` returns
   *not included* on Basic. A "key present ⇒ use snapshots" rule produces 403s and an empty UI.
2. **On Basic, "real-time" is impossible.** The best available data is daily bars (EOD). The UI must
   not imply streaming when the source is EOD.
3. **5 calls/minute is the whole budget.** One multi-ticker snapshot call is 1 call. Per-ticker
   endpoints (custom bars, previous close) are 1 call *each* → 10 tickers = 2 minutes of budget.
4. **Snapshots only exist on Starter+**, and on Starter/Developer they are 15-minute delayed.

Recommended default handling is described in §12 (capability-aware source selection).

---

## 4. Choosing an endpoint

| Goal | Endpoint | Calls for N tickers | Plan floor |
|---|---|---|---|
| Live-ish prices for a watchlist | Full Market Snapshot with `tickers=` | **1** | Starter |
| One ticker detail view | Single Ticker Snapshot | 1 | Starter |
| End-of-day close for the whole market | Daily Market Summary (grouped) | **1** | Basic |
| EOD/OHLC history for one ticker | Custom Bars | 1 | Basic |
| Previous session's OHLC for one ticker | Previous Day Bar | 1 | Basic |
| Open/close + pre/after-market for one ticker/date | Daily Ticker Summary | 1 | Basic |
| Is the market open? | Market Status | 1 | Basic |
| True tick stream | WebSocket `T.*` | 1 connection | Developer+ |

**Rule of thumb:** batch with the grouped/snapshot endpoints; never loop per ticker on a free key.

---

## 5. Endpoint reference

Base URL omitted below; prefixes are all `/v2` unless stated.

### 5.1 Full Market Snapshot — the multi-ticker primitive

```
GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,MSFT,NVDA
```

* `tickers` — case-sensitive comma-separated list. **Empty/omitted returns the whole market**
  (10,000+ tickers); always pass the watchlist explicitly.
* `include_otc` — default `false`. Keep it `false`.
* One call covers **all** requested tickers — this is what makes a 5-call/minute budget workable.
* Snapshot data is **cleared daily at 3:30 AM Eastern (the docs say EST)** and repopulates from ~4:00
  AM ET as exchanges
  report. Between clear and first prints, `tickers` may be empty.

Response fields per ticker:

| Field | Meaning | Notes |
|---|---|---|
| `ticker` | Symbol | |
| `day` | Today's aggregate (`o h l c v vw`) | Resets at the open |
| `prevDay` | Previous session aggregate | Best source for "previous close" |
| `min` | Most recent **minute** bar (`t` in **ms**) | Typically present once the session has prints; still guard for `None` |
| `lastTrade` | Latest trade (`p`, `s`, `x`, `t` in **ns**) | **Only returned if your plan includes trades** |
| `lastQuote` | Latest NBBO (`P`/`p`/`S`/`s`/`t`) | **Only on plans with quotes** |
| `todaysChange` / `todaysChangePerc` | Change vs `prevDay.c` | |
| `updated` | Last update, Unix **nanoseconds** | |
| `fmv` | Fair market value | Business plans only |

**Critical:** on Starter/Developer, `lastTrade` is `null`. Code that reads
`snap.last_trade.price` unconditionally will fail on every non-Advanced plan.

```python
from massive import RESTClient
from massive.rest.models import SnapshotMarketType

client = RESTClient()  # MASSIVE_API_KEY

snaps = client.get_snapshot_all(
    market_type=SnapshotMarketType.STOCKS,      # or the string "stocks"
    tickers=["AAPL", "MSFT", "NVDA"],
)
# get_snapshot_all also accepts a comma-separated string

for s in snaps:
    ...
```

`get_snapshot_all()` returns a `list[TickerSnapshot]` (the API's `tickers` array).

### 5.2 Single Ticker Snapshot

```
GET /v2/snapshot/locale/us/markets/stocks/tickers/{ticker}
```

Same per-ticker object shape as 5.1, but 1 call per ticker and the client unwraps the `ticker` key:

```python
snap = client.get_snapshot_ticker(market_type="stocks", ticker="AAPL")
```

Use only for a focused detail view; for a watchlist, batch with 5.1.

### 5.3 Custom Bars (OHLC history)

```
GET /v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}
```

* `timespan`: `minute` | `hour` | `day` | `week` | `month` | `quarter` | `year`. Confirmed against a
  live `400` response from the API, which enumerates exactly these values.
* `from` / `to`: `YYYY-MM-DD` or Unix **milliseconds**; **inclusive** on both ends, interpreted in
  **Eastern Time**.
* `adjusted` (default `true`) — split-adjusted. Keep `true` for display; `false` for as-traded prices.
* `sort`: `asc` / `desc`.
* `limit`: **max 50000, default 5000** — this caps the number of *base* aggregates used, not the
  number of returned bars; paginate via `next_url`.
* Bars exist only where qualifying trades occurred — gaps mean "no trading", not an error.

```python
bars = list(client.list_aggs(
    ticker="AAPL", multiplier=1, timespan="day",
    from_="2026-01-01", to="2026-11-17",
    adjusted=True, sort="asc", limit=50000,
))
# Agg fields: open high low close volume vwap timestamp(ms) transactions otc
```

`list_aggs` is a generator that follows `next_url` automatically (pagination is on by default;
`RESTClient(pagination=False)` caps results at `limit`).

### 5.4 Daily Market Summary (grouped EOD — all tickers)

```
GET /v2/aggs/grouped/locale/us/market/stocks/{date}
```

Returns one daily bar for **every** U.S. ticker on that date — again **1 call**, available on Basic.
This is the primary EOD path for FinAlly on a free key.

```python
rows = client.get_grouped_daily_aggs(date="2026-11-17", adjusted=True, include_otc=False)
by_ticker = {r.ticker: r for r in rows}      # GroupedDailyAgg.ticker comes from the "T" field
```

* Use a **trading date**. A non-trading date succeeds with HTTP `200` and an **empty result set**
  (verified with a Sunday, 2026-11-15: the response carried no result rows). Validate emptiness, not
  the status code; choose the date via Market Status (§5.7) or by stepping back over weekends.
* `t` is the window timestamp in **ms**; `T` (uppercase) is the ticker.
* Payload is large (10k+ rows, a few MB). Fetch once per session/day and cache; do not poll.

### 5.5 Daily Ticker Summary (open/close + extended hours)

```
GET /v1/open-close/{ticker}/{date}
```

Returns `open`, `high`, `low`, `close`, `volume`, `preMarket`, `afterHours`, `status`. Useful for
"what did the session do" cards. One call per ticker.

```python
d = client.get_daily_open_close_agg(ticker="AAPL", date="2026-11-17")
```

### 5.6 Previous Day Bar

```
GET /v2/aggs/ticker/{ticker}/prev
```

Semantically identical to 5.3 with a 1-day window ending yesterday. One call per ticker.

```python
prev = client.get_previous_close_agg(ticker="AAPL")   # returns ONE PreviousCloseAgg, not a list
# prev.open, prev.high, prev.low, prev.close, prev.volume, prev.vwap, prev.timestamp (ms)
```

Useful as a one-shot fallback when snapshots are unavailable and you need a reference price.

### 5.7 Market Status

```
GET /v1/marketstatus/now
```

```json
{ "market": "extended-hours", "earlyHours": false, "afterHours": true,
  "exchanges": { "nyse": "extended-hours", "nasdaq": "extended-hours", "otc": "closed" },
  "serverTime": "2020-11-10T17:37:37-05:00" }
```

`market` ∈ `open`, `closed`, `extended-hours` (plus the `earlyHours`/`afterHours` booleans). Use it to:

* skip polling when the market is closed (free-tier budget protection),
* label the UI ("EOD data" vs "15-min delayed"),
* pick the last valid trading date for grouped EOD calls.

---

## 6. Field semantics and gotchas

| Topic | Reality |
|---|---|
| **Timestamps** | Aggregates (`t`), `min.t`, WS trade `t` → **milliseconds**. Snapshot `lastTrade.t`, `lastQuote.t`, `updated` → **nanoseconds**. Mixing them up shifts dates by decades. |
| **Price field** | Prefer `lastTrade.p` → `min.c` → `day.c` → `prevDay.c`, in that order. Which ones exist depends on plan and time of day. |
| **`lastTrade` may be null** | Yes, on Starter/Developer, and outside trading hours. Always guard. |
| **`day.c`** | Today's close-so-far; equals the last trade. Not "yesterday's close" — that's `prevDay.c`. |
| **Snapshot clearing** | Cleared 3:30 AM Eastern (docs: "3:30 AM EST"), repopulating from ~4:00 AM ET. Empty arrays shortly after 3:30 AM are normal. |
| **Empty bar windows** | No trades ⇒ no bar. Never treat a gap as an error. |
| **Ticker case** | Symbols are case-sensitive; uppercase before sending. |
| **`next_url`** | Present on paginated responses; the client follows it automatically. |
| **Arrow responses** | Some endpoints can return Apache Arrow (`Accept: application/vnd.apache.arrow.file`); pagination then uses the `Link: rel="next"` header. Not needed for FinAlly. |

---

## 7. Multi-ticker recipes

### 7.1 Live watchlist poll (Starter+) with safe field extraction

```python
from __future__ import annotations

import time
from massive import RESTClient
from massive.rest.models import SnapshotMarketType


def _to_seconds(ts: int | None) -> float | None:
    """Normalize Massive timestamps (ns or ms) to Unix seconds."""
    if ts is None:
        return None
    if ts > 10**17:      # nanoseconds
        return ts / 1e9
    if ts > 10**12:      # milliseconds
        return ts / 1e3
    return float(ts)     # seconds


def _extract_price(snap) -> tuple[float, float | None] | None:
    """Best available price for a snapshot, per plan/time-of-day."""
    for bar, field in ((snap.last_trade, "price"), (snap.min, "close"), (snap.day, "close")):
        if bar is not None:
            value = getattr(bar, field, None)
            if value is not None:
                return float(value), _to_seconds(getattr(bar, "timestamp", None))
    return None


def poll_watchlist(client: RESTClient, tickers: list[str]) -> dict[str, tuple[float, float | None]]:
    """One API call for the whole watchlist. Returns {ticker: (price, ts_seconds)}."""
    snaps = client.get_snapshot_all(
        market_type=SnapshotMarketType.STOCKS,
        tickers=[t.upper() for t in tickers],
    )
    out: dict[str, tuple[float, float | None]] = {}
    for snap in snaps:
        extracted = _extract_price(snap)
        if extracted is not None:
            out[snap.ticker] = extracted
    return out
```

### 7.2 End-of-day snapshot (Basic-compatible)

```python
from datetime import date, timedelta

from massive import RESTClient

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

    A non-trading date is a SUCCESSFUL empty response (verified), so emptiness — not an
    exception — is the signal to step back another day.
    """
    wanted = {t.upper() for t in tickers}
    day = previous_trading_day(today)

    for _ in range(MAX_LOOKBACK_DAYS):
        rows = client.get_grouped_daily_aggs(date=day.isoformat(), adjusted=True)
        prices = {
            r.ticker: r.close
            for r in rows
            if r.ticker in wanted and r.close is not None
        }
        if prices:
            return day, prices
        day = previous_trading_day(day)      # holiday, or not yet published

    raise RuntimeError(f"No grouped-daily data in the last {MAX_LOOKBACK_DAYS} sessions")
```

**When is today's data available?** Not documented, and not something to guess in code. The safe
trigger is "after 16:00 ET plus a buffer", with the empty-result retry above as the real guard. Treat
publication lag as unverified until you probe it on your own key.

**Budget:** 1 call per refresh — the entire watchlist in one response. That is the whole daily cost of
the Basic tier.

#### Prefilling charts with real intraday bars (Basic)

Basic includes **minute aggregates** (end-of-day recency, 2-year history), so you can populate a real
intraday shape once per day instead of shipping blank charts:

```python
def prefill_intraday(client: RESTClient, ticker: str, day: date) -> list[tuple[float, float]]:
    """Yesterday's 1-minute closes: [(unix_seconds, close), ...]. One call per ticker."""
    bars = client.list_aggs(
        ticker=ticker, multiplier=1, timespan="minute",
        from_=day.isoformat(), to=day.isoformat(), limit=50000,
    )
    return [(b.timestamp / 1000.0, b.close) for b in bars if b.close is not None]
```

* Cost: **1 call per ticker**. Ten default tickers = 10 calls = ~2 minutes of the 5/min budget.
  Do it once at startup (or once per day), throttled — never inside a request handler.
* Use it to seed sparkline/chart history, then hold the last value for the rest of the day.
* Minute bar timestamps are **ms**; divide by 1000 for the same seconds-based contract used by the
  frontend.

#### Honesty rules for a Basic build

* Label the UI **"End of day"**; do not render green/red flash animations that imply live ticks.
* Drop the "live" connection dot to a static "EOD" badge.
* Keep the AI assistant and portfolio math fully functional — they work fine on stale prices, as long
  as the trade price shown is the one that was used.

### 7.3 Async wrapper for FastAPI

`RESTClient` is synchronous. Never call it directly on the event loop.

```python
import asyncio


async def fetch_snapshots(client: RESTClient, tickers: list[str]):
    return await asyncio.to_thread(
        client.get_snapshot_all, SnapshotMarketType.STOCKS, tickers
    )
```

`RESTClient` is thread-safe and pools connections (`maxsize`, default 10). Set `maxsize` ≥ the number
of concurrent worker threads.

### 7.4 WebSocket (true streaming — optional, paid tiers)

```python
from massive import WebSocketClient

# Same MASSIVE_API_KEY as REST — WebSocketClient() reads it from the environment.
ws = WebSocketClient(subscriptions=["AM.AAPL", "AM.MSFT"])
ws.run(handle_msg=handle_msg)
```

Requires a paid plan (§3): the free Basic tier has no WebSocket entitlement at all.

Channels for stocks: `A` (second aggregate), `AM` (minute aggregate), `T` (trades), `Q` (quotes),
plus `LULD`, `FMV`, `NOI`. Delayed feed: `ws = WebSocketClient(feed=Feed.Delayed, ...)` →
`delayed.massive.com`. Auth is handled by the client (`{"action":"auth"}`); you can also manage it
manually with `wscat`. The server disconnects consumers that fall behind, and allows **one
connection per asset class** by default.

**FinAlly recommendation:** do **not** adopt WebSockets in v1. Server-side WS fan-out to N browsers
adds reconnect/backpressure complexity that the SSE + polling design already solves. Revisit only if
true tick latency becomes a requirement *and* the plan is Developer+.

---

## 8. Rate-limit budget and resilience

Free tier = **5 calls/minute** (a hard token bucket, not a soft suggestion).

**Unverified, so assume the worst:** whether a `429` carries a `Retry-After` header, and whether the
bucket is a fixed or sliding 60-second window. Back off **≥ 60 s** on a 429 rather than relying on
header hints.

| Strategy | Cost | Verdict |
|---|---|---|
| Snapshot every 15 s | 4 calls/min | ✅ fits Basic budget, still 403s on Basic (no snapshot) |
| Snapshot every 15 s on Starter+ | 4 calls/min | ✅ leaves 1 call/min for ad-hoc detail views |
| Per-ticker custom bars, 10 tickers | 10 calls | ❌ 2 min of budget for one refresh |
| Grouped EOD once per session | 1 call | ✅ the Basic-tier workhorse |

Resilience rules:

1. **Back off on 429.** The client's urllib3 `Retry` covers `413/429/503` with `backoff_factor=0.1`
   (`retries` defaults to 3; derived sleeps ≈ 0.1/0.2/0.4 s — this is computed from urllib3 semantics,
   not a documented figure). That is far too short for a 60-second bucket —
   add your own exponential backoff (e.g. 15 → 30 → 60 → 120 s, capped) around the poll loop.
2. **Never let the poller crash the app.** Catch per cycle, log, and retry next interval. Keep serving
   the last known prices from the cache.
3. **Per-ticker failures are normal.** A delisted or mistyped symbol yields no snapshot entry. Skip it,
   don't abort the batch.
4. **Pause when closed** (`/v1/marketstatus/now`) or when the last successful poll is older than N
   minutes on an EOD plan.
5. **Cache EOD results by date.** Re-fetching the same grouped day is pure waste.
6. **Add jitter** (±10%) to the interval so multiple containers don't align.

---

## 9. Error taxonomy

| Signal | Meaning | Handling |
|---|---|---|
| `AuthError` at construction | No key supplied | Fall back to simulator (FinAlly factory already does this) |
| `401` | Invalid/revoked key | Log once, surface "disconnected" in UI, do not retry hot |
| `403` / `NOT_AUTHORIZED` | Endpoint not in plan (e.g. snapshots on Basic) | **Degrade mode**, not retry: switch to EOD path |
| `429` | Rate limit exceeded | Exponential backoff with jitter |
| `5xx` / timeout | Server/network | Retry with backoff; keep last prices |
| Empty `tickers` array | Outside session, or post-3:30 AM clear | Hold last prices, don't zero them |
| `BadResponse` | Non-2xx after retries | Log body (truncated), treat as transient |

---

## 10. Testing strategy

* **No network in unit tests.** Inject a fake `RESTClient` (or patch the module-level symbol the code
  imports, not `massive.RESTClient` itself — patching the wrong target is the classic failure).
* Build fixtures from the sample payloads in §5 (snapshot with `lastTrade` present *and* absent).
* Cover the plan-degradation matrix: `Basic + snapshots → 403 → EOD`, `Starter → lastTrade null`,
  `marker cleared → empty array`.
* Assert timestamp normalization explicitly (`ns`, `ms`, seconds, `None`).
* Record one real response per endpoint into `backend/tests/fixtures/` when a key is available, then
  replay it offline forever. **Snapshot endpoints cannot be recorded on a free key** (403) — synthesise
  those fixtures from the sample payloads in §5, and cover both the `lastTrade`-present and
  `lastTrade`-absent shapes.

---

## 11. Implementation recommendations for FinAlly

Ordered by impact. Items marked **[gap]** are not implemented in `backend/app/market/massive_client.py`
today (which currently assumes a paid plan and `lastTrade`):

1. **[gap] Detect capability, don't guess from key presence.** Add `MASSIVE_PLAN` (or probe once at
   startup and cache the result) and choose `snapshot` vs `eod` mode. A free key must select the EOD
   path, not fail into 403s.
2. **[gap] Fix price extraction precedence:** `lastTrade.p` → `min.c` → `day.c` → `prevDay.c`
   (guarding `None` at each step). Today the code reads `snap.last_trade.price` unconditionally.
3. **[gap] Fix timestamp units.** Snapshot `lastTrade.t`/`updated` are **nanoseconds**; the current
   `timestamp / 1000.0` yields dates ~50,000 years in the future. Normalize by magnitude (see §7.1).
4. **Make the poll interval configurable:** `MASSIVE_POLL_INTERVAL` (seconds), default `15.0`;
   document that anything below 15 s violates the free tier.
5. **Batch by design.** One `get_snapshot_all` per cycle for the watchlist; never loop per ticker.
6. **Add EOD mode** for Basic: one grouped-daily call per session + `marketstatus` gate; mark prices
   as `stale`/`eod` in the payload so the UI can label them honestly.
7. **Exponential backoff with jitter** in the poll loop; distinguish 403 (stop, degrade) from 429
   (wait) from 5xx (retry).
8. **Expose source health** (last success timestamp, consecutive failures, mode) for the header
   connection dot: green = fresh, yellow = degraded/delayed, red = no data.
9. **Log the request budget** (calls this minute) at DEBUG; assert in tests that one refresh = 1 call.
10. **Keep `api.polygon.io` out of new code.** The client already defaults to `api.massive.com`; the
    legacy host is a compatibility path, not a target.

---

## 12. Sources

All accessed **18 Nov 2026**:

* REST quickstart (auth, base URL, response envelope) — <https://massive.com/docs/rest/quickstart>
* Full Market Snapshot — <https://massive.com/docs/rest/stocks/snapshots/full-market-snapshot>
* Single Ticker Snapshot — <https://massive.com/docs/rest/stocks/snapshots/single-ticker-snapshot>
* Custom Bars (OHLC) — <https://massive.com/docs/rest/stocks/aggregates/custom-bars>
* Daily Market Summary (grouped EOD) — <https://massive.com/docs/rest/stocks/aggregates/daily-market-summary>
* Daily Ticker Summary — <https://massive.com/docs/rest/stocks/aggregates/daily-ticker-summary>
* Previous Day Bar — <https://massive.com/docs/rest/stocks/aggregates/previous-day-bar>
* Market Status — <https://massive.com/docs/rest/stocks/market-operations/market-status>
* WebSocket quickstart (clusters, auth, channels, limits) — <https://massive.com/docs/websocket/quickstart>
* Stocks WebSocket channels — <https://massive.com/docs/websocket/stocks/overview>
* Flat Files (bulk EOD CSV via S3) — <https://massive.com/docs/flat-files/quickstart>
* Plans, rate limits, entitlements — <https://massive.com/pricing>
* Official Python client (README, `massive/rest/aggs.py`, `snapshot.py`, `base.py`, models) —
  <https://github.com/massive-com/client-python>
* Package metadata (v2.10.0, Python ≥3.10, MIT) — <https://pypi.org/project/massive/>
* Documentation index for agents (`llms.txt`, `.md` suffix on any docs URL) —
  <https://massive.com/docs/llms.txt>
