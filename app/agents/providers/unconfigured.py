"""Fallback provider used when no external chat provider is configured."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..manager import ChatMessage, ChatResponse, ProviderError


class UnconfiguredProviderError(ProviderError):
    """Error raised when the unconfigured provider is invoked."""


@dataclass(slots=True)
class UnconfiguredChatProvider:
    """Provider placeholder that fails with a descriptive error message."""

    name: str = "unconfigured"

    async def chat(
        self, messages: Sequence[ChatMessage], **options: object
    ) -> ChatResponse:  # type: ignore[override]
        raise UnconfiguredProviderError(
            "No chat providers are configured. Set OPENROUTER_KEY or another provider "
            "credential before sending chat requests."
        )
