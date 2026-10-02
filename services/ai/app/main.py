"""Sabi AI serving application factory.

One deployable service for the model-backed capabilities: intent resolution
(MQ-001, C-009), discovery ranking (MQ-002, C-010), and interface composition
(MQ-003, C-012). The pinned model build and cost ceilings live in :mod:`core.config`;
each capability is exposed as a feature router under ``/v1``.

This is a private model-serving surface behind the API gateway, not a public API.
The client and the channel gateways never call it directly: they reach the gateway
(architecture.md, "API Gateway / Backend-for-Frontend"), which enforces session
authentication and rate limiting and forwards to the corresponding C-009, C-010, or
C-012 path here. The same service is consumed internally by the agent orchestrator.
Because it sits behind the gateway it performs no authentication of its own; it
validates input and returns the frozen contract body or the shared error envelope.

Every capability grounds through the one shared retrieval registry in
:mod:`app.retrieval` and fails closed through :mod:`app.provider`, so a provider
failure degrades to keyword and search resolution with mandatory confirmation rather
than an ungrounded answer.

Feature routers are auto-discovered: a package at ``<feature>/router.py`` that
exposes ``router: APIRouter`` is mounted at ``/v1``, and paths are declared
without the ``/v1`` prefix. A feature that has not landed yet is skipped, so the
service boots at Foundation and picks the router up the moment its package
appears. The API service discovers its domain modules the same way.
"""

from __future__ import annotations

import importlib
import logging
from types import ModuleType

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api import health
from core.config import ModelSettings

logger = logging.getLogger("sabi.ai")

# Model-backed capabilities, per model-quality.md. Names match the package that
# owns each router so discovery stays declarative.
FEATURE_MODULES = ("intent", "ranking", "composition")


def load_feature_router(module_name: str) -> APIRouter | None:
    """Import ``<module_name>.router`` and return its ``router``.

    Returns ``None`` when the feature package has not landed yet. Any other
    import failure propagates, and a module that exists without an ``APIRouter``
    named ``router`` is a wiring error, so boot fails fast instead of silently
    dropping a capability.
    """

    module_path = f"{module_name}.router"
    try:
        module: ModuleType = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        if exc.name in (module_path, module_name):
            logger.debug("feature router not present yet", extra={"feature": module_name})
            return None
        raise

    router = getattr(module, "router", None)
    if not isinstance(router, APIRouter):
        raise TypeError(f"{module_path} must expose a FastAPI APIRouter named 'router'")
    return router


async def _validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Map a request body that fails a schema to the shared error envelope.

    The frozen contracts define 400 (invalid input), not the framework's default
    422 body, so a bad request keeps one wire error shape across the service. Only
    field names are echoed, never the submitted value.
    """

    fields = sorted(
        {str(error.get("loc", ("body",))[-1]) for error in exc.errors() if error.get("loc")}
    )
    detail = ", ".join(fields) if fields else "request body"
    message = f"invalid request field(s): {detail}"
    return JSONResponse(
        status_code=400,
        content={"error": {"code": "invalid_request", "message": message}},
    )


def _include_feature_routers(app: FastAPI) -> None:
    for name in FEATURE_MODULES:
        router = load_feature_router(name)
        if router is not None:
            app.include_router(router, prefix="/v1")


def create_app(settings: ModelSettings | None = None) -> FastAPI:
    settings = settings or ModelSettings.from_env()
    app = FastAPI(
        title="Sabi AI",
        version="1.0.0",
        description=(
            "Private model-serving surface for intent resolution (C-009), discovery "
            "ranking (C-010), and interface composition (C-012). Reached through the "
            "API gateway, which enforces authentication and rate limiting."
        ),
        openapi_url="/openapi.json",
    )
    app.state.settings = settings

    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.include_router(health.router)
    _include_feature_routers(app)
    return app


app = create_app()
