import asyncio
from typing import Callable, Iterable

from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.rate_limiter import (
    InMemoryRateLimiter,
    RateLimitBypassStore,
    RateLimitMiddleware,
)


def make_app(
    limiter: InMemoryRateLimiter,
    *,
    bypass_store: RateLimitBypassStore | None = None,
    resolver: Callable[[Request], Iterable[str]] | None = None,
) -> FastAPI:
    app = FastAPI()

    def default_resolver(request: Request) -> list[str]:
        ip = request.headers.get("x-client-ip", "unknown")
        return [f"ip:{ip}"]

    app.add_middleware(
        RateLimitMiddleware,
        limiter=limiter,
        bypass_store=bypass_store,
        identifier_resolver=resolver or default_resolver,
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def test_rate_limit_returns_429_when_exceeded() -> None:
    async def _run() -> None:
        limiter = InMemoryRateLimiter(rate=1, capacity=1)
        app = make_app(limiter)

        transport = ASGITransport(app=app, client=("198.51.100.10", 0))
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            headers = {"x-client-ip": "198.51.100.10"}

            first = await client.get("/health", headers=headers)
            assert first.status_code == 200

            second = await client.get("/health", headers=headers)
            assert second.status_code == 429
            payload = second.json()
            assert payload["error"] == "rate_limited"
            assert payload["retry_after"] >= 0
            assert any(key.lower() == "retry-after" for key in second.headers)

    asyncio.run(_run())


def test_rate_limit_bypass_allows_repeated_requests() -> None:
    async def _run() -> None:
        limiter = InMemoryRateLimiter(rate=1, capacity=1)
        bypass_store = RateLimitBypassStore()
        await bypass_store.add("203.0.113.5")

        app = make_app(limiter, bypass_store=bypass_store)

        transport = ASGITransport(app=app, client=("203.0.113.5", 0))
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            headers = {"x-client-ip": "203.0.113.5"}

            first = await client.get("/health", headers=headers)
            assert first.status_code == 200

            second = await client.get("/health", headers=headers)
            assert second.status_code == 200

    asyncio.run(_run())
