"""Unit tests for credential redaction filter.

Purpose: Verifies sensitive substrings are redacted from log records and normal text is preserved.
Inputs: Synthetic log records and messages.
Outputs: Redacted log strings.
"""

from __future__ import annotations

import logging

from iir.common.logging import RedactingFilter, redact_text


def test_redacting_filter_redacts_password_assignment() -> None:
    """The logging filter redacts password= assignments."""
    raw_message = 'Failed auth for user simulator with password="super_secret_password_123"'
    redacted = redact_text(raw_message)

    assert "super_secret_password_123" not in redacted
    assert "password=[REDACTED]" in redacted


def test_redacting_filter_redacts_fake_key() -> None:
    """The logging filter redacts fake API keys and bearer tokens."""
    raw_message = "Calling upstream service with sk-fakeApiKey1234567890ABCDEF and Bearer secretBearerToken12345"
    redacted = redact_text(raw_message)

    assert "sk-fakeApiKey1234567890ABCDEF" not in redacted
    assert "secretBearerToken12345" not in redacted
    assert "[REDACTED]" in redacted


def test_redacting_filter_in_log_record() -> None:
    """RedactingFilter redacts msg and record.args."""
    flt = RedactingFilter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Connecting with secret=%s",
        args=("verySecret12345",),
        exc_info=None,
    )
    flt.filter(record)

    assert "verySecret12345" not in record.msg
    assert "secret=[REDACTED]" in record.msg
    assert record.args is None or "verySecret12345" not in str(record.args)


def test_normal_engineering_text_preserved() -> None:
    """Normal engineering tokens such as INV-07, 412.5 W, 58.2 C must remain unchanged."""
    normal_text = (
        "Inverter INV-07 telemetry reading: 412.5 W, 58.2 C, 230.1 V at 2026-11-09T10:00:00Z"
    )
    result = redact_text(normal_text)

    assert result == normal_text
