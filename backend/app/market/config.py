"""Environment-driven configuration and plan capability model.

The load-bearing rule: **a key is not a capability.** A free Basic key authenticates fine but is
not entitled to snapshot endpoints, so selection must consider the plan, not just key presence.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum


class ConfigurationError(RuntimeError):
    """Invalid or contradictory market data configuration."""


class Plan(str, Enum):
    BASIC = "basic"
    STARTER = "starter"
    DEVELOPER = "developer"
    ADVANCED = "advanced"

    @property
    def supports_snapshots(self) -> bool:
        return self is not Plan.BASIC

    @property
    def snapshot_delay_minutes(self) -> int:
        return {
            Plan.BASIC: 0,
            Plan.STARTER: 15,
            Plan.DEVELOPER: 15,
            Plan.ADVANCED: 0,
        }[self]

    @property
    def min_poll_interval(self) -> float:
        # Basic is limited to 5 calls/minute; it uses EOD mode, but keep the floor honest.
        return 15.0 if self is Plan.BASIC else 2.0


def _env_float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number, got {raw!r}") from exc


@dataclass(frozen=True, slots=True)
class MarketDataConfig:
    api_key: str
    plan: Plan
    source: str  # auto | massive | simulator
    poll_interval: float
    event_probability: float
    eod_refresh_seconds: int
    eod_lookback_days: int

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> MarketDataConfig:
        env = os.environ if env is None else env
        api_key = env.get("MASSIVE_API_KEY", "").strip()
        source = env.get("MARKET_DATA_SOURCE", "auto").strip().lower()
        if source not in {"auto", "massive", "simulator"}:
            raise ConfigurationError(
                f"MARKET_DATA_SOURCE must be auto|massive|simulator, got {source!r}"
            )

        raw_plan = env.get("MASSIVE_PLAN", "basic").strip().lower()
        try:
            plan = Plan(raw_plan)
        except ValueError as exc:
            raise ConfigurationError(f"Unknown MASSIVE_PLAN {raw_plan!r}") from exc

        if source == "massive" and not api_key:
            raise ConfigurationError("MARKET_DATA_SOURCE=massive requires MASSIVE_API_KEY")

        poll_interval = max(
            plan.min_poll_interval, _env_float(env, "MASSIVE_POLL_INTERVAL", 15.0)
        )
        return cls(
            api_key=api_key,
            plan=plan,
            source=source,
            poll_interval=poll_interval,
            event_probability=_env_float(env, "SIM_EVENT_PROBABILITY", 0.001),
            eod_refresh_seconds=int(_env_float(env, "MASSIVE_EOD_REFRESH", 1800)),
            eod_lookback_days=int(_env_float(env, "MASSIVE_EOD_LOOKBACK", 5)),
        )
