# Docker Assets

This directory groups the container build assets for the chat service and the
optional ham3d MCP server. The `docker-compose.yml` file now lives alongside
these Dockerfiles, so reference it explicitly (for example with
`docker compose -f docker/docker-compose.yml ...`) when launching services from
the project root.

## Images

- `api.Dockerfile` – Builds the FastAPI application image that powers the chat
  service. The resulting container runs `uvicorn app.main:app` as a non-root
  user.
- `ham3d.Dockerfile` – Packages the ham3d MySQL-backed MCP server. The entry
  point launches `python -m mcp_servers.ham3d_mysql` so the MCP agent can
  connect over stdio.

Both images install dependencies from `requirements.txt`. Provide database
credentials for the ham3d server via environment variables before starting the
container (for example by populating `.env`).

## Example commands

```bash
# Build and run the API locally
docker compose -f docker/docker-compose.yml up --build

# Build and launch the ham3d MCP server profile only
docker compose -f docker/docker-compose.yml --profile mcp run --rm mcp-ham3d
```

To build either image manually with `docker build`, pass the Dockerfile path
explicitly. For example:

```bash
docker build -f docker/api.Dockerfile -t chat-api .
docker build -f docker/ham3d.Dockerfile -t ham3d-mcp .
```
