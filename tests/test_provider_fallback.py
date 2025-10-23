"""Tests for provider fallback behaviour in the sessions API."""

import asyncio
from typing import Sequence

from httpx import ASGITransport, AsyncClient

from app.agents.manager import (
    ChatMessage as ProviderChatMessage,
    ChatResponse,
    ProviderError,
    ProviderManager,
)
from app.dependencies import (
    get_chat_memory,
    get_metrics_collector,
    get_provider_manager,
    get_rate_limit_bypass_store,
    get_rate_limiter,
    get_session_store,
    set_chat_memory,
    set_metrics_collector,
    set_provider_manager,
    set_rate_limit_bypass_store,
    set_rate_limiter,
    set_session_store,
)
from app.main import create_app
from app.memory import InMemoryChatMemory
from app.observability import MetricsCollector
from app.rate_limiter import InMemoryRateLimiter, RateLimitBypassStore
from app.sessions import InMemorySessionStore


class _FailingProvider:
    """Provider stub that always raises a ``ProviderError``."""

    name = "primary"

    def __init__(self, message: str = "primary failed") -> None:
        self.message = message
        self.calls = 0

    async def chat(self, messages: Sequence[ProviderChatMessage], **options):  # type: ignore[override]
        self.calls += 1
        raise ProviderError(self.message)


class _SuccessfulProvider:
    """Provider stub that returns a fixed assistant message."""

    name = "secondary"

    def __init__(self, content: str = "fallback response") -> None:
        self.content = content
        self.calls = 0

    async def chat(self, messages: Sequence[ProviderChatMessage], **options):  # type: ignore[override]
        self.calls += 1
        return ChatResponse(
            message=ProviderChatMessage(role="assistant", content=self.content),
            raw={"provider": self.name},
            usage={"calls": self.calls},
        )


def test_messages_endpoint_uses_fallback_provider_when_primary_fails() -> None:
    async def _run() -> None:
        original_store = get_session_store()
        original_memory = get_chat_memory()
        original_manager = get_provider_manager()
        original_limiter = get_rate_limiter()
        original_bypass = get_rate_limit_bypass_store()
        original_metrics = get_metrics_collector()

        store = InMemorySessionStore()
        memory = InMemoryChatMemory(default_limit=5)
        manager = ProviderManager()

        primary = _FailingProvider()
        fallback = _SuccessfulProvider(content="from fallback")
        manager.register(primary)
        manager.register(fallback)

        session = await store.create_session(provider="primary", fallback_provider="secondary")

        try:
            set_session_store(store)
            set_chat_memory(memory)
            set_provider_manager(manager)
            set_rate_limiter(InMemoryRateLimiter(rate=100.0, capacity=100))
            set_rate_limit_bypass_store(RateLimitBypassStore())
            set_metrics_collector(MetricsCollector())

            app = create_app()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post(
                    f"/sessions/{session.id}/messages",
                    json={"content": "hello"},
                )

            assert response.status_code == 200
            payload = response.json()
            assert payload["provider"] == "secondary"
            assert payload["provider_source"] == "fallback"
            assert payload["history"][0]["content"] == "hello"
            assert payload["history"][1]["content"] == "from fallback"
            assert primary.calls == 1
            assert fallback.calls == 1
        finally:
            set_session_store(original_store)
            set_chat_memory(original_memory)
            set_provider_manager(original_manager)
            set_rate_limiter(original_limiter)
            set_rate_limit_bypass_store(original_bypass)
            set_metrics_collector(original_metrics)

    asyncio.run(_run())


def test_messages_endpoint_returns_error_when_fallback_unavailable() -> None:
    async def _run() -> None:
        original_store = get_session_store()
        original_memory = get_chat_memory()
        original_manager = get_provider_manager()
        original_limiter = get_rate_limiter()
        original_bypass = get_rate_limit_bypass_store()
        original_metrics = get_metrics_collector()

        store = InMemorySessionStore()
        memory = InMemoryChatMemory(default_limit=5)
        manager = ProviderManager()

        primary = _FailingProvider(message="primary boom")
        manager.register(primary)

        session = await store.create_session(provider="primary", fallback_provider="missing")

        try:
            set_session_store(store)
            set_chat_memory(memory)
            set_provider_manager(manager)
            set_rate_limiter(InMemoryRateLimiter(rate=100.0, capacity=100))
            set_rate_limit_bypass_store(RateLimitBypassStore())
            set_metrics_collector(MetricsCollector())

            app = create_app()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post(
                    f"/sessions/{session.id}/messages",
                    json={"content": "hi"},
                )

            assert response.status_code == 502
            payload = response.json()
            assert payload["error"]["code"] == "provider_error"
            assert (
                payload["error"]["message"]
                == "Primary provider failed and fallback provider is not available."
            )
            assert primary.calls == 1
        finally:
            set_session_store(original_store)
            set_chat_memory(original_memory)
            set_provider_manager(original_manager)
            set_rate_limiter(original_limiter)
            set_rate_limit_bypass_store(original_bypass)
            set_metrics_collector(original_metrics)

    asyncio.run(_run())
