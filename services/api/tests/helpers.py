"""Test helpers shared across the API suite."""

from __future__ import annotations

from app.core.config import Settings


def make_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "_env_file": None,
        "environment": "development",
        "session_secret": "test-session-secret",
        "recovery_code_pepper": "test-recovery-pepper",
    }
    defaults.update(overrides)
    return Settings(**defaults)
