"""Error envelope for the payment module's HTTP surface.

The module is reached by the API gateway, so it must return the same wire error
shape as the rest of the platform (DELIVERY.md, conventions):

    { "error": { "code": string, "message": string, "details": object? } }

Messages never echo a submitted value, SQL, or a stack trace.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class PaymentError(Exception):
    """A contract error carrying the status code and machine code."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = dict(details) if details else None


def error_body(code: str, message: str, details: Mapping[str, Any] | None = None) -> dict:
    payload: dict[str, Any] = {"code": code, "message": message}
    if details:
        payload["details"] = dict(details)
    return {"error": payload}


async def _payment_error_handler(_: Request, exc: PaymentError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message, exc.details),
    )


async def _validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Only field names travel back, never the submitted value (NFR-024).
    fields = sorted(
        {str(error.get("loc", ("body",))[-1]) for error in exc.errors() if error.get("loc")}
    )
    detail = ", ".join(fields) if fields else "request body"
    return JSONResponse(
        status_code=400,
        content=error_body("invalid_request", f"invalid request field(s): {detail}"),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(PaymentError, _payment_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)


__all__ = ["PaymentError", "error_body", "register_exception_handlers"]
