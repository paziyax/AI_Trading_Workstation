# Build & Ownership Contract — FinAlly

Frozen once, respected by every agent. `planning/PLAN.md` is the product spec;
`API_CONTRACT.md` and `DB_CONTRACT.md` are the two interface specs. This file defines
who owns what, where files go, how to run things, and what "done" means.

## Ownership map

| Area | Owner | Paths |
| --- | --- | --- |
| Database | DB engineer | `backend/db/`, `backend/app/db/`, `backend/tests/db/` |
| LLM | LLM engineer | `backend/app/llm/`, `backend/tests/llm/` |
| API + services | Backend API engineer | `backend/app/main.py`, `backend/app/config.py`, `backend/app/api/`, `backend/app/services/`, `backend/tests/api/`, `backend/tests/services/` |
| Frontend | Frontend engineer | `frontend/` |
| Containers & scripts | DevOps engineer | `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `scripts/`, `.env.example`, deployment section of `README.md` |
| E2E | Integration tester | `test/` |
| Market data | **Complete — do not modify** | `backend/app/market/`, `backend/tests/market/` |

Shared files (`backend/pyproject.toml`, `AGENTS.md`, `README.md` outside deployment,
`.gitignore`, `planning/`) are edited by the lead only. If a change is needed, report it
instead of editing.

## Layout to produce

```
backend/
  app/
    __init__.py
    main.py            # FastAPI app factory + lifespan
    config.py          # Settings.from_env(): db path, static dir, initial cash
    api/               # routers: health, portfolio, watchlist, chat, deps
    services/          # portfolio valuation, trade execution, snapshots, chat orchestration
    db/                # database.py, repositories.py, models.py, errors.py
    llm/               # config.py, client.py, schemas.py, prompts.py, mock.py
    market/            # existing, untouched
  db/                  # schema.sql, seed.sql
  tests/               # market/, db/, llm/, api/, services/
frontend/              # Next.js app (App Router, TypeScript, static export)
test/                  # Playwright E2E + docker-compose.test.yml
scripts/               # start/stop for mac/linux and windows
db/                    # runtime SQLite (gitignored contents)
Dockerfile
docker-compose.yml
.env.example
```

## Environment variables

| Name | Default | Used by |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | empty | LLM |
| `MASSIVE_API_KEY` | empty | market (existing) |
| `MARKET_DATA_SOURCE` | `auto` | market (existing) |
| `MASSIVE_PLAN` | `basic` | market (existing) |
| `LLM_MOCK` | `false` | LLM |
| `LLM_MODEL` | `openrouter/openai/gpt-oss-120b` | LLM |
| `LLM_PROVIDER` | `cerebras` | LLM (OpenRouter provider order) |
| `LLM_TIMEOUT_SECONDS` | `30` | LLM |
| `FINALLY_DB_PATH` | `<repo>/db/finally.db` | DB |
| `INITIAL_CASH` | `10000` | DB seed / API |
| `STATIC_DIR` | `<repo>/frontend/out` | API |
| `FINALLY_PORT` | `8000` | scripts (container listens on 8000) |
| `SNAPSHOT_INTERVAL_SECONDS` | `30` | API background task |

`.env` is read from the repo root by the backend (`python-dotenv`, `override=False`).
Never commit `.env`; `.env.example` is committed with empty values.

## Commands (Windows, from repo root)

```powershell
# backend: install + test + lint (run from backend/)
uv sync --extra dev
uv run --module pytest
uv run --module ruff check app tests

# frontend
npm --prefix frontend install
npm --prefix frontend run test -- --run
npm --prefix frontend run build          # produces frontend/out

# run the whole app natively (no Docker), from repo root
$env:LLM_MOCK="true"; $env:STATIC_DIR="frontend/out"
uv run --project backend uvicorn app.main:app --port 8000
```

Run pytest **from `backend/`** — invoking it from the repo root picks the wrong rootdir and
produces spurious failures. On this machine use `uv run --module pytest` (not the `.exe`
shims) — Smart App Control blocks freshly created unsigned shims.

## Runtime behaviour

- One FastAPI process, port `8000`, serves `/api/*` and the static export.
- Startup: load `.env` → `Database.initialize()` → build `PriceCache` → create and
  `start()` the market source with the current watchlist → start the 30 s snapshot task.
- Shutdown: stop the source, cancel the snapshot task. Both idempotent.
- The database file lives on a Docker volume at `/app/db`; the app must create it if absent.
- `LLM_MOCK=true` must make zero network calls.
- No CORS config: same origin only.

## Module contracts between owners

### DB → API

Exactly the surface in `DB_CONTRACT.md`. API never writes SQL. `TradeError` is the only
domain error the API maps to HTTP 400.

### LLM → API

```python
# app/llm/config.py
@dataclass(frozen=True)
class LLMConfig:
    mock: bool; api_key: str; model: str; provider: str; timeout: float
    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> LLMConfig

# app/llm/schemas.py  (pydantic v2)
class TradeAction(BaseModel): ticker: str; side: Literal["buy", "sell"]; quantity: float
class WatchlistChange(BaseModel): ticker: str; action: Literal["add", "remove"]
class LLMResponse(BaseModel): message: str; trades: list[TradeAction]; watchlist_changes: list[WatchlistChange]

# app/llm/prompts.py
def build_context(portfolio: dict, watchlist: list[dict], recent_trades: list[dict]) -> str

# app/llm/client.py
class ChatClient(Protocol):
    async def complete(self, *, user_message: str, context: str, portfolio: dict,
                       history: list[tuple[str, str]]) -> LLMResponse: ...
class LLMError(RuntimeError): ...
def create_chat_client(config: LLMConfig) -> ChatClient   # mock or live
```

`build_context` and the mock client receive plain dicts shaped like `GET /api/portfolio`
and `GET /api/watchlist` items — no imports from `app.db` or `app.api`.

### API → Frontend

Only `API_CONTRACT.md`. Frontend must not import backend code.

### DevOps → everyone

Container listens on `8000`; `STATIC_DIR=/app/static`; `FINALLY_DB_PATH=/app/db/finally.db`.
Docker is **not** installed on this machine: write and review configs, never run `docker`
or install it. Scripts must be idempotent and support `--build`.

## Definition of done per agent

1. Code matches the contracts; no edits outside owned paths.
2. Unit tests written and passing (pytest for backend, Vitest for frontend).
3. `ruff check` clean for touched backend paths.
4. Work committed in the agent's own worktree, nothing pushed.
5. Final report: what was built, commands run, test counts, deviations/risks.
