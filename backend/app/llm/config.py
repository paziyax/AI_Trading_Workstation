"""Environment-driven configuration for the FinAlly chat assistant.

Reading the environment is deliberately total: a missing or malformed optional value
degrades to the documented default instead of preventing the application from starting.
A missing ``OPENROUTER_API_KEY`` is not an error here either - the live client reports it
at call time, which lets the API layer answer the chat request with a 503 instead of
failing at import or startup.
"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_MODEL = "openrouter/openai/gpt-oss-120b"
DEFAULT_PROVIDER = "cerebras"
DEFAULT_TIMEOUT_SECONDS = 30.0

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _text(env: Mapping[str, str], name: str, default: str) -> str:
    raw = env.get(name, "")
    value = raw.strip() if isinstance(raw, str) else ""
    return value or default


def _flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name, "")
    value = raw.strip().lower() if isinstance(raw, str) else ""
    if not value:
        return default
    return value in _TRUTHY


def _timeout(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name, "")
    value = raw.strip() if isinstance(raw, str) else ""
    if not value:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    return parsed if math.isfinite(parsed) and parsed > 0 else default


@dataclass(frozen=True, slots=True)
class LLMConfig:
    """Everything the chat client needs to reach OpenRouter or run offline."""

    mock: bool
    api_key: str
    model: str
    provider: str
    timeout: float

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> LLMConfig:
        """Build a config from ``env`` (defaults to ``os.environ``).

        Never raises: blank or malformed optional values fall back to the defaults.
        """

        source = os.environ if env is None else env
        return cls(
            mock=_flag(source, "LLM_MOCK", False),
            api_key=_text(source, "OPENROUTER_API_KEY", ""),
            model=_text(source, "LLM_MODEL", DEFAULT_MODEL),
            provider=_text(source, "LLM_PROVIDER", DEFAULT_PROVIDER).lower(),
            timeout=_timeout(source, "LLM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS),
        )
