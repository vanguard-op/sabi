"""Payment module settings.

The module reads its own database URL; it never shares the primary store's
connection string, which keeps the transaction boundary real (architecture.md).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_MANDATE_KEY = "local-dev-only-change-me"


class PaymentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "info"
    host: str = "0.0.0.0"
    port: int = 8002

    # Isolated payment records store (own database, own schema).
    payments_database_url: str = (
        "postgresql+psycopg://sabi:local-dev-only-change-me@localhost:5432/sabi_payments"
    )

    # Keyed digest that binds a mandate to its user, amount, and payee (NFR-027).
    # A development placeholder only; production reads it from the secret store.
    mandate_signing_key: SecretStr = SecretStr(DEV_MANDATE_KEY)

    # Mandate lifetime and the default per-payment authorisation limit in kobo,
    # used when the gateway does not forward the user's own set limit (FEAT-005).
    mandate_ttl_seconds: int = 300
    default_authorisation_limit: int = 5_000_000  # ₦50,000

    @property
    def database_url(self) -> str:
        return self.payments_database_url


@lru_cache
def get_payment_settings() -> PaymentSettings:
    return PaymentSettings()
