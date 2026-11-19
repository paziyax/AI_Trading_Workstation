# FinAlly end-to-end tests

Browser tests for the whole app: real FastAPI backend, real SQLite, real
market simulator, real browser. Unit tests stay where they are
(`backend/tests/` for pytest, `frontend/src/**/*.test.tsx` for Vitest).

## Layout

```
test/
  playwright.config.ts   # starts uvicorn on :8123, waits for /api/health
  global-teardown.ts     # deletes the throwaway SQLite files
  e2e/                   # one spec per feature
  helpers/api.ts         # money parsing and API-based setup/cleanup
```

## Run

```powershell
cd test
npm ci
npx playwright install chromium   # first time only (browsers are cached already on this machine)
npm test
```

The config starts the backend itself:

- `LLM_MOCK=true` — deterministic `[mock]` replies, no network, no cost
- `MARKET_DATA_SOURCE=simulator` — no vendor key needed
- a fresh database per run, so the ten seeded tickers and $10,000 cash always apply
- `STATIC_DIR` points at `frontend/out`, so build it first: `cd frontend; npm run build`

Specs run with one worker because the app is single-user and shares one database.

## Specs

| File | Covers |
| --- | --- |
| `01-smoke.spec.ts` | layout, seeded data, streaming prices, flash, selection |
| `02-watchlist.spec.ts` | add, duplicate 409, remove, invalid ticker |
| `03-trade.spec.ts` | buy, sell, insufficient cash, bad quantity |
| `04-portfolio.spec.ts` | positions table, heatmap, P&L chart |
| `05-chat.spec.ts` | greeting, mock reply, executed trade chip, watchlist chip |
| `06-reconnect.spec.ts` | offline → reconnecting → connected |

## Notes

- Tests clean up after themselves at the API level (sell, remove ticker).
- `test/.tmp/`, `test-results/` and `playwright-report/` are gitignored.
- Artifacts on failure: screenshot + trace in `test-results/`.
