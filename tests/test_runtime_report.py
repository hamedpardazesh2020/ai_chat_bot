from __future__ import annotations

from app.agents.manager import ProviderManager
from app.agents.providers.unconfigured import UnconfiguredChatProvider
from app.config import Settings
from app.memory import InMemoryChatMemory
from app.runtime import build_runtime_report


def test_build_runtime_report_basic_snapshot() -> None:
    settings = Settings(
        mcp_agent_servers=[],
        mcp_agent_llm_provider="openrouter",
        openrouter_default_model="openrouter/auto",
        memory_default=12,
        memory_max=24,
    )
    manager = ProviderManager()
    provider = UnconfiguredChatProvider()
    manager.register(provider)
    manager.set_default(provider.name)
    memory = InMemoryChatMemory(default_limit=settings.memory_default, max_limit=settings.memory_max)

    report = build_runtime_report(settings=settings, manager=manager, memory_backend=memory)

    provider_info = report["provider"]
    memory_info = report["memory"]

    assert provider_info["default"] == provider.name
    assert provider_info["uses_openrouter"] is True
    assert provider_info["mcp_servers_configured"] is False
    assert provider_info["mcp_servers_active"] is False
    assert provider_info["default_model"] == "openrouter/auto"
    assert provider_info["openrouter_base_url"] == settings.openrouter_base_url

    assert memory_info["backend"] == "InMemoryChatMemory"
    assert memory_info["default_limit"] == 12
    assert memory_info["max_limit"] == 24


def test_build_runtime_report_with_mcp_servers() -> None:
    settings = Settings(
        mcp_agent_servers=["alpha", "beta"],
        mcp_agent_llm_provider="openrouter",
        mcp_agent_default_model="openrouter/mistral-large",
        memory_default=10,
        memory_max=20,
    )
    manager = ProviderManager()
    provider = UnconfiguredChatProvider()
    manager.register(provider)
    manager.set_default(provider.name)
    memory = InMemoryChatMemory(default_limit=settings.memory_default, max_limit=settings.memory_max)

    report = build_runtime_report(settings=settings, manager=manager, memory_backend=memory)

    provider_info = report["provider"]

    assert provider_info["mcp_servers_configured"] is True
    assert provider_info["mcp_servers_active"] is True
    assert provider_info["mcp_server_names"] == ["alpha", "beta"]
    assert provider_info["default_model"] == "openrouter/mistral-large"
