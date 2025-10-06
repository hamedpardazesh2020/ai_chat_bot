import asyncio
from uuid import uuid4

import pytest

from app.memory import ChatMessage, InMemoryChatMemory, InvalidMemoryLimitError


def test_memory_trims_to_default_limit():
    async def _run() -> None:
        memory = InMemoryChatMemory(default_limit=3)
        session_id = uuid4()

        for index in range(5):
            await memory.append(session_id, ChatMessage(role="user", content=f"msg-{index}"))

        history = await memory.get(session_id)

        assert len(history) == 3
        assert [message.content for message in history] == ["msg-2", "msg-3", "msg-4"]

    asyncio.run(_run())


def test_memory_limit_override_resets_history_and_validates():
    async def _run() -> None:
        memory = InMemoryChatMemory(default_limit=5, max_limit=10)
        session_id = uuid4()

        for index in range(4):
            await memory.append(session_id, ChatMessage(role="user", content=f"msg-{index}"))

        await memory.append(
            session_id,
            ChatMessage(role="assistant", content="trim"),
            limit_override=2,
        )

        history = await memory.get(session_id)
        assert len(history) == 2
        assert [message.content for message in history] == ["msg-3", "trim"]

        with pytest.raises(InvalidMemoryLimitError):
            await memory.append(
                session_id,
                ChatMessage(role="user", content="bad"),
                limit_override=0,
            )

    asyncio.run(_run())
