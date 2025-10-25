"""Utilities for describing the runtime configuration of the service."""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping

from .agents.manager import ProviderManager
from .config import Settings, get_settings
from .dependencies import get_chat_memory, get_provider_manager


_MIN_MCP_SERVERS: int = 1


def build_runtime_report(
    *,
    settings: Settings | None = None,
    manager: ProviderManager | None = None,
    memory_backend: Any | None = None,
) -> Mapping[str, Any]:
    """Return a structured snapshot describing the active runtime configuration."""

    resolved_settings = settings or get_settings()
    resolved_manager = manager or get_provider_manager()
    resolved_memory = memory_backend or get_chat_memory()

    available_providers = sorted(resolved_manager.list_providers())
    default_provider = resolved_manager.default

    llm_provider = resolved_settings.mcp_agent_llm_provider
    uses_openrouter = llm_provider == "openrouter"
    mcp_servers = list(resolved_settings.mcp_agent_servers)
    servers_active = len(mcp_servers) >= _MIN_MCP_SERVERS

    effective_model = resolved_settings.mcp_agent_default_model
    if effective_model is None and uses_openrouter:
        effective_model = resolved_settings.openrouter_default_model

    provider_section: MutableMapping[str, Any] = {
        "default": default_provider,
        "available": available_providers,
        "llm_provider": llm_provider,
        "uses_openrouter": uses_openrouter,
        "default_model": effective_model,
        "openrouter_base_url": (
            resolved_settings.openrouter_base_url if uses_openrouter else None
        ),
        "mcp_servers_configured": bool(mcp_servers),
        "mcp_servers_active": servers_active,
        "mcp_server_names": mcp_servers,
        "mcp_servers_required_minimum": _MIN_MCP_SERVERS,
    }

    memory_section: MutableMapping[str, Any] = {
        "backend": resolved_memory.__class__.__name__,
        "default_limit": resolved_settings.memory_default,
        "max_limit": resolved_settings.memory_max,
    }

    return {
        "provider": provider_section,
        "memory": memory_section,
    }


__all__ = ["build_runtime_report"]
