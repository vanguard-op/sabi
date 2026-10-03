"""Sabi API application factory.

One deployable modular monolith: identity, catalogue, the agent, receipts, and
notifications share this app and the primary store. The payment module is
isolated behind ``app.payments`` and its own store (architecture.md).
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agent.client import build_agent_client
from app.api import health
from app.core.audit import AuditLog
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import CorrelationIdMiddleware, SecurityHeadersMiddleware
from app.core.rate_limit import (
    InMemoryRateLimitStore,
    RateLimiter,
    RedisRateLimitStore,
)
from app.core.sessions import InMemorySessionStore, RedisSessionStore, SessionManager
from app.db.audit import DatabaseAuditLog
from app.db.session import build_session_factory

logger = logging.getLogger("sabi.app")

# Modules that own a router under /v1. A module that has not landed yet is
# skipped so the monolith boots at Foundation and picks the router up when the
# module directory appears. Dotted names are nested packages with their own
# router, such as identity verification under the identity module.
MODULE_NAMES = ("identity", "identity.verification", "catalogue", "registry", "agent", "receipts", "cases", "staff")


def _build_session_store(settings: Settings):
    if settings.environment == "development":
        return InMemorySessionStore()
    return RedisSessionStore(settings.cache_url)


def _build_rate_limit_store(settings: Settings):
    if settings.environment == "development":
        return InMemoryRateLimitStore()
    return RedisRateLimitStore(settings.cache_url)


def _build_audit_log(session_factory) -> AuditLog:  # type: ignore[no-untyped-def]
    return DatabaseAuditLog(session_factory)


def _include_module_routers(app: FastAPI) -> None:
    for name in MODULE_NAMES:
        module_path = f"app.{name}.router"
        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError as exc:
            # Only a missing router module or its parent package is "not landed
            # yet". A ModuleNotFoundError raised from inside an installed
            # dependency must surface, not be swallowed as an absent module.
            missing_self = exc.name == module_path
            missing_parent = exc.name in {f"app.{name}", "app", "app." + name.split(".")[0]}
            if missing_self or missing_parent:
                logger.debug("module router not present yet", extra={"app_module": name})
                continue
            raise
        router = getattr(module, "router", None)
        if router is None:
            raise RuntimeError(f"{module_path} defines no `router` (MODULE_NAMES contract)")
        app.include_router(router, prefix="/v1")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        yield
        # Close whatever client is bound at shutdown time: the factory builds one,
        # and a test may have substituted a double without a close method.
        client = getattr(application.state, "agent_ai_client", None)
        if client is not None and hasattr(client, "close"):
            client.close()

    app = FastAPI(
        title="Sabi API",
        version="1.0.0",
        description="Payable services, the assistant, and receipts for Nigerian users.",
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    session_factory = build_session_factory(settings)
    app.state.session_factory = session_factory
    app.state.session_manager = SessionManager(settings, _build_session_store(settings))
    app.state.rate_limiter = RateLimiter(
        _build_rate_limit_store(settings),
        default_limit=settings.auth_rate_limit_requests,
        default_window_seconds=settings.auth_rate_limit_window_seconds,
    )
    app.state.audit_log = _build_audit_log(session_factory)
    app.state.agent_ai_client = build_agent_client()

    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(CorrelationIdMiddleware)

    register_exception_handlers(app)
    app.include_router(health.router)
    _include_module_routers(app)
    return app


app = create_app()
