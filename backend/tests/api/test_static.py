"""Static export mounting and the backend-only root hint."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from tests.api.conftest import FakeMarketSource, build_app


def test_root_returns_a_hint_when_the_static_dir_is_missing(
    settings: Settings,
) -> None:
    app = build_app(settings, source=FakeMarketSource())

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "frontend" in body["detail"].lower()
    assert body["static_dir"] == str(settings.static_dir)


def test_root_serves_the_exported_index_when_present(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(
        "<!doctype html><html><body>FinAlly shell</body></html>", encoding="utf-8"
    )
    settings = Settings(
        db_path=tmp_path / "db" / "finally.db",
        static_dir=static_dir,
        initial_cash=10_000.0,
        snapshot_interval=3600.0,
    )
    app = build_app(settings, source=FakeMarketSource())

    with TestClient(app) as client:
        root = client.get("/")
        health = client.get("/api/health")

    assert root.status_code == 200
    assert "FinAlly shell" in root.text
    assert root.headers["content-type"].startswith("text/html")
    assert health.status_code == 200


def test_api_routes_win_over_the_static_mount(tmp_path: Path) -> None:
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html>shell</html>", encoding="utf-8")
    settings = Settings(
        db_path=tmp_path / "db" / "finally.db",
        static_dir=static_dir,
        initial_cash=10_000.0,
        snapshot_interval=3600.0,
    )
    app = build_app(settings, source=FakeMarketSource())

    with TestClient(app) as client:
        body = client.get("/api/portfolio").json()

    assert body["cash_balance"] == 10_000.0
