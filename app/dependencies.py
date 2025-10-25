"""Dependency providers for FastAPI route handlers."""
from __future__ import annotations

from .agents.manager import ProviderManager
from .config import get_settings
from .history_store import HistoryStore, history_from_settings
from .memory import ChatMemory, memory_from_settings
from .observability import MetricsCollector
from .rate_limiter import (
    RateLimitBypassStore,
    RateLimiter,
    rate_limiter_from_settings,
)
from .sessions import InMemorySessionStore

_settings = get_settings()
_session_store = InMemorySessionStore(default_memory_limit=_settings.memory_default)
_chat_memory = memory_from_settings(_settings)
_history_store = history_from_settings(_settings)
_provider_manager = ProviderManager()
_rate_limiter = rate_limiter_from_settings(_settings)
_rate_limit_bypass_store = RateLimitBypassStore()
_metrics_collector = MetricsCollector()


def get_session_store() -> InMemorySessionStore:
    """Return the shared session store instance."""

    return _session_store


def get_chat_memory() -> ChatMemory:
    """Return the configured chat memory backend."""

    return _chat_memory


def get_history_store() -> HistoryStore:
    """Return the configured history store backend."""

    return _history_store


def get_provider_manager() -> ProviderManager:
    """Return the global provider manager registry."""

    return _provider_manager


def get_rate_limiter() -> RateLimiter:
    """Return the shared rate limiter instance."""

    return _rate_limiter


def get_rate_limit_bypass_store() -> RateLimitBypassStore:
    """Return the shared rate limit bypass store."""

    return _rate_limit_bypass_store


def get_metrics_collector() -> MetricsCollector:
    """Return the shared metrics collector."""

    return _metrics_collector


def set_session_store(store: InMemorySessionStore) -> None:
    """Override the global session store (primarily for tests)."""

    global _session_store
    _session_store = store


def set_chat_memory(memory: ChatMemory) -> None:
    """Override the global chat memory backend (primarily for tests)."""

    global _chat_memory
    _chat_memory = memory


def set_history_store(store: HistoryStore) -> None:
    """Override the global history store (primarily for tests)."""

    global _history_store
    _history_store = store


def set_provider_manager(manager: ProviderManager) -> None:
    """Override the provider manager instance (primarily for tests)."""

    global _provider_manager
    _provider_manager = manager


def set_rate_limiter(limiter: RateLimiter) -> None:
    """Override the rate limiter instance (primarily for tests)."""

    global _rate_limiter
    _rate_limiter = limiter


def set_rate_limit_bypass_store(store: RateLimitBypassStore) -> None:
    """Override the rate limit bypass store (primarily for tests)."""

    global _rate_limit_bypass_store
    _rate_limit_bypass_store = store


def set_metrics_collector(collector: MetricsCollector) -> None:
    """Override the metrics collector (primarily for tests)."""

    global _metrics_collector
    _metrics_collector = collector


__all__ = [
    "ChatMemory",
    "HistoryStore",
    "ProviderManager",
    "get_chat_memory",
    "get_history_store",
    "get_rate_limit_bypass_store",
    "get_metrics_collector",
    "get_provider_manager",
    "get_rate_limiter",
    "get_session_store",
    "set_chat_memory",
    "set_history_store",
    "set_metrics_collector",
    "set_rate_limit_bypass_store",
    "set_provider_manager",
    "set_rate_limiter",
    "set_session_store",
]
