"""Sabi AI serving application factory.

One deployable service for the model-backed capabilities: intent resolution
(MQ-001), discovery ranking (MQ-002), and interface composition (MQ-003). The
pinned model build and cost ceilings live in :mod:`core.config`; each capability
is exposed as a feature router under ``/v1``.

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

from fastapi import APIRouter, FastAPI

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
            "Model serving for intent resolution, discovery ranking, and interface composition."
        ),
        openapi_url="/openapi.json",
    )
    app.state.settings = settings

    app.include_router(health.router)
    _include_feature_routers(app)
    return app


app = create_app()
