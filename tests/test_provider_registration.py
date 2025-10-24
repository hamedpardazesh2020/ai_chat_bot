"""Tests covering automatic provider registration during app start-up."""

from __future__ import annotations

from app.agents.manager import ProviderManager
from app.config import get_settings
from app.dependencies import get_provider_manager, set_provider_manager
from app.main import create_app


def _reset_settings_cache() -> None:
    """Utility to reset the cached settings between tests."""

    get_settings.cache_clear()


def test_create_app_registers_openrouter_provider(monkeypatch):
    """Providing an OpenRouter key should register the provider by default."""

    monkeypatch.setenv("OPENROUTER_KEY", "sk-or-example")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MCP_AGENT_SERVERS", raising=False)

    _reset_settings_cache()

    original_manager = get_provider_manager()
    manager = ProviderManager()
    set_provider_manager(manager)

    try:
        create_app()
        available = manager.available()
        assert "openrouter" in available
        assert manager.default == "openrouter"
    finally:
        set_provider_manager(original_manager)
        _reset_settings_cache()


def test_create_app_registers_openai_provider(monkeypatch):
    """Providing an OpenAI key should register the OpenAI provider."""

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("OPENROUTER_KEY", raising=False)
    monkeypatch.delenv("MCP_AGENT_SERVERS", raising=False)

    _reset_settings_cache()

    original_manager = get_provider_manager()
    manager = ProviderManager()
    set_provider_manager(manager)

    try:
        create_app()
        available = manager.available()
        assert "openai" in available
        assert manager.default == "openai"
    finally:
        set_provider_manager(original_manager)
        _reset_settings_cache()
