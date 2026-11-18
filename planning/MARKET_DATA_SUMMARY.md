# Market Data — Summary

The market data component of the backend is complete. Implementation spec:
[`archive/Market_Data_Design.md`](archive/Market_Data_Design.md).

## What exists

- `backend/app/market/` — `PriceUpdate` model, `MarketDataSource` contract + health tracking,
  thread-safe `PriceCache`, GBM simulator, Massive REST source, config/factory, SSE stream.
- `backend/tests/market/` — 150 tests, 100% statement coverage, `ruff` clean.

## Behaviour

- Sources **push** into one `PriceCache`; nothing pulls prices, so SSE, valuation, and chat all
  read the same numbers. Prices are rounded to 2 dp and timestamps normalized to Unix seconds.
- Selection uses key **and** plan: Basic keys authenticate but are not entitled to snapshots.
  Basic runs EOD mode; Starter+ polls multi-ticker snapshots.
- EOD mode reads one grouped-daily response, walks back over weekends/holidays, refreshes every
  30 min, and forces a refresh on `add_ticker` so new rows are never blank.
- Snapshot mode skips polling while the market is closed, backs off exponentially (15 s → 5 min,
  ±10% jitter) on errors, and downgrades to EOD at runtime if the account loses entitlement.
- Simulator: GBM per 500 ms of trading-year time, per-ticker sigma/mu, correlated tech/finance
  groups, and occasional 2–5% jump events.
- SSE (`/api/stream/prices`): `retry: 1000` prefix, one frame carrying every ticker, emitted only
  when the cache version changes, comment keepalive every 15 s.

## Verify

```bash
cd backend
uv sync --extra dev
uv run --module pytest
uv run --module ruff check app tests
```

Use the `--module` form, not `uv run pytest`. Where Windows Smart App Control is enforced, the
freshly created unsigned `pytest.exe` shim inside `.venv\Scripts` is blocked (os error 4551),
while the module form runs through the signed interpreter. Same tests, same result.

## Next

Mount `create_stream_router(cache)` in the FastAPI app, start the source on startup, and expose
`/api/health` with `source.health().to_dict()`.
