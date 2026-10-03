"""Google identity tokens for the gateway's hop to the private services.

The AI service and the payment module are private Cloud Run services: only the
gateway's service account holds ``run.invoker`` on them (architecture.md,
"API Gateway / Backend-for-Frontend"; "Payment Module"). A plain HTTP call to a
private Cloud Run origin is rejected, so the gateway attaches a Google-signed
identity token whose audience is the target origin. Cloud Run verifies the
token and the caller's IAM role at the edge, before the request reaches the
service.

Token acquisition is a seam: the transport client owns a provider, and a test
substitutes a deterministic double so no network or metadata server is needed.
The token is a credential and is never logged.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from google.auth.transport import Response as _GoogleResponse


@runtime_checkable
class IdentityTokenProvider(Protocol):
    """Supplies a bearer token for one private service origin."""

    def token(self, audience: str) -> str: ...


class _HttpxResponse(_GoogleResponse):
    """A concrete ``google.auth.transport.Response`` over an httpx response.

    ``google.auth.transport.Response`` is an abstract interface, not a value
    type: it declares ``status``, ``headers``, and ``data`` and cannot be
    constructed directly. Subclassing it, as google-auth's own urllib3 and
    http.client transports do, is what makes the adapter acceptable to
    ``Credentials.refresh``.
    """

    def __init__(self, *, status: int, headers: dict[str, str], data: bytes) -> None:
        self._status = status
        self._headers = headers
        self._data = data

    @property
    def status(self) -> int:
        return self._status

    @property
    def headers(self) -> dict[str, str]:
        return self._headers

    @property
    def data(self) -> bytes:
        return self._data


class _HttpxRequest:
    """The minimal transport request ``google.auth`` needs, over httpx.

    ``google-auth`` ships transports for ``requests``, ``urllib3``, and
    ``aiohttp``; this service already depends on httpx, so the adapter is
    written against it rather than pulling in a second HTTP client. Only the
    metadata-server call google-auth performs goes through here.
    """

    def __call__(
        self,
        url: str,
        method: str = "GET",
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        **_: object,
    ) -> _HttpxResponse:
        import httpx

        response = httpx.request(
            method,
            url,
            content=body,
            headers=headers or {},
            timeout=timeout if timeout is not None else 5.0,
        )
        return _HttpxResponse(
            status=response.status_code,
            headers=dict(response.headers),
            data=response.content,
        )


class GoogleIdentityTokenProvider:
    """Mints a Cloud Run identity token for the calling service account.

    ``google.auth.default`` resolves the service account from the runtime
    metadata server (or ``GOOGLE_APPLICATION_CREDENTIALS``); refreshing it and
    encoding an identity token with the target origin as the JWT audience is
    what Cloud Run's IAM check validates. The transport request and the
    credentials are created once and reused, so repeated calls do not re-resolve
    the account or rebuild the transport.
    """

    def __init__(self) -> None:
        self._request = _HttpxRequest()
        self._credentials = None

    def token(self, audience: str) -> str:
        import google.auth
        from google.auth import jwt as google_jwt

        if self._credentials is None:
            credentials, _ = google.auth.default()
            self._credentials = credentials
        self._credentials.refresh(self._request)
        return google_jwt.encode(self._credentials.signer, self._credentials, audience)


def build_identity_token_provider() -> GoogleIdentityTokenProvider:
    """The provider the app factory binds to its private-service transports."""
    return GoogleIdentityTokenProvider()
