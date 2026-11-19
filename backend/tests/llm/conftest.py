"""Fixtures and fake LiteLLM plumbing for the LLM suite."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from app.llm.config import LLMConfig


def make_config(**overrides: Any) -> LLMConfig:
    base = {
        "mock": False,
        "api_key": "test-key",
        "model": "openrouter/openai/gpt-oss-120b",
        "provider": "cerebras",
        "timeout": 30.0,
    }
    return LLMConfig(**{**base, **overrides})


def sample_portfolio() -> dict[str, Any]:
    return {
        "cash_balance": 8100.0,
        "positions_value": 1910.0,
        "total_value": 10010.0,
        "total_pnl": 10.0,
        "total_pnl_pct": 0.1,
        "unrealized_pnl": 10.0,
        "positions": [
            {
                "ticker": "AAPL",
                "quantity": 10.0,
                "avg_cost": 190.0,
                "current_price": 191.0,
                "market_value": 1910.0,
                "unrealized_pnl": 10.0,
                "unrealized_pnl_pct": 0.5263,
                "weight": 19.08,
            }
        ],
    }


def sample_watchlist() -> list[dict[str, Any]]:
    return [
        {
            "ticker": "AAPL",
            "price": 191.0,
            "previous_price": 190.8,
            "change": 0.2,
            "change_pct": 0.1048,
            "open_price": 190.0,
            "timestamp": 1795102697.4,
        },
        {
            "ticker": "MSFT",
            "price": 420.5,
            "previous_price": 421.0,
            "change": -0.5,
            "change_pct": -0.1188,
            "open_price": 421.0,
            "timestamp": 1795102697.4,
        },
    ]


def sample_trades() -> list[dict[str, Any]]:
    return [
        {
            "id": "trade-1",
            "ticker": "AAPL",
            "side": "buy",
            "quantity": 10.0,
            "price": 190.0,
            "executed_at": "2026-11-19T15:38:22Z",
        }
    ]


def completion(content: str | None) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def payload(**overrides: Any) -> str:
    body: dict[str, Any] = {"message": "Done.", "trades": [], "watchlist_changes": []}
    body.update(overrides)
    return json.dumps(body)


class FakeACompletion:
    """Records every LiteLLM call and returns (or raises) a canned result."""

    def __init__(self, result: Any = None, error: BaseException | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture
def portfolio() -> dict[str, Any]:
    return sample_portfolio()


@pytest.fixture
def watchlist() -> list[dict[str, Any]]:
    return sample_watchlist()


@pytest.fixture
def recent_trades() -> list[dict[str, Any]]:
    return sample_trades()


@pytest.fixture
def fake_acompletion(monkeypatch: pytest.MonkeyPatch):
    """Install a fake ``litellm.acompletion`` and return an installer."""

    def install(
        *,
        content: str | None = None,
        result: Any = None,
        error: BaseException | None = None,
    ) -> FakeACompletion:
        import app.llm.client as client_module

        if result is None:
            result = completion(content)
        fake = FakeACompletion(result=result, error=error)
        monkeypatch.setattr(client_module.litellm, "acompletion", fake)
        return fake

    return install
