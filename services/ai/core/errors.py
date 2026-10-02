"""Error types shared by the model-serving foundation.

Failures are split by how the orchestrator must react:

* :class:`ProviderUnavailable` (and its :class:`ModelTimeout` subtype) means the model
  could not answer, so the caller must degrade to keyword and search resolution.
* :class:`OutputValidationError` means the model answered with something outside the
  output contract, which is treated the same way: fall back, never guess.
"""

from __future__ import annotations


class ModelError(Exception):
    """Base class for model-serving failures."""


class ProviderUnavailable(ModelError):
    """The model provider did not return a usable response."""


class ModelTimeout(ProviderUnavailable):
    """The provider call exceeded its timeout budget."""


class OutputValidationError(ModelError):
    """The provider response did not conform to the capability's output contract."""
