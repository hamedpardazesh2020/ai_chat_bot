"""Administrative endpoints for managing runtime controls."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response, status
from pydantic import BaseModel, Field

from .config import get_settings
from .dependencies import (
    get_chat_memory,
    get_history_store,
    get_rate_limit_bypass_store,
    get_session_store,
)
from .errors import APIError
from .history_store import HistoryStore
from .memory import ChatMemory
from .rate_limiter import RateLimitBypassStore
from .runtime import build_runtime_report
from .sessions import InMemorySessionStore, SessionNotFoundError

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


class ActiveSessionSummary(BaseModel):
    """Summary of an in-memory session available through the runtime."""

    id: UUID
    provider: str | None = None
    fallback_provider: str | None = None
    memory_limit: int | None = None
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActiveMessage(BaseModel):
    """Single chat message from the volatile in-memory transcript."""

    role: str
    content: str
    created_at: datetime


class HistorySessionSummary(BaseModel):
    """Session metadata retrieved from the configured history store."""

    id: UUID
    provider: str | None = None
    fallback_provider: str | None = None
    memory_limit: int | None = None
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class HistorySessionsResponse(BaseModel):
    """Paginated representation of stored chat sessions."""

    sessions: list[HistorySessionSummary]
    limit: int
    offset: int
    count: int


class HistoryMessagePayload(BaseModel):
    """Persisted chat message associated with a stored session."""

    role: str
    content: str
    created_at: datetime
    stored_at: datetime | None = None


class HistoryMessagesResponse(BaseModel):
    """Paginated collection of stored chat messages."""

    session_id: UUID
    messages: list[HistoryMessagePayload]
    limit: int
    offset: int
    count: int


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


def _validate_pagination(limit: int, offset: int) -> tuple[int, int]:
    """Sanitise pagination parameters and raise API errors when invalid."""

    if limit < 1:
        raise APIError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_limit",
            message="Limit must be at least 1.",
        )
    if limit > 200:
        raise APIError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_limit",
            message="Limit cannot exceed 200 records per request.",
        )
    if offset < 0:
        raise APIError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_offset",
            message="Offset cannot be negative.",
        )
    return limit, offset


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


@router.get(
    "/sessions",
    response_model=list[ActiveSessionSummary],
    summary="List active chat sessions",
    response_description="Active sessions currently stored in memory.",
)
async def list_active_sessions(
    store: InMemorySessionStore = Depends(get_session_store),
    _: str = Depends(require_admin_token),
) -> list[ActiveSessionSummary]:
    """Return the currently active sessions tracked by the runtime."""

    sessions = await store.list_sessions()
    return [
        ActiveSessionSummary(
            id=session.id,
            provider=session.provider,
            fallback_provider=session.fallback_provider,
            memory_limit=session.memory_limit,
            created_at=session.created_at,
            metadata=dict(session.metadata),
        )
        for session in sessions
    ]


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[ActiveMessage],
    summary="Active session transcript",
    response_description="Messages currently buffered in the in-memory chat history.",
)
async def get_active_session_messages(
    session_id: UUID,
    store: InMemorySessionStore = Depends(get_session_store),
    memory: ChatMemory = Depends(get_chat_memory),
    _: str = Depends(require_admin_token),
) -> list[ActiveMessage]:
    """Return the volatile chat transcript for the specified session."""

    try:
        await store.get_session(session_id)
    except SessionNotFoundError as exc:
        raise APIError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="session_not_found",
            message=str(exc),
        ) from exc

    history = await memory.get(session_id)
    return [
        ActiveMessage(role=message.role, content=message.content, created_at=message.created_at)
        for message in history
    ]


@router.get(
    "/history/sessions",
    response_model=HistorySessionsResponse,
    summary="List stored chat sessions",
    response_description="Sessions persisted by the configured history backend.",
)
async def list_history_sessions(
    limit: int = 50,
    offset: int = 0,
    history_store: HistoryStore = Depends(get_history_store),
    _: str = Depends(require_admin_token),
) -> HistorySessionsResponse:
    """Return a paginated collection of persisted chat sessions."""

    limit, offset = _validate_pagination(limit, offset)
    sessions = await history_store.list_sessions(limit=limit, offset=offset)
    return HistorySessionsResponse(
        sessions=[
            HistorySessionSummary(
                id=session.id,
                provider=session.provider,
                fallback_provider=session.fallback_provider,
                memory_limit=session.memory_limit,
                created_at=session.created_at,
                metadata=dict(session.metadata),
            )
            for session in sessions
        ],
        limit=limit,
        offset=offset,
        count=len(sessions),
    )


@router.get(
    "/history/sessions/{session_id}/messages",
    response_model=HistoryMessagesResponse,
    summary="Stored session transcript",
    response_description="Messages stored for the specified session in the history backend.",
)
async def get_history_session_messages(
    session_id: UUID,
    limit: int = 50,
    offset: int = 0,
    history_store: HistoryStore = Depends(get_history_store),
    _: str = Depends(require_admin_token),
) -> HistoryMessagesResponse:
    """Return persisted chat messages for a session."""

    limit, offset = _validate_pagination(limit, offset)
    messages = await history_store.get_session_messages(session_id, limit=limit, offset=offset)
    return HistoryMessagesResponse(
        session_id=session_id,
        messages=[
            HistoryMessagePayload(
                role=message.role,
                content=message.content,
                created_at=message.created_at,
                stored_at=message.stored_at,
            )
            for message in messages
        ],
        limit=limit,
        offset=offset,
        count=len(messages),
    )


class ConfigFieldUpdate(BaseModel):
    """Request model for updating a single config field."""

    field: str = Field(..., description="Configuration field name to update.")
    value: Any = Field(..., description="New value for the configuration field.")


class ConfigResponse(BaseModel):
    """Response model containing the current configuration."""

    config: dict[str, Any] = Field(description="Current configuration values.")
    file_path: str = Field(description="Path to the configuration file.")
    available_fields: list[str] = Field(
        description="List of configurable field names.",
    )


@router.get(
    "/config",
    response_model=ConfigResponse,
    summary="Get current configuration",
    response_description="Current application configuration settings.",
)
async def get_configuration(_: str = Depends(require_admin_token)) -> ConfigResponse:
    """Return the current application configuration."""
    from pathlib import Path
    import yaml

    settings = get_settings()

    # Try to find the config file
    config_path = None
    config_data = {}

    # Check if APP_CONFIG_FILE is set
    import os

    configured_path = os.getenv("APP_CONFIG_FILE")
    if configured_path:
        config_path = Path(configured_path)
    else:
        # Use the discovery logic from Settings
        from .config import _DEFAULT_CONFIG_CANDIDATES

        for candidate in _DEFAULT_CONFIG_CANDIDATES:
            if candidate.exists():
                config_path = candidate
                break

    if config_path and config_path.exists():
        config_data = yaml.safe_load(config_path.read_text()) or {}
    else:
        # Return empty config if no file found
        config_path = Path(__file__).parent / "config" / "app.config.yaml"

    # Get all available fields from Settings model
    available_fields = list(settings.model_fields.keys())

    return ConfigResponse(
        config=config_data,
        file_path=str(config_path),
        available_fields=available_fields,
    )


@router.put(
    "/config",
    response_model=dict[str, str],
    summary="Update configuration field",
    response_description="Confirmation of configuration update.",
)
async def update_configuration(
    update: ConfigFieldUpdate,
    _: str = Depends(require_admin_token),
) -> dict[str, str]:
    """Update a single configuration field in the YAML file."""
    from pathlib import Path
    import yaml
    import os

    settings = get_settings()

    # Validate that the field exists in Settings
    if update.field not in settings.model_fields:
        raise APIError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_field",
            message=f"Configuration field '{update.field}' is not valid.",
        )

    # Find the config file
    config_path = None
    configured_path = os.getenv("APP_CONFIG_FILE")
    if configured_path:
        config_path = Path(configured_path)
    else:
        from .config import _DEFAULT_CONFIG_CANDIDATES

        for candidate in _DEFAULT_CONFIG_CANDIDATES:
            if candidate.exists():
                config_path = candidate
                break

    if not config_path or not config_path.exists():
        # Create new config file
        config_path = Path(__file__).parent / "config" / "app.config.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_data = {}
    else:
        config_data = yaml.safe_load(config_path.read_text()) or {}

    # Update the field
    config_data[update.field] = update.value

    # Write back to file
    config_path.write_text(yaml.dump(config_data, allow_unicode=True, sort_keys=False))

    return {"message": f"Configuration field '{update.field}' updated successfully."}


__all__ = ["require_admin_token", "router"]
