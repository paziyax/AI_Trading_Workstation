"""Portfolio valuation, trading and history over HTTP."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db import DatabaseError

TRADE_URL = "/api/portfolio/trade"


def trade(client: TestClient, ticker: str, quantity: float, side: str) -> Any:
    return client.post(
        TRADE_URL, json={"ticker": ticker, "quantity": quantity, "side": side}
    )


def buy(client: TestClient, ticker: str, quantity: float) -> Any:
    return trade(client, ticker, quantity, "buy")


def sell(client: TestClient, ticker: str, quantity: float) -> Any:
    return trade(client, ticker, quantity, "sell")


def history(client: TestClient, limit: int | None = None) -> list[dict[str, Any]]:
    url = "/api/portfolio/history" if limit is None else f"/api/portfolio/history?limit={limit}"
    return client.get(url).json()["points"]


def test_empty_portfolio_starts_at_the_seeded_cash(client: TestClient) -> None:
    body = client.get("/api/portfolio").json()

    assert body == {
        "cash_balance": 10_000.0,
        "positions_value": 0.0,
        "total_value": 10_000.0,
        "total_pnl": 0.0,
        "total_pnl_pct": 0.0,
        "unrealized_pnl": 0.0,
        "positions": [],
    }


def test_buy_updates_cash_position_and_message(client: TestClient) -> None:
    response = buy(client, "AAPL", 10)

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Bought 10 AAPL at $190.00"
    assert body["trade"]["ticker"] == "AAPL"
    assert body["trade"]["side"] == "buy"
    assert body["trade"]["quantity"] == 10.0
    assert body["trade"]["price"] == 190.0
    assert body["trade"]["id"]
    assert body["trade"]["executed_at"].endswith("Z")

    portfolio = body["portfolio"]
    assert portfolio["cash_balance"] == 8100.0
    assert portfolio["positions_value"] == 1900.0
    assert portfolio["total_value"] == 10_000.0
    assert portfolio["total_pnl"] == 0.0
    assert portfolio["unrealized_pnl"] == 0.0
    assert portfolio["positions"] == [
        {
            "ticker": "AAPL",
            "quantity": 10.0,
            "avg_cost": 190.0,
            "current_price": 190.0,
            "market_value": 1900.0,
            "unrealized_pnl": 0.0,
            "unrealized_pnl_pct": 0.0,
            "weight": 19.0,
        }
    ]


def test_buy_averages_the_cost_across_fills(
    client: TestClient, source: Any
) -> None:
    buy(client, "AAPL", 10)
    source.publish("AAPL", 200.0)

    body = buy(client, "AAPL", 10).json()
    position = body["portfolio"]["positions"][0]

    assert position["quantity"] == 20.0
    assert position["avg_cost"] == 195.0
    assert position["current_price"] == 200.0
    assert position["market_value"] == 4000.0
    assert position["unrealized_pnl"] == 100.0
    assert body["portfolio"]["cash_balance"] == 6100.0


def test_sell_partial_keeps_the_position(client: TestClient, source: Any) -> None:
    buy(client, "AAPL", 10)
    source.publish("AAPL", 200.0)

    response = sell(client, "AAPL", 4)

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Sold 4 AAPL at $200.00"
    assert body["portfolio"]["cash_balance"] == 8900.0
    position = body["portfolio"]["positions"][0]
    assert position["quantity"] == 6.0
    assert position["avg_cost"] == 190.0
    assert position["market_value"] == 1200.0
    assert position["unrealized_pnl"] == 60.0
    assert body["portfolio"]["total_value"] == 10_100.0


def test_sell_everything_removes_the_position(
    client: TestClient, source: Any
) -> None:
    buy(client, "AAPL", 10)
    source.publish("AAPL", 200.0)

    body = sell(client, "AAPL", 10).json()

    assert body["portfolio"]["positions"] == []
    assert body["portfolio"]["cash_balance"] == 10_100.0
    assert body["portfolio"]["positions_value"] == 0.0


def test_fractional_shares_are_supported(client: TestClient) -> None:
    body = buy(client, "AAPL", 1.5).json()

    position = body["portfolio"]["positions"][0]
    assert position["quantity"] == 1.5
    assert body["portfolio"]["cash_balance"] == 9715.0
    assert body["message"] == "Bought 1.5 AAPL at $190.00"


def test_insufficient_cash_returns_400(client: TestClient) -> None:
    response = buy(client, "AAPL", 100)

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Insufficient cash: need $19,000.00, available $10,000.00"
    }


def test_oversell_returns_400(client: TestClient) -> None:
    buy(client, "AAPL", 5)

    response = sell(client, "AAPL", 10)

    assert response.status_code == 400
    assert response.json() == {"detail": "Cannot sell 10 AAPL: only 5 owned"}


def test_selling_a_missing_position_returns_400(client: TestClient) -> None:
    response = sell(client, "AAPL", 1)

    assert response.status_code == 400
    assert response.json() == {"detail": "No position in AAPL to sell"}


def test_trading_an_unknown_price_returns_400(client: TestClient) -> None:
    response = buy(client, "ZZZZ", 1)

    assert response.status_code == 400
    assert response.json() == {"detail": "No market price available for ZZZZ"}


@pytest.mark.parametrize("quantity", [0, -1, -0.5])
def test_quantity_must_be_positive(client: TestClient, quantity: float) -> None:
    assert buy(client, "AAPL", quantity).status_code == 422


def test_quantity_above_the_cap_is_rejected(client: TestClient) -> None:
    assert buy(client, "AAPL", 1_000_001).status_code == 422
    assert buy(client, "AAPL", 1_000_000).status_code == 400


@pytest.mark.parametrize("side", ["hold", "", "BUY!"])
def test_invalid_side_is_rejected(client: TestClient, side: str) -> None:
    response = client.post(
        TRADE_URL, json={"ticker": "AAPL", "quantity": 1, "side": side}
    )

    assert response.status_code == 422


@pytest.mark.parametrize("ticker", ["1AAPL", "TOOLONGTICKER", "AA PL", ""])
def test_invalid_ticker_is_rejected(client: TestClient, ticker: str) -> None:
    assert buy(client, ticker, 1).status_code == 422


def test_ticker_is_normalized_to_uppercase(client: TestClient) -> None:
    body = buy(client, "aapl", 2).json()

    assert body["trade"]["ticker"] == "AAPL"
    assert body["portfolio"]["positions"][0]["ticker"] == "AAPL"


def test_snapshot_is_written_after_a_trade(client: TestClient) -> None:
    assert len(history(client)) == 1

    buy(client, "AAPL", 10)

    points = history(client)
    assert len(points) == 2
    assert points[-1]["total_value"] == 10_000.0


def test_history_is_oldest_first_and_respects_the_limit(client: TestClient) -> None:
    buy(client, "AAPL", 1)
    buy(client, "MSFT", 1)
    buy(client, "NVDA", 1)

    points = history(client, limit=2)

    assert len(points) == 2
    assert [point["recorded_at"] for point in points] == sorted(
        point["recorded_at"] for point in points
    )
    assert len(history(client)) == 4


@pytest.mark.parametrize("limit", [0, -5, 2001])
def test_history_limit_is_validated(client: TestClient, limit: int) -> None:
    assert client.get(f"/api/portfolio/history?limit={limit}").status_code == 422


def test_history_accepts_the_maximum_limit(client: TestClient) -> None:
    assert client.get("/api/portfolio/history?limit=2000").status_code == 200


def test_positions_are_sorted_by_market_value(client: TestClient) -> None:
    buy(client, "NVDA", 2)
    buy(client, "AAPL", 2)
    buy(client, "MSFT", 1)

    positions = client.get("/api/portfolio").json()["positions"]

    assert [position["ticker"] for position in positions] == ["NVDA", "MSFT", "AAPL"]
    assert [position["market_value"] for position in positions] == [1000.0, 420.0, 380.0]


def test_weights_are_percentages_of_total_value(client: TestClient) -> None:
    buy(client, "AAPL", 10)
    buy(client, "NVDA", 2)

    body = client.get("/api/portfolio").json()
    weights = [position["weight"] for position in body["positions"]]

    assert body["total_value"] == 10_000.0
    assert weights == [19.0, 10.0]
    assert round(sum(weights), 2) == 29.0
    assert body["positions"][0]["weight"] == round(
        body["positions"][0]["market_value"] / body["total_value"] * 100, 2
    )


def test_missing_price_falls_back_to_average_cost(
    app: Any, client: TestClient
) -> None:
    buy(client, "AAPL", 10)
    app.state.cache.remove("AAPL")

    position = client.get("/api/portfolio").json()["positions"][0]

    assert position["current_price"] == 190.0
    assert position["market_value"] == 1900.0
    assert position["unrealized_pnl"] == 0.0


def test_database_error_maps_to_500(
    app: Any, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BrokenPortfolio:
        def get_profile(self) -> object:
            raise DatabaseError("broken")

    monkeypatch.setattr(app.state.db, "_portfolio", BrokenPortfolio())

    response = client.get("/api/portfolio")

    assert response.status_code == 500
    assert response.json() == {"detail": "Database error"}
