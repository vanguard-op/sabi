"""Primary-store engine and session dependency."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


def create_engine_from_settings(settings: Settings, url: str | None = None) -> Engine:
    database_url = url or settings.database_url
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)


def build_session_factory(settings: Settings) -> sessionmaker[Session]:
    return sessionmaker(
        bind=create_engine_from_settings(settings), autoflush=False, expire_on_commit=False
    )


def get_db(request: Request) -> Iterator[Session]:
    """FastAPI dependency yielding a primary-store session.

    The factory lives on ``app.state`` so a test can substitute an isolated
    database without reconfiguring the process.
    """
    factory: sessionmaker[Session] = request.app.state.session_factory
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
