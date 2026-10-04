"""Application configuration.

All configuration comes from the environment or a managed secret store; nothing
sensitive is compiled in (NFR-024). The development defaults in this module are
placeholders that the settings validator refuses to accept in staging or
production.
"""

from __future__ import annotations

import base64
import os
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "staging", "production"]

# Public placeholder shipped in .env.example. It is not a real secret; the
# validator below rejects it outside development so a forgotten value is caught
# at boot rather than in production.
DEV_PLACEHOLDER = "local-dev-only-change-me"

# Android charts the passkey origin as the base64url-encoded SHA-256 of the
# signing certificate, with no padding (D-038).
_ANDROID_ORIGIN_PREFIX = "android:apk-key-hash:"


def _android_origins(fingerprints: list[str]) -> list[str]:
    """Derive Android passkey origins from signing-cert fingerprints (FEAT-001).

    A fingerprint is colon-separated, case-insensitive hex of the certificate's
    SHA-256. It is normalised, decoded, and re-encoded as unpadded base64url to
    match the value Credential Manager reports as the ceremony origin. Blank
    entries are skipped; an entry that is not valid hex cannot describe a real
    certificate, so it is skipped rather than allowed to break every ceremony.
    """
    origins: list[str] = []
    for fingerprint in fingerprints:
        normalized = fingerprint.replace(":", "").replace(" ", "").strip()
        if not normalized:
            continue
        try:
            digest = bytes.fromhex(normalized)
        except ValueError:
            continue
        encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        origins.append(f"{_ANDROID_ORIGIN_PREFIX}{encoded}")
    return origins


