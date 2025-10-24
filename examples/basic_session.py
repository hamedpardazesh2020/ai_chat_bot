"""Minimal asynchronous example interacting with the Chat Agent API."""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any, Mapping

import httpx


@dataclass(slots=True)
class ExampleConfig:
    """Configuration loaded from environment variables for the sample script."""

    api_url: str = "http://localhost:8000"
    message: str = "Hello there!"
    message_role: str = "user"
    provider: str | None = None
    fallback_provider: str | None = None
    session_memory_limit: int | None = None
    session_metadata: dict[str, Any] = field(default_factory=dict)
    message_provider: str | None = None
    message_memory_limit: int | None = None
    message_options: dict[str, Any] = field(default_factory=dict)
    timeout: float = 30.0

    @classmethod
    def from_env(cls) -> "ExampleConfig":
        """Build a configuration instance by parsing known environment variables."""

        def _parse_int(value: str | None, name: str) -> int | None:
            if value in {None, ""}:
                return None
            try:
                return int(value)
            except ValueError as exc:  # pragma: no cover - defensive guard for examples
                raise RuntimeError(f"{name} must be an integer") from exc

        def _parse_float(value: str | None, name: str, *, default: float) -> float:
            if value in {None, ""}:
                return default
            try:
                return float(value)
            except ValueError as exc:  # pragma: no cover - defensive guard for examples
                raise RuntimeError(f"{name} must be numeric") from exc

        def _parse_mapping(value: str | None, name: str) -> dict[str, Any]:
            if value in {None, ""}:
                return {}
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError as exc:  # pragma: no cover - defensive guard for examples
                raise RuntimeError(f"{name} must be valid JSON") from exc
            if not isinstance(parsed, Mapping):  # pragma: no cover - defensive guard for examples
                raise RuntimeError(f"{name} must decode to a JSON object")
            return dict(parsed)

        return cls(
            api_url=os.getenv("CHAT_API_URL", "http://localhost:8000"),
            message=os.getenv("CHAT_USER_MESSAGE", "Hello there!"),
            message_role=os.getenv("CHAT_MESSAGE_ROLE", "user") or "user",
            provider=os.getenv("CHAT_PROVIDER") or None,
            fallback_provider=os.getenv("CHAT_FALLBACK_PROVIDER") or None,
            session_memory_limit=_parse_int(os.getenv("CHAT_MEMORY_LIMIT"), "CHAT_MEMORY_LIMIT"),
            session_metadata=_parse_mapping(os.getenv("CHAT_SESSION_METADATA"), "CHAT_SESSION_METADATA"),
            message_provider=os.getenv("CHAT_MESSAGE_PROVIDER") or None,
            message_memory_limit=_parse_int(
                os.getenv("CHAT_MESSAGE_MEMORY_LIMIT"),
                "CHAT_MESSAGE_MEMORY_LIMIT",
            ),
            message_options=_parse_mapping(os.getenv("CHAT_MESSAGE_OPTIONS"), "CHAT_MESSAGE_OPTIONS"),
            timeout=_parse_float(os.getenv("CHAT_REQUEST_TIMEOUT"), "CHAT_REQUEST_TIMEOUT", default=30.0),
        )


async def main(config: ExampleConfig) -> None:
    """Create a session, exchange a single message, and clean up."""

    async with httpx.AsyncClient(base_url=config.api_url, timeout=config.timeout) as client:
        session_payload: dict[str, Any] = {}
        if config.provider:
            session_payload["provider"] = config.provider
        if config.fallback_provider:
            session_payload["fallback_provider"] = config.fallback_provider
        if config.session_memory_limit is not None:
            session_payload["memory_limit"] = config.session_memory_limit
        if config.session_metadata:
            session_payload["metadata"] = config.session_metadata

        response = await client.post("/sessions", json=session_payload)
        if not response.is_success:
            raise RuntimeError(
                f"Failed to create session: {response.status_code} {response.text}"
            )

        session = response.json()
        session_id = session["id"]
        provider = session.get("provider") or "<service default>"
        fallback = session.get("fallback_provider") or "<none>"
        print(
            f"Created session {session_id} with provider {provider} and fallback {fallback}"
        )

        try:
            message_payload: dict[str, Any] = {
                "content": config.message,
                "role": config.message_role,
            }
            if config.message_provider:
                message_payload["provider"] = config.message_provider
            if config.message_memory_limit is not None:
                message_payload["memory_limit"] = config.message_memory_limit
            if config.message_options:
                message_payload["options"] = config.message_options

            message_response = await client.post(
                f"/sessions/{session_id}/messages",
                json=message_payload,
            )
            if not message_response.is_success:
                raise RuntimeError(
                    "Message request failed: "
                    f"{message_response.status_code} {message_response.text}"
                )

            payload = message_response.json()
            assistant = payload["message"]["content"]
            provider_name = payload.get("provider")
            provider_source = payload.get("provider_source")
            print(
                f"Assistant replied (provider={provider_name}, source={provider_source}):"
            )
            print(assistant)
            if usage := payload.get("usage"):
                print("Usage metrics:")
                for key, value in usage.items():
                    print(f"  {key}: {value}")
        finally:
            delete_response = await client.delete(f"/sessions/{session_id}")
            if delete_response.status_code == 204:
                print("Session deleted.")
            elif delete_response.status_code == 404:
                print("Session was already removed.")
            else:
                delete_response.raise_for_status()


if __name__ == "__main__":
    asyncio.run(main(ExampleConfig.from_env()))
