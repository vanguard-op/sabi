"""Rail adapter settings.

Rail selection is configuration, not code: the deployed environment chooses the
backend and the licensed partner is added as a backend later, so no caller
changes when the partner is signed (D-027, R-004). Settings are read from the
environment and the secret store only; a credential never lives in code
(NFR-024).

The default is deliberately conservative. Simulating a successful charge in
production would tell a user an obligation was settled when no money moved, so
when ``rail_backend`` is unset the mock is selected only in development and
every other environment falls back to the disabled rail.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

RailBackend = Literal["auto", "mock", "disabled"]
ResolvedBackend = Literal["mock", "disabled"]
Environment = Literal["development", "staging", "production"]


class RailSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="rail_",
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    backend: RailBackend = "auto"
    mock_reference_prefix: str = "SBX"
    # The scenario the sandbox answers with unless a probe enqueues another.
    mock_default_scenario: Literal["success", "decline", "insufficient_funds", "unknown"] = (
        "success"
    )

    # Read here so ``auto`` can resolve without importing the payment settings
    # (which own the datastore, not the rail). Both read the same environment.
    environment: Environment = "development"

    def resolved_backend(self) -> ResolvedBackend:
        """Resolve ``auto``: mock in development, disabled everywhere else."""
        if self.backend == "auto":
            return "mock" if self.environment == "development" else "disabled"
        return self.backend


@lru_cache
def get_rail_settings() -> RailSettings:
    return RailSettings()


__all__ = [
    "Environment",
    "RailBackend",
    "RailSettings",
    "ResolvedBackend",
    "get_rail_settings",
]
