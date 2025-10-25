"""Tests covering automatic provider registration during app start-up."""

from __future__ import annotations

import os

os.environ.setdefault("OPENROUTER_KEY", "sk-or-test")

import pytest

from app.agents.manager import ProviderManager
from app.config import get_settings
from app.dependencies import get_provider_manager, set_provider_manager
from app.main import create_app


def _reset_settings_cache() -> None:
    """Utility to reset the cached settings between tests."""

    get_settings.cache_clear()


def test_create_app_registers_mcp_agent_provider_by_default(monkeypatch):
    """Supplying OpenRouter credentials should register the MCP agent provider."""

    monkeypatch.setenv("OPENROUTER_KEY", "sk-or-example")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MCP_AGENT_SERVERS", raising=False)
    monkeypatch.delenv("MCP_AGENT_LLM", raising=False)

    _reset_settings_cache()

    original_manager = get_provider_manager()
    manager = ProviderManager()
    set_provider_manager(manager)

    try:
        create_app()
        available = manager.available()
        assert set(available) == {"mcp-agent"}
        assert manager.default == "mcp-agent"
    finally:
        set_provider_manager(original_manager)
        _reset_settings_cache()


def test_create_app_supports_openai_llm_fallback(monkeypatch):
    """When configured the MCP agent should use OpenAI as its LLM backend."""

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("MCP_AGENT_LLM", "openai")
    monkeypatch.delenv("OPENROUTER_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("MCP_AGENT_SERVERS", raising=False)

    _reset_settings_cache()

    original_manager = get_provider_manager()
    manager = ProviderManager()
    set_provider_manager(manager)

    try:
        create_app()
        available = manager.available()
        assert set(available) == {"mcp-agent"}
        assert manager.default == "mcp-agent"
    finally:
        set_provider_manager(original_manager)
        _reset_settings_cache()


def test_create_app_registers_unconfigured_provider_when_no_credentials(monkeypatch):
    """A fallback provider should register when no external providers are configured."""

    monkeypatch.delenv("OPENROUTER_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MCP_AGENT_SERVERS", raising=False)

    _reset_settings_cache()

    original_manager = get_provider_manager()
    manager = ProviderManager()
    set_provider_manager(manager)

    try:
        create_app()
        available = manager.available()
        assert set(available) == {"unconfigured"}
        assert manager.default == "unconfigured"
    finally:
        set_provider_manager(original_manager)
        _reset_settings_cache()


def test_create_app_accepts_openrouter_api_key_alias(monkeypatch):
    """The service should honour OPENROUTER_API_KEY as an alias for OPENROUTER_KEY."""

    monkeypatch.delenv("OPENROUTER_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-alias")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MCP_AGENT_SERVERS", raising=False)

    _reset_settings_cache()

    original_manager = get_provider_manager()
    manager = ProviderManager()
    set_provider_manager(manager)

    try:
        create_app()
        available = manager.available()
        assert set(available) == {"mcp-agent"}
        assert manager.default == "mcp-agent"
    finally:
        set_provider_manager(original_manager)
        _reset_settings_cache()
