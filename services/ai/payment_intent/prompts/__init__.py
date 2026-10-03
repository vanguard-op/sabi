"""Versioned prompt artifact for payment-intent extraction.

The prompt lives in ``payment_intent.v1.txt`` beside this module, is content-hashed,
and is pinned with the model build it was tuned for. Like the core prompt artifacts,
the rendered text wraps the user message and retrieved catalogue content as untrusted
data; this loader is a local mirror of :func:`core.prompts.load_prompt` because the
payment-intent capability is served inside this package without adding a new
:class:`~core.config.Capability` to the frozen model-serving foundation.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from core.config import PROMPT_VERSION
from core.errors import ModelError

PROMPT_ID = "payment_intent"

_PROMPT_DIR = Path(__file__).parent
_VERSION_RE = re.compile(r"^v[0-9]+$")


@dataclass(frozen=True)
class PaymentPrompt:
    """A loaded, immutable prompt artifact."""

    version: str
    text: str
    sha256: str

    @property
    def prompt_id(self) -> str:
        return PROMPT_ID


def load_prompt(version: str = PROMPT_VERSION) -> PaymentPrompt:
    """Load the versioned extraction prompt, failing loudly when it is absent."""

    if not _VERSION_RE.match(version):
        raise ModelError(f"invalid prompt version: {version}")
    path = _PROMPT_DIR / f"{PROMPT_ID}.{version}.txt"
    if not path.is_file():
        raise ModelError(f"prompt artifact not found: {path.name}")
    text = path.read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return PaymentPrompt(version=version, text=text, sha256=digest)


__all__ = ["PROMPT_ID", "PaymentPrompt", "load_prompt"]
