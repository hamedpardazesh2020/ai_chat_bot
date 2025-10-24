"""Application entry point for the chat agent backend."""
from __future__ import annotations

import logging
from time import perf_counter
from typing import Any, Awaitable, Callable, Final
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from .admin import router as admin_router
from .api import sessions_router
from .agents.providers.mcp import MCPAgentChatProvider, MCPAgentProviderError
from .agents.providers.openai import OpenAIChatProvider, OpenAIProviderError
from .agents.providers.openrouter import OpenRouterChatProvider, OpenRouterProviderError
from .config import get_settings
from .dependencies import (
    get_metrics_collector,
    get_provider_manager,
    get_rate_limit_bypass_store,
    get_rate_limiter,
)
from .errors import register_exception_handlers
from .logging_utils import configure_logging
from .observability import MetricsCollector
from .rate_limiter import RateLimitMiddleware

META_TAG: Final[str] = "meta"

meta_router = APIRouter()
metrics_router = APIRouter()


@meta_router.get(
    "/health",
    tags=[META_TAG],
    summary="Service health status",
    response_description="Uptime and error counters summarising the API state.",
)
async def health_check(
    metrics: MetricsCollector = Depends(get_metrics_collector),
) -> dict[str, Any]:
    """Return a basic health payload with uptime and error summary."""

    snapshot = await metrics.snapshot()
    return {
        "status": "ok",
        "uptime_seconds": round(metrics.uptime_seconds(), 3),
        "requests_total": snapshot["requests_total"],
        "responses_total": snapshot["responses_total"],
        "errors_total": snapshot["errors_total"],
    }


@metrics_router.get(
    "/metrics",
    tags=[META_TAG],
    summary="Service metrics snapshot",
    response_description="Request, response, and latency metrics captured since start-up.",
)
async def metrics(
    metrics: MetricsCollector = Depends(get_metrics_collector),
) -> dict[str, Any]:
    """Expose the collected metrics as a JSON payload."""

    snapshot = await metrics.snapshot()
    return {
        **snapshot,
        "uptime_seconds": round(metrics.uptime_seconds(), 3),
    }


root_router = APIRouter()


@root_router.get(
    "/",
    summary="API heartbeat",
    response_description="Simple status payload confirming the service is running.",
)
async def root() -> dict[str, str]:
    """Simple root endpoint to verify the application is running."""
    return {"status": "ok"}


def create_app() -> FastAPI:
    """Instantiate and configure the FastAPI application."""
    settings = get_settings()
    configure_logging(settings)
    application = FastAPI(title="Chat Agent API")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(application)
    request_logger = logging.getLogger("app.requests")
    application.add_middleware(
        RateLimitMiddleware,
        limiter=get_rate_limiter(),
        bypass_store=get_rate_limit_bypass_store(),
    )

    provider_logger = logging.getLogger("app.providers")
    manager = get_provider_manager()
    shutdown_callbacks: list[Callable[[], Awaitable[None]]] = []

    def _register_provider(
        provider: Any,
        *,
        prefer_default: bool = False,
    ) -> None:
        """Register a provider instance and track its shutdown callback."""

        manager.register(provider, replace=True)
        if prefer_default or manager.default is None:
            manager.set_default(provider.name)

        close_callback = getattr(provider, "aclose", None)
        if callable(close_callback):
            shutdown_callbacks.append(close_callback)

    if settings.openrouter_key:
        try:
            provider = OpenRouterChatProvider()
        except OpenRouterProviderError as exc:
            provider_logger.error(
                "openrouter_provider_registration_failed",
                extra={"error": str(exc)},
            )
        else:
            _register_provider(provider)

    if settings.openai_api_key:
        try:
            provider = OpenAIChatProvider()
        except OpenAIProviderError as exc:
            provider_logger.error(
                "openai_provider_registration_failed",
                extra={"error": str(exc)},
            )
        else:
            _register_provider(provider)

    if settings.mcp_agent_servers:
        try:
            provider = MCPAgentChatProvider.from_settings(settings)
        except MCPAgentProviderError as exc:
            provider_logger.error(
                "mcp_provider_registration_failed",
                extra={"error": str(exc)},
            )
        else:
            _register_provider(provider, prefer_default=True)

    @application.middleware("http")
    async def _logging_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid4())
        request.state.request_id = request_id
        start_time = perf_counter()
        client_host = request.client.host if request.client else None
        context = {
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "client_ip": client_host,
            "request_id": request_id,
        }
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (perf_counter() - start_time) * 1000
            request_logger.exception(
                "request_failed",
                extra={**context, "duration_ms": round(duration_ms, 3)},
            )
            raise

        duration_ms = (perf_counter() - start_time) * 1000
        response.headers.setdefault("X-Request-ID", request_id)
        request_logger.info(
            "request_completed",
            extra={
                **context,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 3),
            },
        )
        return response

    if settings.metrics_enabled:
        metrics = get_metrics_collector()

        @application.middleware("http")
        async def _metrics_middleware(
            request: Request,
            call_next: Callable[[Request], Awaitable[Response]],
        ) -> Response:
            await metrics.record_request(request.method)
            start_time = perf_counter()
            try:
                response = await call_next(request)
            except Exception:
                await metrics.record_exception()
                raise
            duration = perf_counter() - start_time
            await metrics.record_response(response.status_code, duration)
            return response

        application.include_router(metrics_router)
    application.include_router(root_router)
    application.include_router(meta_router)
    application.include_router(admin_router)
    application.include_router(sessions_router)

    if shutdown_callbacks:

        @application.on_event("shutdown")
        async def _shutdown_providers() -> None:
            for callback in shutdown_callbacks:
                try:
                    await callback()
                except Exception:  # pragma: no cover - defensive logging
                    provider_logger.exception("provider_shutdown_failed")

    return application


app = create_app()


__all__ = ["app", "create_app"]
