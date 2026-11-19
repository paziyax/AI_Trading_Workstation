# Start / stop scripts

One-page guide to running FinAlly in Docker. The container serves the whole app
(FastAPI + static Next.js export) on a single port.

## Prerequisites

- **Docker**: Docker Desktop on Windows/macOS, or Docker Engine on Linux. The
  daemon must be running — the scripts check this and explain what is wrong.
- **`.env`** in the repo root. Create it on first run:
  - macOS/Linux: `cp .env.example .env`
  - Windows: `Copy-Item .env.example .env`
- **`OPENROUTER_API_KEY`** in `.env` for live AI chat. Without a key set
  `LLM_MOCK=true` for deterministic offline replies.
- Optional: `MASSIVE_API_KEY` for real market data; leave empty to use the
  built-in simulator.

The start scripts create `.env` from `.env.example` if it is missing, then start
the app anyway. You can add your key later and restart.

## Usage

### macOS / Linux

```bash
./scripts/start_mac.sh              # build only if finally:latest is missing
./scripts/start_mac.sh --build      # force a rebuild
./scripts/start_mac.sh --no-browser # do not open a browser tab
./scripts/stop_mac.sh
```

If the scripts are not executable yet: `chmod +x scripts/*.sh`.

### Windows PowerShell

```powershell
.\scripts\start_windows.ps1         # build only if finally:latest is missing
.\scripts\start_windows.ps1 -Build  # force a rebuild
.\scripts\stop_windows.ps1
```

If PowerShell blocks local scripts:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_windows.ps1
```

### Docker Compose (alternative)

```bash
docker compose up -d --build
docker compose down        # keeps the volume
```

## What the scripts do

- `start`: checks Docker and the daemon, creates `.env` if absent, builds
  `finally:latest` when missing or when `--build`/`-Build` is passed, removes any
  stale container named `finally`, then runs it detached with port `8000`, the
  `finally-data` volume and `.env`. Both start scripts are safe to run twice.
- `stop`: stops and removes the `finally` container. It never removes the volume
  and succeeds quietly when nothing is running.

The app is at **http://localhost:8000**. Logs:

```bash
docker logs -f finally
```

## Where data lives

The SQLite database is stored in the named Docker volume **`finally-data`**,
mounted at `/app/data` inside the container (`/app/data/finally.db`). It survives
`stop`, container removal and image rebuilds. `docker compose down` also keeps it.

The repo's `db/` directory is only the local mount-point placeholder; with Docker
the real file lives inside the volume. Inspect the volume with:

```bash
docker volume inspect finally-data
```

## Rebuild after code changes

```bash
./scripts/start_mac.sh --build             # macOS/Linux
.\scripts\start_windows.ps1 -Build         # Windows
docker compose up -d --build               # Compose
```

or manually:

```bash
docker build -t finally:latest .
```

## Reset the database

Stopping never deletes data. To start over with $10,000 cash and the default
watchlist, delete the volume while the container is stopped:

```bash
./scripts/stop_mac.sh
docker volume rm finally-data
./scripts/start_mac.sh
```

Windows:

```powershell
.\scripts\stop_windows.ps1
docker volume rm finally-data
.\scripts\start_windows.ps1
```

Compose: `docker compose down -v` removes the volume too.

## Port already in use

The scripts publish host port 8000. Stop the other process (or the old
container: `docker rm -f finally`) and run the start script again.
