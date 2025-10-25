"""Application configuration utilities."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources.providers.env import EnvSettingsSource
from pydantic_settings.sources.providers.dotenv import DotEnvSettingsSource
from pydantic_settings.sources.types import ForceDecode, NoDecode

try:  # pragma: no cover - optional dependency
    import yaml
except Exception:  # pragma: no cover - PyYAML may not be installed
    yaml = None  # type: ignore


class _SafeDecodeMixin:
    """Mixin that relaxes JSON decoding for blank or invalid complex values."""

    def decode_complex_value(self, field_name: str, field: FieldInfo, value: Any) -> Any:  # type: ignore[override]
        if field and (
            NoDecode in field.metadata
            or (self.config.get("enable_decoding") is False and ForceDecode not in field.metadata)
        ):
            return value

        if isinstance(value, (bytes, bytearray)):
            value = value.decode()

        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                # Treat empty strings as an explicit empty value so downstream validators
                # can normalise them without Pydantic attempting JSON decoding.
                return ""
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return value

        return value


class _SafeEnvSettingsSource(_SafeDecodeMixin, EnvSettingsSource):
    """Environment settings source tolerant to non-JSON complex values."""


class _SafeDotEnvSettingsSource(_SafeDecodeMixin, DotEnvSettingsSource):
    """Dotenv settings source with forgiving complex value parsing."""


_PACKAGE_ROOT = Path(__file__).resolve().parent
_PROJECT_ROOT = _PACKAGE_ROOT.parent

_DEFAULT_CONFIG_CANDIDATES: tuple[Path, ...] = (
    _PACKAGE_ROOT / "app.config.yaml",
    _PACKAGE_ROOT / "app.config.yml",
    _PACKAGE_ROOT / "app.config.example.yaml",
    _PACKAGE_ROOT / "app.config.example.yml",
    _PROJECT_ROOT / "app.config.yaml",
    _PROJECT_ROOT / "app.config.yml",
    _PROJECT_ROOT / "app.config.example.yaml",
    _PROJECT_ROOT / "app.config.example.yml",
    _PROJECT_ROOT / "config" / "app.config.yaml",
    _PROJECT_ROOT / "config" / "app.config.yml",
    _PROJECT_ROOT / "config" / "app.config.example.yaml",
    _PROJECT_ROOT / "config" / "app.config.example.yml",
    _PROJECT_ROOT / "config.yaml",
    _PROJECT_ROOT / "config.yml",
)


class Settings(BaseSettings):
    """Central application settings loaded from environment variables.

    The settings object exposes all configurable knobs for the service. Values are
    primarily sourced from environment variables (optionally loaded via a local
    ``.env`` file). A YAML configuration file can also be provided by setting the
    ``APP_CONFIG_FILE`` environment variable, allowing deployment-specific
    overrides without editing the environment directly.
    """

    admin_token: Optional[str] = Field(default=None, env="ADMIN_TOKEN")
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    openrouter_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "openrouter_key", "OPENROUTER_KEY", "OPENROUTER_API_KEY"
        ),
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", env="OPENROUTER_BASE_URL"
    )
    openrouter_default_model: str = Field(
        default="openrouter/auto", env="OPENROUTER_MODEL"
    )
    default_provider_name: str = Field(
        default="mcp-agent", env="DEFAULT_PROVIDER"
    )
    mcp_server_url: Optional[str] = Field(default=None, env="MCP_SERVER_URL")
    mcp_api_key: Optional[str] = Field(default=None, env="MCP_API_KEY")
    mcp_agent_config: Optional[str] = Field(default=None, env="MCP_AGENT_CONFIG")
    mcp_agent_servers: list[str] = Field(
        default_factory=list,
        env="MCP_AGENT_SERVERS",
        metadata=[NoDecode()],
    )
    mcp_agent_app_name: str = Field(default="chat-backend", env="MCP_AGENT_APP_NAME")
    mcp_agent_instruction: Optional[str] = Field(
        default=None, env="MCP_AGENT_INSTRUCTION"
    )
    mcp_agent_llm_provider: str = Field(
        default="openrouter",
        validation_alias=AliasChoices("MCP_AGENT_LLM", "MCP_AGENT_LLM_PROVIDER"),
    )
    mcp_agent_default_model: Optional[str] = Field(
        default=None, env="MCP_AGENT_MODEL"
    )
    initial_system_prompt: Optional[str] = Field(
        default=None,
        env="INITIAL_SYSTEM_PROMPT",
        description="Optional system prompt injected when a new session is created.",
    )

    redis_url: Optional[str] = Field(default=None, env="REDIS_URL")

    history_storage_backend: str = Field(
        default="none", env="HISTORY_STORAGE_BACKEND"
    )
    history_namespace: str = Field(default="chat_history", env="HISTORY_NAMESPACE")
    history_mysql_host: str = Field(default="localhost", env="HISTORY_MYSQL_HOST")
    history_mysql_port: int = Field(default=3306, env="HISTORY_MYSQL_PORT")
    history_mysql_user: Optional[str] = Field(
        default=None, env="HISTORY_MYSQL_USER"
    )
    history_mysql_password: Optional[str] = Field(
        default=None, env="HISTORY_MYSQL_PASSWORD"
    )
    history_mysql_database: Optional[str] = Field(
        default=None, env="HISTORY_MYSQL_DATABASE"
    )
    history_mysql_session_table: str = Field(
        default="chat_sessions", env="HISTORY_MYSQL_SESSION_TABLE"
    )
    history_mysql_message_table: str = Field(
        default="chat_messages", env="HISTORY_MYSQL_MESSAGE_TABLE"
    )
    history_mongodb_uri: str = Field(
        default="mongodb://localhost:27017", env="HISTORY_MONGODB_URI"
    )
    history_mongodb_database: str = Field(
        default="chat_history", env="HISTORY_MONGODB_DATABASE"
    )
    history_mongodb_session_collection: str = Field(
        default="chat_sessions", env="HISTORY_MONGODB_SESSION_COLLECTION"
    )
    history_mongodb_message_collection: str = Field(
        default="chat_messages", env="HISTORY_MONGODB_MESSAGE_COLLECTION"
    )
    history_redis_url: Optional[str] = Field(
        default=None, env="HISTORY_REDIS_URL"
    )

    rate_rps: float = Field(default=1.0, env="RATE_RPS")
    rate_burst: int = Field(default=5, env="RATE_BURST")

    memory_default: int = Field(default=10, env="MEMORY_DEFAULT")
    memory_max: int = Field(default=50, env="MEMORY_MAX")

    metrics_enabled: bool = Field(default=True, env="METRICS_ENABLED")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    provider_timeout_seconds: float = Field(
        default=30.0, env="PROVIDER_TIMEOUT_SECONDS"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        """Inject a YAML settings source between init values and environment variables."""

        return (
            init_settings,
            _SafeEnvSettingsSource(settings_cls),
            _SafeDotEnvSettingsSource(settings_cls),
            cls.yaml_config_settings_source,
            file_secret_settings,
        )

    @staticmethod
    def yaml_config_settings_source() -> Dict[str, Any]:
        """Load settings from a YAML file when configured or available locally."""

        configured_path = os.getenv("APP_CONFIG_FILE")
        candidate: Optional[Path]
        if configured_path:
            candidate = Path(configured_path)
            if not candidate.exists():
                raise FileNotFoundError(
                    f"Config file '{configured_path}' was not found."
                )
        else:
            candidate = Settings._discover_default_config_file()
            if candidate is None:
                return {}

        if candidate.suffix.lower() not in {".yml", ".yaml"}:
            raise ValueError("Unsupported config format. Expected a .yml or .yaml file.")

        if yaml is None:
            raise RuntimeError(
                "PyYAML is required to load YAML configuration files but is not installed."
            )

        data = yaml.safe_load(candidate.read_text()) or {}
        if not isinstance(data, dict):
            raise ValueError("YAML configuration must define a mapping at the root level.")
        return data

    @staticmethod
    def _discover_default_config_file() -> Optional[Path]:
        """Return the first existing config file from the default candidate list."""

        for path in _DEFAULT_CONFIG_CANDIDATES:
            if path.exists():
                return path
        return None

    @field_validator("rate_rps")
    @classmethod
    def _validate_rate_rps(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("RATE_RPS must be greater than 0.")
        return value

    @field_validator("rate_burst")
    @classmethod
    def _validate_rate_burst(cls, value: int) -> int:
        if value < 1:
            raise ValueError("RATE_BURST must be at least 1.")
        return value

    @field_validator("memory_default", "memory_max")
    @classmethod
    def _validate_memory_bounds(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Memory limits must be at least 1.")
        return value

    @model_validator(mode="after")
    def _validate_memory_relationship(self) -> "Settings":
        default = self.memory_default
        maximum = self.memory_max
        if default is not None and maximum is not None and default > maximum:
            raise ValueError("MEMORY_DEFAULT cannot exceed MEMORY_MAX.")
        return self

    @field_validator("provider_timeout_seconds")
    @classmethod
    def _validate_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("PROVIDER_TIMEOUT_SECONDS must be greater than 0.")
        return value

    @field_validator("default_provider_name", mode="before")
    @classmethod
    def _normalise_default_provider(cls, value: Any) -> str:
        if value is None:
            return "mcp-agent"
        if isinstance(value, str):
            trimmed = value.strip()
            return trimmed or "mcp-agent"
        return str(value)

    @field_validator("mcp_agent_servers", mode="before")
    @classmethod
    def _parse_mcp_servers(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, (list, tuple)):
                return [str(item).strip() for item in parsed if str(item).strip()]
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        raise ValueError("MCP_AGENT_SERVERS must be a comma-separated string or list.")

    @field_validator("mcp_agent_llm_provider", mode="before")
    @classmethod
    def _normalise_llm(cls, value: Optional[str]) -> str:
        if not value:
            return "openrouter"
        return str(value).strip().lower()

    @field_validator("history_storage_backend", mode="before")
    @classmethod
    def _normalise_history_backend(cls, value: Optional[str]) -> str:
        if value is None:
            return "none"
        backend = str(value).strip().lower()
        if backend not in {"none", "mysql", "mongodb", "redis"}:
            raise ValueError(
                "HISTORY_STORAGE_BACKEND must be one of: none, mysql, mongodb, redis."
            )
        return backend

    @model_validator(mode="after")
    def _validate_history_configuration(self) -> "Settings":
        backend = self.history_storage_backend
        if backend == "mysql":
            missing = []
            if not (self.history_mysql_host or "").strip():
                missing.append("HISTORY_MYSQL_HOST")
            if not (self.history_mysql_user or "").strip():
                missing.append("HISTORY_MYSQL_USER")
            if not (self.history_mysql_database or "").strip():
                missing.append("HISTORY_MYSQL_DATABASE")
            if missing:
                raise ValueError(
                    "MySQL history storage requires the following settings: "
                    + ", ".join(missing)
                )
        elif backend == "mongodb":
            if not (self.history_mongodb_uri or "").strip():
                raise ValueError(
                    "MongoDB history storage requires HISTORY_MONGODB_URI to be set."
                )
            if not (self.history_mongodb_database or "").strip():
                raise ValueError(
                    "MongoDB history storage requires HISTORY_MONGODB_DATABASE to be set."
                )
        elif backend == "redis":
            if not (self.history_redis_url or self.redis_url):
                raise ValueError(
                    "Redis history storage requires HISTORY_REDIS_URL or REDIS_URL to be set."
                )
        return self

    @property
    def redis_enabled(self) -> bool:
        """Return ``True`` when Redis integration should be used."""

        return bool(self.redis_url)

    @property
    def history_storage_enabled(self) -> bool:
        """Return ``True`` when a persistent history backend is configured."""

        return self.history_storage_backend != "none"

    @property
    def memory_limit(self) -> int:
        """Highest number of exchanges a session is allowed to persist."""

        return self.memory_max


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""

    return Settings()


__all__ = ["Settings", "get_settings"]
