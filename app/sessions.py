"""Session domain models and in-memory storage primitives."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional
from uuid import UUID, uuid4


class SessionError(Exception):
    """Base exception for session related failures."""


class SessionNotFoundError(SessionError):
    """Raised when a session lookup is attempted for an unknown session id."""


class SessionAlreadyExistsError(SessionError):
    """Raised when attempting to create a session that already exists."""


@dataclass(slots=True)
class Session:
    """In-memory representation of a chat session."""

    id: UUID
    provider: Optional[str] = None
    fallback_provider: Optional[str] = None
    memory_limit: Optional[int] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the session into a dictionary for API responses."""

        return {
            "id": str(self.id),
            "provider": self.provider,
            "fallback_provider": self.fallback_provider,
            "memory_limit": self.memory_limit,
            "created_at": self.created_at.isoformat(),
            "metadata": dict(self.metadata),
        }


class InMemorySessionStore:
    """Concurrency-safe in-memory store for active sessions."""

    def __init__(self, *, default_memory_limit: Optional[int] = None) -> None:
        self._default_memory_limit = default_memory_limit
        self._sessions: Dict[UUID, Session] = {}
        self._lock = asyncio.Lock()

    async def create_session(
        self,
        *,
        session_id: Optional[UUID] = None,
        provider: Optional[str] = None,
        fallback_provider: Optional[str] = None,
        memory_limit: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Session:
        """Create and register a new session instance.

        Args:
            session_id: Optional identifier for the session. When omitted a UUID4 is
                generated automatically.
            provider: Preferred provider identifier for subsequent requests.
            fallback_provider: Optional secondary provider to be used if the
                primary fails (wired up in later tasks).
            memory_limit: Explicit per-session memory limit override.
            metadata: Arbitrary metadata that should be attached to the session.

        Returns:
            The freshly created :class:`Session` instance.

        Raises:
            SessionAlreadyExistsError: If the session identifier is already in use.
        """

        resolved_id = session_id or uuid4()
        metadata = dict(metadata or {})
        resolved_memory_limit = memory_limit if memory_limit is not None else self._default_memory_limit

        async with self._lock:
            if resolved_id in self._sessions:
                raise SessionAlreadyExistsError(f"Session {resolved_id} already exists")

            session = Session(
                id=resolved_id,
                provider=provider,
                fallback_provider=fallback_provider,
                memory_limit=resolved_memory_limit,
                metadata=metadata,
            )
            self._sessions[session.id] = session
            return session

    async def get_session(self, session_id: UUID) -> Session:
        """Fetch a session by its identifier."""

        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise SessionNotFoundError(f"Session {session_id} was not found")
            return session

    async def delete_session(self, session_id: UUID) -> None:
        """Delete an existing session."""

        async with self._lock:
            if session_id not in self._sessions:
                raise SessionNotFoundError(f"Session {session_id} was not found")
            del self._sessions[session_id]

    async def list_sessions(self) -> Iterable[Session]:
        """Return a snapshot iterable of all active sessions."""

        async with self._lock:
            return tuple(self._sessions.values())


__all__ = [
    "InMemorySessionStore",
    "Session",
    "SessionAlreadyExistsError",
    "SessionError",
    "SessionNotFoundError",
]
