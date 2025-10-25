"""Provider interfaces and registration utilities for chat agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import (
    Any,
    Dict,
    Iterable,
    Literal,
    Mapping,
    MutableMapping,
    Optional,
    Protocol,
    Sequence,
    TYPE_CHECKING,
)

if TYPE_CHECKING:  # pragma: no cover - typing only import
    from ..sessions import Session


class ProviderError(RuntimeError):
    """Base exception raised for provider related errors."""


class ProviderNotRegisteredError(ProviderError):
    """Raised when attempting to access a provider that is not registered."""


class ProviderAlreadyRegisteredError(ProviderError):
    """Raised when attempting to register a provider name that already exists."""


@dataclass(slots=True)
class ChatMessage:
    """Represents an individual chat message exchanged with a provider."""

    role: str
    """The role of the message author (e.g. ``system``, ``user``, ``assistant``)."""

    content: str
    """The textual content of the message."""

    name: Optional[str] = None
    """Optional identifier for the speaker (useful for function/tool calls)."""

    metadata: Optional[Mapping[str, Any]] = None
    """Optional provider-specific metadata for advanced behaviours."""


@dataclass(slots=True)
class ChatResponse:
    """Standardised response payload returned by chat providers."""

    message: ChatMessage
    """The assistant message returned by the provider."""

    raw: Optional[Mapping[str, Any]] = None
    """Optional raw payload from the upstream provider for diagnostics."""

    usage: Optional[Mapping[str, Any]] = None
    """Optional usage metrics such as token counts returned by the provider."""


class ChatProvider(Protocol):
    """Protocol implemented by all chat providers."""

    name: str

    async def chat(
        self, messages: Sequence[ChatMessage], **options: Any
    ) -> ChatResponse:
        """Generate a chat completion from a sequence of messages."""


class ProviderManager:
    """Maintain a registry of chat providers accessible by name."""

    def __init__(
        self,
        *,
        providers: Optional[Iterable[ChatProvider]] = None,
        default: Optional[str] = None,
    ) -> None:
        self._providers: MutableMapping[str, ChatProvider] = {}
        self._default: Optional[str] = None

        if providers:
            for provider in providers:
                self.register(provider)

        if default:
            self.set_default(default)

    @staticmethod
    def _normalise_name(name: str) -> str:
        """Normalise provider identifiers to ensure consistent lookups."""

        return name.strip().lower()

    def register(
        self,
        provider: ChatProvider,
        *,
        name: Optional[str] = None,
        replace: bool = False,
    ) -> None:
        """Register a provider instance under the given name."""

        key = self._normalise_name(name or provider.name)
        if key in self._providers and not replace:
            raise ProviderAlreadyRegisteredError(f"Provider '{key}' already registered.")

        self._providers[key] = provider

    def list_providers(self) -> list[str]:
        """Return the registered provider names in normalised form."""

        return list(self._providers.keys())

    def unregister(self, name: str) -> None:
        """Remove a provider from the registry."""

        key = self._normalise_name(name)
        if key not in self._providers:
            raise ProviderNotRegisteredError(f"Provider '{name}' is not registered.")

        del self._providers[key]

        if self._default == key:
            self._default = None

    def get(self, name: str) -> ChatProvider:
        """Retrieve a provider by name."""

        key = self._normalise_name(name)
        try:
            return self._providers[key]
        except KeyError as exc:  # pragma: no cover - defensive branch
            raise ProviderNotRegisteredError(
                f"Provider '{name}' is not registered."
            ) from exc

    def set_default(self, name: str) -> None:
        """Designate a default provider name for lookups when none provided."""

        key = self._normalise_name(name)
        if key not in self._providers:
            raise ProviderNotRegisteredError(
                f"Cannot set default provider to '{name}' because it is not registered."
            )

        self._default = key

    @property
    def default(self) -> Optional[str]:
        """Return the currently configured default provider name."""

        return self._default

    def resolve(self, name: Optional[str] = None) -> ChatProvider:
        """Resolve the provider to use, falling back to the default when needed."""

        if name is not None:
            return self.get(name)

        if self._default is None:
            raise ProviderNotRegisteredError("No provider name supplied and no default configured.")

        return self._providers[self._default]

    @dataclass(slots=True)
    class ProviderResolution:
        """Details about the selected provider for a given interaction."""

        name: str
        provider: ChatProvider
        source: Literal["override", "session", "default", "fallback"]

    def resolve_for_session(
        self,
        *,
        session_provider: Optional[str] = None,
    ) -> "ProviderManager.ProviderResolution":
        """Resolve a provider with awareness of session defaults."""

        if session_provider:
            normalised = self._normalise_name(session_provider)
            provider = self.get(normalised)
            return self.ProviderResolution(
                name=normalised,
                provider=provider,
                source="session",
            )

        if self._default is None:
            raise ProviderNotRegisteredError("No default provider configured for resolution.")

        return self.ProviderResolution(
            name=self._default,
            provider=self._providers[self._default],
            source="default",
        )

    def resolve_fallback(
        self,
        fallback_name: Optional[str],
        *,
        primary_name: Optional[str] = None,
    ) -> Optional["ProviderManager.ProviderResolution"]:
        """Resolve an optional fallback provider distinct from the primary.

        Args:
            fallback_name: The name of the fallback provider to attempt.
            primary_name: The normalised name of the primary provider. When the
                fallback matches the primary this method returns ``None`` to
                signal that no additional attempt should be made.

        Returns:
            A :class:`ProviderResolution` for the fallback provider when it is
            configured and distinct from the primary provider. ``None`` is
            returned when no fallback has been configured.

        Raises:
            ProviderNotRegisteredError: If the named fallback provider is not
                registered with the manager.
        """

        if not fallback_name:
            return None

        fallback_key = self._normalise_name(fallback_name)
        if primary_name is not None and self._normalise_name(primary_name) == fallback_key:
            return None

        provider = self.get(fallback_key)
        return self.ProviderResolution(
            name=fallback_key,
            provider=provider,
            source="fallback",
        )

    def resolve_for_request(
        self,
        *,
        session: Optional["Session"] = None,
    ) -> "ProviderManager.ProviderResolution":
        """Resolve a provider using the supplied session model when available."""

        session_provider = session.provider if session is not None else None
        return self.resolve_for_session(
            session_provider=session_provider,
        )

    def available(self) -> Dict[str, ChatProvider]:
        """Return a copy of the registered providers mapping."""

        return dict(self._providers)


__all__ = [
    "ChatMessage",
    "ChatProvider",
    "ChatResponse",
    "ProviderAlreadyRegisteredError",
    "ProviderError",
    "ProviderManager",
    "ProviderManager.ProviderResolution",
    "ProviderNotRegisteredError",
]
