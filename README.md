# Chat Agent Backend

## Overview
The Chat Agent Backend is an asynchronous FastAPI service that brokers chat
conversations between clients and multiple large language model providers. The
service maintains per-session memory, enforces global rate limits, supports
provider failover, and exposes administrative tooling for runtime control and
observability.

## Features
- **Multiple chat providers** – Pluggable connectors for OpenAI, OpenRouter, and
  MCP endpoints with a unified provider interface.
- **Session-based memory** – In-memory or Redis-backed transcript storage with
  configurable retention limits and per-session overrides.
- **Resilience tooling** – Provider fallback, structured error responses, and
  optional Redis-backed distributed rate limiting.
- **Security & governance** – Token-protected admin APIs for rate limit bypass
  management plus global quotas per IP and API key.
- **Observability** – Structured logging, JSON metrics, and health checks for
  operational insight.

## Quickstart
### 1. Install dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure the service
Copy `.env.example` to `.env` and update any values for your environment. At a
minimum you should set credentials for the providers you plan to use and
configure an `ADMIN_TOKEN` if you want to access the admin endpoints.

```bash
cp .env.example .env
# edit .env
```

Provider clients are registered programmatically. During application start-up,
create provider instances and register them with the shared
`ProviderManager` (via `app.dependencies.set_provider_manager`). For example:

```python
from app.agents.manager import ProviderManager
from app.agents.providers.openai import OpenAIChatProvider
from app.dependencies import set_provider_manager

manager = ProviderManager()
manager.register("openai", OpenAIChatProvider.from_settings())
manager.set_default("openai")
set_provider_manager(manager)
```

### 3. Run the API server
```bash
uvicorn app.main:app --reload
```

### 4. Run with Docker Compose (optional)
Build the image and start both the API and Redis services with Docker Compose.
Create a `.env` file (for example by copying `.env.example`) so sensitive
configuration stays outside of version control.

```bash
docker compose up --build
```

The API will be available at <http://localhost:8000>. Redis data persists in the
`redis-data` Docker volume defined by the compose file.

### 5. Execute the test suite
```bash
pytest
```

## Configuration reference
All configuration is sourced from environment variables (or an optional YAML
file referenced by `APP_CONFIG_FILE`). The table below summarises the available
settings.

| Variable | Description | Default |
| --- | --- | --- |
| `ADMIN_TOKEN` | Token required for admin endpoints. When unset the admin API is disabled. | `None` |
| `OPENAI_API_KEY` | API key for the OpenAI connector. | `None` |
| `OPENROUTER_KEY` | API key for the OpenRouter connector. | `None` |
| `MCP_SERVER_URL` | Base URL for the MCP server. | `None` |
| `MCP_API_KEY` | Optional MCP API key. | `None` |
| `REDIS_URL` | Enables Redis-backed memory and rate limiting when provided. | `None` |
| `RATE_RPS` | Average number of requests per second allowed per identity. | `1.0` |
| `RATE_BURST` | Maximum burst size before throttling applies. | `5` |
| `MEMORY_DEFAULT` | Default number of messages stored per session. | `10` |
| `MEMORY_MAX` | Maximum allowed messages stored per session. | `50` |
| `METRICS_ENABLED` | Toggles metrics middleware. | `true` |
| `LOG_LEVEL` | Minimum logging level for structured logs. | `INFO` |
| `PROVIDER_TIMEOUT_SECONDS` | Timeout applied to outbound provider requests. | `30` |
| `APP_CONFIG_FILE` | Optional path to a YAML config file that augments env vars. | `None` |

## API summary
### Health & metrics
- `GET /health` – Returns uptime and error counters for readiness checks.
- `GET /metrics` – Provides request/response counters and latency statistics.

### Session messaging
- `POST /sessions` – Create a new chat session with optional provider
  preferences. The response returns the session metadata and identifier.
- `DELETE /sessions/{session_id}` – Remove a session and clear all stored
  memory for it.
- `POST /sessions/{session_id}/messages` – Send a message to an existing session
  and receive the provider response. The payload accepts optional provider and
  memory overrides.

```json
{
  "content": "Hello there!",
  "role": "user",
  "provider": "openai",
  "options": {
    "model": "gpt-4"
  }
}
```

> **Note:** The request body must include the `content` field shown above. Older
> snippets or third-party examples that send a `message` property will be
> rejected by FastAPI's validation layer with a `content: field required`
> error. Update any clients to provide `content` to avoid HTTP 422 responses.

```json
{
  "session_id": "<uuid>",
  "provider": "openai",
  "provider_source": "session_default",
  "message": {
    "role": "assistant",
    "content": "Hi! How can I help you today?",
    "created_at": "2025-10-06T18:20:00Z"
  },
  "history": [
    { "role": "user", "content": "Hello there!", "created_at": "..." },
    { "role": "assistant", "content": "Hi! How can I help you today?", "created_at": "..." }
  ]
}
```

### Admin endpoints
All admin routes require the `X-Admin-Token` header.

- `GET /admin/bypass` – List IP addresses that bypass the rate limiter.
- `POST /admin/bypass` – Add an IP address to the bypass list.
- `DELETE /admin/bypass/{ip}` – Remove an IP address from the bypass list.

### Rate limiting behaviour
Requests exceeding the configured quota receive HTTP 429 responses with a JSON
body:

```json
{
  "error": "rate_limited",
  "retry_after": 2.0
}
```

### Structured logging & metrics
Each request is logged with a unique `X-Request-ID`. Metrics can be harvested by
polling `/metrics` and include aggregated counters for requests, responses, and
errors.

## Examples

An executable example illustrating the HTTP flow lives in
`examples/basic_session.py`. It creates a session, sends a single message, and
cleans up afterwards. Run it against a local server with:

```bash
python examples/basic_session.py
```

The script reads the `CHAT_API_URL`, `CHAT_PROVIDER`, and `CHAT_USER_MESSAGE`
environment variables so you can target remote deployments or experiment with
different providers and prompts.

For a visual look at the service health, open `examples/metrics.html` in a
browser while the API is running locally. The page uses the Vazir font, polls
`GET /metrics` on a configurable interval (۲۰ ثانیه به طور پیش‌فرض), and plots
live charts for total requests, responses, and errors.

## Development notes
- The default memory backend is in-process. Setting `REDIS_URL` enables the
  Redis-backed implementation for both session memory and distributed rate
  limiting.
- Providers are intentionally decoupled from FastAPI dependencies to ease unit
  testing; you can swap providers by overriding `ProviderManager` during tests.
- Error responses use a consistent `{ "error": { "code": ..., "message": ... } }`
  structure; clients should surface the embedded `X-Request-ID` for support
  cases.
