"""Integration with the upstream ``mcp-agent`` library."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping, Optional, Sequence, Type

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm import AugmentedLLM, RequestParams
from mcp_agent.workflows.llm.augmented_llm_openai import OpenAIAugmentedLLM
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionUserMessageParam,
)

from ..manager import ChatMessage, ChatProvider, ChatResponse, ProviderError
from ...config import Settings, get_settings

__all__ = [
    "MCPAgentProviderError",
    "MCPAgentChatProvider",
]


class MCPAgentProviderError(ProviderError):
    """Raised for configuration or runtime issues while using the MCP agent."""


@dataclass(slots=True)
class _ResolvedMessage:
    """Wrapper for translated history ready for OpenAI-compatible LLMs."""

    history: list[ChatCompletionMessageParam]
    latest: ChatCompletionMessageParam


class MCPAgentChatProvider(ChatProvider):
    """Chat provider that delegates conversation handling to ``mcp-agent``."""

    name = "mcp-agent"

    def __init__(
        self,
        *,
        server_names: Sequence[str],
        instruction: Optional[str] = None,
        llm_class: Type[AugmentedLLM] = OpenAIAugmentedLLM,
        llm_options: Optional[Mapping[str, Any]] = None,
        app: Optional[MCPApp] = None,
        default_model: Optional[str] = None,
        request_overrides: Optional[Mapping[str, Any]] = None,
    ) -> None:
        if not server_names:
            raise MCPAgentProviderError("At least one MCP server name must be configured.")

        self._server_names = list(server_names)
        self._instruction = instruction
        self._llm_class = llm_class
        self._llm_options = dict(llm_options or {})
        self._default_model = default_model
        self._request_overrides = dict(request_overrides or {})

        self._app = app or MCPApp(name="chat-backend")
        self._app_lock = asyncio.Lock()

    @classmethod
    def from_settings(cls, settings: Optional[Settings] = None) -> "MCPAgentChatProvider":
        """Construct the provider from the global :class:`Settings` instance."""

        settings = settings or get_settings()
        server_names = settings.mcp_agent_servers
        if len(server_names) < 2:
            raise MCPAgentProviderError(
                "MCP_AGENT_SERVERS must define at least two MCP servers for aggregation."
            )

        llm_identifier = settings.mcp_agent_llm_provider
        llm_class = cls._resolve_llm_class(llm_identifier)

        if llm_identifier == "openrouter":
            cls._configure_openrouter_environment(settings)

        llm_options: MutableMapping[str, Any] = {}
        default_model = settings.mcp_agent_default_model
        if default_model is None and llm_identifier == "openrouter":
            default_model = settings.openrouter_default_model

        if default_model:
            llm_options["default_model"] = default_model

        app = MCPApp(name=settings.mcp_agent_app_name, settings=settings.mcp_agent_config)

        request_overrides: MutableMapping[str, Any] = {}
        if settings.initial_system_prompt and settings.mcp_agent_instruction is None:
            instruction = settings.initial_system_prompt
        else:
            instruction = settings.mcp_agent_instruction

        if default_model:
            request_overrides["model"] = default_model

        return cls(
            server_names=server_names,
            instruction=instruction,
            llm_class=llm_class,
            llm_options=llm_options,
            app=app,
            default_model=default_model,
            request_overrides=request_overrides,
        )

    @staticmethod
    def _resolve_llm_class(identifier: str) -> Type[AugmentedLLM]:
        if identifier == "openai":
            return OpenAIAugmentedLLM
        if identifier == "openrouter":
            return OpenAIAugmentedLLM
        raise MCPAgentProviderError(
            f"Unsupported MCP agent LLM provider '{identifier}'. Supported values are 'openai' and 'openrouter'."
        )

    @staticmethod
    def _configure_openrouter_environment(settings: Settings) -> None:
        api_key = settings.openrouter_key
        if not api_key:
            raise MCPAgentProviderError(
                "OPENROUTER_KEY must be configured when MCP_AGENT_LLM is set to 'openrouter'."
            )

        os.environ["OPENAI_API_KEY"] = api_key
        os.environ["OPENAI_BASE_URL"] = settings.openrouter_base_url

        default_model = settings.mcp_agent_default_model or settings.openrouter_default_model
        if default_model:
            os.environ["OPENAI_DEFAULT_MODEL"] = default_model

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        **options: Any,
    ) -> ChatResponse:
        if not messages:
            raise MCPAgentProviderError("At least one message is required for MCP agent interactions.")

        resolution = self._prepare_messages(messages)
        server_names = options.pop("server_names", None) or self._server_names
        if isinstance(server_names, str):
            server_names = [part.strip() for part in server_names.split(",") if part.strip()]
        if not server_names:
            raise MCPAgentProviderError("server_names cannot be empty during request resolution.")

        instruction = options.pop("instruction", self._instruction)

        async with self._app_lock:
            async with self._app.run() as running_app:
                agent = Agent(
                    name=self._app.name or "mcp-agent",  # type: ignore[arg-type]
                    instruction=instruction,
                    server_names=list(server_names),
                    context=running_app.context,
                )

                async with agent:
                    llm = await agent.attach_llm(
                        lambda agent: self._llm_class(
                            agent=agent,
                            context=running_app.context,
                            **self._llm_options,
                        )
                    )

                    if resolution.history:
                        llm.history.set(resolution.history)

                    request_params = self._build_request_params(options)
                    response_text = await llm.generate_str(
                        resolution.latest,
                        request_params=request_params,
                    )

        message = ChatMessage(role="assistant", content=response_text)
        raw_payload: MutableMapping[str, Any] = {
            "servers": list(server_names),
            "llm": self._llm_class.__name__,
        }
        if self._default_model:
            raw_payload["model"] = self._default_model

        return ChatResponse(message=message, raw=raw_payload, usage=None)

    def _prepare_messages(self, messages: Sequence[ChatMessage]) -> _ResolvedMessage:
        converted = [self._to_llm_message(message) for message in messages]
        if not converted:
            raise MCPAgentProviderError("Unable to translate conversation history for MCP agent.")

        history = converted[:-1]
        latest = converted[-1]
        return _ResolvedMessage(history=history, latest=latest)

    @staticmethod
    def _to_llm_message(message: ChatMessage) -> ChatCompletionMessageParam:
        role = (message.role or "user").strip().lower()
        content = message.content or ""

        if role == "system":
            return ChatCompletionSystemMessageParam(role="system", content=content)
        if role == "assistant":
            return ChatCompletionAssistantMessageParam(role="assistant", content=content)
        if role == "tool":
            return ChatCompletionToolMessageParam(role="tool", content=content, tool_call_id="tool")
        return ChatCompletionUserMessageParam(role="user", content=content)

    def _build_request_params(self, overrides: Mapping[str, Any]) -> RequestParams:
        params = RequestParams(**self._request_overrides)
        params.use_history = False
        for key, value in overrides.items():
            setattr(params, key, value)
        return params

    async def aclose(self) -> None:
        await self._app.cleanup()

    async def __aenter__(self) -> "MCPAgentChatProvider":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()
