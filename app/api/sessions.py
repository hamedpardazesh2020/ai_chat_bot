"""Sessions API routes for managing chat conversations."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field

from ..agents.manager import (
    ChatMessage as ProviderChatMessage,
    ProviderError,
    ProviderManager,
    ProviderNotRegisteredError,
)
from ..config import get_settings
from ..dependencies import (
    ChatMemory,
    HistoryStore,
    get_chat_memory,
    get_history_store,
    get_provider_manager,
    get_session_store,
)
from ..errors import APIError
from ..memory import ChatMessage as MemoryChatMessage, InvalidMemoryLimitError
from ..sessions import InMemorySessionStore, Session, SessionNotFoundError

router = APIRouter(prefix="/sessions", tags=["sessions"])

logger = logging.getLogger("app.api.sessions")


class SessionCreateRequest(BaseModel):
    """Request payload for creating a new chat session."""

    memory_limit: Optional[int] = Field(
        default=None,
        ge=1,
        description="Override for the number of messages to retain for the session.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary metadata to associate with the session.",
    )


class SessionResponse(BaseModel):
    """Representation of a chat session returned to API consumers."""

    id: UUID
    memory_limit: Optional[int] = None
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessagePayload(BaseModel):
    """Representation of a chat message returned to API consumers."""

    role: str
    content: str
    created_at: datetime
    metadata: dict[str, Any] | None = None


class MessageRequest(BaseModel):
    """Request schema for posting a chat message to a session."""

    content: str = Field(..., min_length=1, description="Content of the user message.")
    role: str = Field(
        default="user",
        description="Role associated with the message (defaults to 'user').",
    )
    memory_limit: Optional[int] = Field(
        default=None,
        ge=1,
        description="Optional override for the number of messages to retain.",
    )
    options: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional provider-specific options to forward.",
    )


class MessageResponse(BaseModel):
    """Response returned after sending a chat message."""

    session_id: UUID
    message: MessagePayload
    usage: dict[str, Any] | None = None
    history: list[MessagePayload]


def _session_to_payload(session: Session) -> SessionResponse:
    """Convert a session domain model into the API response representation."""

    return SessionResponse(
        id=session.id,
        memory_limit=session.memory_limit,
        created_at=session.created_at,
        metadata=dict(session.metadata),
    )


def _memory_to_provider(message: MemoryChatMessage) -> ProviderChatMessage:
    """Translate a memory message into a provider compatible message."""

    return ProviderChatMessage(role=message.role, content=message.content)


def _memory_to_payload(message: MemoryChatMessage) -> MessagePayload:
    """Convert a memory message into the API payload representation."""

    return MessagePayload(
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        metadata=None,
    )


def _provider_to_payload(message: ProviderChatMessage) -> MessagePayload:
    """Convert a provider message into the API payload representation."""

    metadata = dict(message.metadata) if isinstance(message.metadata, Mapping) else None
    return MessagePayload(
        role=message.role,
        content=message.content,
        created_at=datetime.now(timezone.utc),
        metadata=metadata,
    )


async def _persist_session_metadata(
    history_store: HistoryStore, session: Session
) -> None:
    try:
        await history_store.record_session(session)
    except Exception:  # pragma: no cover - defensive logging
        logger.exception(
            "history_store_session_failed",
            extra={"event": "history_store_session_failed", "session_id": str(session.id)},
        )


async def _persist_messages(
    history_store: HistoryStore, session_id: UUID, messages: Sequence[MemoryChatMessage]
) -> None:
    if not messages:
        return
    try:
        await history_store.record_messages(session_id, list(messages))
    except Exception:  # pragma: no cover - defensive logging
        logger.exception(
            "history_store_messages_failed",
            extra={"event": "history_store_messages_failed", "session_id": str(session_id)},
        )


async def _remove_history(history_store: HistoryStore, session_id: UUID) -> None:
    try:
        await history_store.delete_session(session_id)
    except Exception:  # pragma: no cover - defensive logging
        logger.exception(
            "history_store_delete_failed",
            extra={"event": "history_store_delete_failed", "session_id": str(session_id)},
        )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=SessionResponse,
    summary="Create a chat session",
    response_description="Metadata describing the newly created session.",
)
async def create_session(
    request: SessionCreateRequest,
    store: InMemorySessionStore = Depends(get_session_store),
    memory: ChatMemory = Depends(get_chat_memory),
    providers: ProviderManager = Depends(get_provider_manager),
    history_store: HistoryStore = Depends(get_history_store),
) -> SessionResponse:
    """Create a new chat session with optional provider preferences."""

    settings = get_settings()
    if request.memory_limit is not None:
        if request.memory_limit < 1:
            raise APIError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_memory_limit",
                message="Memory limit must be at least 1.",
            )
        if request.memory_limit > settings.memory_limit:
            raise APIError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_memory_limit",
                message="Requested memory limit exceeds the allowed maximum.",
                details={
                    "requested": request.memory_limit,
                    "maximum": settings.memory_limit,
                },
            )

    try:
        default_resolution = providers.resolve_for_session()
    except ProviderNotRegisteredError as exc:
        raise APIError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="provider_not_available",
            message=str(exc),
        ) from exc

    session = await store.create_session(
        provider=default_resolution.name,
        fallback_provider=None,
        memory_limit=request.memory_limit,
        metadata=request.metadata,
    )

    await _persist_session_metadata(history_store, session)

    initial_prompt = settings.initial_system_prompt
    if initial_prompt:
        system_message = MemoryChatMessage(role="system", content=initial_prompt)
        try:
            await memory.append(
                session.id,
                system_message,
                limit_override=session.memory_limit,
            )
        except InvalidMemoryLimitError as exc:
            raise APIError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_memory_limit",
                message=str(exc),
            ) from exc
        await _persist_messages(history_store, session.id, [system_message])

    logger.info(
        "session_created",
        extra={
            "event": "session_created",
            "session_id": str(session.id),
            "provider": session.provider,
            "fallback_provider": session.fallback_provider,
        },
    )

    return _session_to_payload(session)


@router.post(
    "/{session_id}/messages",
    response_model=MessageResponse,
    summary="Send a chat message",
    response_description="Assistant reply and updated session history.",
)
async def post_message(
    session_id: UUID,
    request: MessageRequest,
    store: InMemorySessionStore = Depends(get_session_store),
    memory: ChatMemory = Depends(get_chat_memory),
    providers: ProviderManager = Depends(get_provider_manager),
    history_store: HistoryStore = Depends(get_history_store),
) -> MessageResponse:
    """Handle a new chat message for the given session."""

    try:
        session = await store.get_session(session_id)
    except SessionNotFoundError as exc:
        logger.info(
            "session_not_found",
            extra={"event": "session_not_found", "session_id": str(session_id)},
        )
        raise APIError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="session_not_found",
            message=str(exc),
        ) from exc

    limit_override = request.memory_limit or session.memory_limit
    settings = get_settings()
    if limit_override is not None:
        if limit_override < 1:
            raise APIError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_memory_limit",
                message="Memory limit must be at least 1.",
            )
        if limit_override > settings.memory_limit:
            raise APIError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_memory_limit",
                message="Requested memory limit exceeds the allowed maximum.",
                details={
                    "requested": limit_override,
                    "maximum": settings.memory_limit,
                },
            )

    history = await memory.get(session_id)
    provider_messages = [_memory_to_provider(message) for message in history]
    provider_messages.append(ProviderChatMessage(role=request.role, content=request.content))

    try:
        resolution = providers.resolve_for_request(
            session=session,
        )
    except ProviderNotRegisteredError as exc:
        raise APIError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="provider_not_found",
            message=str(exc),
        ) from exc

    active_resolution = resolution
    try:
        response = await resolution.provider.chat(provider_messages, **request.options)
    except ProviderError as primary_error:
        try:
            fallback_resolution = providers.resolve_fallback(
                session.fallback_provider,
                primary_name=resolution.name,
            )
        except ProviderNotRegisteredError as fallback_exc:
            logger.error(
                "fallback_not_registered",
                extra={
                    "event": "fallback_not_registered",
                    "provider": resolution.name,
                    "fallback_provider": session.fallback_provider,
                    "session_id": str(session_id),
                },
            )
            raise APIError(
                status_code=status.HTTP_502_BAD_GATEWAY,
                code="provider_error",
                message="Primary provider failed and fallback provider is not available.",
                details={
                    "provider": resolution.name,
                    "source": resolution.source,
                    "fallback_provider": session.fallback_provider,
                },
            ) from primary_error

        if fallback_resolution is None:
            logger.error(
                "provider_error",
                extra={
                    "event": "provider_error",
                    "provider": resolution.name,
                    "session_id": str(session_id),
                    "fallback_provider": session.fallback_provider,
                },
            )
            raise APIError(
                status_code=status.HTTP_502_BAD_GATEWAY,
                code="provider_error",
                message=str(primary_error),
                details={
                    "provider": resolution.name,
                    "source": resolution.source,
                    "fallback_provider": session.fallback_provider,
                },
            ) from primary_error

        try:
            response = await fallback_resolution.provider.chat(
                provider_messages,
                **request.options,
            )
        except ProviderError as fallback_error:
            logger.error(
                "provider_fallback_failed",
                extra={
                    "event": "provider_fallback_failed",
                    "provider": resolution.name,
                    "fallback_provider": fallback_resolution.name,
                    "session_id": str(session_id),
                },
            )
            raise APIError(
                status_code=status.HTTP_502_BAD_GATEWAY,
                code="provider_error",
                message=str(fallback_error),
                details={
                    "provider": resolution.name,
                    "source": resolution.source,
                    "fallback_provider": fallback_resolution.name,
                },
            ) from fallback_error

        logger.warning(
            "provider_fallback_used",
            extra={
                "event": "provider_fallback_used",
                "provider": resolution.name,
                "fallback_provider": fallback_resolution.name,
                "session_id": str(session_id),
            },
        )
        active_resolution = fallback_resolution

    user_memory_message = MemoryChatMessage(role=request.role, content=request.content)
    assistant_message = response.message
    assistant_memory_message = MemoryChatMessage(
        role=assistant_message.role,
        content=assistant_message.content,
    )

    try:
        await memory.append(
            session_id,
            user_memory_message,
            limit_override=limit_override,
        )
        await memory.append(
            session_id,
            assistant_memory_message,
            limit_override=limit_override,
        )
    except InvalidMemoryLimitError as exc:
        raise APIError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_memory_limit",
            message=str(exc),
        ) from exc

    await _persist_messages(
        history_store,
        session_id,
        [user_memory_message, assistant_memory_message],
    )

    final_history = await memory.get(session_id)

    return MessageResponse(
        session_id=session.id,
        message=_provider_to_payload(assistant_message),
        usage=dict(response.usage) if isinstance(response.usage, Mapping) else None,
        history=[_memory_to_payload(message) for message in final_history],
    )


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a chat session",
    response_description="Session memory and metadata are removed.",
)
async def delete_session(
    session_id: UUID,
    store: InMemorySessionStore = Depends(get_session_store),
    memory: ChatMemory = Depends(get_chat_memory),
    history_store: HistoryStore = Depends(get_history_store),
) -> Response:
    """Delete an existing session and clear associated memory."""

    try:
        await store.delete_session(session_id)
    except SessionNotFoundError as exc:
        logger.info(
            "session_delete_not_found",
            extra={"event": "session_delete_not_found", "session_id": str(session_id)},
        )
        raise APIError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="session_not_found",
            message=str(exc),
        ) from exc

    await memory.clear(session_id)
    await _remove_history(history_store, session_id)
    logger.info(
        "session_deleted",
        extra={"event": "session_deleted", "session_id": str(session_id)},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
