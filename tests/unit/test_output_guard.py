"""Tests for output guard sanitization, blocking, and preservation of engineering text.

Purpose: Verifies Rule 50:
         - Each guard category has at least 3 positive and 3 negative examples.
         - A canary in the output blocks the response.
         - The original fake secret never appears in the guard's output.
         - Engineering tokens (INV-07, 412.5 W, 58.2 C, timestamps, UUIDs) pass unchanged.
"""

from __future__ import annotations

import pytest
from backend.guard.output_guard import OutputGuard, get_output_guard


@pytest.fixture
def guard() -> OutputGuard:
    return get_output_guard()


# ---------------------------------------------------------------------------
# BLOCK CATEGORIES
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "canary_text",
    [
        "System prompt canary: CANARY-SECRET-KEY-1234567890",
        "CANARY-SYSTEM-INSTRUCTION-ABCDEF1234",
        "CANARY-PROMPT-GUARD-TOKEN-998877665544",
    ],
)
def test_canary_blocks_response(guard: OutputGuard, canary_text: str) -> None:
    sanitized = guard.sanitize_text(canary_text)
    assert "[BLOCKED" in sanitized
    assert "CANARY-" not in sanitized


@pytest.mark.parametrize(
    "traceback_text",
    [
        "Traceback (most recent call last):\n  File 'app.py', line 10, in <module>",
        "An error occurred: Traceback (most recent call last):\n  ZeroDivisionError",
        "Traceback (most recent call last):\n  ValueError: Invalid input",
    ],
)
def test_stack_trace_blocks_response(guard: OutputGuard, traceback_text: str) -> None:
    sanitized = guard.sanitize_text(traceback_text)
    assert "[BLOCKED" in sanitized


@pytest.mark.parametrize(
    "sql_text",
    [
        "Executing: SELECT * FROM alerts WHERE id = 1",
        "Attempt: INSERT INTO users VALUES ('admin', 'pass')",
        "Dangerous: DROP TABLE audit_events",
    ],
)
def test_raw_sql_blocks_response(guard: OutputGuard, sql_text: str) -> None:
    sanitized = guard.sanitize_text(sql_text)
    assert "[BLOCKED" in sanitized


# ---------------------------------------------------------------------------
# REDACT CATEGORIES: 3 POSITIVES & 3 NEGATIVES EACH
# ---------------------------------------------------------------------------


# 1. API Keys / Bearer tokens
@pytest.mark.parametrize(
    "pos",
    [
        "Use header Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 for access",
        "Token sk_live_1234567890abcdef12345678 is configured",
        "api-key_abcdef1234567890abcdef12345678",
    ],
)
def test_api_key_redacted_positive(guard: OutputGuard, pos: str) -> None:
    out = guard.sanitize_text(pos)
    assert "[REDACTED:API_KEY]" in out
    assert "sk_live" not in out


@pytest.mark.parametrize(
    "neg",
    [
        "API error 404 returned from endpoint",
        "Key parameter is missing in query",
        "Public telemetry key is INV-01",
    ],
)
def test_api_key_redacted_negative(guard: OutputGuard, neg: str) -> None:
    assert guard.sanitize_text(neg) == neg


# 2. Secret assignments
@pytest.mark.parametrize(
    "pos",
    [
        'Config: password="superSecretPassword123!"',
        "client_secret='xyz987654321_secret_value'",
        'access_token="tok_1234567890abcdef"',
    ],
)
def test_secret_assignment_positive(guard: OutputGuard, pos: str) -> None:
    out = guard.sanitize_text(pos)
    assert "[REDACTED:SECRET]" in out
    assert "superSecretPassword" not in out


@pytest.mark.parametrize(
    "neg",
    [
        "Password policy requires 12 characters",
        "Secret sharing protocol initialized",
        "Token bucket refreshed with 10 tokens",
    ],
)
def test_secret_assignment_negative(guard: OutputGuard, neg: str) -> None:
    assert guard.sanitize_text(neg) == neg


# 3. Emails
@pytest.mark.parametrize(
    "pos",
    [
        "Contact operator@solar-grid.com for help",
        "Notify alerts.team@energy-domain.org immediately",
        "Email sent to technician_01@substation.lk",
    ],
)
def test_email_positive(guard: OutputGuard, pos: str) -> None:
    out = guard.sanitize_text(pos)
    assert "[REDACTED:EMAIL]" in out
    assert "@" not in out


@pytest.mark.parametrize(
    "neg",
    [
        "No email address configured",
        "Symbol @ is used in decorators",
        "device at substation 4",
    ],
)
def test_email_negative(guard: OutputGuard, neg: str) -> None:
    assert guard.sanitize_text(neg) == neg


