import asyncio
from uuid import UUID, uuid4

import os

os.environ.setdefault("OPENROUTER_KEY", "sk-or-test")

import pytest

from httpx import ASGITransport, AsyncClient

from app.sessions import (
    InMemorySessionStore,
    SessionAlreadyExistsError,
    SessionNotFoundError,
)
from app.dependencies import (
    get_chat_memory,
    get_history_store,
    get_metrics_collector,
    get_provider_manager,
    get_rate_limit_bypass_store,
    get_rate_limiter,
    get_session_store,
    set_chat_memory,
    set_history_store,
    set_metrics_collector,
    set_provider_manager,
    set_rate_limit_bypass_store,
    set_rate_limiter,
    set_session_store,
)
from app.main import create_app
from app.memory import ChatMessage as MemoryChatMessage, InMemoryChatMemory
from app.observability import MetricsCollector
from app.rate_limiter import InMemoryRateLimiter, RateLimitBypassStore
from app.agents.manager import (
    ChatMessage as ProviderChatMessage,
    ChatResponse,
    ProviderManager,
)
from app.history_store import NoOpHistoryStore


class _SilentProvider:
    name = "mcp-agent"

    async def chat(self, messages, **options):  # type: ignore[override]
        return ChatResponse(
            message=ProviderChatMessage(role="assistant", content="placeholder"),
            raw={},
            usage={},
        )


def test_create_and_get_session_uses_defaults():
    async def _run() -> None:
        store = InMemorySessionStore(default_memory_limit=7)

        session = await store.create_session()

        assert session.provider is None
        assert session.memory_limit == 7

        fetched = await store.get_session(session.id)
        assert fetched is session

    asyncio.run(_run())


def test_delete_session_removes_entry_and_blocks_duplicates():
    async def _run() -> None:
        store = InMemorySessionStore()
        session_id = uuid4()

        await store.create_session(session_id=session_id)

        with pytest.raises(SessionAlreadyExistsError):
            await store.create_session(session_id=session_id)

        await store.delete_session(session_id)

        with pytest.raises(SessionNotFoundError):
            await store.get_session(session_id)

        with pytest.raises(SessionNotFoundError):
            await store.delete_session(session_id)

    asyncio.run(_run())


def test_session_lifecycle_endpoints_manage_store_and_memory() -> None:
    async def _run() -> None:
        original_store = get_session_store()
        original_memory = get_chat_memory()
        original_history = get_history_store()
        original_limiter = get_rate_limiter()
        original_bypass = get_rate_limit_bypass_store()
        original_metrics = get_metrics_collector()
        original_manager = get_provider_manager()

        store = InMemorySessionStore()
        memory = InMemoryChatMemory(default_limit=5)
        history = NoOpHistoryStore()
        limiter = InMemoryRateLimiter(rate=1000, capacity=1000)
        bypass = RateLimitBypassStore()
        metrics = MetricsCollector()
        manager = ProviderManager()
        provider = _SilentProvider()
        manager.register(provider)
        manager.set_default(provider.name)

        set_session_store(store)
        set_chat_memory(memory)
        set_history_store(history)
        set_rate_limiter(limiter)
        set_rate_limit_bypass_store(bypass)
        set_metrics_collector(metrics)
        set_provider_manager(manager)

        app = create_app()
        transport = ASGITransport(app=app)

        try:
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post(
                    "/sessions",
                    json={"metadata": {"topic": "demo"}},
                )
                assert response.status_code == 201
                payload = response.json()
                session_id = UUID(payload["id"])
                assert payload["metadata"] == {"topic": "demo"}

                await memory.append(
                    session_id, MemoryChatMessage(role="user", content="hello")
                )

                delete_response = await client.delete(f"/sessions/{session_id}")
                assert delete_response.status_code == 204

                assert await memory.get(session_id) == []
                with pytest.raises(SessionNotFoundError):
                    await store.get_session(session_id)
        finally:
            set_session_store(original_store)
            set_chat_memory(original_memory)
            set_history_store(original_history)
            set_provider_manager(original_manager)
            set_rate_limiter(original_limiter)
            set_rate_limit_bypass_store(original_bypass)
            set_metrics_collector(original_metrics)

    asyncio.run(_run())


