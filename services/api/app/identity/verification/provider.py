"""Boundary to the national identity verification provider (NIN, BVN).

The provider is a controlled failure domain: an unreachable or erroring provider
must queue the check rather than fail it (nfr.md, degradation table; FEAT-002).
This module defines the port as a protocol and a deterministic in-process
implementation for development and tests, so the service can be exercised
without a live NIMC path. It never logs or returns the submitted identifier; a
provider reference is an opaque correlation handle, not the identity number.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class ProviderOutcome(StrEnum):
    """What the provider says about a submitted identity."""

    MATCH = "match"
    NO_MATCH = "no_match"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ProviderResult:
    """A single provider answer.

    ``reference`` is present only for a completed check and is opaque; it is the
    provider's correlation handle, never the identifier itself.
    """

    outcome: ProviderOutcome
    reference: str | None = None


@runtime_checkable
class IdentityProvider(Protocol):
    """The one capability the verification service needs from the provider."""

    def check(self, *, method: str, identifier: str) -> ProviderResult: ...


class UnavailableIdentityProvider:
    """Always-unavailable provider.

    The default when no provider is wired: the check is queued, never fabricated.
    This keeps a missing integration from silently marking accounts verified.
    """

    def check(self, *, method: str, identifier: str) -> ProviderResult:
        return ProviderResult(outcome=ProviderOutcome.UNAVAILABLE)


class StubIdentityProvider:
    """Deterministic provider for development and tests.

    A well-formed check succeeds unless the caller registers the value as a known
    failure. Tests construct this directly; nothing here is reachable from a
    production request.
    """

    def __init__(self, no_match: set[str] | None = None) -> None:
        self._no_match = no_match or set()

    def check(self, *, method: str, identifier: str) -> ProviderResult:
        if identifier in self._no_match:
            return ProviderResult(outcome=ProviderOutcome.NO_MATCH, reference=f"{method}-ref")
        return ProviderResult(outcome=ProviderOutcome.MATCH, reference=f"{method}-ref")
