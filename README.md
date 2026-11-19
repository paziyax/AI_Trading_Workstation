# AI Trading Workstation

A visually stunning AI-powered trading workstation that streams live market data, simulates portfolio trading, and integrates an LLM chat assistant that can analyze positions and execute trades via natural language.

Built entirely by coding agents as a capstone project for an agentic AI coding course.

## Features

- **Live price streaming** via SSE with green/red flash animations
- **Simulated portfolio** — $10k virtual cash, market orders, instant fills
- **Portfolio visualizations** — heatmap (treemap), P&L chart, positions table
- **AI chat assistant** — analyzes holdings, suggests and auto-executes trades
- **Watchlist management** — track tickers manually or via AI
- **Dark terminal aesthetic** — Bloomberg-inspired, data-dense layout

## Architecture

Single Docker container serving everything on port 8000:

- **Frontend**: Next.js (static export) with TypeScript and Tailwind CSS
- **Backend**: FastAPI (Python/uv) with SSE streaming
- **Database**: SQLite with lazy initialization
- **AI**: LiteLLM → OpenRouter (DeepSeek V4.1 Flash 1017) with structured outputs
- **Market data**: Built-in GBM simulator (default) or Massive API (optional)

## Quick Start

```bash
# Clone and configure
cp .env.example .env
# Add your OPENROUTER_API_KEY to .env

# Run with Docker
docker build -t finally .
docker run -v finally-data:/app/data -p 8000:8000 --env-file .env finally

# Open http://localhost:8000
```

## Run with Docker

The app ships as one container (FastAPI serving the static Next.js export) on port 8000.
Build once, then use the start/stop scripts:

```bash
# macOS / Linux
cp .env.example .env               # first run only; add OPENROUTER_API_KEY
./scripts/start_mac.sh --build     # build + start detached
./scripts/stop_mac.sh              # stop and remove the container
```

```powershell
# Windows PowerShell
Copy-Item .env.example .env        # first run only; add OPENROUTER_API_KEY
.\scripts\start_windows.ps1 -Build
.\scripts\stop_windows.ps1
```

Open **http://localhost:8000**. The SQLite database lives in the named volume
`finally-data` mounted at `/app/data`, so it survives restarts and rebuilds; the stop
scripts never delete it. To reset the portfolio, stop the container and run
`docker volume rm finally-data`. Full details: [scripts/README.md](scripts/README.md).

Compose users can run `docker compose up -d --build` instead.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes | OpenRouter API key for AI chat |
| `MASSIVE_API_KEY` | No | Massive (Polygon.io) key for real market data; omit to use simulator |
| `MARKET_DATA_SOURCE` | No | `auto` (default), `massive` or `simulator` |
| `MASSIVE_PLAN` | No | Your Massive tier: `basic` (default), `starter`, `developer`, `advanced` |
| `LLM_MOCK` | No | Set `true` for deterministic mock LLM responses (testing) |

## Market Data: Simulator or Massive

The app ships with a **built-in simulator**, so it works with no market data account at all.
Massive is optional and is only called when you configure it.

| Want | Configure |
|---|---|
| Fake prices — free, ~2 updates/sec, runs 24/7 | leave `MASSIVE_API_KEY` empty, or set `MARKET_DATA_SOURCE=simulator` |
| Real prices | set `MASSIVE_API_KEY=...` and `MASSIVE_PLAN=<your tier>` |
| Force a specific source | `MARKET_DATA_SOURCE=simulator` or `MARKET_DATA_SOURCE=massive` |

- The default is `MARKET_DATA_SOURCE=auto`: a key means Massive, no key means the simulator.
- `MARKET_DATA_SOURCE=massive` with an empty key fails at startup instead of silently falling back.
- `MASSIVE_PLAN` must match what you actually bought. The backend picks its data mode from the plan,
  not from the key alone.

### Which Massive plan gives real intraday prices

| Plan | Price | Data recency | Produces live prices? |
|---|---|---|---|
| Basic | free | end of day | **No** — end-of-day bars, refreshed every 30 min |
| Starter | $29/mo | 15-minute delayed | delayed only |
| Developer | $79/mo | 15-minute delayed | delayed only |
| Advanced | $199/mo | real time | **Yes** |

A Basic key authenticates fine but is **not entitled to snapshots**, so the backend falls back to
end-of-day mode and prices look frozen. If the UI shows no prices, check `/api/health`:
`"mode": "eod"` means the plan is too low; `"mode": "simulator"` means the simulator is running.
Full entitlement table: [planning/archive/MASSIVE_API.md](planning/archive/MASSIVE_API.md).

## Project Structure

```
finally/
├── frontend/    # Next.js static export
├── backend/     # FastAPI uv project
├── planning/    # Project documentation and agent contracts
├── test/        # Playwright E2E tests
├── db/          # SQLite volume mount (runtime)
└── scripts/     # Start/stop helpers
```

## OpenCode GitHub bot

This repository is wired to the OpenCode GitHub App. Comment `/oc` (or `/opencode`) on an issue or pull request to have the agent run a task, and every pull request that is not a draft gets an automatic review. See [OpenCode GitHub Integration](.github/OPENCODE_GITHUB.md) for how it works, required setup, and troubleshooting.

## License

See [LICENSE](LICENSE).
