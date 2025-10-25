# Project Workflow Guidelines

This repository hosts the FastAPI-based AI chat bot service. Follow these guidelines when making changes within this project:

1. **Environment Setup**
   - Install dependencies with `pip install -r requirements.txt`.
   - Copy `.env.example` to `.env` and fill in provider credentials before running the app locally.

2. **Development Workflow**
   - Place application code under the `app/` package and tests under `tests/`.
   - Prefer asynchronous FastAPI patterns already used in the project.
   - Keep provider implementations isolated in `app/agents/providers/` and update related configuration in `app/config.py`.

3. **Testing & Validation**
   - Run `pytest` before submitting changes.
   - Ensure new features include corresponding tests in `tests/` when applicable.

4. **Documentation**
   - Update `README.md` and `.env.example` whenever configuration or usage changes.
   - When adding new runnable services or programs, place their Dockerfiles inside the `docker/` directory and update `docker/docker-compose.yml` accordingly.

These instructions apply to the entire repository.

## Provider configuration reminders
- The service exposes **exactly one provider**, `mcp-agent`. There must be no
  alternate routing or fallback providers wired into the runtime, nor any way
  to select a different provider outside the configuration layer.
- Configuration for `mcp-agent` comes solely from the environment / config
  files (for local development, `.env`). Never add request parameters, query
  flags, or UI controls that alter provider choice.
- `mcp-agent` always serves requests. When no MCP servers are configured it
  must transparently delegate to OpenRouter using the credentials supplied via
  configuration. Optional MCP servers are added **only** when
  `MCP_AGENT_SERVERS` is provided, in which case the agent should fan out to
  those servers. Leaving the value blank must keep the OpenRouter-only flow.
- OpenRouter (or another configured LLM backend) may only be changed through
  configuration values such as `MCP_AGENT_LLM` and `MCP_AGENT_MODEL`. Runtime
  toggles or ad-hoc request parameters are prohibited.
