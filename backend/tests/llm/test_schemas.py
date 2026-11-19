"""Structured-output parsing and the provider-facing JSON schema."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from app.llm.schemas import (
    RESPONSE_JSON_SCHEMA,
    LLMResponse,
    TradeAction,
    WatchlistChange,
)


def test_full_payload_parses() -> None:
    response = LLMResponse.model_validate_json(
        """
        {
          "message": "Buying five shares of Apple.",
          "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 5}],
          "watchlist_changes": [{"ticker": "PYPL", "action": "add"}]
        }
        """
    )

    assert response.message == "Buying five shares of Apple."
    assert response.trades == [TradeAction(ticker="AAPL", side="buy", quantity=5.0)]
    assert response.watchlist_changes == [WatchlistChange(ticker="PYPL", action="add")]


def test_missing_action_arrays_default_to_empty() -> None:
    response = LLMResponse.model_validate_json('{"message": "No changes."}')

    assert response.trades == []
    assert response.watchlist_changes == []


def test_null_action_arrays_are_treated_as_empty() -> None:
    response = LLMResponse.model_validate_json(
        '{"message": "No changes.", "trades": null, "watchlist_changes": null}'
    )

    assert response.trades == []
    assert response.watchlist_changes == []


def test_tickers_and_sides_are_normalized() -> None:
    response = LLMResponse.model_validate_json(
        """
        {
          "message": "Selling.",
          "trades": [{"ticker": " brk.b ", "side": "SELL", "quantity": "1.5"}],
          "watchlist_changes": [{"ticker": "pypl", "action": "ADD"}]
        }
        """
    )

    assert response.trades[0].ticker == "BRK.B"
    assert response.trades[0].side == "sell"
    assert response.trades[0].quantity == 1.5
    assert response.watchlist_changes[0].ticker == "PYPL"
    assert response.watchlist_changes[0].action == "add"


@pytest.mark.parametrize("side", ["hold", "BUYING", "", None, 1])
def test_invalid_side_is_rejected(side: Any) -> None:
    with pytest.raises(ValidationError):
        TradeAction(ticker="AAPL", side=side, quantity=1)


@pytest.mark.parametrize("action", ["watch", "DELETE", "", None, 0])
def test_invalid_watchlist_action_is_rejected(action: Any) -> None:
    with pytest.raises(ValidationError):
        WatchlistChange(ticker="PYPL", action=action)


@pytest.mark.parametrize("quantity", [0, -1, -0.5, "zero", None, float("inf"), "Infinity"])
def test_non_positive_or_non_finite_quantity_is_rejected(quantity: Any) -> None:
    with pytest.raises(ValidationError):
        TradeAction(ticker="AAPL", side="buy", quantity=quantity)


@pytest.mark.parametrize("ticker", ["", "  ", "1AAPL", "AAPL/USD", "AAPL USD", "TOOLONGTICKER"])
def test_invalid_ticker_is_rejected(ticker: str) -> None:
    with pytest.raises(ValidationError):
        TradeAction(ticker=ticker, side="buy", quantity=1)


def test_extra_field_in_trade_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TradeAction(ticker="AAPL", side="buy", quantity=1, reason="momentum")


def test_extra_field_in_watchlist_change_is_rejected() -> None:
    with pytest.raises(ValidationError):
        WatchlistChange(ticker="PYPL", action="add", reason="payments")


def test_extra_top_level_field_is_ignored() -> None:
    response = LLMResponse.model_validate_json(
        '{"message": "Hi.", "trades": [], "watchlist_changes": [], "confidence": 0.9}'
    )

    assert response.message == "Hi."


@pytest.mark.parametrize("message", ["", "   ", "\n\t"])
def test_empty_message_is_rejected(message: str) -> None:
    with pytest.raises(ValidationError):
        LLMResponse.model_validate_json(json.dumps({"message": message}))


def test_message_whitespace_is_trimmed() -> None:
    response = LLMResponse.model_validate_json('{"message": "  Hello there.  "}')

    assert response.message == "Hello there."


def test_malformed_json_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LLMResponse.model_validate_json("Sure! Here is the JSON you asked for: {}")


def _object_nodes(node: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        if node.get("type") == "object":
            found.append(node)
        for value in node.values():
            found.extend(_object_nodes(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_object_nodes(value))
    return found


def test_schema_is_strict_at_every_object_node() -> None:
    objects = _object_nodes(RESPONSE_JSON_SCHEMA)

    assert len(objects) == 3  # response, trade item, watchlist change item
    for node in objects:
        assert node["additionalProperties"] is False
        assert sorted(node["required"]) == sorted(node["properties"])
        assert all("type" in schema for schema in node["properties"].values())


def test_schema_declares_the_action_shapes() -> None:
    trade = RESPONSE_JSON_SCHEMA["properties"]["trades"]["items"]
    change = RESPONSE_JSON_SCHEMA["properties"]["watchlist_changes"]["items"]

    assert trade["properties"]["side"]["enum"] == ["buy", "sell"]
    assert trade["required"] == ["ticker", "side", "quantity"]
    assert change["properties"]["action"]["enum"] == ["add", "remove"]
    assert change["required"] == ["ticker", "action"]


def test_schema_has_no_optional_properties() -> None:
    assert RESPONSE_JSON_SCHEMA["required"] == ["message", "trades", "watchlist_changes"]
    for node in _object_nodes(RESPONSE_JSON_SCHEMA):
        assert "anyOf" not in node
        assert "oneOf" not in node
