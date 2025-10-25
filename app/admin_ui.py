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
    """Render the session management dashboard."""

    return templates.TemplateResponse(
        "admin/sessions.html",
        {"request": request, "page_id": "sessions"},
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
