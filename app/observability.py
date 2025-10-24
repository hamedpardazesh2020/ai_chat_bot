"""Utilities for application health checks and lightweight metrics."""
from __future__ import annotations

import asyncio
from asyncio import Lock
from collections import defaultdict
from time import time
from typing import Any, Dict, Optional


class MetricsCollector:
    """Collect simple in-memory metrics for the API."""

    def __init__(self) -> None:
        self._lock: Optional[Lock] = None
        self._lock_loop: Optional[asyncio.AbstractEventLoop] = None
        self._requests_total = 0
        self._responses_total = 0
        self._errors_total = 0
        self._latency_total = 0.0
        self._latency_count = 0
        self._requests_by_method: Dict[str, int] = defaultdict(int)
        self._responses_by_status: Dict[str, int] = defaultdict(int)
        self._started_at = time()

    async def record_request(self, method: str) -> None:
        """Record an incoming request."""

        lock = self._ensure_lock()
        async with lock:
            self._requests_total += 1
            self._requests_by_method[method.upper()] += 1

    async def record_response(self, status_code: int, latency_seconds: float) -> None:
        """Record a completed response."""

        lock = self._ensure_lock()
        async with lock:
            self._responses_total += 1
            self._responses_by_status[str(status_code)] += 1
            self._latency_total += latency_seconds
            self._latency_count += 1
            if status_code >= 500:
                self._errors_total += 1

    async def record_exception(self) -> None:
        """Record an exception raised during request handling."""

        lock = self._ensure_lock()
        async with lock:
            self._errors_total += 1

    def uptime_seconds(self) -> float:
        """Return seconds elapsed since collector initialisation."""

        return time() - self._started_at

    async def snapshot(self) -> Dict[str, Any]:
        """Return a copy of the current metrics state."""

        lock = self._ensure_lock()
        async with lock:
            avg_latency_ms = (
                (self._latency_total / self._latency_count) * 1000
                if self._latency_count
                else 0.0
            )
            return {
                "requests_total": self._requests_total,
                "responses_total": self._responses_total,
                "errors_total": self._errors_total,
                "requests_by_method": dict(self._requests_by_method),
                "responses_by_status": dict(self._responses_by_status),
                "request_latency_avg_ms": round(avg_latency_ms, 3),
            }

    def _ensure_lock(self) -> Lock:
        """Return a lock bound to the current running event loop."""

        loop = asyncio.get_running_loop()
        lock = self._lock
        if (
            lock is None
            or self._lock_loop is None
            or self._lock_loop.is_closed()
            or self._lock_loop is not loop
        ):
            lock = Lock()
            self._lock = lock
            self._lock_loop = loop
        return lock


__all__ = ["MetricsCollector"]
