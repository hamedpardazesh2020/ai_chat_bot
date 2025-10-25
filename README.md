# Chat Agent Backend

## Overview
The Chat Agent Backend is an asynchronous FastAPI service that brokers chat
conversations between clients and OpenRouter-hosted large language models while
optionally orchestrating Model Context Protocol (MCP) agents. The service
maintains per-session memory, enforces global rate limits, provides transparent
failover for environment-configured backends, and exposes administrative
tooling for runtime control and observability.

## Features
- **MCP Agent orchestration** – Built-in integration with the
  [`mcp-agent`](https://github.com/lastmile-ai/mcp-agent) framework so a single
  session can reason over multiple MCP servers (for example, `filesystem` plus
  `fetch`) while delegating tool selection to the LLM.
- **Session-based memory** – In-memory or Redis-backed transcript storage with
  configurable retention limits and per-session overrides.
- **History archiving** – Optional MySQL, MongoDB, or Redis persistence for
  completed exchanges while retaining a no-storage mode for ephemeral chats.
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
Copy the bundled template `app/config/app.config.example.yaml` to
`app/config/app.config.yaml` and populate the values so the API can start
without injecting environment variables during container builds. The template
contains sane defaults and remains tracked in Git, while the real
`app.config.yaml` is ignored so you can safely store local API keys. The
settings loader automatically reads the YAML file when no explicit
`APP_CONFIG_FILE` is supplied, allowing Docker images to boot without extra bind
mounts. Runtime environment variables still take precedence, so you can
override individual values via `docker run -e ...` or your orchestrator. At a
minimum set `openrouter_key` (or `OPENROUTER_KEY`) so the service can
authenticate with the OpenRouter API and configure an `admin_token` if you want
to access the admin endpoints. The bundled configuration pins
`default_provider_name: mcp-agent`, so once credentials are provided every chat
request runs through the embedded MCP agent, which uses OpenRouter as its
default LLM backend.

If you prefer traditional dotenv workflows copy `.env.example` to `.env`. Any
values defined in `.env` or directly in the process environment override the
YAML configuration file.

If you skip provider credentials the API now starts with a built-in
`unconfigured` provider that rejects chat requests with a clear error. This
keeps local development environments and Docker containers healthy while still
signalling that an upstream model must be configured before the chat endpoints
become useful. Provider selection cannot be overridden through the HTTP API or
sample clients.

```bash
cp .env.example .env
# edit .env
```

When `MCP_AGENT_SERVERS` lists one or more server identifiers the application
automatically enables MCP server orchestration within the
`MCPAgentChatProvider`. The provider loads its server catalogue from the
`mcp_agent.config.yaml` file referenced by `MCP_AGENT_CONFIG`. A minimal
configuration that connects to both the filesystem and fetch reference servers
looks like this:

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

Set `MCP_AGENT_SERVERS=filesystem,fetch` (or any other entries defined in the
configuration file) and choose the LLM the agent should attach. If you want
to expose the ham3d catalogue search server defined in
`mcp_servers/ham3d_mysql.py`, reference the bundled
`mcp_servers/ham3d_mysql/config/mcp_agent.config.yaml` from your MCP agent
configuration. The example server expects a
MySQL database and reads connection information from the `HAM3D_DB_*`
environment variables (see `mcp_servers/.env.ham3d.example` for the defaults).

#### Launch the MCP servers

Start each configured server in its own terminal so the agent can connect over
`stdio`:

```bash
npx mcp-server-filesystem
npx mcp-server-fetch
```

For the ham3d catalogue server populate the `HAM3D_DB_*` variables **with real
values** and then run the module from the project root (note the module path
after `-m`). The server will raise `RuntimeError: Environment variable
HAM3D_DB_USER must be configured for the ham3d server.` (or similar) if any of
the required variables are missing or blank.

```bash
export HAM3D_DB_HOST=127.0.0.1
export HAM3D_DB_USER=root
export HAM3D_DB_PASSWORD="super-secret"
export HAM3D_DB_NAME=ham3dbot_ham3d_shop
python -m mcp_servers.ham3d_mysql
```

PowerShell users can set the variables for the current session like this:

```powershell
$env:HAM3D_DB_HOST = "127.0.0.1"
$env:HAM3D_DB_USER = "root"
$env:HAM3D_DB_PASSWORD = "super-secret"
$env:HAM3D_DB_NAME = "ham3dbot_ham3d_shop"
```

After exporting the variables, launch the server:

```bash
python -m mcp_servers.ham3d_mysql
# Windows PowerShell example when using a virtual environment
.\.venv\Scripts\python.exe -m mcp_servers.ham3d_mysql
```

> **Docker option:** Build and launch the ham3d server through the dedicated
> `docker/ham3d.Dockerfile` when you prefer container isolation. The
> compose file in `docker/docker-compose.yml`
> exposes an optional profile so the service only starts when requested:
>
> ```bash
> docker compose -f docker/docker-compose.yml --profile mcp build mcp-ham3d
> docker compose -f docker/docker-compose.yml --profile mcp run --rm mcp-ham3d
> ```

Populate the `HAM3D_DB_*` variables with valid credentials before running the
container so the server can connect to your database. You can copy
`mcp_servers/.env.ham3d.example` to `mcp_servers/.env.ham3d` and update the
values, then load them via `set -a && source mcp_servers/.env.ham3d`.

Do not append a filesystem path after `-m`; Python expects an importable module
name and will raise `No module named ...` if a path is provided.

> **Tip:** Storing the credentials in `mcp_servers/.env.ham3d` (or another
> dedicated env file) is convenient, but Python will not automatically load that
> file when you start the MCP server directly. Source the file yourself
> (`set -a && source mcp_servers/.env.ham3d`) or run the command through a
> helper such as
> `python -m dotenv run --dotenv-path mcp_servers/.env.ham3d -- python -m mcp_servers.ham3d_mysql`
> so the environment variables are populated before the module imports.

The embedded MCP agent automatically reuses your OpenRouter credentials when
`MCP_AGENT_LLM` is left at its default (`openrouter`). Advanced deployments can
swap in a different LLM by setting `MCP_AGENT_LLM` alongside the relevant
environment variables.

To inject a custom system prompt at the beginning of every conversation, set
the `INITIAL_SYSTEM_PROMPT` environment variable (or provide it via the YAML
configuration file). The message is stored in session memory immediately after a
session is created so that the provider receives it with the very first user
message.

If you need to call a specific MCP tool per request, supply a `tool_name`
option when posting a message. This assumes the MCP agent is registered and set
as the default backend via environment configuration (for example,
`DEFAULT_PROVIDER=mcp-agent`).

```json
{
  "content": "برای من خلاصه بنویس",
  "options": { "tool_name": "summarise" }
}
```

### History storage configuration

By default transcripts are not archived outside the in-memory/Redis chat
context. Set `HISTORY_STORAGE_BACKEND` to one of `none`, `mysql`, `mongodb`, or
`redis` to enable long-term storage. Each backend has dedicated settings that
must be populated alongside the selector:

- **none** – disables archival storage and keeps conversations ephemeral.
- **mysql** – provide `HISTORY_MYSQL_HOST`, `HISTORY_MYSQL_PORT`,
  `HISTORY_MYSQL_USER`, and `HISTORY_MYSQL_DATABASE`. Optional fields allow you
  to override the session/message table names. The service creates the tables on
  demand when they do not exist.
- **mongodb** – configure `HISTORY_MONGODB_URI` and
  `HISTORY_MONGODB_DATABASE` plus optional collection names. A
  `motor`-powered client handles inserts and index creation.
- **redis** – set `HISTORY_REDIS_URL` or reuse `REDIS_URL` to push session
  metadata and messages into Redis lists.

The `HISTORY_NAMESPACE` setting scopes keys/records per deployment so multiple
environments can share the same infrastructure without collisions.

### 3. Run the API server
```bash
uvicorn app.main:app --reload
```

### 4. Run with Docker Compose (optional)
Build the image and start both the API and Redis services with Docker Compose.
Create a `.env` file (for example by copying `.env.example`) so sensitive
configuration stays outside of version control.

```bash
docker compose -f docker/docker-compose.yml up --build
```

The API will be available at <http://localhost:8000>. Redis data persists in the
`redis-data` Docker volume defined by the compose file. Run the command from the
repository root so the compose file can reference project-relative paths.

All Docker assets (Dockerfiles plus additional notes) live in the `docker/`
directory. See `docker/README.md` for advanced build options or to run the
containers manually with `docker build`.

To include the optional ham3d MCP server, enable the `mcp` profile when starting
Compose. The profile keeps the service disabled by default so deployments that
do not need ham3d remain unaffected.

```bash
docker compose -f docker/docker-compose.yml --profile mcp up mcp-ham3d
```

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
| `DEFAULT_PROVIDER` | Name of the provider the backend uses for every request. Clients cannot override this value. | `mcp-agent` |
| `OPENROUTER_KEY` | API key used by the MCP agent when `MCP_AGENT_LLM=openrouter`. | `None` |
| `OPENROUTER_BASE_URL` | Override the OpenRouter API endpoint used by the MCP agent. | `https://openrouter.ai/api/v1` |
| `OPENROUTER_MODEL` | Default OpenRouter model requested when none is supplied explicitly. | `openrouter/auto` |
| `MCP_SERVER_URL` | Legacy fallback for the deprecated MCP client. | `None` |
| `MCP_API_KEY` | Optional API key for legacy MCP servers. | `None` |
| `MCP_AGENT_CONFIG` | Path to an `mcp_agent.config.yaml` describing downstream MCP servers. | `None` |
| `MCP_AGENT_SERVERS` | Comma separated list of MCP server names to expose to the agent. Leave blank to run the agent without MCP servers. | `None` |
| `MCP_AGENT_APP_NAME` | Override the logical name reported by the embedded MCP app. | `chat-backend` |
| `MCP_AGENT_INSTRUCTION` | Optional instruction passed to the agent instead of `INITIAL_SYSTEM_PROMPT`. | `None` |
| `MCP_AGENT_LLM` | Identifier for the augmented LLM to attach (`openai` or `openrouter`). | `openrouter` |
| `MCP_AGENT_MODEL` | Default model requested by the agent. Falls back to `OPENROUTER_MODEL` when using OpenRouter. | `None` |
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
- `POST /sessions` – Create a new chat session using the provider defined via
  environment configuration. The response returns the session metadata and
  identifier. The backend always selects the OpenRouter integration configured
  through environment variables; clients cannot override or even see the
  provider choice through the public API.
- `DELETE /sessions/{session_id}` – Remove a session and clear all stored
  memory for it.
- `POST /sessions/{session_id}/messages` – Send a message to an existing session
  and receive the provider response. The payload accepts optional memory
  overrides plus provider-specific options such as temperature or tool hints.

```json
{
  "content": "Hello there!",
  "role": "user",
  "options": {
    "model": "gpt-4o-mini"
  }
}
```

> **Note:** The request body must include the `content` field shown above. Older
> snippets or third-party examples that send a `message` property will be
> rejected by FastAPI's validation layer with a `content: field required`
> error. Update any clients to provide `content` to avoid HTTP 422 responses.



### Admin endpoints
All admin routes require the `X-Admin-Token` header.

- `GET /admin/bypass` – List IP addresses that bypass the rate limiter.
- `POST /admin/bypass` – Add an IP address to the bypass list.
- `DELETE /admin/bypass/{ip}` – Remove an IP address from the bypass list.
- `GET /admin/runtime` – Return the currently resolved provider and memory configuration.

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
polling `/metrics` and include aggregated counters for chat activity (session
creation and message posts), responses, and errors. Introspection endpoints such
as `/metrics` and `/health` are intentionally excluded from the counters so the
statistics focus solely on live conversation traffic.

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

The script honours the following environment variables so you can target remote
deployments or tailor both the session and the first message:

- `CHAT_API_URL` – Base URL for the running API instance (defaults to
  `http://localhost:8000`).
- `CHAT_MEMORY_LIMIT` – Memory window requested when creating the session.
- `CHAT_SESSION_METADATA` – JSON object attached to the session metadata.
- `CHAT_USER_MESSAGE` – Content of the initial message.
- `CHAT_MESSAGE_ROLE` – Override the role for the initial message.
- `CHAT_MESSAGE_MEMORY_LIMIT` – Per-request memory limit override.
- `CHAT_MESSAGE_OPTIONS` – JSON object forwarded to the provider as request
  options (for example, temperature or tool hints).
- `CHAT_REQUEST_TIMEOUT` – HTTP timeout in seconds when calling the API.

All JSON fields must decode to an object. Invalid values raise a descriptive
error before any network call is attempted.

For a visual look at the service health, open `examples/metrics.html` in a
browser while the API is running locally. The page uses the Vazir font, polls
`GET /metrics` on a configurable interval (۲۰ ثانیه به طور پیش‌فرض), and plots
live charts for total requests, responses, and errors.

The interactive client at `examples/chat.html` exposes advanced controls for
session metadata, memory limits, and per-message request options. Use the
expandable panels to attach JSON metadata or to forward provider specific
options with each request.

## Development notes
- The default memory backend is in-process. Setting `REDIS_URL` enables the
  Redis-backed implementation for both session memory and distributed rate
  limiting.
- Providers are intentionally decoupled from FastAPI dependencies to ease unit
  testing; you can swap providers by overriding `ProviderManager` during tests
  without exposing additional provider selection controls to API consumers.
- Error responses use a consistent `{ "error": { "code": ..., "message": ... } }`
  structure; clients should surface the embedded `X-Request-ID` for support
  cases.
