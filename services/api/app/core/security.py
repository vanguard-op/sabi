"""Credential and secret handling.

Recovery secrets are stored one-way with Argon2id and a server-side pepper; a
stored hash can never be reversed into a code (NFR-021). Passkey private keys
never reach the server, so only the public credential is handled here.
"""

from __future__ import annotations

import hmac
import secrets
from hashlib import sha256

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Argon2id with explicit, pinned cost parameters (NFR-021).
_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)

# Unambiguous alphabet: no I, O, 0, or 1, so a code read aloud is not misheard.
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_RECOVERY_GROUPS = 4
_RECOVERY_GROUP_LENGTH = 4


def _pepper(secret: str, pepper: str) -> bytes:
    return hmac.new(pepper.encode("utf-8"), secret.encode("utf-8"), sha256).digest()


def hash_secret(secret: str, pepper: str) -> str:
    """Hash a recovery-style secret with Argon2id and a server-side pepper."""
    return _HASHER.hash(_pepper(secret, pepper))


def verify_secret(secret: str, stored_hash: str, pepper: str) -> bool:
    """Constant-time verification of a secret against its stored hash."""
    try:
        return _HASHER.verify(stored_hash, _pepper(secret, pepper))
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def secret_needs_rehash(stored_hash: str) -> bool:
    try:
        return _HASHER.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return True


def generate_recovery_code() -> str:
    """Return a single-use recovery code, grouped for legibility."""
    groups = [
        "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(_RECOVERY_GROUP_LENGTH))
        for _ in range(_RECOVERY_GROUPS)
    ]
    return "-".join(groups)


def new_nonce() -> str:
    """A single-use value for a signed payment mandate (NFR-027)."""
    return secrets.token_urlsafe(24)


def constant_time_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def mask_identifier(value: str, visible: int = 4) -> str:
    """Mask an identity or account number for storage and display.

    Only the trailing characters remain; the full value is never persisted
    (schema.md: identifierMasked, maskedIdentifier).
    """
    if visible < 0:
        raise ValueError("visible must be non-negative")
    if not value:
        return ""
    if len(value) <= visible:
        return "*" * len(value)
    return "*" * (len(value) - visible) + value[-visible:]
