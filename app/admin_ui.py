"""Lightweight admin interface views rendered with Jinja templates."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

router = APIRouter(prefix="/admin/ui", tags=["admin-ui"])


@router.get("/", response_class=HTMLResponse, name="admin-ui-home")
async def home_page(request: Request) -> HTMLResponse:
    """Render the admin home page with quick links to tools."""

    return templates.TemplateResponse(
        "admin/home.html",
        {"request": request, "page_id": "home"},
    )


@router.get("/sessions", response_class=HTMLResponse, name="admin-ui-sessions")
async def sessions_page(request: Request) -> HTMLResponse:
    """Render the session management dashboard (legacy - redirects to active sessions)."""

    return templates.TemplateResponse(
        "admin/sessions.html",
        {"request": request, "page_id": "sessions"},
    )


@router.get("/active-sessions", response_class=HTMLResponse, name="admin-ui-active-sessions")
async def active_sessions_page(request: Request) -> HTMLResponse:
    """Render the active sessions page with time-based filtering."""

    return templates.TemplateResponse(
        "admin/active_sessions.html",
        {"request": request, "page_id": "active-sessions"},
    )


@router.get("/sessions/{session_id}/history", response_class=HTMLResponse, name="admin-ui-session-history")
async def session_history_page(request: Request, session_id: str) -> HTMLResponse:
    """Render the session chat history page."""

    return templates.TemplateResponse(
        "admin/session_history.html",
        {"request": request, "page_id": "session-history", "session_id": session_id},
    )


@router.get("/history", response_class=HTMLResponse, name="admin-ui-history")
async def history_page(request: Request) -> HTMLResponse:
    """Render the chat history sessions page with date filtering."""

    return templates.TemplateResponse(
        "admin/history.html",
        {"request": request, "page_id": "history"},
    )


@router.get("/metrics", response_class=HTMLResponse, name="admin-ui-metrics")
async def metrics_page(request: Request) -> HTMLResponse:
    """Render the in-app metrics visualisation."""

    return templates.TemplateResponse(
        "admin/metrics.html",
        {"request": request, "page_id": "metrics"},
    )


@router.get("/runtime", response_class=HTMLResponse, name="admin-ui-runtime")
async def runtime_page(request: Request) -> HTMLResponse:
    """Render the runtime diagnostics view."""

    return templates.TemplateResponse(
        "admin/runtime.html",
        {"request": request, "page_id": "runtime"},
    )


@router.get("/bypass", response_class=HTMLResponse, name="admin-ui-bypass")
async def bypass_page(request: Request) -> HTMLResponse:
    """Render the rate limit bypass management console."""

    return templates.TemplateResponse(
        "admin/bypass.html",
        {"request": request, "page_id": "bypass"},
    )


@router.get("/token", response_class=HTMLResponse, name="admin-ui-token")
async def token_page(request: Request) -> HTMLResponse:
    """Render the admin token management screen."""

    return templates.TemplateResponse(
        "admin/token.html",
        {"request": request, "page_id": "token"},
    )


@router.get("/config", response_class=HTMLResponse, name="admin-ui-config")
async def config_page(request: Request) -> HTMLResponse:
    """Render the application configuration management interface."""

    return templates.TemplateResponse(
        "admin/config.html",
        {"request": request, "page_id": "config"},
    )
