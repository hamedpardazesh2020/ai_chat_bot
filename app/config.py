"""Application configuration utilities."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseSettings, Field, root_validator, validator

try:  # pragma: no cover - optional dependency
    import yaml
except Exception:  # pragma: no cover - PyYAML may not be installed
    yaml = None  # type: ignore


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
    openrouter_key: Optional[str] = Field(default=None, env="OPENROUTER_KEY")
    mcp_server_url: Optional[str] = Field(default=None, env="MCP_SERVER_URL")
    mcp_api_key: Optional[str] = Field(default=None, env="MCP_API_KEY")

    redis_url: Optional[str] = Field(default=None, env="REDIS_URL")

    rate_rps: float = Field(default=1.0, env="RATE_RPS")
    rate_burst: int = Field(default=5, env="RATE_BURST")

    memory_default: int = Field(default=10, env="MEMORY_DEFAULT")
    memory_max: int = Field(default=50, env="MEMORY_MAX")

    metrics_enabled: bool = Field(default=True, env="METRICS_ENABLED")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    provider_timeout_seconds: float = Field(
        default=30.0, env="PROVIDER_TIMEOUT_SECONDS"
    )

    class Config:
        """Pydantic configuration."""

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

        @classmethod
        def customise_sources(cls, init_settings, env_settings, file_secret_settings):
            """Inject a YAML settings source between init values and env values."""

            return (
                init_settings,
                cls.yaml_config_settings_source,
                env_settings,
                file_secret_settings,
            )

        @staticmethod
        def yaml_config_settings_source(settings: BaseSettings) -> Dict[str, Any]:
            """Load settings from a YAML file when ``APP_CONFIG_FILE`` is set."""

            config_file = os.getenv("APP_CONFIG_FILE")
            if not config_file:
                return {}

            path = Path(config_file)
            if not path.exists():
                raise FileNotFoundError(f"Config file '{config_file}' was not found.")

            if path.suffix.lower() not in {".yml", ".yaml"}:
                raise ValueError(
                    "Unsupported config format. Expected a .yml or .yaml file."
                )

            if yaml is None:
                raise RuntimeError(
                    "PyYAML is required to load YAML configuration files but is not installed."
                )

            data = yaml.safe_load(path.read_text()) or {}
            if not isinstance(data, dict):
                raise ValueError("YAML configuration must define a mapping at the root level.")
            return data

    @validator("rate_rps")
    def _validate_rate_rps(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("RATE_RPS must be greater than 0.")
        return value

    @validator("rate_burst")
    def _validate_rate_burst(cls, value: int) -> int:
        if value < 1:
            raise ValueError("RATE_BURST must be at least 1.")
        return value

    @validator("memory_default", "memory_max")
    def _validate_memory_bounds(cls, value: int, field) -> int:  # type: ignore[override]
        if value < 1:
            raise ValueError(f"{field.name.upper()} must be at least 1.")
        return value

    @root_validator
    def _validate_memory_relationship(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        default = values.get("memory_default")
        maximum = values.get("memory_max")
        if default is not None and maximum is not None and default > maximum:
            raise ValueError("MEMORY_DEFAULT cannot exceed MEMORY_MAX.")
        return values

    @validator("provider_timeout_seconds")
    def _validate_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("PROVIDER_TIMEOUT_SECONDS must be greater than 0.")
        return value

    @property
    def redis_enabled(self) -> bool:
        """Return ``True`` when Redis integration should be used."""

        return bool(self.redis_url)

    @property
    def memory_limit(self) -> int:
        """Highest number of exchanges a session is allowed to persist."""

        return self.memory_max


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""

    return Settings()


__all__ = ["Settings", "get_settings"]
