import logging

from app.core.logging import JsonFormatter, get_correlation_id, redact, set_correlation_id


def test_redact_removes_nested_secrets() -> None:
    cleaned = redact(
        {
            "Authorization": "Bearer abc",
            "session_secret": "xyz",
            "user": {"displayName": "Ada", "recovery_code": "ABCD-EFGH"},
            "list": [{"token": "t"}],
        }
    )
    assert cleaned["Authorization"] == "[redacted]"
    assert cleaned["session_secret"] == "[redacted]"
    assert cleaned["user"]["displayName"] == "Ada"
    assert cleaned["user"]["recovery_code"] == "[redacted]"
    assert cleaned["list"][0]["token"] == "[redacted]"


def test_formatter_redacts_sensitive_record_attributes() -> None:
    record = logging.LogRecord(
        name="sabi.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="something happened",
        args=(),
        exc_info=None,
    )
    record.session_secret = "super-secret"
    output = JsonFormatter().format(record)
    assert "super-secret" not in output
    assert "something happened" in output


def test_correlation_id_roundtrip() -> None:
    generated = set_correlation_id()
    assert get_correlation_id() == generated
    assert set_correlation_id("fixed-id") == "fixed-id"
