"""Payment module application.

Separately deployable, with its own store and audit log. The modular monolith
reaches it through a port; nothing here imports the primary application.

The payment surface is behind the API gateway, which authenticates the account
owner and forwards the resolved payee. This service performs no session
authentication of its own and returns the frozen C-017..C-019 bodies or the
shared error envelope (architecture.md, "Payment Module").
"""

from __future__ import annotations

import importlib
from types import ModuleType

from fastapi import APIRouter, FastAPI

from sabi_payments.core.config import PaymentSettings, get_payment_settings
from sabi_payments.core.errors import register_exception_handlers
from sabi_payments.db.audit import PaymentAuditLog
from sabi_payments.db.session import build_session_factory
from sabi_payments.payments.service import PaymentService
from sabi_payments.rail.factory import build_rail

# Feature routers are auto-discovered: a package exposing ``router: APIRouter``
# is mounted at ``/v1`` and declares its paths without the prefix.
FEATURE_MODULES = ("payments",)


def _load_feature_router(module_name: str) -> APIRouter | None:
    module_path = f"sabi_payments.{module_name}.router"
    try:
        module: ModuleType = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        if exc.name in (module_path, f"sabi_payments.{module_name}"):
            return None
        raise
    router = getattr(module, "router", None)
    if not isinstance(router, APIRouter):
        raise TypeError(f"{module_path} must expose a FastAPI APIRouter named 'router'")
    return router


def create_app(settings: PaymentSettings | None = None) -> FastAPI:
    settings = settings or get_payment_settings()
    app = FastAPI(
        title="Sabi Payments",
        version="1.0.0",
        description=(
            "Isolated payment module: signed mandates, execution, state, and audit "
            "(FEAT-005). Reached through the API gateway."
        ),
        openapi_url="/openapi.json",
    )
    app.state.settings = settings
    session_factory = build_session_factory(settings)
    app.state.session_factory = session_factory
    app.state.audit_log = PaymentAuditLog(session_factory)
    app.state.payment_service = PaymentService(
        session_factory,
        settings=settings,
        audit=app.state.audit_log,
        rail=build_rail(),
    )

    register_exception_handlers(app)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    for name in FEATURE_MODULES:
        router = _load_feature_router(name)
        if router is not None:
            app.include_router(router, prefix="/v1")

    return app


app = create_app()
