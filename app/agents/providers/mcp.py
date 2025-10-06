"""Asynchronous Model Context Protocol (MCP) provider implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping, Optional, Sequence

import httpx

from ..manager import ChatMessage, ChatProvider, ChatResponse, ProviderError
from ...config import get_settings

__all__ = [
    "MCPProviderError",
    "MCPHandshakeError",
    "MCPClient",
    "MCPChatProvider",
]


class MCPProviderError(ProviderError):
    """Raised when the MCP provider encounters a recoverable error."""


class MCPHandshakeError(MCPProviderError):
    """Raised when the MCP handshake fails."""


@dataclass(slots=True)
class MCPHandshakeResponse:
    """Container for data returned by the MCP handshake."""

    data: Mapping[str, Any]


class MCPClient:
    """Thin asynchronous HTTP client for interacting with an MCP server."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
        timeout: Optional[float] = None,
        client_name: str = "chat-backend",
        client_version: str = "1.0.0",
        handshake_endpoint: str = "/handshake",
        tool_invoke_template: str = "/tools/{tool_name}/invoke",
        default_headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client_owner = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
        )
        self._client_name = client_name
        self._client_version = client_version
        self._handshake_endpoint = handshake_endpoint
        self._tool_invoke_template = tool_invoke_template
        self._api_key = api_key

        headers: MutableMapping[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if default_headers:
            headers.update(default_headers)
        self._headers = headers

        self._handshake_result: Optional[MCPHandshakeResponse] = None

    async def handshake(self, *, force: bool = False) -> MCPHandshakeResponse:
        """Perform the MCP handshake, caching the server response."""

        if self._handshake_result is not None and not force:
            return self._handshake_result

        payload = {
            "client_name": self._client_name,
            "client_version": self._client_version,
        }

        try:
            response = await self._client.post(
                self._handshake_endpoint,
                json=payload,
                headers=self._headers,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise MCPHandshakeError(
                f"Handshake rejected with status {exc.response.status_code}."
            ) from exc
        except httpx.HTTPError as exc:
            raise MCPHandshakeError("Error communicating with MCP server during handshake.") from exc

        data = response.json()
        if not isinstance(data, Mapping):
            raise MCPHandshakeError("Unexpected handshake payload from MCP server.")

        self._handshake_result = MCPHandshakeResponse(data=data)
        return self._handshake_result

    async def call_tool(
        self,
        tool_name: str,
        payload: Mapping[str, Any],
        *,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Mapping[str, Any]:
        """Invoke a remote tool exposed by the MCP server."""

        if not tool_name:
            raise MCPProviderError("tool_name is required to call an MCP tool.")

        await self.handshake()

        request_headers: MutableMapping[str, str] = dict(self._headers)
        if headers:
            request_headers.update(headers)

        endpoint = self._tool_invoke_template.format(tool_name=tool_name)

        try:
            response = await self._client.post(endpoint, json=payload, headers=request_headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise MCPProviderError(
                f"MCP tool '{tool_name}' returned status {exc.response.status_code}."
            ) from exc
        except httpx.HTTPError as exc:
            raise MCPProviderError("Error communicating with MCP server while calling tool.") from exc

        data = response.json()
        if not isinstance(data, Mapping):
            raise MCPProviderError("Unexpected tool response payload from MCP server.")

        return data

    async def aclose(self) -> None:
        """Close the underlying HTTP client if it is owned by this instance."""

        if self._client_owner:
            await self._client.aclose()

    async def __aenter__(self) -> "MCPClient":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()


class MCPChatProvider(ChatProvider):
    """Chat provider that delegates message handling to an MCP tool."""

    name = "mcp"

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        default_tool: str = "chat",
        client: Optional[MCPClient] = None,
        timeout: Optional[float] = None,
    ) -> None:
        settings = get_settings()

        server_url = (base_url or settings.mcp_server_url or "").strip()
        if not server_url:
            raise MCPProviderError("MCP server URL is required to use the MCP provider.")

        self._default_tool = default_tool
        self._client_owner = client is None
        self._client = client or MCPClient(
            base_url=server_url,
            api_key=api_key or settings.mcp_api_key,
            timeout=timeout or settings.provider_timeout_seconds,
        )

    async def chat(self, messages: Sequence[ChatMessage], **options: Any) -> ChatResponse:
        """Invoke the configured MCP tool with the provided chat transcript."""

        if not messages:
            raise MCPProviderError("At least one message is required to call the MCP provider.")

        tool_name = options.pop("tool_name", self._default_tool)
        tool_payload = {
            "messages": [self._serialise_message(message) for message in messages],
            "options": options or None,
        }

        response_payload = await self._client.call_tool(tool_name, tool_payload)

        message_payload = self._extract_message_payload(response_payload)
        chat_message = ChatMessage(
            role=message_payload.get("role", "assistant"),
            content=message_payload.get("content", ""),
            name=message_payload.get("name"),
            metadata={k: v for k, v in message_payload.items() if k not in {"role", "content", "name"}},
        )

        usage = response_payload.get("usage") if isinstance(response_payload, Mapping) else None

        return ChatResponse(message=chat_message, raw=response_payload, usage=usage)

    async def aclose(self) -> None:
        """Close the underlying MCP client when owned by the provider."""

        if self._client_owner:
            await self._client.aclose()

    async def __aenter__(self) -> "MCPChatProvider":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()

    @staticmethod
    def _serialise_message(message: ChatMessage) -> Mapping[str, Any]:
        payload: MutableMapping[str, Any] = {
            "role": message.role,
            "content": message.content,
        }
        if message.name:
            payload["name"] = message.name
        if message.metadata:
            payload["metadata"] = dict(message.metadata)
        return payload

    @staticmethod
    def _extract_message_payload(response: Mapping[str, Any]) -> Mapping[str, Any]:
        message = response.get("message")
        if isinstance(message, Mapping):
            return message
        return response
