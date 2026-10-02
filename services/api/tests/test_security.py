import re

from app.core.security import (
    generate_recovery_code,
    hash_secret,
    mask_identifier,
    secret_needs_rehash,
    verify_secret,
)

PEPPER = "unit-test-pepper"


def test_secret_hash_is_argon2id_and_reversible_only_by_verify() -> None:
    stored = hash_secret("RECOVERY-CODE", PEPPER)
    assert stored.startswith("$argon2id$")
    assert "RECOVERY-CODE" not in stored
    assert verify_secret("RECOVERY-CODE", stored, PEPPER) is True
    assert verify_secret("WRONG-CODE", stored, PEPPER) is False


def test_hash_is_bound_to_the_pepper() -> None:
    stored = hash_secret("RECOVERY-CODE", PEPPER)
    assert verify_secret("RECOVERY-CODE", stored, "another-pepper") is False


def test_current_hash_does_not_need_rehash() -> None:
    assert secret_needs_rehash(hash_secret("code", PEPPER)) is False
    assert secret_needs_rehash("not-a-hash") is True


def test_recovery_code_format_and_alphabet() -> None:
    code = generate_recovery_code()
    assert re.fullmatch(r"[A-Z2-9]{4}(-[A-Z2-9]{4}){3}", code)
    assert not set("IO01") & set(code)


def test_recovery_codes_are_unique() -> None:
    assert len({generate_recovery_code() for _ in range(200)}) == 200


def test_mask_identifier_keeps_only_the_tail() -> None:
    assert mask_identifier("12345678901") == "*******8901"
    assert mask_identifier("1234") == "****"
    assert mask_identifier("12", visible=4) == "**"
    assert mask_identifier("") == ""
