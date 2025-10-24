"""Rate limiting utilities supporting in-memory and Redis backends."""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import math
import time
from dataclasses import dataclass
from typing import Iterable, List, Optional, Protocol

from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

try:  # pragma: no cover - redis is optional for non-redis deployments
    from redis.asyncio import Redis as AsyncRedis
    from redis.asyncio import from_url as redis_from_url
    from redis.exceptions import RedisError
except Exception:  # pragma: no cover - redis may not be installed in tests
    AsyncRedis = None  # type: ignore
    redis_from_url = None  # type: ignore
    RedisError = None  # type: ignore

if False:  # pragma: no cover - for type checking only
    from .config import Settings


logger = logging.getLogger("app.rate_limiter")


@dataclass(frozen=True)
class RateLimitDecision:
    """Result of a rate limit check."""

    allowed: bool
    retry_after: float = 0.0


class RateLimiter(Protocol):
    """Protocol implemented by rate limiter backends."""

    async def acquire(self, identifier: str, *, tokens: int = 1) -> RateLimitDecision:
        """Consume ``tokens`` for ``identifier`` if available."""


class TokenBucket:
    """Simple token bucket implementation supporting concurrent access."""

    def __init__(self, rate: float, capacity: int) -> None:
        if rate <= 0:
            raise ValueError("rate must be greater than 0")
        if capacity < 1:
            raise ValueError("capacity must be at least 1")

        self._rate = float(rate)
        self._capacity = float(capacity)
        self._tokens = float(capacity)
        self._updated_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> RateLimitDecision:
        if tokens < 1:
            raise ValueError("tokens must be at least 1")

        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._updated_at
            if elapsed > 0:
                self._tokens = min(
                    self._capacity, self._tokens + elapsed * self._rate
                )
                self._updated_at = now

            if self._tokens >= tokens:
                self._tokens -= tokens
                return RateLimitDecision(True, 0.0)

            deficit = tokens - self._tokens
            retry_after = deficit / self._rate
            return RateLimitDecision(False, max(0.0, retry_after))


class InMemoryRateLimiter:
    """Maintain per-identifier token buckets in local process memory."""

    def __init__(self, *, rate: float, capacity: int) -> None:
        if rate <= 0:
            raise ValueError("rate must be greater than 0")
        if capacity < 1:
            raise ValueError("capacity must be at least 1")

        self._rate = float(rate)
        self._capacity = int(capacity)
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, identifier: str, *, tokens: int = 1) -> RateLimitDecision:
        if not identifier:
            raise ValueError("identifier must be provided")

        bucket = await self._get_bucket(identifier)
        return await bucket.acquire(tokens)

    async def _get_bucket(self, identifier: str) -> TokenBucket:
        bucket = self._buckets.get(identifier)
        if bucket is not None:
            return bucket

        async with self._lock:
            bucket = self._buckets.get(identifier)
            if bucket is None:
                bucket = TokenBucket(rate=self._rate, capacity=self._capacity)
                self._buckets[identifier] = bucket
            return bucket


class RedisRateLimiter:
    """Distributed token bucket implementation backed by Redis."""

    _SCRIPT = """
    local key = KEYS[1]
    local rate = tonumber(ARGV[1])
    local capacity = tonumber(ARGV[2])
    local now = tonumber(ARGV[3])
    local tokens_requested = tonumber(ARGV[4])
    local ttl_ms = tonumber(ARGV[5])

    local data = redis.call('HMGET', key, 'tokens', 'timestamp')
    local tokens = tonumber(data[1])
    local timestamp = tonumber(data[2])

    if tokens == nil then
        tokens = capacity
    end

    if timestamp == nil then
        timestamp = now
    end

    local elapsed = math.max(0, now - timestamp)
    local replenished = math.min(capacity, tokens + (elapsed * rate))

    local allowed = replenished >= tokens_requested
    local retry_after = 0

    if allowed then
        replenished = replenished - tokens_requested
    else
        local deficit = tokens_requested - replenished
        retry_after = deficit / rate
    end

    redis.call('HMSET', key, 'tokens', replenished, 'timestamp', now)
    redis.call('PEXPIRE', key, ttl_ms)

    if allowed then
        return {1, retry_after}
    end

    return {0, retry_after}
    """

    def __init__(
        self,
        *,
        rate: float,
        capacity: int,
        redis: "AsyncRedis",
        key_prefix: str = "rate_limiter",
        ttl_multiplier: float = 2.0,
    ) -> None:
        if rate <= 0:
            raise ValueError("rate must be greater than 0")
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        if redis is None:  # pragma: no cover - defensive programming
            raise ValueError("redis client must be provided")
        if ttl_multiplier <= 0:
            raise ValueError("ttl_multiplier must be greater than 0")

        self._rate = float(rate)
        self._capacity = float(capacity)
        self._redis = redis
        self._key_prefix = key_prefix.rstrip(":")
        # TTL ensures idle buckets eventually expire. We convert to ms for Redis.
        ttl_seconds = max(1.0, (capacity / rate) * ttl_multiplier)
        self._ttl_ms = int(math.ceil(ttl_seconds * 1000))
        self._script = redis.register_script(self._SCRIPT)

    async def acquire(self, identifier: str, *, tokens: int = 1) -> RateLimitDecision:
        if not identifier:
            raise ValueError("identifier must be provided")
        if tokens < 1:
            raise ValueError("tokens must be at least 1")

        key = f"{self._key_prefix}:{identifier}"
        now = time.time()
        result = await self._script(
            keys=[key],
            args=[self._rate, self._capacity, now, float(tokens), self._ttl_ms],
        )

        # Redis returns a list of responses which may be bytes/str/float depending on
        # client configuration. Normalise into primitives before constructing result.
        allowed_raw, retry_after_raw = result  # type: ignore[misc]
        allowed = bool(int(float(allowed_raw)))
        retry_after = float(retry_after_raw)
        return RateLimitDecision(allowed, retry_after)


