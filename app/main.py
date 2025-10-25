"""Application entry point for the chat agent backend."""
from __future__ import annotations

import logging
from time import perf_counter
from typing import Any, Awaitable, Callable, Final
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from .admin import router as admin_router
from .admin_ui import router as admin_ui_router
from .api import sessions_router
from .agents.manager import ProviderNotRegisteredError
from .agents.providers import (
    MCPAgentChatProvider,
    MCPAgentProviderError,
    UnconfiguredChatProvider,
)
from .config import get_settings
from .dependencies import (
    get_metrics_collector,
    get_provider_manager,
    get_rate_limit_bypass_store,
    get_rate_limiter,
    get_history_store,
)
from .errors import register_exception_handlers
from .logging_utils import configure_logging
from .observability import MetricsCollector
from .runtime import build_runtime_report
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
    startup_logger = logging.getLogger("app.startup")
    application.add_middleware(
        RateLimitMiddleware,
        limiter=get_rate_limiter(),
        bypass_store=get_rate_limit_bypass_store(),
    )

    provider_logger = logging.getLogger("app.providers")
    manager = get_provider_manager()
    shutdown_callbacks: list[Callable[[], Awaitable[None]]] = []

    def _register_provider(provider: Any) -> None:
        """Register a provider instance and track its shutdown callback."""

        manager.register(provider, replace=True)
        if manager.default is None:
            manager.set_default(provider.name)

        close_callback = getattr(provider, "aclose", None)
        if callable(close_callback):
            shutdown_callbacks.append(close_callback)

    try:
        provider = MCPAgentChatProvider.from_settings(settings)
    except MCPAgentProviderError as exc:
        provider_logger.error(
            "mcp_provider_registration_failed",
            extra={"error": str(exc)},
        )
    else:
        _register_provider(provider)

    desired_default = (settings.default_provider_name or "").strip()
    if desired_default:
        try:
            manager.set_default(desired_default)
        except ProviderNotRegisteredError:
            provider_logger.warning(
                "default_provider_unavailable",
                extra={"requested_provider": desired_default},
            )

    if manager.default is None:
        provider_logger.warning(
            "default_provider_unavailable",
            extra={"requested_provider": desired_default or None},
        )
        unconfigured = UnconfiguredChatProvider()
        _register_provider(unconfigured)

    runtime_report = build_runtime_report(
        settings=settings,
        manager=manager,
        history_backend=get_history_store(),
    )
    provider_info = runtime_report["provider"]
    memory_info = runtime_report["memory"]
    history_info = runtime_report["history"]
    log_payload = {
        "default_provider": provider_info["default"],
        "available_providers": ",".join(provider_info["available"]),
        "llm_provider": provider_info["llm_provider"],
        "uses_openrouter": provider_info["uses_openrouter"],
        "mcp_servers_configured": provider_info["mcp_servers_configured"],
        "mcp_servers_active": provider_info["mcp_servers_active"],
        "mcp_server_names": ",".join(provider_info["mcp_server_names"]),
        "mcp_servers_required_minimum": provider_info["mcp_servers_required_minimum"],
        "memory_backend": memory_info["backend"],
        "memory_default_limit": memory_info["default_limit"],
        "memory_max_limit": memory_info["max_limit"],
        "history_backend": history_info["backend"],
        "history_configured_backend": history_info["configured_backend"],
        "history_enabled": history_info["enabled"],
        "history_namespace": history_info["namespace"],
    }
    if provider_info.get("default_model"):
        log_payload["llm_default_model"] = provider_info["default_model"]
    if provider_info.get("openrouter_base_url"):
        log_payload["openrouter_base_url"] = provider_info["openrouter_base_url"]

    startup_logger.info("runtime_configuration_resolved", extra=log_payload)

    @application.middleware("http")
    async def _logging_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid4())
        request.state.request_id = request_id
        start_time = perf_counter()
        client_host = request.client.host if request.client else None
        path = request.url.path
        log_request = not path.startswith("/metrics")
        context = {
            "event": "request",
            "method": request.method,
            "path": path,
            "client_ip": client_host,
            "request_id": request_id,
        }
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (perf_counter() - start_time) * 1000
            if log_request:
                request_logger.exception(
                    "request_failed",
                    extra={**context, "duration_ms": round(duration_ms, 3)},
                )
            raise

        duration_ms = (perf_counter() - start_time) * 1000
        response.headers.setdefault("X-Request-ID", request_id)
        if log_request:
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

        def _should_track_metrics(request: Request) -> bool:
            """Return True when the request should contribute to service metrics."""

            method = request.method.upper()
            path = request.url.path
            if method == "POST" and path == "/sessions":
                return True
            if (
                method == "POST"
                and path.startswith("/sessions/")
                and path.endswith("/messages")
            ):
                return True
            return False

        @application.middleware("http")
        async def _metrics_middleware(
            request: Request,
            call_next: Callable[[Request], Awaitable[Response]],
        ) -> Response:
            track_metrics = _should_track_metrics(request)
            start_time = perf_counter() if track_metrics else None
            if track_metrics:
                await metrics.record_request(request.method)
            try:
                response = await call_next(request)
            except Exception:
                if track_metrics:
                    await metrics.record_exception()
                raise
            if track_metrics and start_time is not None:
                duration = perf_counter() - start_time
                await metrics.record_response(response.status_code, duration)
            return response

        application.include_router(metrics_router)
    application.include_router(root_router)
    application.include_router(meta_router)
    application.include_router(admin_router)
    application.include_router(admin_ui_router)
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
