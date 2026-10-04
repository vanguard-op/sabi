"""Fixtures for the API-service integration and acceptance tests.

Run in a process where only ``services/api`` is on ``sys.path`` (the API service
and the AI service each expose a top-level ``app`` package, so they cannot share an
interpreter). The command that runs this directory sets that up; see
``tests/README.md``.

Reference: CONTRACTS.md, DELIVERY.md, roadmap.md Phase 1.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

_ROOT = Path(__file__).resolve().parents[2]
_API_ROOT = _ROOT / "services" / "api"
_PAYMENTS_ROOT = _ROOT / "services" / "payments"
for _path in (_API_ROOT, _PAYMENTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from app.core.audit import InMemoryAuditLog  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.core.rate_limit import InMemoryRateLimitStore, RateLimiter  # noqa: E402
from app.core.sessions import (  # noqa: E402
    InMemorySessionStore,
    SessionKind,
    SessionManager,
)
from app.db.base import Base  # noqa: E402


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="development",
        session_secret="gate-session-secret",
        recovery_code_pepper="gate-recovery-pepper",
    )


@pytest.fixture
def db_session_factory() -> Iterator[sessionmaker[Session]]:
    # Import the models before create_all so the metadata holds every table,
    # regardless of which test module happens to trigger the first import.
    import app.db.models  # noqa: F401

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def api_app(settings: Settings, db_session_factory: sessionmaker[Session]) -> Iterator[FastAPI]:
    """The real API service, built by its own factory, over in-memory stores."""

    from app.main import create_app

    application = create_app(settings)
    application.state.session_factory = db_session_factory
    application.state.session_manager = SessionManager(settings, InMemorySessionStore())
    application.state.rate_limiter = RateLimiter(
        InMemoryRateLimitStore(), default_limit=1000, default_window_seconds=60
    )
    application.state.audit_log = InMemoryAuditLog()
    yield application


@pytest.fixture
def api_client(api_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(api_app) as client:
        yield client


@pytest.fixture
def session_manager(api_app: FastAPI) -> SessionManager:
    return api_app.state.session_manager


class FakeAgentAIClient:
    """A deterministic stand-in for the gateway's AI-service client.

    The gateway is the client's single entry point, so the assembled API service
    exposes the agent surface without a running AI service. This double lets the
    integration suite prove the gateway forwards the contract request and returns
    the AI service's body unchanged, while the model behaviour itself stays the AI
    service's own suite.
    """

    def __init__(self) -> None:
        self.intent_calls: list[dict] = []
        self.surface_calls: list[dict] = []

    def resolve_intent(
        self,
        *,
        text: str,
        locale: str,
        channel: str,
        history: list[dict] | None = None,
        candidates: list[dict] | None = None,
    ) -> dict:
        self.intent_calls.append({"text": text, "locale": locale, "channel": channel})
        return {
            "reply": "I've got Ikeja Electric. Confirm and I'll prepare it.",
            "intent": {
                "intentType": "bill_payment",
                "target": "svc-electric",
                "amount": None,
                "currency": "NGN",
                "reference": None,
                "constraints": {},
                "confidence": 0.95,
                "detectedLanguage": "pcm",
            },
            "candidates": [],
            "source": "model",
        }

    def compose_surface(self, *, task: str, context: dict) -> dict:
        self.surface_calls.append({"task": task, "context": context})
        # Mirror the AI service's C-012 contract: an unknown task is a 400 with
        # the shared envelope. The gateway must forward that as the same error.
        from app.core.errors import APIError, ErrorCode

        if task not in {"confirmation", "amount_entry", "receipt", "discovery"}:
            raise APIError(400, ErrorCode.INVALID_REQUEST, "That task is not supported.")
        return {"messages": [{"type": "createSurface", "surfaceId": "s1"}], "fallback": task}


@pytest.fixture
def agent_ai_client(api_app: FastAPI) -> FakeAgentAIClient:
    """Substitute the AI-service client the gateway forwards to."""

    from app.agent.deps import get_agent_client

    double = FakeAgentAIClient()
    api_app.state.agent_ai_client = double
    api_app.dependency_overrides[get_agent_client] = lambda: double
    return double


def sign_in(
    client: TestClient,
    manager: SessionManager,
    *,
    kind: SessionKind = SessionKind.USER,
    role: str | None = None,
    mfa_verified: bool = False,
) -> None:
    token, _ = manager.issue(user_id="gate-user", kind=kind, role=role, mfa_verified=mfa_verified)
    client.cookies.set(manager.settings.session_cookie_name, token)


@pytest.fixture
def sign_in_as():
    return sign_in


@pytest.fixture
def seed_user(db_session_factory: sessionmaker[Session]):
    """Create a real account row so account-owner surfaces resolve it.

    The session cookie carries only a user id; the account and channel surfaces
    look that id up, so an integration test must seed the row the way
    registration does rather than mint a session for an unknown id.
    """

    from app.db.models import User

    def _seed(**overrides):
        values = {
            "display_name": "Ngozi",
            "locale": "en",
            "preferred_channel": "app",
            "kyc_status": "unverified",
            "account_status": "active",
        }
        values.update(overrides)
        with db_session_factory() as db:
            user = User(**values)
            db.add(user)
            db.commit()
            db.refresh(user)
            return user.id

    return _seed


@pytest.fixture
def signed_in_user(api_client, session_manager, seed_user, sign_in_as):
    """A client authenticated as a freshly seeded account owner."""

    user_id = seed_user()
    sign_in_as(api_client, session_manager)
    # Reissue the cookie bound to the seeded user id.
    token, _ = session_manager.issue(user_id=user_id)
    api_client.cookies.set(session_manager.settings.session_cookie_name, token)
    return user_id


# --------------------------------------------------------------------------- #
# Phase 2: the payment loop crosses the gateway -> isolated payment module hop.
# --------------------------------------------------------------------------- #


class SyncASGITransport:
    """Drive an ASGI app from a synchronous httpx client, in the same process.

    The API gateway's payment client is synchronous (``httpx.Client``), while
    ``httpx`` only ships an async ASGI transport. This adapter runs the real
    payment-module app in a fresh event loop per request, so the integration
    suite exercises the actual C-017..C-019 HTTP boundary and error envelope
    rather than a hand-written body double. It is a test-transport, never
    application code.
    """

    @property
    def app(self):  # type: ignore[no-untyped-def]
        return self._app

    def __init__(self, app) -> None:  # type: ignore[no-untyped-def]
        self._app = app

    def close(self) -> None:
        """Satisfy the httpx transport lifecycle; no pooled resources to release."""

    def handle_request(self, request):  # type: ignore[no-untyped-def]
        import anyio
        import httpx

        async def _send():
            transport = httpx.ASGITransport(app=self._app)
            async with httpx.AsyncClient(
                transport=transport, base_url=str(request.url.copy_with(path="", query=None))
            ) as client:
                outgoing = client.build_request(
                    request.method,
                    request.url.path,
                    params=request.url.params,
                    headers=request.headers,
                    content=request.content,
                )
                return await client.send(outgoing)

        with anyio.from_thread.start_blocking_portal() as portal:
            response = portal.call(_send)
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            content=response.content,
            request=request,
        )


class _SucceedingRail:
    """A rail double that settles both a charge and a refund."""

    def __init__(self) -> None:
        from sabi_payments.core.rail import RailOutcome
        from sabi_payments.rail.port import RailRefundOutcome

        self.charge_outcome = RailOutcome(status="succeeded", reference="SBX-RAIL-1")
        self.refund_outcome = RailRefundOutcome(status="reversed", refund_reference="SBX-RF-1")
        self.charges: list = []
        self.refunds: list = []

    def charge(self, request):  # type: ignore[no-untyped-def]
        self.charges.append(request)
        return self.charge_outcome

    def refund(self, request):  # type: ignore[no-untyped-def]
        self.refunds.append(request)
        return self.refund_outcome


@pytest.fixture
def payment_rail():
    return _SucceedingRail()


@pytest.fixture
def payment_module_app(payment_rail):
    """The real isolated payment module, over an in-memory store and rail double.

    Built by its own factory so the integration suite proves the assembled whole
    including the module's mandate signing, authorisation-limit, duplicate, and
    idempotency rules (FEAT-005; NFR-027) — not a body echo. Only the store and
    the rail are swapped for tests; the app, routers, validation, and error
    envelope are the delivered code.
    """

    from sabi_payments.core.config import PaymentSettings
    from sabi_payments.db.base import Base as PaymentBase
    from sabi_payments.main import create_app as create_payment_app
    from sabi_payments.payments.service import PaymentService

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    PaymentBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    settings = PaymentSettings(
        _env_file=None,
        environment="development",
        payments_database_url="sqlite://",
        mandate_signing_key="gate-payment-mandate-key",
    )
    application = create_payment_app(settings)
    # The factory `create_app` builds points at its own engine; the service and
    # any test that inspects the store must share the SQLite factory with the
    # tables created above, so bind it on the app state too.
    application.state.session_factory = factory
    application.state.payment_service = PaymentService(
        factory,
        settings=settings,
        rail=payment_rail,
    )
    yield application
    engine.dispose()


@pytest.fixture
def live_payment_module(api_app: FastAPI, payment_module_app) -> Iterator[None]:
    """Point the gateway's payment client at the in-process payment module.

    The gateway forwards over its real HTTP client; only the transport is swapped
    so the hop is real in every other respect. This is the seam a deployment uses
    when the module runs as a separate service.
    """

    import httpx
    from app.payments.client import PaymentEndpoint

    client = api_app.state.payment_module_client
    client._client = httpx.Client(  # type: ignore[assignment]
        base_url=PaymentEndpoint("http://payments", 5.0).base_url,
        transport=SyncASGITransport(payment_module_app),
    )
    yield
    client._client.close()


@pytest.fixture
def payment_lookup():
    """An in-memory payment lookup the receipt and case views read through."""

    from app.payments_port import InMemoryPaymentLookup

    return InMemoryPaymentLookup()


@pytest.fixture
def refund_port():
    """An in-memory refund boundary returning a settled reversal."""

    from app.payments_port import RefundPort, RefundView

    class _Port(RefundPort):
        def __init__(self) -> None:
            self.calls: list[dict] = []
            self.result = RefundView(status="reversed", refund_reference="SBX-RF-1")

        def refund(self, *, user_id, payment_id, reason, idempotency_key) -> RefundView:
            self.calls.append(
                {
                    "user_id": user_id,
                    "payment_id": payment_id,
                    "reason": reason,
                    "idempotency_key": idempotency_key,
                }
            )
            return self.result

    return _Port()


@pytest.fixture
def seed_service(db_session_factory):
    """Create a real catalogue row so the gateway can resolve a payee."""

    from app.db.models import Service

    def _seed(**overrides):
        values = {
            "type": "biller",
            "name": "Ikeja Electric",
            "collecting_body": "Ikeja Electricity Distribution Company",
            "category": "electricity",
            "currency": "NGN",
            "known_amount": 500_00,
            "status": "active",
        }
        values.update(overrides)
        with db_session_factory() as db:
            service = Service(**values)
            db.add(service)
            db.commit()
            db.refresh(service)
            return service.id

    return _seed


@pytest.fixture
def phase2_ports(api_app: FastAPI, payment_lookup, refund_port):
    """Bind the in-memory boundaries the receipt/case/federal views read through.

    A deployment binds its own adapters on these ``app.state`` keys (the ports
    are resolved lazily); the integration suite binds in-memory ones so the
    assembled app's cross-store surfaces are exercised without Postgres or a
    second process.
    """

    api_app.state.receipts_payment_lookup = payment_lookup
    api_app.state.cases_payment_lookup = payment_lookup
    api_app.state.cases_refund_port = refund_port
    api_app.state.federal_payment_lookup = payment_lookup
    yield {"lookup": payment_lookup, "refund": refund_port}


@pytest.fixture
def biller_port():
    """An in-memory biller boundary the everyday-bill flow validates against."""

    from app.bills.ports import InMemoryBillerPort

    return InMemoryBillerPort()


@pytest.fixture
def bill_payment_port():
    """An in-memory payment module for the one-step bill authorise-and-execute."""

    from app.bills.ports import InMemoryBillPaymentPort

    return InMemoryBillPaymentPort()


@pytest.fixture
def bill_ports(api_app: FastAPI, biller_port, bill_payment_port, payment_lookup):
    """Bind the biller, bill-payment, and token-lookup boundaries."""

    api_app.state.bills_biller = biller_port
    api_app.state.bills_payments = bill_payment_port
    api_app.state.bills_payment_lookup = payment_lookup
    yield {"biller": biller_port, "payments": bill_payment_port, "lookup": payment_lookup}


@pytest.fixture
def channel_identity():
    from app.channels.ports import InMemoryChannelIdentityLookup

    return InMemoryChannelIdentityLookup()


@pytest.fixture
def channel_payments():
    from app.channels.ports import InMemoryChannelPaymentPort

    return InMemoryChannelPaymentPort()


@pytest.fixture
def channel_sms():
    from app.channels.ports import InMemorySmsDeliveryPort

    return InMemorySmsDeliveryPort()


@pytest.fixture
def channel_ports(api_app: FastAPI, channel_identity, channel_payments, channel_sms):
    """Bind the USSD/SMS channel's identity, payment, and SMS boundaries."""

    from app.channels.sessions import InMemoryUssdSessionStore

    api_app.state.channels_identity = channel_identity
    api_app.state.channels_payments = channel_payments
    api_app.state.channels_sms = channel_sms
    api_app.state.channels_sessions = InMemoryUssdSessionStore()
    yield {
        "identity": channel_identity,
        "payments": channel_payments,
        "sms": channel_sms,
    }
