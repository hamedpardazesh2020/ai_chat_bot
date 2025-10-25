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
- By default `mcp-agent` calls the OpenRouter API. Ensure the required
  OpenRouter credentials (for example `OPENROUTER_KEY`) are read from the
  configuration layer so every chat request is proxied through OpenRouter.
- Support optional MCP servers by reading `MCP_AGENT_SERVERS` from the
  configuration. When this value is provided, `mcp-agent` must include those
  servers when chatting. When it is absent, the agent must behave exactly like
  the OpenRouter-only flow.
