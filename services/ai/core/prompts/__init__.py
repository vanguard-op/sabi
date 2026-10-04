"""Versioned prompt artifacts.

Prompts are code: they live in files named ``<capability>.<version>.txt`` beside this
module, are content-hashed, and are pinned to the model build they were tuned for. The
rendered text wraps user input and retrieved catalogue content as untrusted data; the
model is instructed never to treat it as instructions.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from core.config import Capability, prompt_version_for
from core.errors import ModelError

_PROMPT_DIR = Path(__file__).parent
_VERSION_RE = re.compile(r"^v[0-9]+$")


@dataclass(frozen=True)
class Prompt:
    """A loaded, immutable prompt artifact."""

    capability: Capability
    version: str
    text: str
    sha256: str

    @property
    def prompt_id(self) -> str:
        return self.capability.value


def load_prompt(capability: Capability, version: str | None = None) -> Prompt:
    """Load a versioned prompt artifact from disk, failing loudly when it is absent.

    The version defaults to the one the capability is pinned to (``config``), so a
    capability can move to a new prompt version without affecting the others.
    """

    resolved = version or prompt_version_for(capability)
    if not _VERSION_RE.match(resolved):
        raise ModelError(f"invalid prompt version: {resolved}")
    path = _PROMPT_DIR / f"{capability.value}.{resolved}.txt"
    if not path.is_file():
        raise ModelError(f"prompt artifact not found: {path.name}")
    text = path.read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return Prompt(capability=capability, version=resolved, text=text, sha256=digest)


def render(template: str, values: Mapping[str, str]) -> str:
    """Substitute ``[[token]]`` placeholders.

    Explicit tokens are used rather than :meth:`str.format` so that braces inside
    prompt examples and JSON snippets are never interpreted as fields. Unknown tokens
    are left untouched instead of raising, so a missing value cannot blank a prompt.
    """

    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"[[{key}]]", str(value))
    return rendered
