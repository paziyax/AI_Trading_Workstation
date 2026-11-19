"""Health endpoint: process, database, market source and assistant mode."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.api.deps import DatabaseDep, LLMConfigDep, MarketSourceDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def get_health(
    database: DatabaseDep,
    source: MarketSourceDep,
    llm_config: LLMConfigDep,
) -> dict[str, object]:
    """Answer 200 even while degraded: the status field carries the nuance."""

    try:
        database.portfolio.get_profile()
        database_status = "ok"
    except Exception:
        logger.exception("Health check: the database is not usable")
        database_status = "error"

    return {
        "status": "ok" if database_status == "ok" else "degraded",
        "database": database_status,
        "market": source.health().to_dict(),
        "llm": {
            "mode": "mock" if llm_config.mock else "live",
            "model": llm_config.model,
        },
    }