class Settings(BaseSettings):
    """Runtime settings for the modular monolith."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Environment = "development"
    log_level: str = "info"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Primary store and the isolated payment store. The payment module keeps its
    # own database, schema, and transaction boundary (architecture.md).
    database_url: str = "postgresql+psycopg://sabi:local-dev-only-change-me@localhost:5432/sabi"
    payments_database_url: str = (
        "postgresql+psycopg://sabi:local-dev-only-change-me@localhost:5432/sabi_payments"
    )
    cache_url: str = "redis://localhost:6379/0"

    # Store selection for sessions and rate-limit counters, decoupled from the
    # environment name so staging can run without a cache. "auto" keeps the
    # development in-memory default and requires Redis once a hosted environment
    # has a cache URL; "memory" forces the in-process stores; "redis" requires a
    # reachable cache and fails the boot if it cannot connect rather than
    # silently degrading to memory. A hosted environment with no cache URL and
    # no explicit choice fails the validator rather than guessing.
    session_store_backend: Literal["auto", "memory", "redis"] = "auto"
    rate_limit_store_backend: Literal["auto", "memory", "redis"] = "auto"

    # In-process boundary to the isolated payment module. It can be lifted to a
    # network hop without touching callers (architecture.md, payment module).
    payments_base_url: str = "http://localhost:8002"
    payments_request_timeout_seconds: float = 5.0

    # Private AI service origin. Unlike the payment hop, the AI base URL is read
    # from the environment by the client itself; it is declared here so store
    # and deployment validation can reason about whether a hosted gateway is
    # configured to reach its private service.
    ai_base_url: str = ""

    # WebAuthn relying party (FEAT-001). The private key never leaves the device;
    # only the public credential is stored (schema.md, AuthCredential).
    webauthn_rp_id: str = "localhost"
    webauthn_rp_name: str = "Sabi"
    webauthn_origin: str = "http://localhost:8000"

    # Android app identity for Digital Asset Links (FEAT-001). The RP origin
    # serves /.well-known/assetlinks.json naming the app package and the SHA-256
    # fingerprints of every certificate it is signed with (debug, upload, and
    # Play App Signing), or Android refuses to associate the app with the domain
    # and every ceremony fails with `domain-not-associated`. The same list backs
    # the Android passkey origin: each certificate yields
    # `android:apk-key-hash:<base64url(sha256(cert))>`, so the association file
    # and the WebAuthn allowlist can never drift apart (D-038).
    android_package_name: str = "ng.sabi.sabi_mobile"
    android_cert_fingerprints: list[str] = Field(default_factory=list)

    # iOS app identity for the Apple App Site Association file. The
    # `webcredentials.apps` entries are `<TeamID>.<bundle id>`.
    apple_app_id: str = ""

    # Session and recovery secrets (NFR-021, NFR-024, NFR-026).
    session_cookie_name: str = "sabi_session"
    session_secret: SecretStr = SecretStr(DEV_PLACEHOLDER)
    recovery_code_pepper: SecretStr = SecretStr(DEV_PLACEHOLDER)

    # Session lifetimes: absolute cap plus idle expiry; channel sessions are
    # time-bound separately and kept short (NFR-006, NFR-026).
    session_absolute_timeout_seconds: int = 60 * 60 * 24 * 30
    session_idle_timeout_seconds: int = 60 * 60 * 12
    channel_session_timeout_seconds: int = 120

    # None means "secure unless running in development over plain HTTP". The
    # cookie is always Secure outside development regardless of this setting.
    session_cookie_secure: bool | None = None
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    # Rate-limit defaults for the unauthenticated auth surfaces (C-001, C-003).
    auth_rate_limit_requests: int = 20
    auth_rate_limit_window_seconds: int = 60

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def secure_cookies(self) -> bool:
        """Whether session cookies carry the Secure attribute (NFR-026)."""
        if self.is_production:
            return True
        if self.session_cookie_secure is not None:
            return self.session_cookie_secure
        return self.environment != "development"

    @property
    def hsts_enabled(self) -> bool:
        """HSTS is emitted everywhere except local development over HTTP (NFR-022)."""
        return self.environment != "development"

    @property
    def webauthn_allowed_origins(self) -> list[str]:
        """Origins a passkey ceremony may present (FEAT-001).

        The web client presents ``webauthn_origin`` and iOS presents
        ``https://<rp_id>``. Android presents
        ``android:apk-key-hash:<base64url(sha256(cert))>`` for its signing
        certificate, so one origin is derived per configured cert fingerprint
        rather than configured separately; the same certificates are named in
        ``/.well-known/assetlinks.json`` and stay in step with it (D-038). The
        verifier treats the web origin as the primary and admits the native
        origins alongside it, so a valid native ceremony is not rejected merely
        for not being the web origin.
        """
        origins = [self.webauthn_origin, f"https://{self.webauthn_rp_id}"]
        origins.extend(_android_origins(self.android_cert_fingerprints))
        # py_webauthn matches origins by exact membership; drop duplicates so a
        # deployment where the web and iOS origins coincide stays unambiguous.
        return list(dict.fromkeys(origins))

    @model_validator(mode="after")
    def _validate(self) -> Settings:
        if self.environment != "development":
            for name, value in (
                ("session_secret", self.session_secret),
                ("recovery_code_pepper", self.recovery_code_pepper),
            ):
                raw = value.get_secret_value()
                if not raw or raw == DEV_PLACEHOLDER:
                    raise ValueError(f"{name} must be set from the secret store")
        self._assert_payment_isolation()
        self._assert_store_selection()
        return self

    @property
    def resolved_session_store_backend(self) -> Literal["memory", "redis"]:
        """The session store the app will build. ``auto`` is not a store."""
        return self._resolve_store_backend("session", self.session_store_backend)

    @property
    def resolved_rate_limit_store_backend(self) -> Literal["memory", "redis"]:
        """The rate-limit store the app will build. ``auto`` is not a store."""
        return self._resolve_store_backend("rate-limit", self.rate_limit_store_backend)

    def _resolve_store_backend(
        self, label: str, configured: Literal["auto", "memory", "redis"]
    ) -> Literal["memory", "redis"]:
        if configured != "auto":
            return configured
        if self.cache_configured and (self.environment != "development" or self.is_hosted):
            return "redis"
        return "memory"

    @property
    def is_hosted(self) -> bool:
        """Whether the app is running on Cloud Run rather than a local process.

        Cloud Run always sets ``K_SERVICE``; its presence means the private
        service hops carry a Google-signed identity token. This is deliberately
        narrower than "not development" so a plain staging container or a test
        process keeps its unauthenticated HTTP transport.
        """
        return bool(os.environ.get("K_SERVICE"))

    @property
    def cache_configured(self) -> bool:
        return bool(self.cache_url.strip())

    def _assert_store_selection(self) -> None:
        """A hosted or production environment may never default to memory.

        Development may run in memory; staging may run in memory when no cache
        is provided (D-032); production must have a cache and must select Redis,
        so a missing cache fails the boot instead of silently degrading
        sessions and rate limits to a single process.
        """
        resolved_session = self.resolved_session_store_backend
        resolved_rate = self.resolved_rate_limit_store_backend

        if self.is_production:
            for label, resolved in (
                ("session_store_backend", resolved_session),
                ("rate_limit_store_backend", resolved_rate),
            ):
                if resolved != "redis":
                    raise ValueError(
                        f"{label} must resolve to redis in production; an in-memory store "
                        "does not survive a restart or scale past one instance"
                    )
            if not self.cache_configured:
                raise ValueError("cache_url must be set in production")

        if self.is_hosted and not self.cache_configured:
            # Staging (or production) on Cloud Run with no cache at all: the
            # stores must be an explicit in-memory choice, never an accident.
            for label, configured in (
                ("session_store_backend", self.session_store_backend),
                ("rate_limit_store_backend", self.rate_limit_store_backend),
            ):
                if configured == "auto":
                    raise ValueError(
                        f"{label} must be set explicitly when no cache_url is configured "
                        "in a hosted environment"
                    )

        if (
            not self.is_production
            and (resolved_session == "redis" or resolved_rate == "redis")
            and not self.cache_configured
        ):
            raise ValueError("cache_url must be set when a redis store is selected")

    def _assert_payment_isolation(self) -> None:
        """The payment store must not be the primary database (architecture.md)."""
        primary = urlsplit(self.database_url)
        payments = urlsplit(self.payments_database_url)
        if primary.scheme.startswith("postgresql") and payments.scheme.startswith("postgresql"):
            if primary.path == payments.path:
                raise ValueError(
                    "payments_database_url must point at a separate database from database_url"
                )


@lru_cache
def get_settings() -> Settings:
    return Settings()
