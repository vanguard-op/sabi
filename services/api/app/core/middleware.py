"""ASGI middleware for correlation ids and security headers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import Settings
from app.core.logging import set_correlation_id

RequestHandler = Callable[[Request], Awaitable[Response]]


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Propagate an inbound request id, or mint one, on every response."""

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        correlation_id = set_correlation_id(request.headers.get("X-Request-ID"))
        response = await call_next(request)
        response.headers["X-Request-ID"] = correlation_id
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Transport and content hardening (NFR-022, NFR-025)."""

    def __init__(self, app, settings: Settings) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        response = await call_next(request)
        if self.settings.hsts_enabled:
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'none'"
        return response
