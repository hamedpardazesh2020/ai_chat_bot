"""Async OpenAI chat completion provider."""

from __future__ import annotations

from typing import Any, Dict, Mapping, MutableMapping, Optional, Sequence

import httpx

from ..manager import ChatMessage, ChatProvider, ChatResponse, ProviderError
from ...config import get_settings

__all__ = [
    "OpenAIProviderError",
    "OpenAIChatProvider",
]


class OpenAIProviderError(ProviderError):
    """Raised when the OpenAI provider encounters an error."""


class OpenAIChatProvider(ChatProvider):
    """Implementation of the :class:`ChatProvider` protocol for OpenAI."""

    name = "openai"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: str = "gpt-3.5-turbo",
        base_url: str = "https://api.openai.com",
        timeout: Optional[float] = None,
        client: Optional[httpx.AsyncClient] = None,
        default_headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        settings = get_settings()

        self._api_key = api_key or settings.openai_api_key
        if not self._api_key:
            raise OpenAIProviderError("OpenAI API key is required to use the provider.")

        self._model = model
        self._timeout = timeout or settings.provider_timeout_seconds
        self._base_url = base_url.rstrip("/")
        self._client_owner = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
        )

        headers: MutableMapping[str, str] = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if default_headers:
            headers.update(default_headers)
        self._headers = headers

    async def chat(self, messages: Sequence[ChatMessage], **options: Any) -> ChatResponse:
        """Generate a chat completion using OpenAI's API."""

        if not messages:
            raise OpenAIProviderError("At least one message is required to call OpenAI.")

        payload: Dict[str, Any] = {
            "model": options.pop("model", self._model),
            "messages": [self._serialise_message(message) for message in messages],
        }
        payload.update(options)

        try:
            response = await self._client.post(
                "/v1/chat/completions",
                json=payload,
                headers=self._headers,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:  # pragma: no cover - defensive logging path
            detail = self._extract_error_detail(exc.response)
            raise OpenAIProviderError(
                f"OpenAI API error {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.HTTPError as exc:
            raise OpenAIProviderError("Error communicating with the OpenAI API.") from exc

        data = response.json()
        try:
            first_choice = data["choices"][0]
            message_payload = first_choice["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenAIProviderError("Unexpected response payload from OpenAI API.") from exc

        chat_message = ChatMessage(
            role=message_payload.get("role", "assistant"),
            content=message_payload.get("content", ""),
            name=message_payload.get("name"),
            metadata=self._build_message_metadata(first_choice),
        )

        usage = data.get("usage")
        raw_payload = data if isinstance(data, Mapping) else None

        return ChatResponse(message=chat_message, raw=raw_payload, usage=usage)

    async def aclose(self) -> None:
        """Close the underlying HTTP client when owned by the provider."""

        if self._client_owner:
            await self._client.aclose()

    async def __aenter__(self) -> "OpenAIChatProvider":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()

    @staticmethod
    def _serialise_message(message: ChatMessage) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "role": message.role,
            "content": message.content,
        }
        if message.name:
            payload["name"] = message.name
        if message.metadata:
            payload.update({k: v for k, v in message.metadata.items() if k not in payload})
        return payload

    @staticmethod
    def _build_message_metadata(choice: Mapping[str, Any]) -> Mapping[str, Any]:
        metadata: Dict[str, Any] = {}
        finish_reason = choice.get("finish_reason")
        if finish_reason is not None:
            metadata["finish_reason"] = finish_reason

        if "content_filter_results" in choice:
            metadata["content_filter_results"] = choice["content_filter_results"]

        return metadata

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:  # pragma: no cover - non-JSON response
            return response.text

        if isinstance(data, Mapping):
            error = data.get("error")
            if isinstance(error, Mapping):
                message = error.get("message")
                if isinstance(message, str):
                    return message
        return response.text
