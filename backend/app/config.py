"""Environment-driven configuration for the FinAlly API layer.

The repository root is derived from this file's location, so the defaults work from a
checkout, from a Docker image (``/app``) and from a test process alike. ``.env`` is loaded
once, with ``override=False``: a real environment variable always wins over the file.

Reading is deliberately total - a blank or malformed optional value falls back to the
documented default instead of preventing the process from starting. Paths may be relative;
they are resolved against the repository root so ``STATIC_DIR=frontend/out`` works from any
working directory.
"""

from __future__ import annotations

import logging
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DB_PATH = REPO_ROOT / "db" / "finally.db"
DEFAULT_STATIC_DIR = REPO_ROOT / "frontend" / "out"
DEFAULT_INITIAL_CASH = 10_000.0
DEFAULT_SNAPSHOT_INTERVAL_SECONDS = 30.0

logger = logging.getLogger(__name__)


def _load_dotenv() -> None:
    """Load ``<repo>/.env`` into ``os.environ`` without overwriting real variables."""

    env_file = REPO_ROOT / ".env"
    if not env_file.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - python-dotenv is a declared dependency
        logger.warning("python-dotenv is unavailable; skipping %s", env_file)
        return
    load_dotenv(env_file, override=False)


def _text(env: Mapping[str, str], name: str, default: str) -> str:
    raw = env.get(name, "")
    value = raw.strip() if isinstance(raw, str) else ""
    return value or default


def _path(env: Mapping[str, str], name: str, default: Path) -> Path:
    raw = _text(env, name, "")
    path = Path(raw).expanduser() if raw else default
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def _number(
    env: Mapping[str, str],
    name: str,
    default: float,
    *,
    minimum: float,
) -> float:
    raw = _text(env, name, "")
    if not raw:
        return default
    try:
        parsed = float(raw)
    except ValueError:
        logger.warning("%s=%r is not a number; using %s", name, raw, default)
        return default
    if not math.isfinite(parsed) or parsed < minimum:
        logger.warning("%s=%r is out of range; using %s", name, raw, default)
        return default
    return parsed


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything the API layer needs outside the database and the LLM client."""

    db_path: Path
    static_dir: Path
    initial_cash: float = DEFAULT_INITIAL_CASH
    snapshot_interval: float = DEFAULT_SNAPSHOT_INTERVAL_SECONDS

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Build the settings from ``env`` (defaults to the process environment).

        When ``env`` is omitted the repository ``.env`` file is loaded first, so callers
        normally do not need ``python-dotenv`` themselves.
        """

        if env is None:
            _load_dotenv()
            source: Mapping[str, str] = os.environ
        else:
            source = env
        return cls(
            db_path=_path(source, "FINALLY_DB_PATH", DEFAULT_DB_PATH),
            static_dir=_path(source, "STATIC_DIR", DEFAULT_STATIC_DIR),
            initial_cash=_number(
                source, "INITIAL_CASH", DEFAULT_INITIAL_CASH, minimum=0.0
            ),
            snapshot_interval=_number(
                source,
                "SNAPSHOT_INTERVAL_SECONDS",
                DEFAULT_SNAPSHOT_INTERVAL_SECONDS,
                minimum=0.01,
            ),
        )
