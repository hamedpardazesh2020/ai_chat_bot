"""Tests for the application configuration settings."""

from __future__ import annotations

from app.config import Settings


def test_mcp_agent_servers_handles_empty_string(monkeypatch):
    """An empty environment variable should yield an empty list."""

    monkeypatch.setenv("MCP_AGENT_SERVERS", "")
    settings = Settings()
    assert settings.mcp_agent_servers == []


def test_mcp_agent_servers_parses_comma_separated(monkeypatch):
    """Comma separated entries should be normalised into a list."""

    monkeypatch.setenv("MCP_AGENT_SERVERS", "alpha , beta,gamma")
    settings = Settings()
    assert settings.mcp_agent_servers == ["alpha", "beta", "gamma"]


def test_mcp_agent_servers_parses_json_array(monkeypatch):
    """JSON arrays remain supported for backwards compatibility."""

    monkeypatch.setenv("MCP_AGENT_SERVERS", '["delta", "epsilon"]')
    settings = Settings()
    assert settings.mcp_agent_servers == ["delta", "epsilon"]


def test_mcp_agent_servers_blank_dotenv(tmp_path, monkeypatch):
    """Blank values coming from a dotenv file should not raise errors."""

    env_file = tmp_path / ".env"
    env_file.write_text("MCP_AGENT_SERVERS=\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.mcp_agent_servers == []
