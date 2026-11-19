# API Contract — FinAlly

Frozen interface between the frontend, the backend API layer and the integration tests.
Anything not listed here is implementation detail and may change freely.

- All routes are served from the same origin (FastAPI on port **8000**).
- All responses are JSON unless noted.
- Errors use FastAPI's shape: `{"detail": "<human readable message>"}`
  with status **400** (domain rule), **404** (missing resource) or **422** (malformed body).
- Money values are floats rounded to 2 decimals. Percentages are floats in percent units
  (`0.53` means 0.53%), not fractions.
- Timestamps are ISO-8601 UTC strings ending in `Z`, e.g. `2026-11-19T15:38:22Z`.
- Tickers are uppercased at every boundary. Valid ticker pattern: `^[A-Z][A-Z0-9.\-]{0,9}$`.
- Single hardcoded user: `user_id = "default"`.

## 1. Health

`GET /api/health` → `200`

```json
{
  "status": "ok",
  "database": "ok",
  "market": { "mode": "simulator", "connected": true, "detail": "simulator",
              "last_success_at": 1795102697.4, "consecutive_failures": 0,
              "last_error": null, "age_seconds": 0.5 },
  "llm": { "mode": "mock", "model": "openrouter/openai/gpt-oss-120b" }
}
```

`market` is exactly `SourceHealth.to_dict()` from `app.market.interface`.
`llm.mode` is `"mock"` or `"live"`.

## 2. Portfolio

`GET /api/portfolio` → `200`

```json
{
  "cash_balance": 8100.0,
  "positions_value": 1910.0,
  "total_value": 10010.0,
  "total_pnl": 10.0,
  "total_pnl_pct": 0.1,
  "unrealized_pnl": 10.0,
  "positions": [
    {
      "ticker": "AAPL",
      "quantity": 10.0,
      "avg_cost": 190.0,
      "current_price": 191.0,
      "market_value": 1910.0,
      "unrealized_pnl": 10.0,
      "unrealized_pnl_pct": 0.5263,
      "weight": 19.08
    }
  ]
}
```

- `total_value = cash_balance + positions_value`.
- `total_pnl = total_value - 10000.0` (the seeded starting cash).
- `unrealized_pnl` is the sum of position P&L.
- `weight` is percent of `total_value` (`market_value / total_value * 100`).
- A position whose price is missing from the cache uses `avg_cost` as `current_price`.
- Positions are ordered by `market_value` descending.

`POST /api/portfolio/trade`

Request:

```json
{ "ticker": "AAPL", "quantity": 10, "side": "buy" }
```

- `quantity`: number, `> 0`, `<= 1_000_000`.
- `side`: `"buy"` | `"sell"`.
- Execution price is the current cache price. No fees, no slippage, instant fill.

`200` response:

```json
{
  "message": "Bought 10 AAPL at $190.00",
  "trade": {
    "id": "uuid",
    "ticker": "AAPL",
    "side": "buy",
    "quantity": 10.0,
    "price": 190.0,
    "executed_at": "2026-11-19T15:38:22Z"
  },
  "portfolio": { "...": "same shape as GET /api/portfolio" }
}
```

Domain failures → `400` with `detail`:
- `No market price available for <TICKER>`
- `Insufficient cash: need $1900.00, available $100.00`
- `Cannot sell 10 AAPL: only 5 owned`
- `No position in <TICKER> to sell`

`GET /api/portfolio/history?limit=500` → `200`

```json
{ "points": [ { "total_value": 10000.0, "recorded_at": "2026-11-19T15:00:00Z" } ] }
```

- Oldest first. `limit` default `500`, max `2000`.
- A snapshot is inserted immediately after every trade and every 30 s by a background task.

## 3. Watchlist

`GET /api/watchlist` → `200`

```json
{
  "tickers": [
    {
      "ticker": "AAPL",
      "price": 191.0,
      "previous_price": 190.8,
      "change": 0.2,
      "change_pct": 0.1048,
      "open_price": 190.0,
      "timestamp": 1795102697.4
    }
  ]
}
```

