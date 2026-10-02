"""Opaque identifier generation.

Identifiers are UUIDv7 strings: time-ordered so they index well, and opaque to
clients (DELIVERY.md, conventions).
"""

from __future__ import annotations

import os
import threading
import time
import uuid

_LOCK = threading.Lock()
_last_ms = 0
_sequence = 0

_MAX_SEQUENCE = 0x0FFF
_RAND_B_MASK = (1 << 62) - 1


def new_id() -> str:
    """Return a new UUIDv7 string, monotonic within the process."""
    global _last_ms, _sequence
    with _LOCK:
        now_ms = int(time.time() * 1000)
        if now_ms > _last_ms:
            _last_ms = now_ms
            _sequence = int.from_bytes(os.urandom(2), "big") & _MAX_SEQUENCE
        else:
            _sequence += 1
            if _sequence > _MAX_SEQUENCE:
                _last_ms += 1
                _sequence = 0
        timestamp_ms = _last_ms
        rand_b = int.from_bytes(os.urandom(8), "big") & _RAND_B_MASK

    value = (timestamp_ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76
    value |= (_sequence & _MAX_SEQUENCE) << 64
    value |= 0x2 << 62
    value |= rand_b
    return str(uuid.UUID(int=value))


def is_uuid7(value: str) -> bool:
    """Whether a string is a well-formed UUID with version 7."""
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return parsed.version == 7 and str(parsed) == value.lower()
