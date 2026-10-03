"""HTTP boundary from the aggregator adapter to the aggregator's send API.

The gateway hands an SMS to the notification path; the aggregator adapter posts
it to the mobile-network/USSD/SMS aggregator (architecture.md, "External
integrations"). This module is the transport: one pooled client, a resolved
endpoint, and a failure that is reported rather than swallowed.

Configuration follows the payment-hop convention: an explicit
``aggregator_base_url`` setting first, then the ``AGGREGATOR_BASE_URL``
environment override, then a host/port pair. No credential is read from code;
the API key is a secret injected from the managed store (NFR-024) and is only
ever placed in an outbound header, never logged.

A transport failure, a timeout, or a 5xx means the aggregator cannot be reached.
That is reported as :class:`AggregatorUnavailable`, an ``APIError`` the gateway
already treats as a retained-for-retry delivery failure (FEAT-010, alternate
path C), so a provider outage never rolls back a successful payment.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.errors import APIError

logger = logging.getLogger("sabi.channels.aggregator")

# Transport error code for an unreachable aggregator. Like the other gateway
# hops it is a system condition, reported as 503.
AGGREGATOR_UNAVAILABLE = "aggregator_unavailable"

_DEFAULT_AGGREGATOR_HOST = "localhost"
_DEFAULT_AGGREGATOR_PORT = 8003
_DEFAULT_TIMEOUT_SECONDS = 5.0

# The aggregator's send endpoint. Africa's Talking posts to ``/version1/messaging``
# with a form body; a compatible aggregator exposes the same path. It is
# overridable so a different vendor's path does not require a code change.
_DEFAULT_SEND_PATH = "/version1/messaging"


@dataclass(frozen=True, slots=True)
class AggregatorEndpoint:
    """Resolved base URL, send path, timeout, and credential for the aggregator."""

    base_url: str
    send_path: str
    timeout_seconds: float
    api_key: str | None = None
    sender_id: str | None = None

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> AggregatorEndpoint:
        source = os.environ if env is None else env
        override = (source.get("AGGREGATOR_BASE_URL") or "").strip()
        host = (source.get("AGGREGATOR_HOST") or "").strip() or _DEFAULT_AGGREGATOR_HOST
        port = (source.get("AGGREGATOR_PORT") or "").strip() or str(_DEFAULT_AGGREGATOR_PORT)
        base_url = override.rstrip("/") if override else f"http://{host}:{port}"
        send_path = (source.get("AGGREGATOR_SEND_PATH") or "").strip() or _DEFAULT_SEND_PATH
        api_key = (source.get("AGGREGATOR_API_KEY") or "").strip() or None
        sender_id = (source.get("AGGREGATOR_SENDER_ID") or "").strip() or None
        return cls(
            base_url=base_url,
            send_path=send_path,
            timeout_seconds=_timeout(source),
            api_key=api_key,
            sender_id=sender_id,
        )

    @classmethod
    def from_settings(cls, settings: Any) -> AggregatorEndpoint:
        """Build from application settings, with an env override for the base.

        The environment wins where it is set, so a deployment can point the hop
        at a service address without a code change; otherwise a configured
        ``aggregator_base_url`` setting is used, falling back to the defaults.
        """

        source = dict(os.environ)
        configured = str(getattr(settings, "aggregator_base_url", "") or "").strip()
        if configured and not source.get("AGGREGATOR_BASE_URL", "").strip():
            source["AGGREGATOR_BASE_URL"] = configured
        return cls.from_env(source)


def _timeout(source: dict[str, str]) -> float:
    raw = (source.get("AGGREGATOR_REQUEST_TIMEOUT_SECONDS") or "").strip()
    try:
        value = float(raw) if raw else _DEFAULT_TIMEOUT_SECONDS
    except ValueError:
        return _DEFAULT_TIMEOUT_SECONDS
    return value if value > 0 else _DEFAULT_TIMEOUT_SECONDS


class AggregatorClient:
    """Posts SMS send requests to the aggregator with a single pooled client."""

    def __init__(self, endpoint: AggregatorEndpoint) -> None:
        self._endpoint = endpoint
        self._client = httpx.Client(
            base_url=endpoint.base_url,
            timeout=endpoint.timeout_seconds,
        )

    def close(self) -> None:
        self._client.close()

    def send_sms(self, *, msisdn: str, body: str, sender_id: str | None = None) -> None:
        """Queue one SMS for delivery; raises :class:`AggregatorUnavailable` on failure."""

        payload: dict[str, str] = {"to": msisdn, "message": body}
        sender = sender_id or self._endpoint.sender_id
        if sender:
            payload["from"] = sender
        headers: dict[str, str] = {}
        if self._endpoint.api_key:
            headers["apiKey"] = self._endpoint.api_key
        self._post(self._endpoint.send_path, data=payload, headers=headers)

    def _post(self, path: str, *, data: dict[str, str], headers: dict[str, str]) -> None:
        try:
            response = self._client.post(path, data=data, headers=headers)
        except httpx.HTTPError:
            # Never surface the transport detail; it can carry the aggregator
            # address. The caller gets one retryable condition.
            logger.warning("aggregator call failed", extra={"path": path})
            raise AggregatorUnavailable() from None
        if response.status_code >= 500:
            logger.warning(
                "aggregator returned a server error",
                extra={"path": path, "status": response.status_code},
            )
            raise AggregatorUnavailable()
        if response.status_code >= 400:
            # A rejected send is a configuration or address problem, not a
            # transient one; report it as unavailable so the message is retained
            # rather than silently dropped (FEAT-010).
            logger.warning(
                "aggregator rejected the send",
                extra={"path": path, "status": response.status_code},
            )
            raise AggregatorUnavailable()


class AggregatorUnavailable(APIError):
    """The aggregator could not be reached or refused the send."""

    def __init__(self) -> None:
        super().__init__(
            503,
            AGGREGATOR_UNAVAILABLE,
            "The SMS service is unavailable right now. The message will be retried.",
        )


__all__ = [
    "AGGREGATOR_UNAVAILABLE",
    "AggregatorClient",
    "AggregatorEndpoint",
    "AggregatorUnavailable",
]
