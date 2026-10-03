import pytest
from pydantic import ValidationError

from app.core.config import DEV_PLACEHOLDER, Settings


def test_development_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.environment == "development"
    assert settings.secure_cookies is False
    assert settings.hsts_enabled is False
    assert settings.session_absolute_timeout_seconds > settings.session_idle_timeout_seconds


def test_production_rejects_placeholder_secrets() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            session_secret=DEV_PLACEHOLDER,
            recovery_code_pepper="a-real-pepper",
        )


def test_production_requires_secure_cookies_and_hsts() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        session_secret="a-real-session-secret",
        recovery_code_pepper="a-real-pepper",
    )
    assert settings.secure_cookies is True
    assert settings.hsts_enabled is True


def test_production_forces_secure_even_when_overridden_off() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        session_secret="a-real-session-secret",
        recovery_code_pepper="a-real-pepper",
        session_cookie_secure=False,
    )
    assert settings.secure_cookies is True


def test_payment_store_must_be_a_separate_database() -> None:
    same = "postgresql+psycopg://sabi:secret@localhost:5432/sabi"
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url=same,
            payments_database_url=same,
        )


def test_payment_store_separate_database_is_allowed() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://sabi:secret@localhost:5432/sabi",
        payments_database_url="postgresql+psycopg://sabi:secret@localhost:5432/sabi_payments",
    )
    assert settings.database_url != settings.payments_database_url


# --------------------------------------------------------------------------- #
# Store selection per environment
# --------------------------------------------------------------------------- #
def test_development_defaults_to_in_memory_stores() -> None:
    settings = Settings(_env_file=None)
    assert settings.resolved_session_store_backend == "memory"
    assert settings.resolved_rate_limit_store_backend == "memory"


def test_hosted_staging_runs_in_memory_when_no_cache_is_configured() -> None:
    settings = Settings(
        _env_file=None,
        environment="staging",
        session_secret="a-real-session-secret",
        recovery_code_pepper="a-real-pepper",
        cache_url="",
    )
    assert settings.resolved_session_store_backend == "memory"
    assert settings.resolved_rate_limit_store_backend == "memory"


def test_staging_with_a_cache_resolves_to_redis() -> None:
    settings = Settings(
        _env_file=None,
        environment="staging",
        session_secret="a-real-session-secret",
        recovery_code_pepper="a-real-pepper",
        cache_url="redis://cache.internal:6379/0",
    )
    assert settings.resolved_session_store_backend == "redis"
    assert settings.resolved_rate_limit_store_backend == "redis"


def test_explicit_memory_backend_is_honoured_over_a_configured_cache() -> None:
    settings = Settings(
        _env_file=None,
        environment="staging",
        session_secret="a-real-session-secret",
        recovery_code_pepper="a-real-pepper",
        cache_url="redis://cache.internal:6379/0",
        session_store_backend="memory",
        rate_limit_store_backend="memory",
    )
    assert settings.resolved_session_store_backend == "memory"
    assert settings.resolved_rate_limit_store_backend == "memory"


def test_production_requires_redis() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        session_secret="a-real-session-secret",
        recovery_code_pepper="a-real-pepper",
        cache_url="redis://cache.internal:6379/0",
    )
    assert settings.resolved_session_store_backend == "redis"
    assert settings.resolved_rate_limit_store_backend == "redis"


def test_production_refuses_an_explicit_memory_store() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            session_secret="a-real-session-secret",
            recovery_code_pepper="a-real-pepper",
            cache_url="redis://cache.internal:6379/0",
            session_store_backend="memory",
        )


def test_production_refuses_a_missing_cache() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="production",
            session_secret="a-real-session-secret",
            recovery_code_pepper="a-real-pepper",
            cache_url="",
        )


def test_redis_selection_without_a_cache_url_fails() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            environment="staging",
            session_secret="a-real-session-secret",
            recovery_code_pepper="a-real-pepper",
            cache_url="",
            session_store_backend="redis",
        )
