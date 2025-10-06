"""Session conversation history backends.

This module provides both in-memory and Redis-backed implementations for storing
recent chat exchanges per session. A lightweight protocol is exposed so the
rest of the application can remain agnostic to the actual persistence
mechanism. The Redis backend mirrors the interface of the in-memory version and
automatically enforces message limits while allowing per-session overrides.
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import (
    TYPE_CHECKING,
    AsyncIterator,
    Deque,
    Dict,
    Iterable,
    List,
    Optional,
    Protocol,
)
from uuid import UUID

try:  # pragma: no cover - optional dependency
    from redis.asyncio import Redis as AsyncRedis
    from redis.asyncio import from_url as redis_from_url
except Exception:  # pragma: no cover - redis may not be installed for tests
    AsyncRedis = None  # type: ignore
    redis_from_url = None  # type: ignore

if TYPE_CHECKING:  # pragma: no cover - for type checkers only
    from .config import Settings


class MemoryError(Exception):
    """Base class for memory related failures."""


class InvalidMemoryLimitError(MemoryError):
    """Raised when a memory limit outside the allowed bounds is requested."""


@dataclass(slots=True)
class ChatMessage:
    """Representation of a single message stored in session memory."""

    role: str
    content: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, str]:
        """Serialise the message to a JSON-compatible dictionary."""

        return {
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, str]) -> "ChatMessage":
        """Recreate a ``ChatMessage`` from its serialised dictionary form."""

        created_at_raw = payload.get("created_at")
        created_at = (
            datetime.fromisoformat(created_at_raw)
            if created_at_raw is not None
            else datetime.now(timezone.utc)
        )
        return cls(
            role=payload.get("role", "unknown"),
            content=payload.get("content", ""),
            created_at=created_at,
        )


class ChatMemory(Protocol):
    """Protocol describing the behaviour of chat memory backends."""

    async def append(
        self, session_id: UUID, message: ChatMessage, *, limit_override: Optional[int] = None
    ) -> None:
        """Persist a new message for the given session."""

    async def get(self, session_id: UUID) -> List[ChatMessage]:
        """Return the stored messages for the session."""

    async def iter(self, session_id: UUID) -> AsyncIterator[ChatMessage]:
        """Yield messages for the session in chronological order."""

    async def clear(self, session_id: UUID) -> None:
        """Remove all stored messages for the session."""


class InMemoryChatMemory:
    """Maintain recent conversation history for sessions using an in-memory deque."""

    def __init__(self, *, default_limit: int = 10, max_limit: Optional[int] = None) -> None:
        if default_limit < 1:
            raise ValueError("default_limit must be at least 1")
        if max_limit is not None and max_limit < 1:
            raise ValueError("max_limit must be at least 1 when provided")
        if max_limit is not None and default_limit > max_limit:
            raise ValueError("default_limit cannot exceed max_limit")

        self._default_limit = default_limit
        self._max_limit = max_limit
        self._messages: Dict[UUID, Deque[ChatMessage]] = {}
        self._limits: Dict[UUID, int] = {}
        self._lock = asyncio.Lock()

    async def append(
        self,
        session_id: UUID,
        message: ChatMessage,
        *,
        limit_override: Optional[int] = None,
    ) -> None:
        """Append a message to a session's history, trimming as needed."""

        limit = self._resolve_limit(limit_override)
        async with self._lock:
            history = self._messages.get(session_id)
            current_limit = self._limits.get(session_id)

            if history is None or current_limit != limit:
                history = self._rebuild_history(history, limit)
                self._messages[session_id] = history
                self._limits[session_id] = limit

            history.append(message)

    async def get(self, session_id: UUID) -> List[ChatMessage]:
        """Return a copy of the stored messages for the session."""

        async with self._lock:
            history = self._messages.get(session_id)
            if history is None:
                return []
            return list(history)

    async def iter(self, session_id: UUID) -> AsyncIterator[ChatMessage]:
        """Yield the messages for the session in chronological order."""

        for message in await self.get(session_id):
            yield message

    async def clear(self, session_id: UUID) -> None:
        """Remove all stored messages for the session."""

        async with self._lock:
            self._messages.pop(session_id, None)
            self._limits.pop(session_id, None)

    def _resolve_limit(self, limit_override: Optional[int]) -> int:
        """Return the effective memory limit for a session interaction."""

        limit = limit_override if limit_override is not None else self._default_limit
        if limit < 1:
            raise InvalidMemoryLimitError("Memory limit must be at least 1 message")
        if self._max_limit is not None and limit > self._max_limit:
            raise InvalidMemoryLimitError(
                f"Memory limit {limit} exceeds maximum allowed {self._max_limit}"
            )
        return limit

    def _rebuild_history(
        self, history: Optional[Deque[ChatMessage]], limit: int
    ) -> Deque[ChatMessage]:
        """Rebuild an existing deque with a new limit if required."""

        new_history: Deque[ChatMessage] = deque(maxlen=limit)
        if history:
            # Keep the most recent messages within the new limit.
            for item in list(history)[-limit:]:
                new_history.append(item)
        return new_history


