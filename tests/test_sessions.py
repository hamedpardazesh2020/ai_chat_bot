import asyncio
from uuid import UUID, uuid4

import pytest

from httpx import AsyncClient

from app.sessions import (
    InMemorySessionStore,
    SessionAlreadyExistsError,
    SessionNotFoundError,
)
from app.dependencies import (
    get_chat_memory,
    get_metrics_collector,
    get_rate_limit_bypass_store,
    get_rate_limiter,
    get_session_store,
    set_chat_memory,
    set_metrics_collector,
    set_rate_limit_bypass_store,
    set_rate_limiter,
    set_session_store,
)
from app.main import create_app
from app.memory import ChatMessage as MemoryChatMessage, InMemoryChatMemory
from app.observability import MetricsCollector
from app.rate_limiter import InMemoryRateLimiter, RateLimitBypassStore


def test_create_and_get_session_uses_defaults():
    async def _run() -> None:
        store = InMemorySessionStore(default_memory_limit=7)

        session = await store.create_session(provider="openai")

        assert session.provider == "openai"
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
        original_limiter = get_rate_limiter()
        original_bypass = get_rate_limit_bypass_store()
        original_metrics = get_metrics_collector()

        store = InMemorySessionStore()
        memory = InMemoryChatMemory(default_limit=5)
        limiter = InMemoryRateLimiter(rate=1000, capacity=1000)
        bypass = RateLimitBypassStore()
        metrics = MetricsCollector()

        set_session_store(store)
        set_chat_memory(memory)
        set_rate_limiter(limiter)
        set_rate_limit_bypass_store(bypass)
        set_metrics_collector(metrics)

        app = create_app()

        try:
            async with AsyncClient(app=app, base_url="http://testserver") as client:
                response = await client.post(
                    "/sessions",
                    json={"provider": "openai", "metadata": {"topic": "demo"}},
                )
                assert response.status_code == 201
                payload = response.json()
                session_id = UUID(payload["id"])
                assert payload["provider"] == "openai"
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
            set_rate_limiter(original_limiter)
            set_rate_limit_bypass_store(original_bypass)
            set_metrics_collector(original_metrics)

    asyncio.run(_run())


def test_missing_message_content_returns_readable_validation_error() -> None:
    async def _run() -> None:
        original_store = get_session_store()
        original_memory = get_chat_memory()
        original_limiter = get_rate_limiter()
        original_bypass = get_rate_limit_bypass_store()
        original_metrics = get_metrics_collector()

        store = InMemorySessionStore()
        memory = InMemoryChatMemory(default_limit=5)
        limiter = InMemoryRateLimiter(rate=1000, capacity=1000)
        bypass = RateLimitBypassStore()
        metrics = MetricsCollector()

        set_session_store(store)
        set_chat_memory(memory)
        set_rate_limiter(limiter)
        set_rate_limit_bypass_store(bypass)
        set_metrics_collector(metrics)

        app = create_app()

        try:
            async with AsyncClient(app=app, base_url="http://testserver") as client:
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
                    == "Request validation failed: content: field required"
                )
        finally:
            set_session_store(original_store)
            set_chat_memory(original_memory)
            set_rate_limiter(original_limiter)
            set_rate_limit_bypass_store(original_bypass)
            set_metrics_collector(original_metrics)

    asyncio.run(_run())
