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
- The backend must always communicate with the primary agent through the
  OpenRouter API by default. Keep OpenRouter registered and selected through
  environment variables (for example `OPENROUTER_KEY` and
  `DEFAULT_PROVIDER`).
- Provider selection must never be exposed to, or configurable from, any
  public API surface or example client. All routing changes happen through the
  environment only.
- Support optional MCP servers that attach to the agent via environment
  configuration. The system should operate without MCP settings when they are
  omitted, and default to OpenRouter-only behaviour.
