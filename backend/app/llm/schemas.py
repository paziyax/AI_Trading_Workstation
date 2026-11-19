"""Structured-output models and the hand-written JSON schema sent to the provider.

The pydantic models are the parse boundary for untrusted model output. The schema below
is deliberately written by hand rather than generated from the models so that every
provider-facing requirement of strict structured output is explicit: all properties are
required, no object accepts unexpected keys, and no pydantic-only keyword leaks through.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

TICKER_PATTERN = r"^[A-Z][A-Z0-9.\-]{0,9}$"
_TICKER_RE = re.compile(TICKER_PATTERN)


def _normalize_ticker(value: str) -> str:
    ticker = value.strip().upper()
    if not _TICKER_RE.match(ticker):
        raise ValueError("ticker must match ^[A-Z][A-Z0-9.\\-]{0,9}$")
    return ticker


class TradeAction(BaseModel):
    """A single market order requested by the assistant."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    ticker: str
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0, allow_inf_nan=False)

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, value: str) -> str:
        return _normalize_ticker(value)

    @field_validator("side", mode="before")
    @classmethod
    def _side(cls, value: Any) -> Any:
        return value.strip().lower() if isinstance(value, str) else value


class WatchlistChange(BaseModel):
    """A single watchlist addition or removal requested by the assistant."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    ticker: str
    action: Literal["add", "remove"]

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, value: str) -> str:
        return _normalize_ticker(value)

    @field_validator("action", mode="before")
    @classmethod
    def _action(cls, value: Any) -> Any:
        return value.strip().lower() if isinstance(value, str) else value


class LLMResponse(BaseModel):
    """The assistant reply plus the actions it wants the API layer to execute.

    Missing or ``null`` action arrays are treated as "no actions" because several
    OpenAI-compatible providers emit ``null`` for an empty array. Unexpected top-level
    keys are ignored: they are harmless and should not cost the user a reply. Action
    objects stay strict, since a misshapen action should never be executed silently.
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    message: str = Field(min_length=1)
    trades: list[TradeAction] = Field(default_factory=list)
    watchlist_changes: list[WatchlistChange] = Field(default_factory=list)

    @field_validator("trades", "watchlist_changes", mode="before")
    @classmethod
    def _none_is_empty(cls, value: Any) -> Any:
        return [] if value is None else value


RESPONSE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "message": {
            "type": "string",
            "description": "The conversational reply shown to the user. Never empty.",
        },
        "trades": {
            "type": "array",
            "description": "Market orders to execute immediately; use [] when none.",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Uppercase ticker symbol, e.g. AAPL.",
                    },
                    "side": {
                        "type": "string",
                        "enum": ["buy", "sell"],
                    },
                    "quantity": {
                        "type": "number",
                        "description": "Number of shares to trade; must be greater than zero.",
                    },
                },
                "required": ["ticker", "side", "quantity"],
                "additionalProperties": False,
            },
        },
        "watchlist_changes": {
            "type": "array",
            "description": "Watchlist edits to apply; use [] when none.",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Uppercase ticker symbol, e.g. PYPL.",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["add", "remove"],
                    },
                },
                "required": ["ticker", "action"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["message", "trades", "watchlist_changes"],
    "additionalProperties": False,
}
