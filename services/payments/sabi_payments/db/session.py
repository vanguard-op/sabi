"""Payment-store engine and session factory."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from sabi_payments.core.config import PaymentSettings


def create_engine_from_settings(settings: PaymentSettings, url: str | None = None) -> Engine:
    database_url = url or settings.database_url
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)


def build_session_factory(settings: PaymentSettings) -> sessionmaker[Session]:
    return sessionmaker(
        bind=create_engine_from_settings(settings), autoflush=False, expire_on_commit=False
    )
