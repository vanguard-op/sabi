"""Sabi API application factory.

One deployable modular monolith: identity, catalogue, the agent, receipts, and
notifications share this app and the primary store. The payment module is
isolated behind ``app.payments`` and its own store (architecture.md).
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
from collections.abc import AsyncIterator, Callable, Iterable
from contextlib import asynccontextmanager
from types import ModuleType

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
from app.payments.client import HttpPaymentModuleRefundPort, build_payment_client

logger = logging.getLogger("sabi.app")

# The module inventory for the API surface under /v1. A module that has not
# landed yet (its package directory is absent) is skipped so the monolith boots
# at Foundation and picks the router up when the module appears. Dotted names
# are nested packages with their own router, such as identity verification under
# the identity module. Every other landed package must expose
# ``app/<name>/router.py``: a package that is present but whose router cannot be
# imported is a contract violation and fails the boot rather than being skipped.
MODULE_NAMES = (
    "identity",
    "identity.verification",
    "catalogue",
    "registry",
    "agent",
    "payments",
    "receipts",
    "cases",
    "bills",
    "channels",
    "staff",
    "federal",
    "audit",
    "reconciliation",
)

# Landed packages that intentionally expose no HTTP surface: job and service
# layers reached in-process or by the scheduler, never by a client. They are
# part of the module inventory but mount nothing, so the guard skips them by
# declaration rather than by guessing from a failed import.
ROUTERLESS_MODULES = frozenset({"reconciliation"})


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


def _module_landed(
    module_path: str,
    *,
    find_spec: Callable[[str], object | None] = importlib.util.find_spec,
) -> bool:
    """Whether the module's package is present on disk.

    Presence is read from the package itself, not inferred from an import
    failure: a router module that is missing says nothing about whether its
    package landed.
    """
    package_path = module_path.rsplit(".router", 1)[0]
    try:
        return find_spec(package_path) is not None
    except ModuleNotFoundError:
        # A missing parent package means the submodule never landed.
        return False


def _include_module_routers(
    app: FastAPI,
    *,
    module_names: Iterable[str] = MODULE_NAMES,
    routerless: frozenset[str] = ROUTERLESS_MODULES,
    find_spec: Callable[[str], object | None] = importlib.util.find_spec,
    import_module: Callable[[str], ModuleType] = importlib.import_module,
) -> None:
    for name in module_names:
        module_path = f"app.{name}.router"
        if not _module_landed(module_path, find_spec=find_spec):
            logger.debug("module has not landed yet", extra={"app_module": name})
            continue
        try:
            module = import_module(module_path)
        except ModuleNotFoundError as exc:
            # The package landed, so a missing router module is a module that
            # declares no HTTP surface, or a real gap. Only the declared
            # routerless modules are allowed to be absent; everything else
            # surfaces instead of booting without its routes.
            if exc.name == module_path and name in routerless:
                logger.debug("module declares no HTTP surface", extra={"app_module": name})
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
        for state_key in ("agent_ai_client", "payment_module_client"):
            client = getattr(application.state, state_key, None)
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
    app.state.payment_module_client = build_payment_client(settings)
    # The case workflow's refund boundary now resolves to the isolated payment
    # module over the same hop the gateway's payment endpoints use (C-029).
    app.state.cases_refund_port = HttpPaymentModuleRefundPort(app.state.payment_module_client)

    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(CorrelationIdMiddleware)

    register_exception_handlers(app)
    app.include_router(health.router)
    _include_module_routers(app)
    return app


app = create_app()
