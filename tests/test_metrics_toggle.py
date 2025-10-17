"""Tests covering optional metrics instrumentation configuration."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app import dependencies
from app.config import Settings
from app.main import create_app
from app.observability import MetricsCollector


def _override_settings(monkeypatch, **overrides) -> None:
    """Patch ``get_settings`` to return a customised ``Settings`` instance."""

    settings = Settings(**overrides)
    monkeypatch.setattr("app.main.get_settings", lambda: settings)


def test_metrics_enabled_records_requests(monkeypatch) -> None:
    """When metrics are enabled the middleware should record request counts."""

    dependencies.set_metrics_collector(MetricsCollector())
    _override_settings(monkeypatch, metrics_enabled=True)

    app = create_app()
    client = TestClient(app)

    before = asyncio.run(dependencies.get_metrics_collector().snapshot())
    response = client.get("/")
    assert response.status_code == 200
    metrics_response = client.get("/metrics")
    assert metrics_response.status_code == 200

    after = asyncio.run(dependencies.get_metrics_collector().snapshot())
    assert after["requests_total"] > before["requests_total"]
    assert "/metrics" in {route.path for route in app.router.routes}


def test_metrics_disabled_hides_route_and_middleware(monkeypatch) -> None:
    """Disabling metrics removes the route and stops counters from changing."""

    dependencies.set_metrics_collector(MetricsCollector())
    _override_settings(monkeypatch, metrics_enabled=False)

    app = create_app()
    client = TestClient(app)

    assert "/metrics" not in {route.path for route in app.router.routes}

    missing = client.get("/metrics")
    assert missing.status_code == 404

    before = asyncio.run(dependencies.get_metrics_collector().snapshot())
    health = client.get("/health")
    assert health.status_code == 200
    client.get("/")
    after = asyncio.run(dependencies.get_metrics_collector().snapshot())
    assert after["requests_total"] == before["requests_total"]
