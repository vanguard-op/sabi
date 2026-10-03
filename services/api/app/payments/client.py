"""Boundary from the API gateway to the isolated payment module over HTTP.

The gateway is the client's single entry point (architecture.md, "API Gateway /
Backend-for-Frontend"). It authenticates the account owner, resolves the service
to its collecting body, and forwards the three payment operations the client
needs to the separately deployable payment module (architecture.md, "Payment
Module"). The module performs no authentication of its own because it sits
behind this hop, so trusted context travels as headers, never in the client body:

- ``X-Sabi-User-Id``: the authenticated account owner the operation is scoped to.
- ``X-Sabi-Payee``: the collecting body the gateway resolved for the service.
- ``X-Sabi-Service-Type``: the catalogue service type, so the module records a
  government payment distinctly from an everyday bill.
- ``X-Sabi-Authorisation-Limit``: the user's set limit in kobo, when the gateway
  knows one. Absent means the module applies its configured default (FEAT-005).

The gateway also forwards a refund (C-029) through the same hop. A refund acts on
a payment the module already holds, so its context carries only the account owner;
the module's refund body travels back unchanged. The port the case workflow
consumes is :class:`HttpPaymentModuleRefundPort`, which adapts a module response
to the cross-store ``RefundView``.

The upstream module returns the same shared error envelope the API uses, so an
upstream 4xx is re-raised with its code, message, and details intact. The details
matter for C-017: an upstream 409 carries the existing ``paymentId`` and
``railReference`` so a duplicate authorisation resolves to the first payment. The
same pass-through covers C-029's duplicate-refund 409.

A transport failure, a timeout, or an unexpected status means the module cannot
be reached at all; that is reported as ``payment_unavailable`` (503) rather than
being dressed up as a declined payment, because the gateway has no grounded
result to give the client.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import httpx

from app.core.errors import APIError, ErrorCode
from app.core.identity import IdentityTokenProvider
from app.payments_port import RefundView

logger = logging.getLogger("sabi.payments")

# Transport error code for an unreachable payment module. It is a gateway
# condition, not part of the C-017..C-019 error lists, which describe direct
# calls to the module.
PAYMENT_UNAVAILABLE = "payment_unavailable"

_DEFAULT_PAYMENTS_HOST = "localhost"
_DEFAULT_PAYMENTS_PORT = 8002
_DEFAULT_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class PaymentEndpoint:
    """Resolved base URL and timeout for the payment module."""

    base_url: str
    timeout_seconds: float

    @classmethod
    def from_settings(cls, settings: Any) -> PaymentEndpoint:
        """Build from application settings, with an env override for the base.

        ``PAYMENTS_BASE_URL`` wins when set so a deployment can point the hop at
        a service address without a code change; otherwise the configured base
        URL is used, falling back to host and port.
        """

        override = os.environ.get("PAYMENTS_BASE_URL", "").strip()
        if override:
            return cls(base_url=override.rstrip("/"), timeout_seconds=_timeout(settings))
        configured = str(getattr(settings, "payments_base_url", "") or "").strip()
        if configured:
            return cls(base_url=configured.rstrip("/"), timeout_seconds=_timeout(settings))
        host = os.environ.get("PAYMENTS_HOST", "").strip() or _DEFAULT_PAYMENTS_HOST
        port = os.environ.get("PAYMENTS_PORT", "").strip() or str(_DEFAULT_PAYMENTS_PORT)
        return cls(base_url=f"http://{host}:{port}", timeout_seconds=_timeout(settings))


def _timeout(settings: Any) -> float:
    raw = os.environ.get("PAYMENTS_REQUEST_TIMEOUT_SECONDS", "").strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    configured = getattr(settings, "payments_request_timeout_seconds", None)
    if isinstance(configured, (int, float)) and configured > 0:
        return float(configured)
    return _DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True, slots=True)
class ForwardContext:
    """The trusted values the gateway attaches to a forwarded call.

    ``payee`` and ``service_type`` are set only for the authorisation call,
    which resolves a service; execution and listing are scoped to the account
    owner alone, so their context carries just ``user_id``.
    """

    user_id: str
    payee: str | None = None
    service_type: str | None = None
    authorisation_limit: int | None = None


@runtime_checkable
class PaymentModuleClient(Protocol):
    """The payment operations the gateway forwards (C-017..C-019, C-029)."""

    def authorise(
        self, *, context: ForwardContext, body: dict[str, Any], idempotency_key: str | None
    ) -> dict[str, Any]: ...

    def execute(
        self,
        *,
        context: ForwardContext,
        payment_id: str,
        body: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]: ...

    def list_payments(
        self, *, context: ForwardContext, cursor: str | None, limit: int, status: str | None
    ) -> dict[str, Any]: ...

    def refund(
        self,
        *,
        context: ForwardContext,
        payment_id: str,
        body: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]: ...


class HttpPaymentModuleClient:
    """Forwards to the payment module over HTTP with a single pooled client."""

    def __init__(
        self,
        endpoint: PaymentEndpoint,
        *,
        identity_provider: IdentityTokenProvider | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=endpoint.base_url,
            timeout=endpoint.timeout_seconds,
        )
        # The payment module is a private Cloud Run service; the audience is its
        # origin. Local and test transports bind no provider and keep the plain
        # HTTP hop unchanged.
        self._audience = str(httpx.URL(endpoint.base_url))
        self._identity_provider = identity_provider

    def close(self) -> None:
        self._client.close()

    def authorise(
        self, *, context: ForwardContext, body: dict[str, Any], idempotency_key: str | None
    ) -> dict[str, Any]:
        headers = self._headers(context)
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return self._post("/v1/payments/authorise", json=body, headers=headers)

    def execute(
        self,
        *,
        context: ForwardContext,
        payment_id: str,
        body: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        headers = self._headers(context)
        headers["Idempotency-Key"] = idempotency_key
        return self._post(f"/v1/payments/{payment_id}/execute", json=body, headers=headers)

    def list_payments(
        self, *, context: ForwardContext, cursor: str | None, limit: int, status: str | None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        if status:
            params["status"] = status
        return self._get("/v1/payments", params=params, headers=self._headers(context))

    def refund(
        self,
        *,
        context: ForwardContext,
        payment_id: str,
        body: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        headers = self._headers(context)
        headers["Idempotency-Key"] = idempotency_key
        return self._post(f"/v1/payments/{payment_id}/refund", json=body, headers=headers)

    @staticmethod
    def _headers(context: ForwardContext) -> dict[str, str]:
        headers = {"X-Sabi-User-Id": context.user_id}
        if context.payee is not None:
            headers["X-Sabi-Payee"] = context.payee
        if context.service_type is not None:
            headers["X-Sabi-Service-Type"] = context.service_type
        if context.authorisation_limit is not None:
            headers["X-Sabi-Authorisation-Limit"] = str(context.authorisation_limit)
        return headers

    def _auth_headers(self) -> dict[str, str]:
        """Attach an identity token for the private origin, when configured.

        The value is a credential: it travels on the request only and is never
        logged. No provider means local or test transport, and the hop stays a
        plain unauthenticated HTTP call.
        """
        if self._identity_provider is None:
            return {}
        return {"Authorization": f"Bearer {self._identity_provider.token(self._audience)}"}

    def _post(self, path: str, *, json: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        try:
            response = self._client.post(
                path, json=json, headers={**headers, **self._auth_headers()}
            )
        except httpx.HTTPError:
            # Never surface the underlying transport detail; it can carry the
            # service address. The client gets one retryable message.
            logger.warning("payment module call failed", extra={"path": path})
            raise PaymentModuleUnavailable() from None
        return _read(response, path)

    def _get(self, path: str, *, params: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        try:
            response = self._client.get(
                path, params=params, headers={**headers, **self._auth_headers()}
            )
        except httpx.HTTPError:
            logger.warning("payment module call failed", extra={"path": path})
            raise PaymentModuleUnavailable() from None
        return _read(response, path)


def _read(response: httpx.Response, path: str) -> dict[str, Any]:
    if response.status_code >= 500:
        logger.warning(
            "payment module returned a server error",
            extra={"path": path, "status": response.status_code},
        )
        raise PaymentModuleUnavailable()
    if response.status_code >= 400:
        raise _upstream_error(response)
    try:
        payload = response.json()
    except ValueError:
        logger.warning("payment module returned a non-JSON body", extra={"path": path})
        raise PaymentModuleUnavailable() from None
    if not isinstance(payload, dict):
        raise PaymentModuleUnavailable()
    return payload


class PaymentModuleUnavailable(APIError):
    """The payment module could not be reached or answered unexpectedly."""

    def __init__(self) -> None:
        super().__init__(
            503,
            PAYMENT_UNAVAILABLE,
            "Payments are paused right now. Your request is safe; try again shortly.",
        )


def _upstream_error(response: httpx.Response) -> APIError:
    """Translate a 4xx from the payment module into the same contract error.

    The module returns a shared envelope whose details may carry the existing
    payment for a duplicate authorisation (C-017 409). Code, message, and
    details are forwarded verbatim; an unexpected body falls back to the code
    implied by the status. Only envelope fields are read, never the upstream URL
    or headers.
    """

    status = response.status_code
    code: str = ErrorCode.INVALID_REQUEST
    message = "That request is not valid."
    details: dict[str, Any] | None = None
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            if isinstance(error.get("code"), str) and error["code"]:
                code = error["code"]
            if isinstance(error.get("message"), str) and error["message"]:
                message = error["message"]
            if isinstance(error.get("details"), dict):
                details = dict(error["details"])
    return APIError(status, code, message, details=details)


def build_payment_client(
    settings: Any, *, identity_provider: IdentityTokenProvider | None = None
) -> HttpPaymentModuleClient:
    return HttpPaymentModuleClient(
        PaymentEndpoint.from_settings(settings), identity_provider=identity_provider
    )


class HttpPaymentModuleRefundPort:
    """The case workflow's refund boundary, backed by the payment module hop.

    The case service consumes the cross-store :class:`RefundPort`; this adapter
    forwards to the module's C-029 endpoint through the same client the gateway
    uses, so a refund and a gateway-originated call share one hop and one
    transport. The owner is the only trusted context a refund needs, and the
    idempotency key travels as the contract header. The module's body supplies
    the status and reference; a payload without a usable status is treated as an
    unreachable module, never fabricated into a settled refund.
    """

    def __init__(self, client: PaymentModuleClient) -> None:
        self._client = client

    def refund(
        self,
        *,
        user_id: str,
        payment_id: str,
        reason: str,
        idempotency_key: str,
    ) -> RefundView:
        payload = self._client.refund(
            context=ForwardContext(user_id=user_id),
            payment_id=payment_id,
            body={"reason": reason},
            idempotency_key=idempotency_key,
        )
        status = payload.get("status")
        if not isinstance(status, str) or not status:
            raise PaymentModuleUnavailable()
        reference = payload.get("refundReference")
        return RefundView(
            status=status,
            refund_reference=reference if isinstance(reference, str) and reference else None,
        )
