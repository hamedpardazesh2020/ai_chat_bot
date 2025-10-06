- [x] **T01 — Project scaffolding** (completed: scaffolded FastAPI project structure)
      Create project skeleton, venv/requirements, base FastAPI app, folder structure.
- [x] **T02 — Configuration & settings** (completed: implemented Pydantic settings loader with YAML support)
      Implement `config.py` with Pydantic settings and `.env.example`.
- [x] **T03 — App entry & routing skeleton** (completed: added app factory with placeholder meta routes)
      `main.py` with FastAPI app, routers, /health, /metrics placeholders.
- [x] **T04 — Sessions: domain & storage** (completed: added session domain model and store)
      Implement `sessions.py` (create/delete session, in-memory store).
- [x] **T05 — Memory (in-memory)** (completed: added configurable deque-backed session memory)
      Implement message history per session with deque; configurable N (default 10).
- [x] **T06 — Memory (Redis backend)** (completed: added Redis-backed memory with factory selection)
      Add Redis storage option with same interface; auto-select if REDIS_URL present.
- [x] **T07 — Provider interface** (completed: added provider protocol and registry manager)
      Define common provider interface and manager (`agents/manager.py`).
- [x] **T08 — Provider: OpenAI** (completed: implemented async OpenAI chat provider)
      Implement `providers/openai.py` with async calls.
- [x] **T09 — Provider: OpenRouter** (completed: added async OpenRouter chat provider)
      Implement `providers/openrouter.py` with async calls.
- [x] **T10 — Provider: MCP (client stub)** (completed: added async MCP client/provider with handshake & tool invocation)
      Implement `providers/mcp.py` with handshake + `call_tool`.
- [x] **T11 — Provider selection logic** (completed: added provider resolution helpers with override support)
      Per-session default + per-request override via headers/body param.
- [x] **T12 — Messages endpoint end-to-end** (completed: added session message API wiring providers and memory)
      `POST /sessions/{id}/messages` wiring provider + memory.
- [x] **T13 — Rate limiter (in-memory)** (completed: added token-bucket middleware enforcing per-IP/API key limits)
      Token-bucket middleware with RATE_RPS/RATE_BURST.
- [x] **T14 — Rate limiter (Redis option)** (completed: added Redis-backed distributed token bucket)
      Distributed token-bucket using Redis.
- [x] **T15 — Rate bypass allowlist + admin API** (completed: added bypass store, admin endpoints, and middleware integration)
      IP allowlist store + POST/DELETE /admin/bypass with auth.
- [x] **T16 — Admin security** (completed: enforced ADMIN_TOKEN validation for admin APIs)
      Token auth for admin endpoints (ENV `ADMIN_TOKEN`).
- [x] **T17 — Health & Metrics (JSON)** (completed: added metrics collector with health and metrics endpoints)
      Implement /health and /metrics counters.
- [x] **T18 — Logging & errors** (completed: added structured logging middleware and API error handlers)
      Structured logging, consistent error responses.
- [x] **T19 — Provider fallback** (completed: added provider fallback resolution and API failover logic)
      Optional fallback provider when primary fails.
- [x] **T20 — Tests: sessions & memory** (completed: added async session and memory trimming tests)
      pytest for session create/delete and memory trimming.
- [x] **T21 — Tests: rate limit & bypass** (completed: added middleware-focused rate limit and bypass tests)
      pytest for 429 and bypass behavior.
- [x] **T22 — Tests: provider fallback** (completed: added async API tests covering fallback success and error cases)
      pytest with mocked providers.
- [x] **T23 — Documentation** (completed: expanded README and enriched OpenAPI metadata)
      README with quickstart, config, API summary; update OpenAPI descriptions.
- [x] **T24 — Docker & Compose** (completed: added Dockerfile and docker-compose stack with Redis service)
      Dockerfile and docker-compose (with Redis).
- [x] **T25 — Polish** (completed: tightened typing, added lifecycle endpoints, and documented examples)
      Final pass on types, comments, and minimal examples.