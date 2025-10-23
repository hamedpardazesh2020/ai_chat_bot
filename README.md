# Chat Agent Backend

## Overview
The Chat Agent Backend is an asynchronous FastAPI service that brokers chat
conversations between clients and multiple large language model providers. The
service maintains per-session memory, enforces global rate limits, supports
provider failover, and exposes administrative tooling for runtime control and
observability.

## Features
- **MCP Agent orchestration** – Built-in integration with the
  [`mcp-agent`](https://github.com/lastmile-ai/mcp-agent) framework so a single
  session can reason over multiple MCP servers (for example, `filesystem` plus
  `fetch`) while delegating tool selection to the LLM.
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

When `MCP_AGENT_SERVERS` lists at least two server identifiers the application
automatically registers an `MCPAgentChatProvider`. The provider loads its
server catalogue from the `mcp_agent.config.yaml` file referenced by
`MCP_AGENT_CONFIG`. A minimal configuration that connects to both the
filesystem and fetch reference servers looks like this:

```yaml
# mcp_agent.config.yaml
mcp:
  servers:
    filesystem:
      transport: stdio
      command: npx
      args:
        - mcp-server-filesystem
      env:
        ROOT: /data
    fetch:
      transport: stdio
      command: npx
      args:
        - mcp-server-fetch
```

Set `MCP_AGENT_SERVERS=filesystem,fetch` (or any other two entries defined in
the configuration file) and supply an `OPENAI_API_KEY` so the built-in
`OpenAIAugmentedLLM` can coordinate the tools.

To inject a custom system prompt at the beginning of every conversation, set
the `INITIAL_SYSTEM_PROMPT` environment variable (or provide it via the YAML
configuration file). The message is stored in session memory immediately after a
session is created so that the provider receives it with the very first user
message.

If you need to call a specific MCP tool per request, supply a `tool_name`
option when posting a message:

```json
{
  "content": "برای من خلاصه بنویس",
  "provider": "support-mcp",
  "options": { "tool_name": "summarise" }
}
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
| `OPENAI_API_KEY` | API key consumed by the embedded `mcp-agent` LLM. | `None` |
| `MCP_SERVER_URL` | Legacy fallback for the deprecated MCP client. | `None` |
| `MCP_API_KEY` | Optional API key for legacy MCP servers. | `None` |
| `MCP_AGENT_CONFIG` | Path to an `mcp_agent.config.yaml` describing downstream MCP servers. | `None` |
| `MCP_AGENT_SERVERS` | Comma separated list of at least two server names to expose to the agent. | `None` |
| `MCP_AGENT_APP_NAME` | Override the logical name reported by the embedded MCP app. | `chat-backend` |
| `MCP_AGENT_INSTRUCTION` | Optional instruction passed to the agent instead of `INITIAL_SYSTEM_PROMPT`. | `None` |
| `MCP_AGENT_LLM` | Identifier for the augmented LLM to attach (currently `openai`). | `openai` |
| `MCP_AGENT_MODEL` | Default OpenAI model requested by the agent. | `None` |
| `INITIAL_SYSTEM_PROMPT` | System prompt stored when new sessions are created. | `None` |
| `REDIS_URL` | Enables Redis-backed memory and rate limiting when provided. | `None` |
| `RATE_RPS` | Average number of requests per second allowed per identity. | `1.0` |
| `RATE_BURST` | Maximum burst size before throttling applies. | `5` |
| `MEMORY_DEFAULT` | Default number of messages stored per session. | `10` |
| `MEMORY_MAX` | Maximum allowed messages stored per session. | `50` |
| `METRICS_ENABLED` | Toggles metrics middleware and the `/metrics` endpoint. | `true` |
| `LOG_LEVEL` | Minimum logging level for structured logs. | `INFO` |
| `PROVIDER_TIMEOUT_SECONDS` | Timeout applied to outbound provider requests. | `30` |
| `APP_CONFIG_FILE` | Optional path to a YAML config file that augments env vars. | `None` |

## API summary
### Health & metrics
- `GET /health` – Returns uptime and error counters for readiness checks.
- `GET /metrics` – Provides request/response counters and latency statistics.
  This route is only available when `METRICS_ENABLED` is `true`.

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
  "provider": "mcp-agent",
  "options": {
    "model": "gpt-4o-mini"
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
  "provider": "mcp-agent",
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

#### Disabling metrics collection
Set the environment variable `METRICS_ENABLED=false` (or the equivalent setting
in your YAML config) to skip registering the metrics middleware and the
`/metrics` route altogether. The `/health` endpoint remains available and still
reports uptime, but request and latency counters stay unchanged because no
instrumentation runs. This is useful for privacy-sensitive deployments or when
you want to minimise per-request overhead.

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
