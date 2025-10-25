"""Administrative endpoints for managing runtime controls."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Response, status
from pydantic import BaseModel, Field

from .config import get_settings
from .dependencies import get_rate_limit_bypass_store
from .errors import APIError
from .rate_limiter import RateLimitBypassStore
from .runtime import build_runtime_report

router = APIRouter(prefix="/admin", tags=["admin"])


class BypassEntry(BaseModel):
    """Request model for bypass operations."""

    ip: str = Field(..., description="IPv4 or IPv6 address to exempt from rate limiting.")


class RuntimeProviderInfo(BaseModel):
    """Describes the resolved provider configuration."""

    default: str | None = Field(
        description="Name of the default provider handling chat sessions.",
    )
    available: list[str] = Field(
        description="Providers registered and available for use.",
    )
    llm_provider: str = Field(
        description="Configured upstream LLM integration for the MCP agent.",
    )
    uses_openrouter: bool = Field(
        description="Whether the MCP agent is configured to use the OpenRouter API.",
    )
    default_model: str | None = Field(
        description="Model identifier applied by default for LLM requests.",
    )
    openrouter_base_url: str | None = Field(
        description="OpenRouter base URL when OpenRouter is the active provider.",
    )
    mcp_servers_configured: bool = Field(
        description="Indicates if any MCP servers are configured.",
    )
    mcp_servers_active: bool = Field(
        description="True when enough MCP servers are configured for activation.",
    )
    mcp_server_names: list[str] = Field(
        description="Normalised MCP server identifiers supplied to the agent.",
    )
    mcp_servers_required_minimum: int = Field(
        description="Minimum servers required for MCP activation.",
    )


class RuntimeMemoryInfo(BaseModel):
    """Summarises the configured session memory limits."""

    backend: str = Field(description="Active chat memory backend implementation name.")
    default_limit: int = Field(
        description="Number of exchanges stored per session by default.",
    )
    max_limit: int = Field(
        description="Maximum number of exchanges retained per session.",
    )


class RuntimeDiagnostics(BaseModel):
    """Container for runtime diagnostic information exposed by the admin API."""

    provider: RuntimeProviderInfo
    memory: RuntimeMemoryInfo


async def require_admin_token(
    token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> str:
    """Validate the admin token header against configured credentials."""

    settings = get_settings()
    expected = settings.admin_token

    if not expected:
        raise APIError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="admin_disabled",
            message="Admin endpoints are unavailable because ADMIN_TOKEN is not configured.",
        )

    if not token:
        raise APIError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="missing_admin_token",
            message="Admin token header is required.",
        )

    if token != expected:
        raise APIError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="invalid_admin_token",
            message="Provided admin token is invalid.",
        )

    return token


@router.get(
    "/bypass",
    response_model=list[str],
    summary="List rate limit bypass entries",
    response_description="Collection of IP addresses currently exempt from rate limiting.",
)
async def list_bypass_entries(
    store: RateLimitBypassStore = Depends(get_rate_limit_bypass_store),
    _: str = Depends(require_admin_token),
) -> list[str]:
    """Return the configured rate limit bypass IP addresses."""

    return await store.list()


@router.post(
    "/bypass",
    status_code=status.HTTP_201_CREATED,
    summary="Add a rate limit bypass entry",
    response_description="The normalised IP address that was added to the bypass list.",
)
async def add_bypass_entry(
    entry: BypassEntry,
    store: RateLimitBypassStore = Depends(get_rate_limit_bypass_store),
    _: str = Depends(require_admin_token),
) -> dict[str, str]:
    """Add an IP address to the bypass list and return the normalised value."""

    try:
        ip = await store.add(entry.ip)
    except ValueError as exc:  # Normalise raises for invalid values
        raise APIError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_ip",
            message=str(exc),
        ) from exc

    return {"ip": ip}


@router.delete(
    "/bypass/{ip}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a rate limit bypass entry",
    response_description="Empty response returned when the bypass entry is removed.",
)
async def remove_bypass_entry(
    ip: str,
    store: RateLimitBypassStore = Depends(get_rate_limit_bypass_store),
    _: str = Depends(require_admin_token),
) -> Response:
    """Remove an IP address from the bypass list."""

    try:
        removed = await store.remove(ip)
    except ValueError as exc:
        raise APIError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_ip",
            message=str(exc),
        ) from exc

    if not removed:
        raise APIError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="bypass_not_found",
            message="Bypass entry was not found.",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/runtime",
    response_model=RuntimeDiagnostics,
    summary="Runtime configuration snapshot",
    response_description="Current provider and memory configuration for the service.",
)
async def runtime_diagnostics(_: str = Depends(require_admin_token)) -> RuntimeDiagnostics:
    """Expose the resolved runtime configuration for observability purposes."""

    report = build_runtime_report()
    return RuntimeDiagnostics(**report)


__all__ = ["require_admin_token", "router"]
