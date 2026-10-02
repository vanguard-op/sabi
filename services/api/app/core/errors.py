"""Error envelope and exception handlers.

Every error the API returns uses one shape (DELIVERY.md, conventions):

    { "error": { "code": string, "message": string, "details": object? } }

Handlers never echo raw input, SQL, or stack traces: validation details are
scrubbed so a submitted secret cannot travel back in a response (NFR-024).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("sabi.errors")


class ErrorCode(StrEnum):
    """Stable machine-readable error codes shared with the client."""

    INVALID_REQUEST = "invalid_request"
    VALIDATION_FAILED = "validation_failed"
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"
    CHALLENGE_EXPIRED = "challenge_expired"
    PAYMENT_UNAVAILABLE = "payment_unavailable"
    INTERNAL_ERROR = "internal_error"


_STATUS_CODES: dict[int, ErrorCode] = {
    400: ErrorCode.INVALID_REQUEST,
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    409: ErrorCode.CONFLICT,
    410: ErrorCode.CHALLENGE_EXPIRED,
    422: ErrorCode.VALIDATION_FAILED,
    429: ErrorCode.RATE_LIMITED,
    503: ErrorCode.PAYMENT_UNAVAILABLE,
}


class APIError(Exception):
    """Raised by services to return a contract error with the standard envelope."""

    def __init__(
        self,
        status_code: int,
        code: ErrorCode | str,
        message: str,
        details: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = str(code)
        self.message = message
        self.details = dict(details) if details else None
        self.headers = dict(headers) if headers else None


def error_body(code: str, message: str, details: Mapping[str, Any] | None = None) -> dict:
    payload: dict[str, Any] = {"code": code, "message": message}
    if details:
        payload["details"] = dict(details)
    return {"error": payload}


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=error_body(code, message, details),
        headers=dict(headers) if headers else None,
    )


def _scrub_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep loc/type/msg; drop the input value and context (may hold secrets)."""
    scrubbed = []
    for error in errors:
        scrubbed.append(
            {
                "loc": [str(part) for part in error.get("loc", [])],
                "type": error.get("type"),
                "msg": error.get("msg"),
            }
        )
    return scrubbed


async def _api_error_handler(_: Request, exc: APIError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message, exc.details, exc.headers)


async def _validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(
        422,
        ErrorCode.VALIDATION_FAILED,
        "The request is not valid.",
        {"fields": _scrub_validation_errors(exc.errors())},
    )


async def _http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _STATUS_CODES.get(exc.status_code, ErrorCode.INVALID_REQUEST)
    message = exc.detail if isinstance(exc.detail, str) else "The request failed."
    return error_response(exc.status_code, code, message, headers=getattr(exc, "headers", None))


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "unhandled error",
        extra={"path": request.url.path, "method": request.method},
    )
    return error_response(500, ErrorCode.INTERNAL_ERROR, "Something went wrong on our side.")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(APIError, _api_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
