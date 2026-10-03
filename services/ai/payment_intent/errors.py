"""Contract error envelope for the payment-intent endpoint.

Everything the module returns uses the one shape from the delivery conventions:

    { "error": { "code": string, "message": string, "details": object? } }

A body that fails validation is mapped to 400 rather than the framework's default
422, so the module keeps one wire error shape. Error messages never echo the submitted
value back.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: Mapping[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = dict(details)
    return JSONResponse(status_code=status_code, content=body)


def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Map a request body that fails the schema to the contract's 400 envelope."""

    fields = sorted(
        {str(error.get("loc", ("body",))[-1]) for error in exc.errors() if error.get("loc")}
    )
    detail = ", ".join(fields) if fields else "request body"
    return error_response(400, "invalid_request", f"invalid request field(s): {detail}")


__all__ = ["error_response", "validation_error_handler"]
