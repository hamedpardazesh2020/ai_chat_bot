- **T01 — Project scaffolding** (2025-10-06T14:36:01Z)
  - Summary: Created initial project structure with FastAPI entrypoint and placeholder modules.
  - Files: README.md; requirements.txt; app/__init__.py; app/main.py; app/config.py; app/sessions.py; app/memory.py; app/rate_limiter.py; app/admin.py; app/agents/__init__.py; app/agents/manager.py; app/agents/providers/__init__.py; app/agents/providers/openai.py; app/agents/providers/openrouter.py; app/agents/providers/mcp.py; tests/__init__.py.
  - Notes: Install dependencies with `pip install -r requirements.txt`.
- **T02 — Configuration & settings** (2025-10-06T14:40:01Z)
  - Summary: Implemented typed Pydantic settings with YAML fallback support and provided example environment file.
  - Files: app/config.py; .env.example; tasks.md.
  - Notes: Copy `.env.example` to `.env` and adjust values or set `APP_CONFIG_FILE` to a YAML config for overrides.
- **T03 — App entry & routing skeleton** (2025-10-06T14:45:41Z)
  - Summary: Added FastAPI application factory with root, health, and metrics placeholder routes.
  - Files: app/main.py; tasks.md; tasksDone.md.
  - Notes: Launch with `uvicorn app.main:app --reload` to exercise the placeholder endpoints.
- **T04 — Sessions: domain & storage** (2025-10-06T15:06:06Z)
  - Summary: Implemented the session domain model with concurrency-safe in-memory storage supporting create, fetch, delete, and listing operations.
  - Files: app/sessions.py; tasks.md; tasksDone.md.
  - Notes: Session store can be instantiated via `InMemorySessionStore()`; no additional setup required for in-memory usage.
- **T05 — Memory (in-memory)** (2025-10-06T15:13:05Z)
  - Summary: Added deque-backed in-memory chat history with configurable limits and validation helpers.
  - Files: app/memory.py; tasks.md; tasksDone.md.
  - Notes: Instantiate `InMemoryChatMemory` with desired defaults; no additional setup required.
- **T06 — Memory (Redis backend)** (2025-10-06T15:19:56Z)
  - Summary: Added Redis-backed chat memory implementation, shared factory helpers, and configuration-based selection logic.
  - Files: app/memory.py; tasks.md; tasksDone.md.
  - Notes: Provide `REDIS_URL` to enable Redis memory or pass a Redis client to `memory_from_settings`.

- **T07 — Provider interface** (2025-10-06T15:30:00Z)
  - Summary: Introduced chat provider protocol, response/message models, and a registry manager with default resolution support.
  - Files: app/agents/manager.py; tasks.md; tasksDone.md.
  - Notes: Instantiate `ProviderManager` with provider instances and set a default via `set_default` for fallback lookups.
- **T08 — Provider: OpenAI** (2025-10-06T15:45:00Z)
  - Summary: Implemented the asynchronous OpenAI chat provider with configurable client setup, error handling, and response normalisation.
  - Files: app/agents/providers/openai.py; tasks.md; tasksDone.md.
  - Notes: Ensure `OPENAI_API_KEY` is set; instantiate `OpenAIChatProvider` or register via `ProviderManager` for usage.

- **T09 — Provider: OpenRouter** (2025-10-06T16:33:22Z)
  - Summary: Added the asynchronous OpenRouter chat provider with configurable headers, request handling, and response normalisation mirroring the upstream API contract.
  - Files: app/agents/providers/openrouter.py; tasks.md; tasksDone.md.
  - Notes: Set `OPENROUTER_KEY` and optionally provide referer/title headers when initialising `OpenRouterChatProvider` or registering it with the provider manager.

- **T10 — Provider: MCP (client stub)** (2025-10-06T17:05:00Z)
  - Summary: Implemented an asynchronous MCP client with handshake caching and tool invocation plus a chat provider wrapper.
  - Files: app/agents/providers/mcp.py; tasks.md; tasksDone.md.
  - Notes: Configure `MCP_SERVER_URL` (and optionally `MCP_API_KEY`) before instantiating `MCPChatProvider` or using the client directly.

- **T11 — Provider selection logic** (2025-10-06T17:45:00Z)
  - Summary: Added provider manager resolution helpers that honour per-request overrides and session defaults.
  - Files: app/agents/manager.py; tasks.md; tasksDone.md.
  - Notes: Use `ProviderManager.resolve_for_request` when handling API calls to consistently apply overrides.
- **T12 — Messages endpoint end-to-end** (2025-10-06T16:55:47Z)
  - Summary: Added the session messages API endpoint that resolves providers, forwards conversation history, and persists user and assistant messages using the configured memory backend.
  - Files: app/api/__init__.py; app/api/sessions.py; app/dependencies.py; app/main.py; tasks.md.
  - Notes: Register at least one provider on the shared ProviderManager (via `app.dependencies.set_provider_manager`) before exercising `POST /sessions/{id}/messages`.
- **T13 — Rate limiter (in-memory)** (2025-10-06T17:00:42Z)
  - Summary: Implemented a configurable in-memory token bucket limiter and FastAPI middleware that enforces per-IP and per-API-key request quotas based on settings.
  - Files: app/rate_limiter.py; app/dependencies.py; app/main.py; tasks.md; tasksDone.md.
  - Notes: Middleware is registered automatically; adjust RATE_RPS and RATE_BURST to tune limits.

