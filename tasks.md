- [ ] **T01 — Project scaffolding**
      Create project skeleton, venv/requirements, base FastAPI app, folder structure.
- [ ] **T02 — Configuration & settings**
      Implement `config.py` with Pydantic settings and `.env.example`.
- [ ] **T03 — App entry & routing skeleton**
      `main.py` with FastAPI app, routers, /health, /metrics placeholders.
- [ ] **T04 — Sessions: domain & storage**
      Implement `sessions.py` (create/delete session, in-memory store).
- [ ] **T05 — Memory (in-memory)**
      Implement message history per session with deque; configurable N (default 10).
- [ ] **T06 — Memory (Redis backend)**
      Add Redis storage option with same interface; auto-select if REDIS_URL present.
- [ ] **T07 — Provider interface**
      Define common provider interface and manager (`agents/manager.py`).
- [ ] **T08 — Provider: OpenAI**
      Implement `providers/openai.py` with async calls.
- [ ] **T09 — Provider: OpenRouter**
      Implement `providers/openrouter.py` with async calls.
- [ ] **T10 — Provider: MCP (client stub)**
      Implement `providers/mcp.py` with handshake + `call_tool`.
- [ ] **T11 — Provider selection logic**
      Per-session default + per-request override via headers/body param.
- [ ] **T12 — Messages endpoint end-to-end**
      `POST /sessions/{id}/messages` wiring provider + memory.
- [ ] **T13 — Rate limiter (in-memory)**
      Token-bucket middleware with RATE_RPS/RATE_BURST.
- [ ] **T14 — Rate limiter (Redis option)**
      Distributed token-bucket using Redis.
- [ ] **T15 — Rate bypass allowlist + admin API**
      IP allowlist store + POST/DELETE /admin/bypass with auth.
- [ ] **T16 — Admin security**
      Token auth for admin endpoints (ENV `ADMIN_TOKEN`).
- [ ] **T17 — Health & Metrics (JSON)**
      Implement /health and /metrics counters.
- [ ] **T18 — Logging & errors**
      Structured logging, consistent error responses.
- [ ] **T19 — Provider fallback**
      Optional fallback provider when primary fails.
- [ ] **T20 — Tests: sessions & memory**
      pytest for session create/delete and memory trimming.
- [ ] **T21 — Tests: rate limit & bypass**
      pytest for 429 and bypass behavior.
- [ ] **T22 — Tests: provider fallback**
      pytest with mocked providers.
- [ ] **T23 — Documentation**
      README with quickstart, config, API summary; update OpenAPI descriptions.
- [ ] **T24 — Docker & Compose**
      Dockerfile and docker-compose (with Redis).
- [ ] **T25 — Polish**
      Final pass on types, comments, and minimal examples.