"""``GET /api/health`` and startup resilience."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import DatabaseError
from app.llm import ChatClient, MockChatClient
from app.main import create_app
from tests.api.conftest import FakeMarketSource, build_app

MARKET_KEYS = {
    "mode",
    "connected",
    "detail",
    "last_success_at",
    "consecutive_failures",
    "last_error",
    "age_seconds",
}


def test_health_shape(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert set(body["market"]) == MARKET_KEYS
    assert body["market"]["mode"] == "simulator"
    assert body["market"]["connected"] is True
    assert body["market"]["consecutive_failures"] == 0
    assert body["llm"]["mode"] in {"mock", "live"}
    assert isinstance(body["llm"]["model"], str) and body["llm"]["model"]


def test_health_reports_mock_mode_from_environment(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_MOCK", "true")
    monkeypatch.setenv("LLM_MODEL", "openrouter/test/model")
    app = build_app(settings, source=FakeMarketSource())

    with TestClient(app) as client:
        body = client.get("/api/health").json()

    assert body["llm"] == {"mode": "mock", "model": "openrouter/test/model"}
    assert isinstance(app.state.chat_client, MockChatClient)


def test_health_reports_database_failure(
    app: object,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenPortfolio:
        def get_profile(self) -> object:
            raise DatabaseError("profile unreadable")

    monkeypatch.setattr(app.state.db, "_portfolio", BrokenPortfolio())

    body = client.get("/api/health").json()

    assert body["status"] == "degraded"
    assert body["database"] == "error"


def test_startup_survives_a_failing_market_source(settings: Settings) -> None:
    source = FakeMarketSource()
    source.start_error = RuntimeError("vendor down")
    app = build_app(settings, source=source)

    with TestClient(app) as client:
        body = client.get("/api/health").json()
        portfolio = client.get("/api/portfolio")

    assert source.starts == 1
    assert body["status"] == "ok"
    assert body["market"]["connected"] is False
    assert body["market"]["last_error"].startswith("RuntimeError")
    assert portfolio.status_code == 200
    assert source.stops == 1


def test_lifespan_writes_an_initial_snapshot(app: object) -> None:
    with TestClient(app) as client:
        points = client.get("/api/portfolio/history").json()["points"]

    assert len(points) == 1
    assert points[0]["total_value"] == 10_000.0
    assert app.state.db.portfolio.list_snapshots(10) != []


def test_startup_does_not_duplicate_the_initial_snapshot(
    settings: Settings,
    tmp_path: Path,
) -> None:
    app = build_app(settings, source=FakeMarketSource())
    with TestClient(app):
        pass
    with TestClient(app) as client:
        points = client.get("/api/portfolio/history").json()["points"]

    assert len(points) == 1


def test_app_exposes_collaborators_on_state(
    app: object,
    chat_client: ChatClient,
) -> None:
    assert app.state.chat_client is chat_client
    assert app.state.cache is not None
    assert app.state.session_tracker is not None
    assert app.state.snapshot_task is None


def test_create_app_defaults_are_constructible(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "composed.db"))
    monkeypatch.setenv("STATIC_DIR", str(tmp_path / "missing"))
    monkeypatch.setenv("LLM_MOCK", "true")

    app = create_app()

    assert isinstance(app.state.chat_client, MockChatClient)
    assert app.state.settings.db_path == tmp_path / "composed.db"
