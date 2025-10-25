"""Persistent storage backends for chat history."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional, Protocol, Sequence, TYPE_CHECKING
from uuid import UUID

try:  # pragma: no cover - optional dependency
    from redis.asyncio import Redis as AsyncRedis
    from redis.asyncio import from_url as redis_from_url
except Exception:  # pragma: no cover - redis may not be installed
    AsyncRedis = None  # type: ignore[assignment]
    redis_from_url = None  # type: ignore[assignment]

try:  # pragma: no cover - optional dependency
    import aiomysql
except Exception:  # pragma: no cover - aiomysql may be unavailable for tests
    aiomysql = None  # type: ignore[assignment]

try:  # pragma: no cover - optional dependency
    from motor.motor_asyncio import AsyncIOMotorClient
except Exception:  # pragma: no cover - motor may be unavailable
    AsyncIOMotorClient = None  # type: ignore[assignment]

if TYPE_CHECKING:  # pragma: no cover - imported only for typing
    from .config import Settings
    from .memory import ChatMessage
    from .sessions import Session


class HistoryStore(Protocol):
    """Protocol implemented by transcript persistence backends."""

    async def record_session(self, session: "Session") -> None:
        """Persist metadata about a newly created session."""

    async def record_messages(
        self, session_id: UUID, messages: Sequence["ChatMessage"]
    ) -> None:
        """Persist one or more chat messages for the session."""

    async def delete_session(self, session_id: UUID) -> None:
        """Remove stored session metadata and associated messages."""

    async def aclose(self) -> None:
        """Release any open connections held by the backend."""


class NoOpHistoryStore:
    """History store implementation that intentionally discards data."""

    async def record_session(self, session: "Session") -> None:  # pragma: no cover - trivial
        return

    async def record_messages(
        self, session_id: UUID, messages: Sequence["ChatMessage"]
    ) -> None:  # pragma: no cover - trivial
        return

    async def delete_session(self, session_id: UUID) -> None:  # pragma: no cover - trivial
        return

    async def aclose(self) -> None:  # pragma: no cover - trivial
        return


class RedisHistoryStore:
    """Redis-backed history store persisting sessions and message transcripts."""

    def __init__(
        self,
        client: "AsyncRedis",
        *,
        namespace: str = "chat_history",
    ) -> None:
        if AsyncRedis is None:  # pragma: no cover - safety net when redis not installed
            raise RuntimeError("redis package is required for RedisHistoryStore usage.")

        self._client = client
        self._namespace = namespace.rstrip(":")

    async def record_session(self, session: "Session") -> None:
        payload = {
            "id": str(session.id),
            "provider": session.provider or "",
            "fallback_provider": session.fallback_provider or "",
            "memory_limit": "" if session.memory_limit is None else str(session.memory_limit),
            "created_at": session.created_at.isoformat(),
            "metadata": json.dumps(session.metadata, ensure_ascii=False),
        }
        session_key = self._session_key(session.id)
        await self._client.hset(session_key, mapping=payload)
        await self._client.sadd(self._session_index_key(), str(session.id))

    async def record_messages(
        self, session_id: UUID, messages: Sequence["ChatMessage"]
    ) -> None:
        if not messages:
            return

        encoded = [
            json.dumps(
                {
                    "session_id": str(session_id),
                    **message.to_dict(),
                    "stored_at": datetime.now(timezone.utc).isoformat(),
                },
                ensure_ascii=False,
            )
            for message in messages
        ]
        await self._client.rpush(self._messages_key(session_id), *encoded)

    async def delete_session(self, session_id: UUID) -> None:
        await self._client.delete(
            self._session_key(session_id),
            self._messages_key(session_id),
        )
        await self._client.srem(self._session_index_key(), str(session_id))

    async def aclose(self) -> None:
        await self._client.close()

    def _session_key(self, session_id: UUID) -> str:
        return f"{self._namespace}:session:{session_id}"

    def _messages_key(self, session_id: UUID) -> str:
        return f"{self._namespace}:messages:{session_id}"

    def _session_index_key(self) -> str:
        return f"{self._namespace}:sessions"

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        namespace: str = "chat_history",
        **redis_kwargs: object,
    ) -> "RedisHistoryStore":
        if redis_from_url is None:  # pragma: no cover - safety net when redis missing
            raise RuntimeError("redis package is required for RedisHistoryStore usage.")

        client = redis_from_url(url, encoding="utf-8", decode_responses=True, **redis_kwargs)
        return cls(client, namespace=namespace)


class MySQLHistoryStore:
    """MySQL-backed history store using ``aiomysql`` connection pools."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        namespace: str = "chat_history",
        session_table: str = "chat_sessions",
        message_table: str = "chat_messages",
        connect_timeout: int = 10,
    ) -> None:
        if aiomysql is None:  # pragma: no cover - optional dependency guard
            raise RuntimeError("aiomysql is required for MySQL history storage usage.")

        self._namespace = namespace
        self._session_table = session_table
        self._message_table = message_table
        self._pool: Optional[aiomysql.Pool] = None
        self._pool_kwargs = dict(
            host=host,
            port=port,
            user=user,
            password=password,
            db=database,
            autocommit=False,
            connect_timeout=connect_timeout,
            charset="utf8mb4",
        )
        self._init_lock = asyncio.Lock()
        self._initialised = False

    async def record_session(self, session: "Session") -> None:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    f"""
                    INSERT INTO {self._session_table}
                        (namespace, id, provider, fallback_provider, memory_limit, created_at, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        provider = VALUES(provider),
                        fallback_provider = VALUES(fallback_provider),
                        memory_limit = VALUES(memory_limit),
                        created_at = VALUES(created_at),
                        metadata = VALUES(metadata)
                    """,
                    (
                        self._namespace,
                        str(session.id),
                        session.provider,
                        session.fallback_provider,
                        session.memory_limit,
                        session.created_at.strftime("%Y-%m-%d %H:%M:%S.%f"),
                        json.dumps(session.metadata, ensure_ascii=False),
                    ),
                )
            await connection.commit()

    async def record_messages(
        self, session_id: UUID, messages: Sequence["ChatMessage"]
    ) -> None:
        if not messages:
            return

        pool = await self._get_pool()
        async with pool.acquire() as connection:
            async with connection.cursor() as cursor:
                payloads = [
                    (
                        self._namespace,
                        str(session_id),
                        message.role,
                        message.content,
                        message.created_at.strftime("%Y-%m-%d %H:%M:%S.%f"),
                        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f"),
                    )
                    for message in messages
                ]
                await cursor.executemany(
                    f"""
                    INSERT INTO {self._message_table}
                        (namespace, session_id, role, content, created_at, stored_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    payloads,
                )
            await connection.commit()

    async def delete_session(self, session_id: UUID) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    f"DELETE FROM {self._session_table} WHERE namespace = %s AND id = %s",
                    (self._namespace, str(session_id)),
                )
                await cursor.execute(
                    f"DELETE FROM {self._message_table} WHERE namespace = %s AND session_id = %s",
                    (self._namespace, str(session_id)),
                )
            await connection.commit()

    async def aclose(self) -> None:
        if self._pool is not None:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None

    async def _get_pool(self) -> "aiomysql.Pool":
        if self._pool is None:
            async with self._init_lock:
                if self._pool is None:
                    self._pool = await aiomysql.create_pool(**self._pool_kwargs)
                    await self._initialise_schema(self._pool)
        return self._pool

    async def _initialise_schema(self, pool: "aiomysql.Pool") -> None:
        if self._initialised:
            return
        async with pool.acquire() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._session_table} (
                        namespace VARCHAR(64) NOT NULL,
                        id CHAR(36) NOT NULL,
                        provider VARCHAR(255) NULL,
                        fallback_provider VARCHAR(255) NULL,
                        memory_limit INT NULL,
                        created_at DATETIME(6) NOT NULL,
                        metadata JSON NULL,
                        PRIMARY KEY (namespace, id)
                    ) CHARACTER SET utf8mb4
                    """
                )
                await cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {self._message_table} (
                        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        namespace VARCHAR(64) NOT NULL,
                        session_id CHAR(36) NOT NULL,
                        role VARCHAR(32) NOT NULL,
                        content LONGTEXT NOT NULL,
                        created_at DATETIME(6) NOT NULL,
                        stored_at DATETIME(6) NOT NULL,
                        INDEX idx_session (namespace, session_id)
                    ) CHARACTER SET utf8mb4
                    """
                )
            await connection.commit()
        self._initialised = True


class MongoHistoryStore:
    """MongoDB-backed history store implemented with ``motor``."""

    def __init__(
        self,
        *,
        uri: str,
        database: str,
        namespace: str = "chat_history",
        session_collection: str = "chat_sessions",
        message_collection: str = "chat_messages",
    ) -> None:
        if AsyncIOMotorClient is None:  # pragma: no cover - optional dependency guard
            raise RuntimeError("motor is required for MongoDB history storage usage.")

        self._client = AsyncIOMotorClient(uri)
        self._database = self._client[database]
        self._sessions = self._database[session_collection]
        self._messages = self._database[message_collection]
        self._namespace = namespace
        self._init_lock = asyncio.Lock()
        self._initialised = False

    async def record_session(self, session: "Session") -> None:
        await self._ensure_indexes()
        payload = {
            "namespace": self._namespace,
            "id": str(session.id),
            "provider": session.provider,
            "fallback_provider": session.fallback_provider,
            "memory_limit": session.memory_limit,
            "created_at": session.created_at,
            "metadata": session.metadata,
        }
        await self._sessions.update_one(
            {"namespace": self._namespace, "id": str(session.id)},
            {"$set": payload},
            upsert=True,
        )

    async def record_messages(
        self, session_id: UUID, messages: Sequence["ChatMessage"]
    ) -> None:
        if not messages:
            return
        await self._ensure_indexes()
        now = datetime.now(timezone.utc)
        documents = [
            {
                "namespace": self._namespace,
                "session_id": str(session_id),
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at,
                "stored_at": now,
            }
            for message in messages
        ]
        await self._messages.insert_many(documents)

    async def delete_session(self, session_id: UUID) -> None:
        await self._ensure_indexes()
        await self._sessions.delete_one(
            {"namespace": self._namespace, "id": str(session_id)}
        )
        await self._messages.delete_many(
            {"namespace": self._namespace, "session_id": str(session_id)}
        )

    async def aclose(self) -> None:
        self._client.close()

    async def _ensure_indexes(self) -> None:
        if self._initialised:
            return
        async with self._init_lock:
            if self._initialised:
                return
            await self._sessions.create_index(
                [("namespace", 1), ("id", 1)], unique=True
            )
            await self._messages.create_index(
                [("namespace", 1), ("session_id", 1)]
            )
            self._initialised = True


def history_from_settings(settings: "Settings") -> HistoryStore:
    """Create a history store instance based on configuration settings."""

    backend = settings.history_storage_backend
    namespace = settings.history_namespace

    if backend == "mysql":
        return MySQLHistoryStore(
            host=settings.history_mysql_host,
            port=settings.history_mysql_port,
            user=settings.history_mysql_user or "",
            password=settings.history_mysql_password or "",
            database=settings.history_mysql_database,
            namespace=namespace,
            session_table=settings.history_mysql_session_table,
            message_table=settings.history_mysql_message_table,
        )

    if backend == "mongodb":
        return MongoHistoryStore(
            uri=settings.history_mongodb_uri,
            database=settings.history_mongodb_database,
            namespace=namespace,
            session_collection=settings.history_mongodb_session_collection,
            message_collection=settings.history_mongodb_message_collection,
        )

    if backend == "redis":
        redis_url = settings.history_redis_url or settings.redis_url
        if not redis_url:
            raise ValueError("Redis URL must be configured for history storage.")
        return RedisHistoryStore.from_url(redis_url, namespace=namespace)

    return NoOpHistoryStore()


__all__ = [
    "HistoryStore",
    "MongoHistoryStore",
    "MySQLHistoryStore",
    "NoOpHistoryStore",
    "RedisHistoryStore",
    "history_from_settings",
]
