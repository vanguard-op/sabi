"""Passkey association files served from the relying-party origin (FEAT-001).

A passkey ceremony only reaches the device when the RP origin vouches for the
app, and each platform looks for its own file under ``/.well-known/``:

- **Android** fetches ``assetlinks.json`` and checks that the app's package name
  and signing-certificate SHA-256 are listed. Without a match, Credential Manager
  fails with ``domain-not-associated`` before any credential is created.
- **iOS** fetches ``apple-app-site-association`` and checks that the app's
  ``<TeamID>.<bundle>`` appears under ``webcredentials.apps``.

Both files are served from the gateway because it *is* the RP origin
(``webauthn_rp_id``), so there is no second host to keep in step. They are
public, unauthenticated, and must not redirect: Apple and Google fetch the exact
URL, and a redirect is treated as a failure.

Each file is emitted only when its identity is configured, so a development or
test environment that has no signing certificate returns 404 rather than
advertising an app it cannot vouch for.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.config import Settings

router = APIRouter(tags=["system"])

# The web credential relationship Android requires for a passkey.
_ANDROID_RELATION = "delegate_permission/common.get_login_creds"


def _settings(request: Request) -> Settings:
    return request.app.state.settings


@router.get("/.well-known/assetlinks.json")
def asset_links(request: Request) -> JSONResponse:
    """Digital Asset Links for the Android app (FEAT-001).

    One statement per configured signing certificate: debug and release builds
    are signed with different keys, and Play App Signing adds another, so all
    of them must be listed or the file works for one build and not the others.
    """
    settings = _settings(request)
    fingerprints = [f for f in settings.android_cert_fingerprints if f.strip()]
    if not fingerprints:
        # No certificate configured: this origin cannot vouch for an app.
        return JSONResponse(status_code=404, content={"detail": "Not configured."})

    statement = {
        "relation": [_ANDROID_RELATION],
        "target": {
            "namespace": "android_app",
            "package_name": settings.android_package_name,
            "sha256_cert_fingerprints": fingerprints,
        },
    }
    return JSONResponse(
        content=[statement],
        # Digitally-linked Apps requires this exact media type.
        media_type="application/json",
    )


@router.get("/.well-known/apple-app-site-association")
def apple_app_site_association(request: Request) -> JSONResponse:
    """The Apple App Site Association file for the iOS app (FEAT-001).

    Served with an ``application/json`` content type and no ``.json`` extension,
    which is what Apple requires at this path.
    """
    settings = _settings(request)
    app_id = settings.apple_app_id.strip()
    if not app_id:
        return JSONResponse(status_code=404, content={"detail": "Not configured."})

    return JSONResponse(
        content={
            "webcredentials": {"apps": [app_id]},
        },
        media_type="application/json",
    )


__all__ = ["router"]