class IdentifierResolver(Protocol):
    """Callable returning rate limit identifiers for a request."""

    def __call__(self, request: Request) -> Iterable[str]:
        ...


def default_identifier_resolver(request: Request) -> List[str]:
    """Return identifiers derived from the client IP and optional API key."""

    identifiers: List[str] = []

    api_key = request.headers.get("x-api-key")
    if api_key:
        identifiers.append(f"api_key:{api_key.strip()}")

    client_host = request.client.host if request.client else None
    identifiers.append(f"ip:{client_host or 'unknown'}")

    return identifiers


class RateLimitBypassStore:
    """Concurrency-safe in-memory store of IPs bypassing rate limits."""

    def __init__(self, *, initial: Optional[Iterable[str]] = None) -> None:
        self._entries: set[str] = set()
        self._lock = asyncio.Lock()
        if initial:
            for entry in initial:
                try:
                    normalised = self._normalise(entry)
                except ValueError:
                    continue
                self._entries.add(normalised)

    async def add(self, ip_address: str) -> str:
        """Add ``ip_address`` to the bypass set and return the normalised value."""

        normalised = self._normalise(ip_address)
        async with self._lock:
            self._entries.add(normalised)
        return normalised

    async def remove(self, ip_address: str) -> bool:
        """Remove ``ip_address`` from the bypass set, returning ``True`` if present."""

        normalised = self._normalise(ip_address)
        async with self._lock:
            removed = normalised in self._entries
            self._entries.discard(normalised)
            return removed

    async def is_bypassed(self, ip_address: Optional[str]) -> bool:
        """Return ``True`` when ``ip_address`` is configured to bypass limits."""

        if not ip_address:
            return False

        try:
            normalised = self._normalise(ip_address)
        except ValueError:
            return False

        async with self._lock:
            return normalised in self._entries

    async def list(self) -> List[str]:
        """Return a sorted list of bypass entries."""

        async with self._lock:
            return sorted(self._entries)

    @staticmethod
    def _normalise(value: str) -> str:
        if not value:
            raise ValueError("IP address must be provided")
        return str(ipaddress.ip_address(value.strip()))


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware applying rate limits before requests reach route handlers."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        limiter: RateLimiter,
        bypass_store: Optional[RateLimitBypassStore] = None,
        identifier_resolver: IdentifierResolver = default_identifier_resolver,
        tokens: int = 1,
    ) -> None:
        super().__init__(app)
        self._limiter = limiter
        self._bypass_store = bypass_store
        self._identifier_resolver = identifier_resolver
        self._tokens = tokens

    async def dispatch(
        self, request: StarletteRequest, call_next
    ) -> Response:  # type: ignore[override]
        client_host = request.client.host if request.client else None
        if self._bypass_store and await self._bypass_store.is_bypassed(client_host):
            return await call_next(request)

        identifiers = list(self._identifier_resolver(request))
        if not identifiers:
            identifiers = ["anonymous"]

        for identifier in identifiers:
            try:
                decision = await self._limiter.acquire(identifier, tokens=self._tokens)
            except Exception as exc:  # pragma: no cover - defensive fallback
                if RedisError is not None and isinstance(exc, RedisError):
                    logger.warning(
                        "rate_limit_check_failed",
                        extra={
                            "identifier": identifier,
                            "error": str(exc),
                        },
                    )
                    return await call_next(request)
                raise
            if not decision.allowed:
                return self._rate_limited_response(decision.retry_after)

        response = await call_next(request)
        return response

    @staticmethod
    def _rate_limited_response(retry_after: float) -> Response:
        retry_after = max(0.0, retry_after)
        retry_header = max(1, int(math.ceil(retry_after))) if retry_after else 1
        payload = {"error": "rate_limited", "retry_after": retry_after}
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=payload,
            headers={"Retry-After": str(retry_header)},
        )


def rate_limiter_from_settings(
    settings: "Settings", *, redis_client: Optional["AsyncRedis"] = None
) -> RateLimiter:
    """Create a rate limiter based on the provided application settings."""

    if settings.redis_enabled:
        if redis_client is None:
            if redis_from_url is None:  # pragma: no cover - requires redis extra
                raise RuntimeError(
                    "redis package is required for RedisRateLimiter usage."
                )
            if not settings.redis_url:
                raise ValueError(
                    "REDIS_URL must be configured when redis integration is enabled."
                )
            redis_client = redis_from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )

        return RedisRateLimiter(
            rate=settings.rate_rps,
            capacity=settings.rate_burst,
            redis=redis_client,
        )

    return InMemoryRateLimiter(rate=settings.rate_rps, capacity=settings.rate_burst)


__all__ = [
    "InMemoryRateLimiter",
    "RedisRateLimiter",
    "RateLimitDecision",
    "RateLimitBypassStore",
    "RateLimitMiddleware",
    "RateLimiter",
    "default_identifier_resolver",
    "rate_limiter_from_settings",
]
