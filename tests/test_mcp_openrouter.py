import os

import pytest

from app.agents.providers.mcp import MCPAgentChatProvider, MCPAgentProviderError
from app.config import Settings


def _base_settings(**overrides) -> Settings:
    payload = {
        "openrouter_key": "sk-or-example",
        "openrouter_base_url": "https://router.example/api",
        "openrouter_default_model": "openrouter/example",
    }
    payload.update(overrides)
    return Settings.model_construct(**payload)


def test_configure_openrouter_environment_sets_defaults(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_DEFAULT_MODEL", raising=False)

    settings = _base_settings()

    MCPAgentChatProvider._configure_openrouter_environment(settings)

    assert os.environ["OPENAI_API_KEY"] == "sk-or-example"
    assert os.environ["OPENAI_BASE_URL"] == "https://router.example/api"
    assert os.environ["OPENAI_DEFAULT_MODEL"] == "openrouter/example"


def test_configure_openrouter_environment_prefers_agent_model(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_DEFAULT_MODEL", raising=False)

    settings = _base_settings(mcp_agent_default_model="openrouter/custom")

    MCPAgentChatProvider._configure_openrouter_environment(settings)

    assert os.environ["OPENAI_DEFAULT_MODEL"] == "openrouter/custom"


def test_configure_openrouter_environment_requires_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = _base_settings(openrouter_key=None)

    with pytest.raises(MCPAgentProviderError):
        MCPAgentChatProvider._configure_openrouter_environment(settings)


def test_settings_default_llm_is_openrouter(monkeypatch):
    monkeypatch.delenv("MCP_AGENT_LLM", raising=False)

    settings = Settings()

    assert settings.mcp_agent_llm_provider == "openrouter"