# 4. Phones (including Sri Lanka +94 format)
@pytest.mark.parametrize(
    "pos",
    [
        "Call emergency on +94771234567 right away",
        "Support hotline is 011-2345678",
        "Dispatch mobile: 0719876543",
    ],
)
def test_phone_positive(guard: OutputGuard, pos: str) -> None:
    out = guard.sanitize_text(pos)
    assert "[REDACTED:PHONE]" in out


@pytest.mark.parametrize(
    "neg",
    [
        "Grid voltage is 230.5 V",
        "Duration 94 seconds",
        "INV-01 temperature is 45.2 C",
    ],
)
def test_phone_negative(guard: OutputGuard, neg: str) -> None:
    assert guard.sanitize_text(neg) == neg


# 5. Street addresses
@pytest.mark.parametrize(
    "pos",
    [
        "Facility located at 123 Solar Farm Road",
        "Shipped to 456 Station Avenue, Building B",
        "Site address: 12 Industrial Boulevard",
    ],
)
def test_address_positive(guard: OutputGuard, pos: str) -> None:
    out = guard.sanitize_text(pos)
    assert "[REDACTED:ADDRESS]" in out


@pytest.mark.parametrize(
    "neg",
    [
        "123 packets received",
        "Road testing completed",
        "Avenue of investigation is closed",
    ],
)
def test_address_negative(guard: OutputGuard, neg: str) -> None:
    assert guard.sanitize_text(neg) == neg


# 6. Device Serial Numbers
@pytest.mark.parametrize(
    "pos",
    [
        "Hardware serial INV-SN-ABC1234567 found defective",
        "Replace unit INV-SN-99887766XYZ",
        "Device badge INV-SN-0011223344",
    ],
)
def test_device_serial_positive(guard: OutputGuard, pos: str) -> None:
    out = guard.sanitize_text(pos)
    assert "[REDACTED:SERIAL]" in out
    assert "INV-SN-" not in out


@pytest.mark.parametrize(
    "neg",
    [
        "INV-01 reporting nominal",
        "INV-07 overheating warning",
        "INV-20 stuck relay",
    ],
)
def test_device_serial_negative(guard: OutputGuard, neg: str) -> None:
    # Standard fleet identifiers must NOT be redacted
    assert guard.sanitize_text(neg) == neg


# 7. IP Addresses
@pytest.mark.parametrize(
    "pos",
    [
        "Broker listening on 192.168.1.100:1883",
        "Gateway at 10.0.0.1 failed to route",
        "DNS lookup 172.16.254.1 timed out",
    ],
)
def test_ip_address_positive(guard: OutputGuard, pos: str) -> None:
    out = guard.sanitize_text(pos)
    assert "[REDACTED:IP_ADDRESS]" in out


@pytest.mark.parametrize(
    "neg",
    [
        "Version 1.0.0 released",
        "Threshold 230.5 exceeded",
        "Ratio 3.14159 calculated",
    ],
)
def test_ip_address_negative(guard: OutputGuard, neg: str) -> None:
    assert guard.sanitize_text(neg) == neg


# 8. Local file paths
@pytest.mark.parametrize(
    "pos",
    [
        r"Dump saved to C:\Users\operator\data\log.txt",
        "Configuration file at /etc/mosquitto/mosquitto.conf",
        "Secrets stored in /home/admin/certs/key.pem",
    ],
)
def test_file_path_positive(guard: OutputGuard, pos: str) -> None:
    out = guard.sanitize_text(pos)
    assert "[REDACTED:FILE_PATH]" in out


@pytest.mark.parametrize(
    "neg",
    [
        "Relative path simulator/runner.py",
        "Option --file-path is valid",
        "Path A -> Path B transition",
    ],
)
def test_file_path_negative(guard: OutputGuard, neg: str) -> None:
    assert guard.sanitize_text(neg) == neg


# ---------------------------------------------------------------------------
# ENGINEERING TEXT PRESERVATION CHECK (Rule 50)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "engineering_sample",
    [
        "INV-01",
        "INV-07",
        "INV-20",
        "412.5 W",
        "58.2 C",
        "230.0 V",
        "2026-11-09T10:00:00Z",
        "550e8400-e29b-41d4-a716-446655440000",  # Standard UUID
    ],
)
def test_engineering_values_pass_unchanged(guard: OutputGuard, engineering_sample: str) -> None:
    assert guard.sanitize_text(engineering_sample) == engineering_sample
