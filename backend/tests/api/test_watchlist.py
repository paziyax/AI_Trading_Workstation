"""Watchlist read model, add and remove over HTTP."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import NEW_TICKER_PRICE, SEED_TICKERS

WATCHLIST_URL = "/api/watchlist"
ITEM_KEYS = {
    "ticker",
    "price",
    "previous_price",
    "change",
    "change_pct",
    "open_price",
    "timestamp",
}


def items(client: TestClient) -> list[dict[str, Any]]:
    return client.get(WATCHLIST_URL).json()["tickers"]


def test_default_watchlist_is_seeded_in_insertion_order(client: TestClient) -> None:
    body = client.get(WATCHLIST_URL).json()

    assert [item["ticker"] for item in body["tickers"]] == SEED_TICKERS
    assert all(set(item) == ITEM_KEYS for item in body["tickers"])
    aapl = body["tickers"][0]
    assert aapl["price"] == 190.0
    assert aapl["open_price"] == 190.0
    assert aapl["change"] == 0.0
    assert aapl["change_pct"] == 0.0
    assert isinstance(aapl["timestamp"], float)


def test_session_change_is_measured_from_the_first_observed_price(
    client: TestClient, source: Any
) -> None:
    assert client.get(WATCHLIST_URL).status_code == 200  # records the session open at 190
    source.publish("AAPL", 191.0)

    item = items(client)[0]

    assert item["ticker"] == "AAPL"
    assert item["price"] == 191.0
    assert item["previous_price"] == 190.0
    assert item["open_price"] == 190.0
    assert item["change"] == 1.0
    assert item["change_pct"] == 0.5263


def test_session_open_survives_later_updates(client: TestClient, source: Any) -> None:
    client.get(WATCHLIST_URL)
    source.publish("AAPL", 200.0)
    source.publish("AAPL", 210.0)

    item = items(client)[0]

    assert item["open_price"] == 190.0
    assert item["price"] == 210.0
    assert item["change"] == 20.0


def test_ticker_without_a_price_returns_nulls(app: Any, client: TestClient) -> None:
    app.state.cache.remove("AAPL")

    item = items(client)[0]

    assert item == {
        "ticker": "AAPL",
        "price": None,
        "previous_price": None,
        "change": None,
        "change_pct": None,
        "open_price": None,
        "timestamp": None,
    }


def test_add_ticker_persists_and_notifies_the_source(
    client: TestClient, source: Any
) -> None:
    response = client.post(WATCHLIST_URL, json={"ticker": "PYPL"})

    assert response.status_code == 201
    assert response.json() == {"ticker": "PYPL", "added": True}
    assert source.added == ["PYPL"]

    listed = items(client)
    assert listed[-1]["ticker"] == "PYPL"
    assert listed[-1]["price"] == NEW_TICKER_PRICE
    assert listed[-1]["open_price"] == NEW_TICKER_PRICE


def test_add_normalizes_lowercase_tickers(client: TestClient, source: Any) -> None:
    response = client.post(WATCHLIST_URL, json={"ticker": "  pypl "})

    assert response.status_code == 201
    assert response.json()["ticker"] == "PYPL"
    assert source.added == ["PYPL"]


def test_adding_a_duplicate_returns_409(client: TestClient, source: Any) -> None:
    response = client.post(WATCHLIST_URL, json={"ticker": "AAPL"})

    assert response.status_code == 409
    assert response.json() == {"detail": "AAPL is already in the watchlist"}
    assert source.added == []


def test_adding_the_same_ticker_twice_returns_409(client: TestClient, source: Any) -> None:
    assert client.post(WATCHLIST_URL, json={"ticker": "PYPL"}).status_code == 201

    response = client.post(WATCHLIST_URL, json={"ticker": "PYPL"})

    assert response.status_code == 409
    assert source.added == ["PYPL"]


@pytest.mark.parametrize("ticker", ["123", "BAD TICKER", "TOOLONGTICKER", ""])
def test_invalid_ticker_is_rejected(client: TestClient, ticker: str) -> None:
    assert client.post(WATCHLIST_URL, json={"ticker": ticker}).status_code == 422


def test_delete_removes_from_repository_and_source(
    client: TestClient, source: Any
) -> None:
    response = client.delete(f"{WATCHLIST_URL}/GOOGL")

    assert response.status_code == 200
    assert response.json() == {"ticker": "GOOGL", "removed": True}
    assert source.removed == ["GOOGL"]
    assert "GOOGL" not in [item["ticker"] for item in items(client)]


def test_delete_normalizes_the_path_ticker(client: TestClient, source: Any) -> None:
    response = client.delete(f"{WATCHLIST_URL}/googl")

    assert response.status_code == 200
    assert response.json()["ticker"] == "GOOGL"
    assert source.removed == ["GOOGL"]


def test_delete_missing_ticker_returns_404(client: TestClient, source: Any) -> None:
    response = client.delete(f"{WATCHLIST_URL}/ZZZZ")

    assert response.status_code == 404
    assert response.json() == {"detail": "ZZZZ is not in the watchlist"}
    assert source.removed == []


def test_delete_with_invalid_pattern_returns_422(client: TestClient) -> None:
    assert client.delete(f"{WATCHLIST_URL}/1BAD").status_code == 422


def test_re_adding_after_delete_starts_a_new_session(
    client: TestClient, source: Any
) -> None:
    client.delete(f"{WATCHLIST_URL}/AAPL")
    source.publish("AAPL", 200.0)
    assert client.post(WATCHLIST_URL, json={"ticker": "AAPL"}).status_code == 201

    item = [entry for entry in items(client) if entry["ticker"] == "AAPL"][0]

    assert item["open_price"] == 200.0
    assert item["change"] == 0.0
