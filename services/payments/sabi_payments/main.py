"""Payment module application.

Separately deployable, with its own store and audit log. The modular monolith
reaches it through a port; nothing here imports the primary application.
"""

from __future__ import annotations

from fastapi import FastAPI

from sabi_payments.core.config import PaymentSettings, get_payment_settings
from sabi_payments.db.session import build_session_factory


def create_app(settings: PaymentSettings | None = None) -> FastAPI:
    settings = settings or get_payment_settings()
    app = FastAPI(title="Sabi Payments", version="1.0.0", openapi_url="/openapi.json")
    app.state.settings = settings
    app.state.session_factory = build_session_factory(settings)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
