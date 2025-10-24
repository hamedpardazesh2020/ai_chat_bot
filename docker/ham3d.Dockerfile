# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY mcp_servers ./mcp_servers

RUN useradd --create-home mcpuser
USER mcpuser

ENV PYTHONPATH=/app

CMD ["python", "-m", "mcp_servers.ham3d_mysql"]
