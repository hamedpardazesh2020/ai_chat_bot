"""Tests covering optional metrics instrumentation configuration."""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("OPENROUTER_KEY", "sk-or-test")

from fastapi.testclient import TestClient

from app import dependencies
from app.agents.manager import (
    ChatMessage as ProviderChatMessage,
    ChatResponse,
    ProviderManager,
)
from app.config import Settings
from app.main import create_app
from app.observability import MetricsCollector


class _SilentProvider:
    name = "mcp-agent"

    async def chat(self, messages, **options):  # type: ignore[override]
        return ChatResponse(
            message=ProviderChatMessage(role="assistant", content="placeholder"),
            raw={},
            usage={},
        )


def _override_settings(monkeypatch, **overrides) -> None:
    """Patch ``get_settings`` to return a customised ``Settings`` instance."""

    settings = Settings(**overrides)
    monkeypatch.setattr("app.main.get_settings", lambda: settings)


def test_metrics_enabled_records_requests(monkeypatch) -> None:
    """When metrics are enabled the middleware should record request counts."""

    original_manager = dependencies.get_provider_manager()
    original_metrics = dependencies.get_metrics_collector()

    manager = ProviderManager()
    provider = _SilentProvider()
    manager.register(provider)
    manager.set_default(provider.name)

    dependencies.set_provider_manager(manager)
    dependencies.set_metrics_collector(MetricsCollector())
    _override_settings(monkeypatch, metrics_enabled=True)

    try:
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
    finally:
        dependencies.set_provider_manager(original_manager)
        dependencies.set_metrics_collector(original_metrics)


def test_metrics_disabled_hides_route_and_middleware(monkeypatch) -> None:
    """Disabling metrics removes the route and stops counters from changing."""

    original_manager = dependencies.get_provider_manager()
    original_metrics = dependencies.get_metrics_collector()

    manager = ProviderManager()
    provider = _SilentProvider()
    manager.register(provider)
    manager.set_default(provider.name)

    dependencies.set_provider_manager(manager)
    dependencies.set_metrics_collector(MetricsCollector())
    _override_settings(monkeypatch, metrics_enabled=False)

    try:
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
    finally:
        dependencies.set_provider_manager(original_manager)
        dependencies.set_metrics_collector(original_metrics)

