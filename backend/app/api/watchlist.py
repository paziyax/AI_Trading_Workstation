"""Watchlist endpoints: the priced list plus manual add and remove."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator

from app.api.deps import CacheDep, DatabaseDep, MarketSourceDep, SessionTrackerDep
from app.services import (
    add_watchlist_ticker,
    build_watchlist,
    normalize_ticker,
    remove_watchlist_ticker,
)

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class WatchlistAddRequest(BaseModel):
    """Body of ``POST /api/watchlist``."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    ticker: str

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, value: str) -> str:
        return normalize_ticker(value)


@router.get("")
def get_watchlist(
    database: DatabaseDep,
    cache: CacheDep,
    tracker: SessionTrackerDep,
) -> dict[str, list[dict[str, object]]]:
    return build_watchlist(database, cache, tracker)


@router.post("", status_code=201)
async def post_watchlist(
    payload: WatchlistAddRequest,
    database: DatabaseDep,
    source: MarketSourceDep,
) -> dict[str, Any]:
    added = await add_watchlist_ticker(database, source, payload.ticker)
    if not added:
        raise HTTPException(
            status_code=409,
            detail=f"{payload.ticker} is already in the watchlist",
        )
    return {"ticker": payload.ticker, "added": True}


@router.delete("/{ticker}")
async def delete_watchlist(
    ticker: str,
    database: DatabaseDep,
    source: MarketSourceDep,
    tracker: SessionTrackerDep,
) -> dict[str, Any]:
    try:
        symbol = normalize_ticker(ticker)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    removed = await remove_watchlist_ticker(database, source, symbol, tracker=tracker)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail=f"{symbol} is not in the watchlist",
        )
    return {"ticker": symbol, "removed": True}
