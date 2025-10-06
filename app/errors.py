"""Centralised error types and handlers for the API."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, MutableMapping, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")


@dataclass(slots=True)
class APIError(Exception):
    """Application-level error representation with structured payload."""

    status_code: int
    code: str
    message: str
    details: Optional[Mapping[str, Any]] = None

    def to_payload(self, request: Optional[Request] = None) -> Dict[str, Any]:
        """Create a serialisable payload for HTTP responses."""

        payload: Dict[str, Any] = {
            "error": {
                "code": self.code,
                "message": self.message,
            }
        }
        if self.details:
            payload["error"]["details"] = dict(self.details)
        if request is not None:
            request_id = getattr(request.state, "request_id", None)
            if request_id:
                payload["request_id"] = request_id
        return payload

    def to_response(self, request: Optional[Request] = None) -> JSONResponse:
        """Serialise the error into a ``JSONResponse``."""

        return JSONResponse(status_code=self.status_code, content=self.to_payload(request))


def _normalise_http_detail(detail: Any) -> MutableMapping[str, Any]:
    """Convert HTTPException details into a predictable mapping."""

    if isinstance(detail, Mapping):
        return dict(detail)
    return {"message": str(detail)}


def _payload_from_http_exception(
    request: Request, exc: StarletteHTTPException
) -> Dict[str, Any]:
    detail = _normalise_http_detail(exc.detail)
    code = detail.pop("error", "http_error")
    message = detail.pop("message", exc.detail if isinstance(exc.detail, str) else exc.reason)
    api_error = APIError(status_code=exc.status_code, code=code, message=str(message), details=detail or None)
    return api_error.to_payload(request)


async def _api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    logger.warning(
        "api_error",
        extra={
            "event": "api_error",
            "code": exc.code,
            "status_code": exc.status_code,
            "path": request.url.path,
            "method": request.method,
        },
    )
    return exc.to_response(request)


async def _http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    payload = _payload_from_http_exception(request, exc)
    logger.warning(
        "http_exception",
        extra={
            "event": "http_exception",
            "status_code": exc.status_code,
            "path": request.url.path,
            "method": request.method,
            "code": payload["error"]["code"],
        },
    )
    return JSONResponse(status_code=exc.status_code, content=payload)


async def _validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = {
        "errors": exc.errors(),
        "body": exc.body,
    }
    error = APIError(
        status_code=422,
        code="validation_error",
        message="Request validation failed.",
        details=details,
    )
    logger.warning(
        "validation_error",
        extra={
            "event": "validation_error",
            "path": request.url.path,
            "method": request.method,
            "errors": exc.errors(),
        },
    )
    return error.to_response(request)


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "internal_error",
        extra={
            "event": "internal_error",
            "path": request.url.path,
            "method": request.method,
        },
    )
    error = APIError(
        status_code=500,
        code="internal_error",
        message="An unexpected error occurred.",
        details={"timestamp": datetime.now(timezone.utc).isoformat()},
    )
    return error.to_response(request)


def register_exception_handlers(app: FastAPI) -> None:
    """Register standard exception handlers on the application."""

    app.add_exception_handler(APIError, _api_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)


__all__ = ["APIError", "register_exception_handlers"]
