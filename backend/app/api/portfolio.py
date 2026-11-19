"""Portfolio endpoints: current valuation, market orders and P&L history."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.deps import CacheDep, DatabaseDep, SettingsDep
from app.db import Trade, TradeError
from app.services import (
    PriceUnavailableError,
    build_portfolio,
    execute_trade,
    normalize_ticker,
    record_snapshot,
)

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

MAX_QUANTITY = 1_000_000.0


class TradeRequest(BaseModel):
    """One market order; quantity and side are validated here, tickers normalized."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    ticker: str
    quantity: float = Field(gt=0, le=MAX_QUANTITY, allow_inf_nan=False)
    side: Literal["buy", "sell"]

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, value: str) -> str:
        return normalize_ticker(value)

    @field_validator("side", mode="before")
    @classmethod
    def _side(cls, value: Any) -> Any:
        return value.strip().lower() if isinstance(value, str) else value


@router.get("")
def get_portfolio(database: DatabaseDep, cache: CacheDep, settings: SettingsDep) -> dict:
    return build_portfolio(database, cache, initial_cash=settings.initial_cash)


@router.post("/trade")
def post_trade(
    payload: TradeRequest,
    database: DatabaseDep,
    cache: CacheDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    try:
        trade = execute_trade(database, cache, payload.ticker, payload.side, payload.quantity)
    except PriceUnavailableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TradeError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    record_snapshot(database, cache)
    return {
        "message": _trade_message(trade),
        "trade": _trade_payload(trade),
        "portfolio": build_portfolio(database, cache, initial_cash=settings.initial_cash),
    }


@router.get("/history")
def get_history(
    database: DatabaseDep,
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> dict[str, list[dict[str, object]]]:
    points = database.portfolio.list_snapshots(limit)
    return {
        "points": [
            {"total_value": point.total_value, "recorded_at": point.recorded_at}
            for point in points
        ]
    }


def _trade_payload(trade: Trade) -> dict[str, object]:
    data = trade.to_dict()
    data["quantity"] = round(trade.quantity, 6)
    data["price"] = round(trade.price, 2)
    return data


def _trade_message(trade: Trade) -> str:
    verb = "Bought" if trade.side == "buy" else "Sold"
    return (
        f"{verb} {_quantity_label(trade.quantity)} {trade.ticker} "
        f"at ${trade.price:,.2f}"
    )


def _quantity_label(quantity: float) -> str:
    value = round(float(quantity), 6)
    return str(int(value)) if value.is_integer() else f"{value:g}"
