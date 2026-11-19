"""FastAPI application factory, lifespan and static-file wiring.

``create_app`` accepts already-built collaborators so tests (and future workers) can run the
whole HTTP surface against a fake market source and a stub chat client. Production calls it
with no arguments; ``app`` at the bottom is what ``uvicorn app.main:app`` imports.

Startup order matters: the database must exist before the watchlist is read, the cache must
exist before the source, and the source must be started before the first snapshot so the
initial point already reflects seeded prices.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import chat, health, portfolio, watchlist
from app.config import Settings
from app.db import Database, DatabaseError
from app.llm import ChatClient, LLMConfig, create_chat_client
from app.market import (
    MarketDataConfig,
    MarketDataSource,
    PriceCache,
    create_market_data_source,
    create_stream_router,
)
from app.services import SessionOpenTracker, record_snapshot

logger = logging.getLogger(__name__)

ROOT_HINT = (
    "FinAlly backend is running, but the frontend has not been built. "
    "Run `npm --prefix frontend run build` (or point STATIC_DIR at an exported build)."
)


async def _snapshot_loop(database: Database, cache: PriceCache, interval: float) -> None:
    """Write a portfolio snapshot every ``interval`` seconds until cancelled."""

    while True:
        await asyncio.sleep(interval)
        try:
            record_snapshot(database, cache)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Periodic portfolio snapshot failed")


def create_app(
    *,
    settings: Settings | None = None,
    source: MarketDataSource | None = None,
    chat_client: ChatClient | None = None,
) -> FastAPI:
    """Build the FinAlly application; injected collaborators replace the defaults."""

    active_settings = settings if settings is not None else Settings.from_env()
    llm_config = LLMConfig.from_env()
    database = Database(active_settings.db_path)
    cache = PriceCache()
    market_source = (
        source
        if source is not None
        else create_market_data_source(cache, MarketDataConfig.from_env())
    )
    llm_client = chat_client if chat_client is not None else create_chat_client(llm_config)
    tracker = SessionOpenTracker()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        database.initialize()

        try:
            await market_source.start(database.watchlist.list_tickers())
        except Exception:
            logger.exception(
                "Market data source failed to start; continuing without live prices"
            )

        try:
            if not database.portfolio.list_snapshots(1):
                record_snapshot(database, cache)
        except Exception:
            logger.exception("Could not write the initial portfolio snapshot")

        task = asyncio.create_task(
            _snapshot_loop(database, cache, active_settings.snapshot_interval),
            name="portfolio-snapshot",
        )
        application.state.snapshot_task = task
        try:
            yield
        finally:
            application.state.snapshot_task = None
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Portfolio snapshot task failed during shutdown")
            try:
                await market_source.stop()
            except Exception:
                logger.exception("Market data source failed to stop cleanly")

    app = FastAPI(title="FinAlly", version="0.1.0", lifespan=lifespan)

    app.state.settings = active_settings
    app.state.db = database
    app.state.cache = cache
    app.state.source = market_source
    app.state.chat_client = llm_client
    app.state.llm_config = llm_config
    app.state.session_tracker = tracker
    app.state.snapshot_task = None

    @app.exception_handler(DatabaseError)
    async def _database_error_handler(
        request: Request, exc: DatabaseError
    ) -> JSONResponse:
        logger.error("Database error on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(status_code=500, content={"detail": "Database error"})

    app.include_router(health.router)
    app.include_router(portfolio.router)
    app.include_router(watchlist.router)
    app.include_router(chat.router)
    app.include_router(create_stream_router(cache))

    static_dir = Path(active_settings.static_dir)
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
    else:

        @app.get("/", include_in_schema=False)
        def root_hint() -> dict[str, str]:
            return {
                "status": "ok",
                "detail": ROOT_HINT,
                "static_dir": str(static_dir),
            }

    return app


app = create_app()
