"""Tests covering the settings loader and config file discovery."""

from __future__ import annotations

import pytest

from app import config as config_module


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """Ensure the cached settings are cleared between tests."""

    config_module.get_settings.cache_clear()
    yield
    config_module.get_settings.cache_clear()


def test_settings_load_from_default_config_when_present(monkeypatch, tmp_path):
    """Settings should fall back to a bundled config file when env vars are absent."""

    config_file = tmp_path / "app.config.yaml"
    config_file.write_text(
        """
openrouter_key: sk-or-config
default_provider_name: mcp-agent
    """.strip()
    )

    monkeypatch.delenv("APP_CONFIG_FILE", raising=False)
    monkeypatch.delenv("OPENROUTER_KEY", raising=False)

    monkeypatch.setattr(
        config_module,
        "_DEFAULT_CONFIG_CANDIDATES",
        (config_file,),
        raising=False,
    )

    settings = config_module.get_settings()

    assert settings.openrouter_key == "sk-or-config"
    assert settings.default_provider_name == "mcp-agent"


def test_settings_fall_back_to_example_config(monkeypatch, tmp_path):
    """Example config files should be considered when concrete configs are absent."""

    missing_primary = tmp_path / "app.config.yaml"
    example_file = tmp_path / "app.config.example.yaml"
    example_file.write_text(
        """
openrouter_key: sk-or-example
default_provider_name: mcp-agent
        """.strip()
    )

    monkeypatch.delenv("APP_CONFIG_FILE", raising=False)
    monkeypatch.delenv("OPENROUTER_KEY", raising=False)

    monkeypatch.setattr(
        config_module,
        "_DEFAULT_CONFIG_CANDIDATES",
        (missing_primary, example_file),
        raising=False,
    )

    settings = config_module.get_settings()

    assert settings.openrouter_key == "sk-or-example"
    assert settings.default_provider_name == "mcp-agent"


def test_environment_overrides_config_file(monkeypatch, tmp_path):
    """Explicit environment variables should override config file values."""

    config_file = tmp_path / "app.config.yaml"
    config_file.write_text(
        """
openrouter_key: sk-or-config
default_provider_name: unconfigured
    """.strip()
    )

    monkeypatch.delenv("APP_CONFIG_FILE", raising=False)
    monkeypatch.setenv("OPENROUTER_KEY", "sk-or-env")

    monkeypatch.setattr(
        config_module,
        "_DEFAULT_CONFIG_CANDIDATES",
        (config_file,),
        raising=False,
    )

    settings = config_module.get_settings()

    assert settings.openrouter_key == "sk-or-env"
    # The default provider name should still come from the config file because it was
    # not overridden by the environment.
    assert settings.default_provider_name == "unconfigured"