- `open_price` is the first price this API process observed for the ticker (session open).
- `change = price - open_price`; `change_pct = change / open_price * 100`.
- Ordered by `added_at` ascending (insertion order).
- A ticker with no cached price yet returns `price: null`, `previous_price: null`,
  `change: null`, `change_pct: null`, `open_price: null`, `timestamp: null`.

`POST /api/watchlist`

```json
{ "ticker": "PYPL" }
```

- `201` → `{ "ticker": "PYPL", "added": true }`
- `409` if already present → `{ "detail": "PYPL is already in the watchlist" }`
- `422` if the ticker pattern is invalid.
- On success the market source's `add_ticker` is called so a price appears without a restart.

`DELETE /api/watchlist/{ticker}` → `200` `{ "ticker": "PYPL", "removed": true }`
- `404` if absent. On success the market source's `remove_ticker` is called.

## 4. Chat

`POST /api/chat`

```json
{ "message": "Buy 5 shares of AAPL" }
```

`200` response:

```json
{
  "message": "Bought 5 AAPL at $191.00. Technology is now 22% of your portfolio.",
  "actions": {
    "trades": [
      { "ticker": "AAPL", "side": "buy", "quantity": 5.0,
        "status": "executed", "price": 191.0, "error": null }
    ],
    "watchlist_changes": [
      { "ticker": "PYPL", "action": "add", "status": "executed", "error": null }
    ]
  },
  "portfolio": { "...": "same shape as GET /api/portfolio" }
}
```

- `status` is `"executed"` or `"failed"`; `error` is a string when failed.
- A failing action never fails the request — it is reported in `actions` and the assistant
  message explains it.
- `message` is 1..2000 chars, required, trimmed. Empty → `422`.
- Both the user message and the assistant reply are persisted in `chat_messages`, the latter
  with `actions` serialized as JSON.
- The portfolio context sent to the LLM is built fresh at request time.
- If the LLM call fails, return `503` `{ "detail": "AI assistant unavailable: <reason>" }`
  (the user message is still persisted).

### LLM structured output (internal, not exposed)

The LLM must return exactly:

```json
{
  "message": "conversational reply",
  "trades": [ { "ticker": "AAPL", "side": "buy", "quantity": 10 } ],
  "watchlist_changes": [ { "ticker": "PYPL", "action": "add" } ]
}
```

`trades` and `watchlist_changes` may be empty arrays. `action` is `"add"` or `"remove"`.

### Mock mode

When `LLM_MOCK=true` the backend must not call any network API. It returns deterministic,
rule-based responses so E2E tests are stable:

| Message contains            | Behaviour                                        |
| --------------------------- | ------------------------------------------------ |
| `buy <n> <ticker>`          | one buy trade of `n` shares                       |
| `sell <n> <ticker>`         | one sell trade of `n` shares                      |
| `add <ticker>`              | one watchlist add                                 |
| `remove <ticker>`           | one watchlist remove                              |
| anything else               | friendly summary of cash, positions and watchlist |

The reply text always starts with `[mock]`. The same validation/execution path as live mode
is used, so mock trades really execute.

## 5. SSE — `GET /api/stream/prices`

Already implemented in `app/market/stream.py`; not to be changed.

- `Content-Type: text/event-stream`, first frame `retry: 1000`.
- Every `data:` frame is a JSON object keyed by ticker:

```json
{ "AAPL": { "ticker": "AAPL", "price": 191.0, "previous_price": 190.8,
            "timestamp": 1795102697.4, "source": "simulator" } }
```

- One frame carries every ticker; clients replace their price map wholesale.
- Comment keepalive `: keep-alive` every 15 s.

## 6. Static files

FastAPI serves the exported frontend from `STATIC_DIR` (default `frontend/out`) at `/`,
with `html=True`, **after** all `/api/*` routes are registered. If the directory is missing,
`/` returns a small JSON hint instead of crashing (backend-only development).