def test_get_session_returns_metadata_and_history() -> None:
    async def _run() -> None:
        original_store = get_session_store()
        original_memory = get_chat_memory()
        original_history = get_history_store()
        original_limiter = get_rate_limiter()
        original_bypass = get_rate_limit_bypass_store()
        original_metrics = get_metrics_collector()
        original_manager = get_provider_manager()

        store = InMemorySessionStore()
        memory = InMemoryChatMemory(default_limit=5)
        history = NoOpHistoryStore()
        limiter = InMemoryRateLimiter(rate=1000, capacity=1000)
        bypass = RateLimitBypassStore()
        metrics = MetricsCollector()
        manager = ProviderManager()
        provider = _SilentProvider()
        manager.register(provider)
        manager.set_default(provider.name)

        set_session_store(store)
        set_chat_memory(memory)
        set_history_store(history)
        set_rate_limiter(limiter)
        set_rate_limit_bypass_store(bypass)
        set_metrics_collector(metrics)
        set_provider_manager(manager)

        app = create_app()
        transport = ASGITransport(app=app)

        try:
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                session_response = await client.post("/sessions", json={})
                session_response.raise_for_status()
                session_id = UUID(session_response.json()["id"])

                await memory.append(session_id, MemoryChatMessage(role="user", content="سلام"))
                await memory.append(
                    session_id, MemoryChatMessage(role="assistant", content="درود")
                )

                response = await client.get(f"/sessions/{session_id}")
                assert response.status_code == 200
                payload = response.json()
                assert payload["id"] == str(session_id)
                assert payload["metadata"] == {}
                history_payload = payload["history"]
                assert len(history_payload) >= 2
                assert history_payload[-2]["role"] == "user"
                assert history_payload[-2]["content"] == "سلام"
                assert history_payload[-1]["role"] == "assistant"
                assert history_payload[-1]["content"] == "درود"

                missing_response = await client.get(f"/sessions/{uuid4()}")
                assert missing_response.status_code == 404
        finally:
            set_session_store(original_store)
            set_chat_memory(original_memory)
            set_history_store(original_history)
            set_provider_manager(original_manager)
            set_rate_limiter(original_limiter)
            set_rate_limit_bypass_store(original_bypass)
            set_metrics_collector(original_metrics)

    asyncio.run(_run())


def test_missing_message_content_returns_readable_validation_error() -> None:
    async def _run() -> None:
        original_store = get_session_store()
        original_memory = get_chat_memory()
        original_history = get_history_store()
        original_limiter = get_rate_limiter()
        original_bypass = get_rate_limit_bypass_store()
        original_metrics = get_metrics_collector()
        original_manager = get_provider_manager()

        store = InMemorySessionStore()
        memory = InMemoryChatMemory(default_limit=5)
        history = NoOpHistoryStore()
        limiter = InMemoryRateLimiter(rate=1000, capacity=1000)
        bypass = RateLimitBypassStore()
        metrics = MetricsCollector()
        manager = ProviderManager()
        provider = _SilentProvider()
        manager.register(provider)
        manager.set_default(provider.name)

        set_session_store(store)
        set_chat_memory(memory)
        set_history_store(history)
        set_rate_limiter(limiter)
        set_rate_limit_bypass_store(bypass)
        set_metrics_collector(metrics)
        set_provider_manager(manager)

        app = create_app()
        transport = ASGITransport(app=app)

        try:
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                session_response = await client.post("/sessions", json={})
                session_response.raise_for_status()
                session_id = session_response.json()["id"]

                response = await client.post(
                    f"/sessions/{session_id}/messages",
                    json={"role": "user"},
                )

                assert response.status_code == 422
                payload = response.json()
                assert payload["error"]["code"] == "validation_error"
                assert (
                    payload["error"]["message"]
                    == "Request validation failed: content: Field required"
                )
        finally:
            set_session_store(original_store)
            set_chat_memory(original_memory)
            set_history_store(original_history)
            set_provider_manager(original_manager)
            set_rate_limiter(original_limiter)
            set_rate_limit_bypass_store(original_bypass)
            set_metrics_collector(original_metrics)

    asyncio.run(_run())

