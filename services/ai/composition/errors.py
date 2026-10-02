"""Contract error envelope for the composition endpoints.

Everything the service returns uses one shape (DELIVERY.md conventions):

    { "error": { "code": string, "message": string } }

The frozen C-012 contract defines 400 for an unknown task, so validation
failures and the unknown-task branch are mapped to that envelope rather than the
framework's default ``{"detail": ...}`` body.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    body = {"error": {"code": code, "message": message}}
    return JSONResponse(status_code=status_code, content=body)


def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Map a request body that fails the schema to the contract's 400 envelope.

    Field names only; the submitted value is never echoed back.
    """

    fields = sorted(
        {str(error.get("loc", ("body",))[-1]) for error in exc.errors() if error.get("loc")}
    )
    detail = ", ".join(fields) if fields else "request body"
    return error_response(400, "invalid_request", f"invalid request field(s): {detail}")