- **T14 — Rate limiter (Redis option)** (2025-10-06T17:10:28Z)
  - Summary: Added Redis-backed distributed token bucket limiter with optional client factory selection based on configuration.
  - Files: app/rate_limiter.py; tasks.md; tasksDone.md.
  - Notes: Provide `REDIS_URL` or pass a Redis client to `rate_limiter_from_settings` to enable the Redis limiter backend.

- **T15 — Rate bypass allowlist + admin API** (2025-10-06T17:16:15Z)
  - Summary: Implemented rate limit bypass store with admin endpoints to manage allowlisted IPs and integrated middleware support.
  - Files: app/admin.py; app/dependencies.py; app/main.py; app/rate_limiter.py; tasks.md; tasksDone.md.
  - Notes: Use `/admin/bypass` endpoints (with `X-Admin-Token` header) to add or remove IPs; allowlisted clients skip rate limiting automatically.

- **T16 — Admin security** (2025-10-06T17:25:00Z)
  - Summary: Enforced admin endpoint protection by validating the `X-Admin-Token` header against the configured `ADMIN_TOKEN` value and disabling the admin surface when unset.
  - Files: app/admin.py; tasks.md; tasksDone.md.
  - Notes: Set `ADMIN_TOKEN` in the environment; requests without the header, with incorrect values, or when the token is unset receive error responses.

- **T17 — Health & Metrics (JSON)** (2025-10-06T17:35:00Z)
  - Summary: Implemented a shared metrics collector with FastAPI middleware powering the /health and /metrics endpoints, exposing uptime and request counters.
  - Files: app/main.py; app/observability.py; app/dependencies.py; tasks.md; tasksDone.md.
  - Notes: Query `/health` for uptime/error summary and `/metrics` for detailed counters; metrics middleware loads automatically.

- **T18 — Logging & errors** (2025-10-06T17:38:50Z)
  - Summary: Added structured JSON logging, request logging middleware, and unified API error handling with consistent responses across admin and session endpoints.
  - Files: app/errors.py; app/logging_utils.py; app/main.py; app/api/sessions.py; app/admin.py; tasks.md; tasksDone.md.
  - Notes: Configure LOG_LEVEL via environment; responses now include a consistent `error` object and propagate the `X-Request-ID` header for traceability.

- **T19 — Provider fallback** (2025-10-06T17:43:38Z)
  - Summary: Added provider manager fallback resolution utilities and updated the session message API to retry with a configured fallback provider when the primary fails.
  - Files: app/agents/manager.py; app/api/sessions.py; tasks.md; tasksDone.md.
  - Notes: Configure `fallback_provider` on sessions to enable automatic failover; failures now log structured events for primary and fallback outcomes.
- **T20 — Tests: sessions & memory** (2025-10-06T17:47:46Z)
  - Summary: Added pytest coverage for session lifecycle operations and chat memory trimming with limit overrides and validation.
  - Files: tests/test_sessions.py; tests/test_memory.py; tasks.md; tasksDone.md.
  - Notes: Run `pytest` to execute the asynchronous session and memory unit tests.
- **T21 — Tests: rate limit & bypass** (2025-10-06T17:55:16Z)
  - Summary: Added asynchronous middleware harness tests verifying 429 responses when quotas are exceeded and allowlisted IPs bypass enforcement.
  - Files: tests/test_rate_limit.py; tasks.md; tasksDone.md.
  - Notes: Run `pytest` to execute the rate limiter suite alongside existing tests.
- **T22 — Tests: provider fallback** (2025-10-06T18:07:41Z)
  - Summary: Added FastAPI-driven tests that verify primary provider failures trigger fallback usage and return structured errors when the fallback is unavailable.
  - Files: tests/test_provider_fallback.py; tests/test_rate_limit.py; requirements.txt; tasks.md; tasksDone.md.
  - Notes: Run `pytest` to execute the expanded suite; pinned dependencies to Pydantic v1-compatible versions for consistency with existing settings.

- **T23 — Documentation** (2025-10-06T18:12:33Z)
  - Summary: Expanded the README with quickstart, configuration, and API guidance while enriching OpenAPI metadata across the service endpoints.
  - Files: README.md; app/main.py; app/admin.py; app/api/sessions.py; tasks.md; tasksDone.md.
  - Notes: Rebuild the FastAPI app to surface updated docs; no additional configuration changes required beyond existing environment settings.

- **T24 — Docker & Compose** (2025-10-06T18:18:00Z)
  - Summary: Added a production-ready Dockerfile and docker-compose stack that launches the API alongside Redis with persistent storage.
  - Files: Dockerfile; docker-compose.yml; README.md; tasks.md; tasksDone.md.
  - Notes: Copy `.env.example` to `.env`, then run `docker compose up --build` to start the stack; the API listens on port 8000 and Redis data is stored in the `redis-data` volume.

- **T25 — Polish** (2025-10-06T18:34:28+00:00)
  - Summary: Tightened typing hints, added session lifecycle endpoints with memory cleanup, provided a runnable usage example, and refreshed docs.
  - Files: app/admin.py; app/api/sessions.py; README.md; examples/basic_session.py; tests/test_sessions.py; tasks.md; tasksDone.md.
  - Notes: Run `pytest` to execute the updated suite; try `python examples/basic_session.py` against a running API for a quick manual check.
