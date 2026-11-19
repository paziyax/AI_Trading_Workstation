# Database Contract — FinAlly

Owned by the database engineer. The API layer and the LLM action executor call this surface
and must not contain raw SQL.

## Location

- Runtime file: `FINALLY_DB_PATH`, default `<repo>/db/finally.db`.
- DDL: `backend/db/schema.sql`.
- Seed data: `backend/db/seed.sql`.
- Python package: `backend/app/db/` (`database.py`, `repositories.py`, `models.py`, `errors.py`).
- Tests: `backend/tests/db/`.

`Database.initialize()` is lazy and idempotent: it creates the parent directory, executes the
schema with `CREATE TABLE IF NOT EXISTS`, then seeds the profile and the ten default tickers
**only when they are missing**. It must be safe to call on every process start.

## Tables

All tables have `user_id TEXT NOT NULL DEFAULT 'default'`.

```sql
users_profile(id TEXT PRIMARY KEY, cash_balance REAL NOT NULL DEFAULT 10000.0,
              created_at TEXT NOT NULL)
watchlist(id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT 'default', ticker TEXT NOT NULL,
          added_at TEXT NOT NULL, UNIQUE(user_id, ticker))
positions(id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT 'default', ticker TEXT NOT NULL,
          quantity REAL NOT NULL, avg_cost REAL NOT NULL, updated_at TEXT NOT NULL,
          UNIQUE(user_id, ticker))
trades(id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT 'default', ticker TEXT NOT NULL,
       side TEXT NOT NULL CHECK(side IN ('buy','sell')), quantity REAL NOT NULL,
       price REAL NOT NULL, executed_at TEXT NOT NULL)
portfolio_snapshots(id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT 'default',
                    total_value REAL NOT NULL, recorded_at TEXT NOT NULL)
chat_messages(id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT 'default',
              role TEXT NOT NULL CHECK(role IN ('user','assistant')), content TEXT NOT NULL,
              actions TEXT, created_at TEXT NOT NULL)
```

Indexes: `trades(user_id, executed_at)`, `portfolio_snapshots(user_id, recorded_at)`,
`chat_messages(user_id, created_at)`, `watchlist(user_id)`.

Timestamps are ISO-8601 UTC ending in `Z`. IDs are `uuid4()` strings.

Seed: profile `default` with `cash_balance = 10000.0`; watchlist `AAPL, GOOGL, MSFT, AMZN,
TSLA, NVDA, META, JPM, V, NFLX` in that order.

Connection rules: `sqlite3`, `row_factory = sqlite3.Row`, `PRAGMA journal_mode=WAL`,
`PRAGMA foreign_keys=ON`, `check_same_thread=False`. Every write is its own transaction
(`with conn:` / `BEGIN IMMEDIATE` for read-modify-write). The database layer is deliberately
**synchronous** — SQLite calls are sub-millisecond and this is a single-user app; do not add
an async wrapper.

## Python surface (exact names)

`app/db/errors.py`

```python
class DatabaseError(RuntimeError): ...
class TradeError(DatabaseError):
    def __init__(self, message: str) -> None: ...
```

`app/db/models.py` — frozen dataclasses with `to_dict()` where noted:
`Profile(id, cash_balance, created_at)`, `Position(ticker, quantity, avg_cost, updated_at)`,
`Trade(id, ticker, side, quantity, price, executed_at)` (+ `to_dict()`),
`Snapshot(total_value, recorded_at)`, `ChatMessage(id, role, content, actions, created_at)`.

`app/db/database.py`

```python
class Database:
    def __init__(self, path: str | Path) -> None
    @property
    def path(self) -> Path
    def initialize(self) -> None
    def connect(self) -> sqlite3.Connection   # caller closes; row_factory set
    # repositories are constructed from the same Database instance:
    @property
    def portfolio(self) -> PortfolioRepository
    @property
    def watchlist(self) -> WatchlistRepository
```

`app/db/repositories.py`

```python
class PortfolioRepository:
    def get_profile(self) -> Profile
    def set_cash_balance(self, cash: float) -> None            # test/maintenance helper
    def get_positions(self) -> list[Position]
    def get_position(self, ticker: str) -> Position | None
    def execute_trade(self, ticker: str, side: str, quantity: float, price: float,
                      *, now: str | None = None) -> Trade
    def list_trades(self, limit: int = 100) -> list[Trade]
    def add_snapshot(self, total_value: float, *, now: str | None = None) -> Snapshot
    def list_snapshots(self, limit: int = 500) -> list[Snapshot]
    def record_chat(self, role: str, content: str, actions: dict | None = None,
                    *, now: str | None = None) -> ChatMessage
    def recent_chat(self, limit: int = 20) -> list[ChatMessage]

class WatchlistRepository:
    def list_tickers(self) -> list[str]                       # insertion order
    def add(self, ticker: str) -> bool                        # False if already present
    def remove(self, ticker: str) -> bool                     # False if absent
```

## `execute_trade` rules (single transaction, atomic)

- `ticker` uppercased; `side` must be `buy` or `sell`; `quantity > 0`; `price > 0`.
- **buy**: `cost = round(quantity * price, 2)`. If `cash + 1e-9 < cost` raise
  `TradeError(f"Insufficient cash: need ${cost:,.2f}, available ${cash:,.2f}")`.
  Cash decreases by `cost`. If a position exists, new quantity `q_old + quantity` and
  `avg_cost = (q_old*avg_old + quantity*price) / (q_old + quantity)`; otherwise
  `avg_cost = price`. Upsert the position. Insert the trade row.
- **sell**: if no position raise `TradeError(f"No position in {ticker} to sell")`.
  If `quantity > position.quantity + 1e-9` raise
  `TradeError(f"Cannot sell {quantity:g} {ticker}: only {position.quantity:g} owned")`.
  Cash increases by `round(quantity * price, 2)`. Decrease position quantity by `quantity`;
  when the remainder is `< 1e-9` delete the row, otherwise update it (avg_cost unchanged).
  Insert the trade row.
- Persisted `quantity` keeps full float precision; the API rounds for display.
- Do **not** write a portfolio snapshot here — the caller knows current prices.

## Watchlist rules

- `add` normalizes to uppercase, validates `^[A-Z][A-Z0-9.\-]{0,9}$` (raise `ValueError`),
  inserts with a UUID and `added_at = now`, returns `False` on duplicate.
- `remove` returns `False` when the ticker was not present.

## Tests required

`backend/tests/db/` with a `tmp_path` database per test:
initialize idempotency, seed contents, buy/sell math (including weighted average),
fractional shares, sell-all deletes the position, insufficient cash, oversell, unknown sell,
trade log ordering, snapshot ordering/limit, chat persistence with JSON actions,
watchlist duplicate/add/remove/order, and a concurrency smoke test (two sequential
`execute_trade` calls keep cash consistent).
