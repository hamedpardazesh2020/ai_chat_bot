"""Minimal asynchronous example interacting with the Chat Agent API."""
from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

API_URL = os.getenv("CHAT_API_URL", "http://localhost:8000")
DEFAULT_MESSAGE = os.getenv("CHAT_USER_MESSAGE", "Hello there!")
DEFAULT_PROVIDER = os.getenv("CHAT_PROVIDER", "openai")


async def main() -> None:
    """Create a session, exchange a single message, and clean up."""

    async with httpx.AsyncClient(base_url=API_URL, timeout=30.0) as client:
        session_payload: dict[str, Any] = {
            "provider": DEFAULT_PROVIDER or None,
        }
        response = await client.post("/sessions", json=session_payload)
        if not response.is_success:
            raise RuntimeError(
                f"Failed to create session: {response.status_code} {response.text}"
            )

        session = response.json()
        session_id = session["id"]
        print(f"Created session {session_id} using provider {session.get('provider')}")

        try:
            message_payload: dict[str, Any] = {
                "content": DEFAULT_MESSAGE,
            }
            message_response = await client.post(
                f"/sessions/{session_id}/messages",
                json=message_payload,
            )
            if message_response.is_success:
                payload = message_response.json()
                assistant = payload["message"]["content"]
                print(f"Assistant replied: {assistant}")
            else:
                print(
                    "Message request failed:",
                    message_response.status_code,
                    message_response.text,
                )
        finally:
            delete_response = await client.delete(f"/sessions/{session_id}")
            if delete_response.status_code == 204:
                print("Session deleted.")
            elif delete_response.status_code == 404:
                print("Session was already removed.")
            else:
                delete_response.raise_for_status()


if __name__ == "__main__":
    asyncio.run(main())