class RedisChatMemory:
    """Redis-backed chat memory with the same interface as the in-memory store."""

    def __init__(
        self,
        client: "AsyncRedis",
        *,
        default_limit: int = 10,
        max_limit: Optional[int] = None,
        namespace: str = "chat_memory",
    ) -> None:
        if AsyncRedis is None:
            raise RuntimeError("redis package is required for RedisChatMemory usage.")

        if default_limit < 1:
            raise ValueError("default_limit must be at least 1")
        if max_limit is not None and max_limit < 1:
            raise ValueError("max_limit must be at least 1 when provided")
        if max_limit is not None and default_limit > max_limit:
            raise ValueError("default_limit cannot exceed max_limit")

        self._client = client
        self._default_limit = default_limit
        self._max_limit = max_limit
        self._namespace = namespace.rstrip(":")

    async def append(
        self,
        session_id: UUID,
        message: ChatMessage,
        *,
        limit_override: Optional[int] = None,
    ) -> None:
        """Append a message to Redis and enforce the configured limit."""

        limit = await self._resolve_limit(session_id, limit_override)
        payload = json.dumps(message.to_dict())
        key = self._history_key(session_id)
        await self._client.rpush(key, payload)
        await self._client.ltrim(key, -limit, -1)

    async def get(self, session_id: UUID) -> List[ChatMessage]:
        """Retrieve the stored messages for the session."""

        data = await self._client.lrange(self._history_key(session_id), 0, -1)
        return list(self._deserialize_many(data))

    async def iter(self, session_id: UUID) -> AsyncIterator[ChatMessage]:
        """Yield the stored messages for a session in chronological order."""

        for message in await self.get(session_id):
            yield message

    async def clear(self, session_id: UUID) -> None:
        """Remove the stored messages and limit metadata for the session."""

        await self._client.delete(
            self._history_key(session_id),
            self._limit_key(session_id),
        )

    async def _resolve_limit(
        self, session_id: UUID, limit_override: Optional[int]
    ) -> int:
        """Determine the effective limit for the session and persist overrides."""

        if limit_override is not None:
            limit = self._validate_limit(limit_override)
            await self._client.set(self._limit_key(session_id), limit)
            return limit

        stored = await self._client.get(self._limit_key(session_id))
        if stored is not None:
            limit = self._validate_limit(int(stored))
        else:
            limit = self._default_limit
            await self._client.set(self._limit_key(session_id), limit)
        return limit

    def _validate_limit(self, limit: int) -> int:
        if limit < 1:
            raise InvalidMemoryLimitError("Memory limit must be at least 1 message")
        if self._max_limit is not None and limit > self._max_limit:
            raise InvalidMemoryLimitError(
                f"Memory limit {limit} exceeds maximum allowed {self._max_limit}"
            )
        return limit

    def _history_key(self, session_id: UUID) -> str:
        return f"{self._namespace}:history:{session_id}"

    def _limit_key(self, session_id: UUID) -> str:
        return f"{self._namespace}:limit:{session_id}"

    def _deserialize_many(self, rows: Iterable[str]) -> Iterable[ChatMessage]:
        for row in rows:
            if not row:
                continue
            try:
                payload = json.loads(row)
            except json.JSONDecodeError:
                payload = {}
            if isinstance(payload, dict):
                yield ChatMessage.from_dict(payload)

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        default_limit: int = 10,
        max_limit: Optional[int] = None,
        namespace: str = "chat_memory",
        **redis_kwargs: object,
    ) -> "RedisChatMemory":
        """Create a Redis-backed chat memory from a connection URL."""

        if redis_from_url is None:
            raise RuntimeError("redis package is required for RedisChatMemory usage.")

        client = redis_from_url(url, encoding="utf-8", decode_responses=True, **redis_kwargs)
        return cls(
            client,
            default_limit=default_limit,
            max_limit=max_limit,
            namespace=namespace,
        )


def create_chat_memory(
    *,
    use_redis: bool,
    default_limit: int,
    max_limit: Optional[int],
    redis_url: Optional[str] = None,
    redis_client: Optional["AsyncRedis"] = None,
) -> ChatMemory:
    """Factory returning a chat memory backend based on configuration."""

    if use_redis:
        if redis_client is None:
            if not redis_url:
                raise ValueError("redis_url must be provided when use_redis is True")
            return RedisChatMemory.from_url(
                redis_url,
                default_limit=default_limit,
                max_limit=max_limit,
            )
        return RedisChatMemory(
            redis_client,
            default_limit=default_limit,
            max_limit=max_limit,
        )

    return InMemoryChatMemory(default_limit=default_limit, max_limit=max_limit)


def memory_from_settings(
    settings: "Settings", *, redis_client: Optional["AsyncRedis"] = None
) -> ChatMemory:
    """Create a chat memory backend honouring the provided settings."""

    return create_chat_memory(
        use_redis=settings.redis_enabled,
        default_limit=settings.memory_default,
        max_limit=settings.memory_limit,
        redis_url=settings.redis_url,
        redis_client=redis_client,
    )


__all__ = [
    "ChatMemory",
    "ChatMessage",
    "InMemoryChatMemory",
    "InvalidMemoryLimitError",
    "MemoryError",
    "RedisChatMemory",
    "create_chat_memory",
    "memory_from_settings",
]
