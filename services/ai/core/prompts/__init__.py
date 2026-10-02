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

from core.config import PROMPT_VERSION, Capability
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


def load_prompt(capability: Capability, version: str = PROMPT_VERSION) -> Prompt:
    """Load a versioned prompt artifact from disk, failing loudly when it is absent."""

    if not _VERSION_RE.match(version):
        raise ModelError(f"invalid prompt version: {version}")
    path = _PROMPT_DIR / f"{capability.value}.{version}.txt"
    if not path.is_file():
        raise ModelError(f"prompt artifact not found: {path.name}")
    text = path.read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return Prompt(capability=capability, version=version, text=text, sha256=digest)


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
