"""Application configuration.

All configuration comes from the environment or a managed secret store; nothing
sensitive is compiled in (NFR-024). The development defaults in this module are
placeholders that the settings validator refuses to accept in staging or
production.
"""

from __future__ import annotations

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

    # In-process boundary to the isolated payment module. It can be lifted to a
    # network hop without touching callers (architecture.md, payment module).
    payments_base_url: str = "http://localhost:8002"
    payments_request_timeout_seconds: float = 5.0

    # WebAuthn relying party (FEAT-001). The private key never leaves the device;
    # only the public credential is stored (schema.md, AuthCredential).
    webauthn_rp_id: str = "localhost"
    webauthn_rp_name: str = "Sabi"
    webauthn_origin: str = "http://localhost:8000"

    # Native clients present a platform origin rather than the web one: iOS runs
    # the ceremony under "https://<rp_id>" and Android under
    # "android:apk-key-hash:<sha256>" for its signing certificate. The iOS origin
    # follows from rp_id; list the Android origins here per deployment. Anything
    # not in this list is refused, so an unrecognised origin cannot slip through.
    webauthn_native_origins: list[str] = Field(default_factory=list)

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

        The web client presents ``webauthn_origin``, iOS ``https://<rp_id>``,
        and Android each configured ``android:apk-key-hash:<sha256>``. The
        verifier treats the web origin as the primary and admits the native
        origins alongside it, so a valid native ceremony is not rejected merely
        for not being the web origin.
        """
        origins = [self.webauthn_origin, f"https://{self.webauthn_rp_id}"]
        origins.extend(self.webauthn_native_origins)
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
        return self

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
