"""Payment module settings.

The module reads its own database URL; it never shares the primary store's
connection string, which keeps the transaction boundary real (architecture.md).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @property
    def database_url(self) -> str:
        return self.payments_database_url


@lru_cache
def get_payment_settings() -> PaymentSettings:
    return PaymentSettings()
