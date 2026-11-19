# FinAlly Backend

FastAPI backend for the FinAlly trading workstation. This package currently implements the
**market data layer**; portfolio, trading, chat, and persistence come next.

## Market data

```
app/market/
  models.py         PriceUpdate — the only value type that leaves the layer
  interface.py      MarketDataSource ABC, SourceHealth, HealthTracker
  cache.py          lock-protected PriceCache (2 dp, version counter)
  simulator.py      GBM math + asyncio adapter
  massive_client.py Massive REST source (snapshot and EOD modes, runtime downgrade)
  config.py         env parsing and plan capability rules
  seed_prices.py    seed prices, volatility, correlations
  factory.py        key + plan -> source
  stream.py         SSE router (/api/stream/prices)
```

Selection: `MARKET_DATA_SOURCE=auto|massive|simulator`. With a key, plans that include snapshot
entitlement poll snapshots; Basic uses grouped-daily end-of-day data.

## Environment

| Variable | Default | Notes |
|---|---|---|
| `MASSIVE_API_KEY` | empty | empty uses the simulator |
| `MASSIVE_PLAN` | `basic` | `basic` has no snapshot entitlement |
| `MARKET_DATA_SOURCE` | `auto` | `massive` without a key is an error |
| `MASSIVE_POLL_INTERVAL` | `15` | floored at 15 s (basic) / 2 s (paid) |
| `MASSIVE_EOD_REFRESH` | `1800` | seconds between EOD refreshes |
| `MASSIVE_EOD_LOOKBACK` | `5` | sessions to walk back over holidays |
| `SIM_EVENT_PROBABILITY` | `0.001` | per-tick jump chance |

## Run

From this directory (`backend/`):

```powershell
uv run --module uvicorn app.main:app --port 8000
```

Add `$env:MARKET_DATA_SOURCE="simulator"` first for the free simulator; omit it to use
Massive with the key from `.env`.

## Tests

```bash
uv sync --extra dev
uv run --module pytest
uv run --module ruff check app tests
```

`pytest` covers both sources, cache rounding, config, SSE framing, health, and a conformance
suite shared by every source.

**Windows note.** If Smart App Control is enforced, freshly created unsigned command shims are
blocked (`An Application Control policy has blocked this file`, `os error 4551`). That affects
`uv run pytest`, `pytest`, `pip`, and `uvicorn`, not the interpreter. Start tools as modules
instead (`uv run --module <tool>` or `python -m <tool>`); same result, same tests.
